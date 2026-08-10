import unittest
import time

from core.models import Permanent
from game.actions import ActionHandler
from game.card_effects import execute_card_effect
from game.game import Game
from game.state import GameState
from network.network import decode_message, encode_message


class FakeServer:
    def send_pdu(self, conn, pdu):
        pass

    def send_error(self, conn, code, message, rejected_action=None):
        pass


class CaptureServer(FakeServer):
    def __init__(self):
        self.sent = []
        self.errors = []

    def send_pdu(self, conn, pdu):
        self.sent.append((conn, pdu))

    def send_error(self, conn, code, message, rejected_action=None):
        self.errors.append((conn, code, message, rejected_action))


def make_game():
    game = Game(FakeServer())
    game.players = {
        "player_1": {
            "conn": None, "hand": [], "library": [], "graveyard": [],
            "exile": [], "battlefield": [], "life": 20,
        },
        "player_2": {
            "conn": None, "hand": [], "library": [], "graveyard": [],
            "exile": [], "battlefield": [], "life": 20,
        },
    }
    return game


class ProtocolRegressionTests(unittest.TestCase):
    def test_frame_round_trip(self):
        pdu = {"type": "PING", "seq_num": 1, "timestamp": 123}
        self.assertEqual(decode_message(encode_message(pdu)), pdu)

    def test_personalized_hand_is_hidden(self):
        game = make_game()
        game.players["player_1"]["hand"] = ["mountain_001"]
        game.players["player_2"]["hand"] = ["island_001"]
        state = GameState(game).build_state_dict("player_1")
        self.assertEqual(state["hand"], {"player_1": ["mountain_001"]})
        self.assertEqual(state["hand_counts"], {"player_2": 1})

    def test_target_validation_rejects_missing_lava_spike_target(self):
        from game.card_catalog import get_card

        action = ActionHandler(make_game())
        self.assertIsNotNone(
            action._validate_spell_targets(
                get_card("lava_spike_001"), [], "player_1"
            )
        )

    def test_creature_spell_does_not_require_a_target(self):
        from game.card_catalog import get_card

        action = ActionHandler(make_game())
        self.assertIsNone(
            action._validate_spell_targets(
                get_card("goblin_guide_001"), [], "player_1"
            )
        )

    def test_play_land_requires_current_priority_token(self):
        game = make_game()
        game.state = "IN_GAME"
        game.phase = "PRECOMBAT_MAIN"
        game.active_player = "player_1"
        game.priority_manager.priority_holder = "player_1"
        game.priority_manager.priority_seq = 7
        game.players["player_1"]["hand"] = ["mountain_001"]

        ActionHandler(game).handle_play_land(
            None, {"type": "PLAY_LAND", "seq_num": 6, "card_id": "mountain_001"}
        )
        self.assertEqual(game.players["player_1"]["hand"], ["mountain_001"])
        self.assertEqual(game.players["player_1"]["battlefield"], [])

    def test_summoning_sick_creature_cannot_activate_tap_ability(self):
        game = make_game()
        game.state = "IN_GAME"
        game.phase = "PRECOMBAT_MAIN"
        game.priority_manager.priority_holder = "player_1"
        game.priority_manager.priority_seq = 9
        source = Permanent("llanowar_elves_001", "player_1", "llanowar_elves_001", 1)
        game.players["player_1"]["battlefield"] = [source]

        ActionHandler(game).handle_activate_ability(
            None,
            {
                "type": "ACTIVATE_ABILITY",
                "seq_num": 9,
                "source_id": source.id,
                "ability_index": 0,
                "targets": [],
                "cost_payment": {"tap": True, "mana": {}},
            },
        )
        self.assertFalse(source.tapped)

    def test_flying_and_vigilance(self):
        flyer = Permanent("air_elemental_001", "player_1", "air_elemental_001", 1)
        angel = Permanent("serra_angel_001", "player_1", "serra_angel_001", 1)
        self.assertTrue(flyer.has_flying())
        self.assertTrue(angel.has_vigilance())

    def test_protection_prevents_combat_damage(self):
        from game.combat import CombatSystem

        game = make_game()
        attacker = Permanent("black_knight_001", "player_1", "attacker", 1)
        blocker = Permanent("white_knight_001", "player_2", "blocker", 1)
        game.players["player_1"]["battlefield"] = [attacker]
        game.players["player_2"]["battlefield"] = [blocker]
        game.combat_system.attackers = [{"creature_id": "attacker", "target": "player_2"}]
        game.combat_system.blockers = [{"creature_id": "blocker", "blocking_id": "attacker"}]
        game.combat_system.deal_combat_damage()
        self.assertEqual(attacker.damage, 0)
        self.assertEqual(blocker.damage, 0)

    def test_chosen_protection_color_is_applied(self):
        game = make_game()
        creature = Permanent("savannah_lions_001", "player_1", "lions", 1)
        game.players["player_1"]["battlefield"] = [creature]
        execute_card_effect(
            game,
            "mother_of_runes_001",
            "player_1",
            [creature.id],
            ability="protection_giver",
            ability_params={"chosen_color": "R"},
        )
        self.assertTrue(creature.has_protection_from("R"))
        self.assertFalse(creature.has_protection_from("B"))

    def test_static_hexproof_rejects_opponent_targeting(self):
        from game.card_catalog import get_card

        game = make_game()
        troll = Permanent("troll_ascetic_001", "player_2", "troll", 1)
        game.players["player_2"]["battlefield"] = [troll]
        action = ActionHandler(game)
        self.assertEqual(
            action._validate_spell_targets(
                get_card('flame_slash_001'),
                [troll.id],
                "player_1",
            ),
            "Target has hexproof",
        )

    def test_no_trample_damage_to_player(self):
        from game.combat import CombatSystem

        game = make_game()
        attacker = Permanent("reckless_wurm_001", "player_1", "attacker", 1)
        blocker = Permanent("grizzly_bears_001", "player_2", "blocker", 1)
        game.players["player_1"]["battlefield"] = [attacker]
        game.players["player_2"]["battlefield"] = [blocker]
        game.combat_system.attackers = [{"creature_id": "attacker", "target": "player_2"}]
        game.combat_system.blockers = [{"creature_id": "blocker", "blocking_id": "attacker"}]
        game.combat_system.deal_combat_damage()
        # Reckless Wurm is 4/4 and Grizzly Bears is 2/2: 2 to the blocker,
        # but MTGNP 1.0 does not implement trample, so no damage goes to the player.
        self.assertEqual(blocker.damage, 2)
        self.assertEqual(game.players["player_2"]["life"], 20)

    def test_regeneration_does_not_save_zero_toughness(self):
        game = make_game()
        creature = Permanent("troll_ascetic_001", "player_1", "troll", 1)
        creature._toughness_bonus = -2
        creature._regeneration_shield = 1
        game.players["player_1"]["battlefield"] = [creature]
        game.priority_manager.check_state_based_actions()
        self.assertEqual(game.players["player_1"]["battlefield"], [])

    def test_ping_ability_is_reachable(self):
        game = make_game()
        source = Permanent(
            "prodigal_sorcerer_001", "player_1", "prodigal_sorcerer_001", 1
        )
        game.players["player_1"]["battlefield"] = [source]
        execute_card_effect(
            game, source.card_id, "player_1", ["player_2"], ability="ping"
        )
        self.assertEqual(game.players["player_2"]["life"], 19)

    def test_regeneration_shield(self):
        game = make_game()
        source = Permanent("troll_ascetic_001", "player_1", "troll_ascetic_001", 1)
        game.players["player_1"]["battlefield"] = [source]
        execute_card_effect(
            game, source.card_id, "player_1", [source.id], ability="regenerate"
        )
        self.assertEqual(source._regeneration_shield, 1)

    def test_prowess_and_illusion_triggers(self):
        game = make_game()
        bear = Permanent("phantasmal_bear_001", "player_1", "bear", 1)
        swift = Permanent("monastery_swiftspear_001", "player_1", "swift", 1)
        game.players["player_1"]["battlefield"] = [bear, swift]
        game.active_player = "player_1"
        game.trigger_manager.check_triggers(
            "SPELL_CAST", {"spell": "lightning_bolt_001", "controller": "player_1"}
        )
        self.assertEqual(
            game.stack[-1].trigger_data["trigger"]["effect"], "prowess"
        )
        game.stack.clear()
        game.trigger_manager.check_triggers(
            "TARGETED", {"target": bear.id, "source": "lightning_bolt_001"}
        )
        self.assertEqual(
            game.stack[-1].trigger_data["trigger"]["effect"], "illusion_sacrifice"
        )


    def test_activated_ability_rejects_hexproof(self):
        game = make_game()
        troll = Permanent("troll_ascetic_001", "player_2", "troll", 1)
        ping_source = Permanent("prodigal_sorcerer_001", "player_1", "ping_source", 2)
        game.players["player_2"]["battlefield"] = [troll]
        game.players["player_1"]["battlefield"] = [ping_source]
        
        class MockConn:
            pass
        conn = MockConn()
        
        action = ActionHandler(game)
        action.handle_activate_ability(
            conn,
            {
                "type": "ACTIVATE_ABILITY",
                "seq_num": 1,
                "source_id": ping_source.id,
                "ability_index": 0,  # ping
                "targets": [troll.id],
                "cost_payment": {"tap": True, "mana": {}},
            },
        )
        # Should be rejected, tap shouldn't happen
        self.assertFalse(ping_source.tapped)

    def test_activated_ability_rejects_protection(self):
        game = make_game()
        knight = Permanent("white_knight_001", "player_2", "knight", 1)  # Protection from black
        ping_source = Permanent("cuombajj_witches_001", "player_1", "ping_source", 2) # Doesn't exist, let's just make it a black permanent
        ping_source.card_data = {'color': 'B', 'abilities': ['ping']}
        game.players["player_2"]["battlefield"] = [knight]
        game.players["player_1"]["battlefield"] = [ping_source]
        
        class MockConn:
            pass
        conn = MockConn()
        
        action = ActionHandler(game)
        action.handle_activate_ability(
            conn,
            {
                "type": "ACTIVATE_ABILITY",
                "seq_num": 1,
                "source_id": ping_source.id,
                "ability_index": 0,
                "targets": [knight.id],
                "cost_payment": {"tap": True, "mana": {}},
            },
        )
        # Should be rejected
        self.assertFalse(ping_source.tapped)

    def test_setup_and_london_mulligan_reach_first_turn(self):
        from game.lifecycle import LifecycleManager

        server = CaptureServer()
        game = Game(server)
        conn1, conn2 = object(), object()
        game.player_conns = [conn1, conn2]
        lifecycle = LifecycleManager(game)
        deck1 = [
            "mountain_001", "mountain_002", "mountain_003", "mountain_004",
            "lightning_bolt_001", "shock_001", "goblin_guide_001", "forest_001",
        ]
        deck2 = [
            "island_001", "island_002", "island_003", "island_004",
            "counterspell_001", "ponder_001", "savannah_lions_001", "plains_001",
        ]
        lifecycle.handle_player_ready(conn1, {
            "type": "PLAYER_READY", "seq_num": 1,
            "player_id": "player_1", "deck_list": deck1,
        })
        lifecycle.handle_player_ready(conn2, {
            "type": "PLAYER_READY", "seq_num": 1,
            "player_id": "player_2", "deck_list": deck2,
        })

        self.assertEqual(game.state, "MULLIGAN")
        self.assertEqual(len(game.players["player_1"]["hand"]), 7)
        self.assertEqual(len(game.players["player_2"]["hand"]), 7)

        p1_seq = game.players["player_1"]["last_seq_num"]
        p2_seq = game.players["player_2"]["last_seq_num"]
        lifecycle.handle_mulligan_choice(conn1, {
            "type": "MULLIGAN_CHOICE", "seq_num": p1_seq,
            "keep": False, "cards_to_bottom": [],
        })
        self.assertEqual(game.players["player_1"]["mulligan_count"], 1)
        self.assertEqual(len(game.players["player_1"]["hand"]), 7)

        p1_keep_seq = game.players["player_1"]["last_seq_num"]
        bottom_card = game.players["player_1"]["hand"][0]
        lifecycle.handle_mulligan_choice(conn1, {
            "type": "MULLIGAN_CHOICE", "seq_num": p1_keep_seq,
            "keep": True, "cards_to_bottom": [bottom_card],
        })
        lifecycle.handle_mulligan_choice(conn2, {
            "type": "MULLIGAN_CHOICE", "seq_num": p2_seq,
            "keep": True, "cards_to_bottom": [],
        })

        self.assertEqual(game.state, "IN_GAME")
        self.assertEqual(game.turn, 1)
        game.priority_manager.reset()

    def test_priority_passes_resolve_spell_and_broadcast_stack_result(self):
        from game.priority import PriorityManager

        server = CaptureServer()
        game = make_game()
        game.server = server
        conn1, conn2 = object(), object()
        game.players["player_1"]["conn"] = conn1
        game.players["player_2"]["conn"] = conn2
        game.player_conns = [conn1, conn2]
        game.state = "IN_GAME"
        game.phase = "PRECOMBAT_MAIN"
        game.active_player = "player_1"
        game.priority_manager.priority_holder = "player_1"
        game.priority_manager.priority_seq = 10
        game.players["player_1"]["hand"] = ["lightning_bolt_001"]
        game.players["player_1"]["battlefield"] = [
            Permanent("mountain_001", "player_1", "mountain_001", 0)
        ]

        ActionHandler(game).handle_cast_spell(conn1, {
            "type": "CAST_SPELL", "seq_num": 10,
            "card_id": "lightning_bolt_001", "targets": ["player_2"],
            "mana_payment": {"R": 1},
        })
        self.assertEqual(len(game.stack), 1)
        first_pass_seq = game.priority_manager.priority_seq
        game.priority_manager.handle_priority_pass(conn1, {
            "type": "PRIORITY_PASS", "seq_num": first_pass_seq,
        })
        second_pass_seq = game.priority_manager.priority_seq
        game.priority_manager.handle_priority_pass(conn2, {
            "type": "PRIORITY_PASS", "seq_num": second_pass_seq,
        })

        self.assertEqual(game.players["player_2"]["life"], 17)
        self.assertEqual(game.stack, [])
        self.assertTrue(any(pdu.get("type") == "STACK_RESOLVE" for _, pdu in server.sent))
        game.priority_manager.reset()

    def test_empty_library_draw_causes_deck_empty_game_over(self):
        server = CaptureServer()
        game = make_game()
        game.server = server
        conn1, conn2 = object(), object()
        game.players["player_1"]["conn"] = conn1
        game.players["player_2"]["conn"] = conn2
        game.player_conns = [conn1, conn2]
        game.state = "IN_GAME"
        game.phase = "PRECOMBAT_MAIN"
        game.active_player = "player_1"

        execute_card_effect(game, "merfolk_looter_001", "player_1", ability="loot")
        game.priority_manager.check_state_based_actions()

        self.assertEqual(game.state, "LOBBY")
        game_over = [pdu for _, pdu in server.sent if pdu.get("type") == "GAME_OVER"][-1]
        self.assertEqual(game_over["reason"], "DECK_EMPTY")
        self.assertEqual(game_over["winner_id"], "player_2")

    def test_mana_expires_before_next_step_handler(self):
        game = make_game()
        game.phase = "UPKEEP"
        game.floating_mana = {"player_1": {"R": 1}}
        observed = []
        game.turn_engine.do_draw_step = lambda: observed.append(game.floating_mana.copy())

        game.turn_engine.advance_step()

        self.assertEqual(observed, [{}])

    def test_invalid_attacker_declaration_is_atomic(self):
        game = make_game()
        game.state = "IN_GAME"
        game.phase = "DECLARE_ATTACKERS"
        game.active_player = "player_1"
        game.priority_manager.priority_holder = "player_1"
        game.priority_manager.priority_seq = 4
        creature = Permanent("savannah_lions_001", "player_1", "attacker", 0)
        game.players["player_1"]["battlefield"] = [creature]
        game.combat_system.attackers = [{"creature_id": "old", "target": "player_2"}]

        ActionHandler(game).handle_declare_attackers(None, {
            "type": "DECLARE_ATTACKERS", "seq_num": 4,
            "attackers": [
                {"creature_id": "attacker", "target": "player_2"},
                {"creature_id": "missing", "target": "player_2"},
            ],
        })

        self.assertEqual(game.combat_system.attackers, [{"creature_id": "old", "target": "player_2"}])
        self.assertFalse(creature.tapped)

    def test_reconnect_reuses_player_and_sends_state(self):
        from game.lifecycle import LifecycleManager

        server = CaptureServer()
        game = make_game()
        game.server = server
        old_conn, other_conn, new_conn = object(), object(), object()
        game.players["player_1"]["conn"] = None
        game.players["player_2"]["conn"] = other_conn
        game.player_conns = [other_conn]
        game.state = "IN_GAME"
        game.phase = "PRECOMBAT_MAIN"
        LifecycleManager(game).handle_player_ready(new_conn, {
            "type": "PLAYER_READY", "seq_num": 1,
            "player_id": "player_1",
        })

        self.assertIs(game.players["player_1"]["conn"], new_conn)
        self.assertIn(new_conn, game.player_conns)
        self.assertTrue(any(pdu.get("type") == "GAME_STATE_UPDATE" for _, pdu in server.sent))

    def test_life_zero_game_over_has_correct_reason_and_winner(self):
        server = CaptureServer()
        game = make_game()
        game.server = server
        conn1, conn2 = object(), object()
        game.players["player_1"]["conn"] = conn1
        game.players["player_2"]["conn"] = conn2
        game.player_conns = [conn1, conn2]
        game.state = "IN_GAME"
        game.active_player = "player_1"
        game.players["player_1"]["life"] = 0

        game.priority_manager.check_state_based_actions()

        game_over = [pdu for _, pdu in server.sent if pdu.get("type") == "GAME_OVER"][-1]
        self.assertEqual(game_over["reason"], "LIFE_ZERO")
        self.assertEqual(game_over["winner_id"], "player_2")
        self.assertEqual(game.state, "LOBBY")

    def test_reconnect_timeout_produces_disconnect_game_over(self):
        import game.lifecycle as lifecycle_module

        server = CaptureServer()
        game = make_game()
        game.server = server
        conn1, conn2 = object(), object()
        game.players["player_1"]["conn"] = conn1
        game.players["player_2"]["conn"] = conn2
        game.player_conns = [conn2]
        game.state = "IN_GAME"
        old_timeout = lifecycle_module.RECONNECT_TIMEOUT
        lifecycle_module.RECONNECT_TIMEOUT = 0.01
        try:
            game.lifecycle_manager.handle_disconnect("player_1")
            deadline = time.time() + 1
            while game.state != "LOBBY" and time.time() < deadline:
                time.sleep(0.01)
        finally:
            lifecycle_module.RECONNECT_TIMEOUT = old_timeout

        game_over = [pdu for _, pdu in server.sent if pdu.get("type") == "GAME_OVER"][-1]
        self.assertEqual(game_over["reason"], "DISCONNECT")
        self.assertEqual(game_over["winner_id"], "player_2")

    def test_client_pong_correlation_ignores_wrong_sequence(self):
        from network.client import MTGNPClient

        client = MTGNPClient()
        client._pending_ping_seq = 8
        client._handle_pdu({"type": "PONG", "seq_num": 7, "timestamp": 1})
        self.assertEqual(client._pending_ping_seq, 8)
        client._handle_pdu({"type": "PONG", "seq_num": 8, "timestamp": 2})
        self.assertIsNone(client._pending_ping_seq)

    def test_client_disconnects_after_pong_timeout(self):
        from network.client import MTGNPClient
        from core.constants import PONG_TIMEOUT

        class DummySocket:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        client = MTGNPClient()
        client.socket = DummySocket()
        client._pending_ping_seq = 1
        client.last_pong_time = time.time() - PONG_TIMEOUT - 1
        client._start_ping()
        deadline = time.time() + 2
        while client.running and time.time() < deadline:
            time.sleep(0.01)

        self.assertFalse(client.running)
        self.assertTrue(client.socket.closed)

if __name__ == "__main__":
    unittest.main()
