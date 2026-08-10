import json
import contextlib
import io
import socket
import struct
import threading
import time
import unittest

from core.constants import MAX_PDU_SIZE
from network.server import MTGNPServer


def frame(pdu):
    payload = json.dumps(pdu, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


def recv_pdu(sock):
    header = recv_exact(sock, 4)
    if not header:
        return None
    length = struct.unpack(">I", header)[0]
    return json.loads(recv_exact(sock, length).decode("utf-8"))


def recv_exact(sock, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            return b"" if not chunks else b"".join(chunks)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_until(sock, predicate, limit=40):
    messages = []
    for _ in range(limit):
        message = recv_pdu(sock)
        if message is None:
            break
        messages.append(message)
        if predicate(message):
            return message, messages
    raise AssertionError(f"Expected PDU was not received; got {messages!r}")


class ServerHarness:
    def __init__(self):
        self.server = MTGNPServer(port=0, verbose=False)
        self.thread = threading.Thread(target=self.server.start, daemon=True)

    def start(self):
        self.thread.start()
        deadline = time.time() + 3
        while self.server.socket is None and time.time() < deadline:
            time.sleep(0.01)
        if self.server.socket is None:
            raise AssertionError("Server did not start")
        self.port = self.server.socket.getsockname()[1]

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=2)


class SocketIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.harness = ServerHarness()
        self.harness.start()
        self.sockets = []

    def tearDown(self):
        for sock in self.sockets:
            try:
                sock.close()
            except OSError:
                pass
        self.harness.stop()

    def connect(self):
        sock = socket.create_connection(("127.0.0.1", self.harness.port), timeout=2)
        sock.settimeout(2)
        self.sockets.append(sock)
        return sock

    def send(self, sock, pdu):
        sock.sendall(frame(pdu))

    def player_ready(self, sock, player_id, deck):
        self.send(sock, {
            "type": "PLAYER_READY", "seq_num": 1,
            "player_id": player_id, "deck_list": deck,
        })

    def start_mulligan(self):
        p1, p2 = self.connect(), self.connect()
        deck1 = [
            "mountain_001", "mountain_002", "mountain_003", "mountain_004",
            "lightning_bolt_001", "shock_001", "goblin_guide_001", "forest_001",
        ]
        deck2 = [
            "island_001", "island_002", "island_003", "island_004",
            "counterspell_001", "ponder_001", "savannah_lions_001", "plains_001",
        ]
        self.player_ready(p1, "player_1", deck1)
        recv_until(p1, lambda p: p.get("type") == "GAME_STATE_UPDATE")
        self.player_ready(p2, "player_2", deck2)
        recv_until(p1, lambda p: p.get("type") == "GAME_STATE_UPDATE" and
                   p.get("state", {}).get("phase") == "MULLIGAN")
        recv_until(p2, lambda p: p.get("type") == "GAME_STATE_UPDATE" and
                   p.get("state", {}).get("phase") == "MULLIGAN")
        return p1, p2

    def finish_mulligan(self, p1, p2):
        game = self.harness.server.game
        p1_seq = game.players["player_1"]["last_seq_num"]
        self.send(p1, {"type": "MULLIGAN_CHOICE", "seq_num": p1_seq,
                       "keep": True, "cards_to_bottom": []})
        deadline = time.time() + 2
        while not game.players["player_1"].get("ready_to_play") and time.time() < deadline:
            time.sleep(0.005)
        self.assertTrue(game.players["player_1"].get("ready_to_play"))

        p2_seq = game.players["player_2"]["last_seq_num"]
        self.send(p2, {"type": "MULLIGAN_CHOICE", "seq_num": p2_seq,
                       "keep": True, "cards_to_bottom": []})
        deadline = time.time() + 2
        while game.state != "IN_GAME" and time.time() < deadline:
            time.sleep(0.005)
        self.assertEqual(game.state, "IN_GAME")

    def test_fragmented_frame_is_reassembled(self):
        sock = self.connect()
        payload = frame({
            "type": "PLAYER_READY", "seq_num": 1,
            "player_id": "fragmented", "deck_list": ["mountain_001"],
        })
        for byte in payload:
            sock.send(bytes([byte]))
        message, _ = recv_until(sock, lambda p: p.get("type") == "GAME_STATE_UPDATE")
        self.assertEqual(message["state"]["phase"], "LOBBY")

    def test_oversized_frame_is_rejected(self):
        sock = self.connect()
        sock.sendall(struct.pack(">I", MAX_PDU_SIZE + 1))
        message = recv_pdu(sock)
        self.assertEqual(message["type"], "ERROR")
        self.assertEqual(message["code"], "INVALID_JSON")

    def test_invalid_json_and_unknown_type_are_rejected_without_disconnect(self):
        sock = self.connect()
        bad_payload = b"not-json"
        sock.sendall(struct.pack(">I", len(bad_payload)) + bad_payload)
        invalid = recv_pdu(sock)
        self.assertEqual(invalid["code"], "INVALID_JSON")

        bad_utf8 = b"\xff"
        sock.sendall(struct.pack(">I", len(bad_utf8)) + bad_utf8)
        invalid_utf8 = recv_pdu(sock)
        self.assertEqual(invalid_utf8["code"], "INVALID_JSON")

        self.send(sock, {"type": "NOT_A_PDU", "seq_num": 2})
        unknown = recv_pdu(sock)
        self.assertEqual(unknown["code"], "UNKNOWN_TYPE")

        self.player_ready(sock, "still_connected", ["mountain_001"])
        valid, _ = recv_until(sock, lambda p: p.get("type") == "GAME_STATE_UPDATE")
        self.assertEqual(valid["state"]["players_ready"], 1)

    def test_third_connection_is_closed(self):
        first, second = self.connect(), self.connect()
        third = self.connect()
        third.settimeout(1)
        try:
            data = third.recv(1)
            self.assertEqual(data, b"")
        finally:
            first.close()
            second.close()

    def test_ping_pong_echoes_sequence_and_timestamp(self):
        sock = self.connect()
        self.send(sock, {"type": "PING", "seq_num": 73, "timestamp": 123456})
        pong = recv_pdu(sock)
        self.assertEqual(pong, {
            "type": "PONG", "seq_num": 73, "timestamp": 123456,
        })

    def test_verbose_mode_emits_labeled_protocol_logging(self):
        self.harness.server.verbose = True
        sock = self.connect()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.send(sock, {"type": "PING", "seq_num": 74, "timestamp": 654321})
            pong = recv_pdu(sock)
            time.sleep(0.02)

        self.assertEqual(pong["type"], "PONG")
        self.assertIn("[SERVER <-", output.getvalue())
        self.assertIn("[SEND]", output.getvalue())

    def test_all_required_client_pdu_types_are_routed(self):
        sock = self.connect()
        routed_types = [
            "MULLIGAN_CHOICE", "CAST_SPELL", "PLAY_LAND",
            "ACTIVATE_ABILITY", "PRIORITY_PASS", "DECLARE_ATTACKERS",
            "DECLARE_BLOCKERS", "ASSIGN_DAMAGE_ORDER", "DISCARD",
            "TRIGGER_ORDER_RESPONSE", "TRIGGER_CHOICE_RESPONSE", "CONCEDE",
        ]
        for index, pdu_type in enumerate(routed_types, start=1):
            self.send(sock, {"type": pdu_type, "seq_num": index})
            response = recv_pdu(sock)
            self.assertIsNotNone(response)
            self.assertNotEqual(
                response.get("code"), "UNKNOWN_TYPE",
                f"{pdu_type} was not routed by the server",
            )

    def test_first_turn_reaches_postcombat_and_next_turn(self):
        p1, p2 = self.start_mulligan()
        game = self.harness.server.game
        self.finish_mulligan(p1, p2)

        deadline = time.time() + 3
        observed_phases = set()
        while time.time() < deadline and game.turn < 2:
            observed_phases.add(game.phase)
            phase = game.phase
            if phase in {
                "UPKEEP", "DRAW", "PRECOMBAT_MAIN", "BEGIN_COMBAT",
                "FIRST_STRIKE_DAMAGE", "COMBAT_DAMAGE", "END_OF_COMBAT",
                "POSTCOMBAT_MAIN", "END_STEP",
            } and game.priority_manager.priority_holder:
                holder = game.priority_manager.priority_holder
                sock = p1 if holder == "player_1" else p2
                self.send(sock, {
                    "type": "PRIORITY_PASS",
                    "seq_num": game.priority_manager.priority_seq,
                })
                time.sleep(0.01)
            elif phase == "DECLARE_ATTACKERS" and game.priority_manager.priority_holder:
                self.send(p1 if game.active_player == "player_1" else p2, {
                    "type": "DECLARE_ATTACKERS",
                    "seq_num": game.priority_manager.priority_seq,
                    "attackers": [],
                })
                time.sleep(0.01)
            elif phase == "DECLARE_BLOCKERS" and game.priority_manager.priority_holder:
                nap = game.get_other_player(game.active_player)
                self.send(p1 if nap == "player_1" else p2, {
                    "type": "DECLARE_BLOCKERS",
                    "seq_num": game.priority_manager.priority_seq,
                    "blockers": [],
                })
                time.sleep(0.01)
            else:
                time.sleep(0.005)

        self.assertGreaterEqual(game.turn, 2)
        self.assertTrue({"UPKEEP", "DRAW", "PRECOMBAT_MAIN", "BEGIN_COMBAT"}.issubset(observed_phases))
        self.assertTrue({"DECLARE_ATTACKERS", "END_OF_COMBAT", "POSTCOMBAT_MAIN", "CLEANUP"}.intersection(observed_phases))

    def test_stale_priority_action_returns_error_and_connection_survives(self):
        p1, p2 = self.start_mulligan()
        # The update sequence is deterministic per connection only after the
        # server sends the MULLIGAN update; capture it from a fresh lobby flow
        # by using the server-side counter visible in the next update.
        # Keep choices accept the sequence in the corresponding update. The
        # test uses the server object only as an oracle, never mutating state.
        self.finish_mulligan(p1, p2)
        # Only the priority holder receives the grant.
        deadline = time.time() + 2
        holder = self.harness.server.game.priority_manager.priority_holder
        while holder is None and time.time() < deadline:
            time.sleep(0.01)
            holder = self.harness.server.game.priority_manager.priority_holder
        self.assertIn(holder, {"player_1", "player_2"})
        target = p1 if holder == "player_1" else p2
        recv_until(target, lambda p: p.get("type") == "PRIORITY_GRANT")
        self.send(target, {"type": "PRIORITY_PASS", "seq_num": -1})
        error, _ = recv_until(target, lambda p: p.get("type") == "ERROR")
        self.assertEqual(error["code"], "STALE_ACTION")
        self.send(target, {"type": "PING", "seq_num": 9, "timestamp": 9})
        pong, _ = recv_until(target, lambda p: p.get("type") == "PONG")
        self.assertEqual(pong["seq_num"], 9)

    def test_game_over_concede_and_same_connections_restart(self):
        p1, p2 = self.start_mulligan()
        self.finish_mulligan(p1, p2)
        time.sleep(0.1)
        p1_seq = self.harness.server.game.players["player_1"]["last_seq_num"]
        self.send(p1, {"type": "CONCEDE", "seq_num": p1_seq})
        game_over, _ = recv_until(p1, lambda p: p.get("type") == "GAME_OVER")
        self.assertEqual(game_over["reason"], "CONCEDE")
        self.assertEqual(self.harness.server.game.state, "LOBBY")

        self.player_ready(p1, "player_1", ["mountain_005"])
        self.player_ready(p2, "player_2", ["island_005"])
        lobby, _ = recv_until(p1, lambda p: p.get("type") == "GAME_STATE_UPDATE" and
                              p.get("state", {}).get("phase") == "MULLIGAN")
        self.assertEqual(lobby["state"]["phase"], "MULLIGAN")

    def test_active_player_can_reconnect_before_timeout(self):
        p1, p2 = self.start_mulligan()
        self.finish_mulligan(p1, p2)
        old_p1 = p1
        old_p1.close()
        deadline = time.time() + 2
        while self.harness.server.game.players.get("player_1", {}).get("conn") is not None and time.time() < deadline:
            time.sleep(0.01)
        self.assertIsNone(self.harness.server.game.players["player_1"]["conn"])

        replacement = self.connect()
        self.send(replacement, {
            "type": "PLAYER_READY", "seq_num": 1, "player_id": "player_1",
        })
        state, _ = recv_until(replacement, lambda p: p.get("type") == "GAME_STATE_UPDATE")
        self.assertIn(state["state"]["phase"], {
            "UNTAP", "UPKEEP", "DRAW", "PRECOMBAT_MAIN", "BEGIN_COMBAT",
            "DECLARE_ATTACKERS", "DECLARE_BLOCKERS", "ASSIGN_DAMAGE_ORDER",
            "FIRST_STRIKE_DAMAGE", "COMBAT_DAMAGE", "END_OF_COMBAT",
            "POSTCOMBAT_MAIN", "END_STEP", "CLEANUP",
        })


if __name__ == "__main__":
    unittest.main()
