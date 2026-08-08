import unittest

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

    def test_trample_single_blocker_assigns_power_once(self):
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
        # 2 trample to the player, for 4 total.
        self.assertEqual(blocker.damage, 2)
        self.assertEqual(game.players["player_2"]["life"], 18)

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


if __name__ == "__main__":
    unittest.main()
