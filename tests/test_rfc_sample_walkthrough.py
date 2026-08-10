import json
import socket
import struct
import threading
import time
import unittest

from network.server import MTGNPServer

def frame(msg: dict) -> bytes:
    payload = json.dumps(msg).encode('utf-8')
    return struct.pack('>I', len(payload)) + payload

def recv_msg(sock: socket.socket) -> dict:
    header = sock.recv(4)
    if not header or len(header) < 4:
        return {}
    length = struct.unpack('>I', header)[0]
    payload = b''
    while len(payload) < length:
        chunk = sock.recv(min(length - len(payload), 4096))
        if not chunk:
            break
        payload += chunk
    if not payload:
        return {}
    return json.loads(payload.decode('utf-8'))

class RFCSampleWalkthroughTest(unittest.TestCase):
    def setUp(self):
        self.server = MTGNPServer(port=0, verbose=False)
        self.server_thread = threading.Thread(target=self.server.start, daemon=True)
        self.server_thread.start()
        
        deadline = time.time() + 3
        while self.server.socket is None and time.time() < deadline:
            time.sleep(0.01)
        if self.server.socket is None:
            raise AssertionError("Server did not start")
        self.port = self.server.socket.getsockname()[1]

        import random
        self.original_choice = random.choice
        random.choice = lambda seq: sorted(seq)[0]  # always pick player_1
        self.original_shuffle = random.shuffle
        random.shuffle = lambda seq: None  # don't shuffle

    def tearDown(self):
        self.server.shutdown()
        self.server_thread.join(timeout=1.0)
        import random
        random.choice = self.original_choice
        random.shuffle = self.original_shuffle

    def send(self, sock, msg):
        sock.sendall(frame(msg))

    def wait_for_type(self, sock, expected_type):
        while True:
            msg = recv_msg(sock)
            if not msg:
                self.fail(f"Connection closed while waiting for {expected_type}")
            if msg.get('type') == expected_type:
                return msg

    def wait_for_phase(self, sock, expected_phase):
        while True:
            msg = recv_msg(sock)
            if not msg:
                self.fail(f"Connection closed while waiting for phase {expected_phase}")
            if msg.get('type') == 'GAME_STATE_UPDATE':
                phase = msg.get('state', {}).get('phase')
                if phase == expected_phase:
                    return msg

    def wait_for_priority_grant(self, sock):
        while True:
            msg = recv_msg(sock)
            if not msg:
                self.fail("Connection closed while waiting for priority grant")
            if msg.get('type') == 'PRIORITY_GRANT':
                return msg.get('seq_num')

    def pass_priority_until(self, p1, p2, expected_phase, expected_turn=None):
        import select
        while True:
            r, _, _ = select.select([p1, p2], [], [], 2.0)
            if not r:
                self.fail(f"Timeout waiting for phase {expected_phase}")
            for sock in r:
                msg = recv_msg(sock)
                if not msg:
                    self.fail(f"Connection closed while waiting for phase {expected_phase}")
                if msg.get('type') == 'GAME_STATE_UPDATE':
                    phase = msg.get('state', {}).get('phase')
                    turn = msg.get('state', {}).get('turn')
                    if phase == expected_phase:
                        if expected_turn is None or turn == expected_turn:
                            return
                elif msg.get('type') == 'ERROR':
                    pass
                elif msg.get('type') == 'PRIORITY_GRANT':
                    self.send(sock, {
                        "type": "PRIORITY_PASS",
                        "seq_num": msg['seq_num']
                    })
                elif msg.get('type') == 'PHASE_TRANSITION':
                    to_phase = msg.get('to_phase')
                    active = msg.get('active_player')
                    seq = msg.get('seq_num')
                    if to_phase == "DECLARE_ATTACKERS":
                        # Active player must declare attackers
                        if (sock == p1 and active == "player_1") or (sock == p2 and active == "player_2"):
                            import time
                            time.sleep(0.02)  # Avoid race condition with server expect_action
                            self.send(sock, {
                                "type": "DECLARE_ATTACKERS",
                                "seq_num": seq,
                                "attackers": []
                            })
                    elif to_phase == "DECLARE_BLOCKERS":
                        # Non-active player must declare blockers
                        if (sock == p1 and active == "player_2") or (sock == p2 and active == "player_1"):
                            import time
                            time.sleep(0.02)  # Avoid race condition with server expect_action
                            self.send(sock, {
                                "type": "DECLARE_BLOCKERS",
                                "seq_num": seq,
                                "blockers": []
                            })

    def pass_priority_to_both(self, p1, p2):
        pass

    def test_rfc_sample_walkthrough(self):
        # 1. LOBBY State
        p1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        p1.settimeout(2)
        p1.connect(('127.0.0.1', self.port))
        
        p2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        p2.settimeout(2)
        p2.connect(('127.0.0.1', self.port))
        
        # Step 1 - Player 1 sends PLAYER_READY
        self.send(p1, {
            "type": "PLAYER_READY",
            "seq_num": 1,
            "player_id": "player_1",
            "deck_list": [
                "lightning_bolt_001", "lightning_bolt_002", "lightning_bolt_003",
                "shock_001",          "shock_002",
                "goblin_guide_001",
                "mountain_001",       "mountain_002"
            ]
        })
        
        # Step 2 - Server acknowledges
        self.wait_for_phase(p1, "LOBBY")
        
        # Step 3 - Player 2 sends PLAYER_READY
        self.send(p2, {
            "type": "PLAYER_READY",
            "seq_num": 1,
            "player_id": "player_2",
            "deck_list": [
                "counterspell_001", "counterspell_002",
                "gray_merchant_001", "gray_merchant_002",
                "island_001", "island_002",
                "swamp_001", "swamp_002"
            ]
        })
        
        # Step 4 - GAME_SETUP phase
        p1_setup = self.wait_for_phase(p1, "GAME_SETUP")
        p2_setup = self.wait_for_phase(p2, "GAME_SETUP")
        self.assertEqual(p1_setup.get("state", {}).get("active_player"), "player_1")
        
        # Steps 5 & 6 - MULLIGAN phase
        p1_state = self.wait_for_phase(p1, "MULLIGAN")
        p2_state = self.wait_for_phase(p2, "MULLIGAN")
        
        # Step 7 - Player 1 keeps
        p1_seq = p1_state.get('seq_num')
        self.send(p1, {
            "type": "MULLIGAN_CHOICE",
            "seq_num": p1_seq,
            "keep": True,
            "cards_to_bottom": []
        })
        
        # Step 8 - Player 2 mulligans
        p2_seq = p2_state.get('seq_num')
        self.send(p2, {
            "type": "MULLIGAN_CHOICE",
            "seq_num": p2_seq,
            "keep": False,
            "cards_to_bottom": []
        })
        
        # Step 9 - Player 2 redraws
        p2_redraw = self.wait_for_phase(p2, "MULLIGAN")
        
        # Step 10 - Player 2 keeps after mulligan, bottoms 1 card
        p2_seq2 = p2_redraw.get('seq_num')
        self.send(p2, {
            "type": "MULLIGAN_CHOICE",
            "seq_num": p2_seq2,
            "keep": True,
            "cards_to_bottom": ["counterspell_002"]
        })
        
        # Step 11-15 - IN_GAME phase - Player 1 turn begins, advance to PRECOMBAT_MAIN
        self.pass_priority_until(p1, p2, "PRECOMBAT_MAIN", 1)
        
        # Step 15 (cont) - Wait for P1 priority in PRECOMBAT_MAIN
        seq1 = self.wait_for_priority_grant(p1)
        
        # Play mountain (mountain_001 because that's what's in hand depending on draw)
        # RFC says mountain_003, but because we didn't shuffle and our deck has mountain_001, we use mountain_001
        self.send(p1, {
            "type": "PLAY_LAND",
            "seq_num": seq1,
            "card_id": "mountain_001"
        })
        
        # Wait for P1 priority after PLAY_LAND
        seq2 = self.wait_for_priority_grant(p1)
        
        # Step 16 - Cast Goblin Guide
        self.send(p1, {
            "type": "CAST_SPELL",
            "seq_num": seq2,
            "card_id": "goblin_guide_001",
            "targets": [],
            "mana_payment": {"R": 1}
        })
        
        # P1 priority after casting
        seq3 = self.wait_for_priority_grant(p1)
        self.send(p1, {"type": "PRIORITY_PASS", "seq_num": seq3})
        
        # P2 priority
        seq4 = self.wait_for_priority_grant(p2)
        self.send(p2, {"type": "PRIORITY_PASS", "seq_num": seq4})
        
        # Spell resolves, P1 receives GAME_STATE_UPDATE
        self.wait_for_type(p1, "GAME_STATE_UPDATE")
        
        # Pass through the rest of Turn 1 to Turn 2's PRECOMBAT_MAIN
        self.pass_priority_until(p1, p2, "PRECOMBAT_MAIN", 2)
        # Now it is Player 2's turn 2 PRECOMBAT_MAIN
        
        seq5 = self.wait_for_priority_grant(p2)
        
        # Step 25 - Player 2 plays swamp_001
        self.send(p2, {
            "type": "PLAY_LAND",
            "seq_num": seq5,
            "card_id": "swamp_001"
        })
        
        seq6 = self.wait_for_priority_grant(p2)
        
        # Step 26 - Player 2 passes, Player 1 casts Lightning Bolt
        self.send(p2, {"type": "PRIORITY_PASS", "seq_num": seq6})
        
        seq7 = self.wait_for_priority_grant(p1)
        
        self.send(p1, {
            "type": "CAST_SPELL",
            "seq_num": seq7,
            "card_id": "lightning_bolt_001",
            "targets": ["player_2"],
            "mana_payment": {"R": 1}
        })
        
        # P1 retains priority and passes
        seq8 = self.wait_for_priority_grant(p1)
        self.send(p1, {"type": "PRIORITY_PASS", "seq_num": seq8})
        
        # P2 priority and passes
        seq9 = self.wait_for_priority_grant(p2)
        self.send(p2, {"type": "PRIORITY_PASS", "seq_num": seq9})
        
        # Wait for Lightning Bolt to resolve
        self.wait_for_type(p1, "GAME_STATE_UPDATE")
        
        # Pass through Turn 2 to Turn 3 (so we can hack state without disrupting phase transitions)
        self.pass_priority_until(p1, p2, "PRECOMBAT_MAIN", 3)
        # Now it is Player 1's turn 3 PRECOMBAT_MAIN.
        
        # HACK: Fast-forward state to match Step 30 / Turn 7
        self.server.game.turn = 7
        self.server.game.players["player_1"]["life"] = 14
        self.server.game.players["player_2"]["life"] = 3
        # Ensure player 1 has lightning_bolt_003
        if "lightning_bolt_003" not in self.server.game.players["player_1"]["hand"]:
            self.server.game.players["player_1"]["hand"].append("lightning_bolt_003")
        
        # P1 priority in PRECOMBAT_MAIN
        seq10 = self.wait_for_priority_grant(p1)
        
        # Step 31 - Player 1 casts Lightning Bolt 3 targeting Player 2 (lethal)
        self.send(p1, {
            "type": "CAST_SPELL",
            "seq_num": seq10,
            "card_id": "lightning_bolt_003",
            "targets": ["player_2"],
            "mana_payment": {"R": 1}
        })
        
        # P1 passes
        seq11 = self.wait_for_priority_grant(p1)
        self.send(p1, {"type": "PRIORITY_PASS", "seq_num": seq11})
        
        # P2 passes
        seq12 = self.wait_for_priority_grant(p2)
        self.send(p2, {"type": "PRIORITY_PASS", "seq_num": seq12})
        
        # Step 32 - GAME_OVER
        game_over = self.wait_for_type(p2, "GAME_OVER")
        self.assertEqual(game_over.get("winner_id"), "player_1")
        self.assertEqual(game_over.get("reason"), "LIFE_ZERO")
        
        # Step 33 - Transition back to LOBBY
        self.send(p1, {
            "type": "PLAYER_READY",
            "seq_num": 2,
            "player_id": "player_1",
            "deck_list": ["mountain_001"]
        })
        lobby_state = self.wait_for_type(p1, "GAME_STATE_UPDATE")
        self.assertEqual(lobby_state.get("state", {}).get("phase"), "LOBBY")
        
        p1.close()
        p2.close()

if __name__ == '__main__':
    unittest.main()
