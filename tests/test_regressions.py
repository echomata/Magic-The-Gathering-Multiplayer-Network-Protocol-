import unittest

from core.models import Permanent
from game.actions import ActionHandler
from game.card_effects import execute_card_effect
from game.game import Game
from game.state import GameState
from network.network import decode_message, encode_message


class FakeServer:
    def __init__(self):
        self.pdus = []
        self.errors = []

    def send_pdu(self, conn, pdu):
        self.pdus.append(pdu)

    def send_error(self, conn, code, message, rejected_action=None):
        self.errors.append((code, message))

    def broadcast_to_game(self, pdu):
        self.pdus.append(pdu)


def make_game():
    game = Game(FakeServer())
    game.players = {
        "player_1": {
            "conn": "conn_1", "hand": [], "library": [], "graveyard": [],
            "exile": [], "battlefield": [], "life": 20,
        },
        "player_2": {
            "conn": "conn_2", "hand": [], "library": [], "graveyard": [],
            "exile": [], "battlefield": [], "life": 20,
        },
    }
    game.player_conns = ["conn_1", "conn_2"]
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

    def test_trample_is_not_implemented_per_rfc(self):
        """RFC 9.7 is explicit: 'MTGNP 1.0 does not implement trample. A
        blocked attacker deals its full combat damage to its blocker(s)
        only, never to the defending player.' This must hold even for
        creatures tagged with a 'trample' ability in the catalog."""
        from game.combat import CombatSystem

        game = make_game()
        attacker = Permanent("reckless_wurm_001", "player_1", "attacker", 1)
        blocker = Permanent("grizzly_bears_001", "player_2", "blocker", 1)
        game.players["player_1"]["battlefield"] = [attacker]
        game.players["player_2"]["battlefield"] = [blocker]
        game.combat_system.attackers = [{"creature_id": "attacker", "target": "player_2"}]
        game.combat_system.blockers = [{"creature_id": "blocker", "blocking_id": "attacker"}]
        game.combat_system.deal_combat_damage()
        # Reckless Wurm is 4/4 and Grizzly Bears is 2/2: all 4 damage goes
        # to the blocker (killing it), NONE reaches the defending player's
        # life total, regardless of the "trample" tag.
        self.assertEqual(blocker.damage, 4)
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

    def test_pacifism_applies_and_persists_across_untap(self):
        """Pacifism is an Enchantment (is_permanent()==True) whose effect
        must ALSO fire on resolve (unlike a mana dork's activated-ability
        effect field, which fires later via ACTIVATE_ABILITY, not on
        cast). And because no card in this pool can remove an Aura, its
        restriction must last indefinitely - NOT wear off at the enchanted
        creature's controller's next untap step."""
        from core.models import StackItem

        game = make_game()
        game.state = "IN_GAME"
        game.phase = "PRECOMBAT_MAIN"
        game.turn = 1
        game.active_player = "player_1"
        target = Permanent("grizzly_bears_001", "player_2", "bear", 0)
        target.summoning_sick = False
        game.players["player_2"]["battlefield"] = [target]

        self.assertTrue(target.can_attack())

        game.stack.append(StackItem("pacifism_001", "player_1", [target.id]))
        game.priority_manager.resolve_stack()

        self.assertTrue(target._pacified)
        self.assertFalse(target.can_attack())
        self.assertIn(
            "pacifism_001",
            [p.card_id for p in game.players["player_1"]["battlefield"]],
        )

        for _ in range(6):
            game.active_player = (
                "player_2" if game.active_player == "player_1" else "player_1"
            )
            game.turn_engine.do_untap_step()
            game.turn_engine.do_cleanup()

        self.assertTrue(target._pacified)
        self.assertFalse(target.can_attack())

    def test_until_end_of_turn_hexproof_expires_at_cleanup_not_next_untap(self):
        """Vines of Vastwood's hexproof grant is 'until end of turn' - it
        must expire at the SAME turn's Cleanup Step, not linger until the
        granted creature's controller's next Untap Step (which would let
        it incorrectly persist through the opponent's entire next turn)."""
        game = make_game()
        creature = Permanent("grizzly_bears_001", "player_1", "bear", 0)
        creature._hexproof = True
        game.players["player_1"]["battlefield"] = [creature]

        game.active_player = "player_1"
        game.turn_engine.do_cleanup()
        self.assertFalse(creature._hexproof)



    def test_regeneration_survives_lethal_combat_damage(self):
        """combat.py had its own inline death-check that bypassed
        _regeneration_shield entirely (only the separate
        check_state_based_actions() respected it) - so a creature that
        should survive combat via regeneration was dying anyway."""
        from core.models import Permanent

        game = make_game()
        game.active_player = "player_1"
        attacker = Permanent("reckless_wurm_001", "player_1", "atk", 0)
        attacker.summoning_sick = False
        regen_blocker = Permanent("grizzly_bears_001", "player_2", "rb", 0)
        regen_blocker._regeneration_shield = 1
        game.players["player_1"]["battlefield"] = [attacker]
        game.players["player_2"]["battlefield"] = [regen_blocker]
        game.combat_system.attackers = [{"creature_id": "atk", "target": "player_2"}]
        game.combat_system.blockers = [{"creature_id": "rb", "blocking_id": "atk"}]
        game.combat_system.deal_combat_damage()

        self.assertEqual(regen_blocker.damage, 0)
        self.assertTrue(regen_blocker.tapped)
        self.assertEqual(regen_blocker._regeneration_shield, 0)
        self.assertIn(
            "grizzly_bears_001",
            [p.card_id for p in game.players["player_2"]["battlefield"]],
        )

    def test_creature_without_regeneration_still_dies_in_combat(self):
        from core.models import Permanent

        game = make_game()
        game.active_player = "player_1"
        attacker = Permanent("reckless_wurm_001", "player_1", "atk", 0)
        attacker.summoning_sick = False
        blocker = Permanent("grizzly_bears_001", "player_2", "pb", 0)
        game.players["player_1"]["battlefield"] = [attacker]
        game.players["player_2"]["battlefield"] = [blocker]
        game.combat_system.attackers = [{"creature_id": "atk", "target": "player_2"}]
        game.combat_system.blockers = [{"creature_id": "pb", "blocking_id": "atk"}]
        game.combat_system.deal_combat_damage()

        self.assertEqual(game.players["player_2"]["battlefield"], [])

    def test_discard_at_cleanup_logic(self):
        game = make_game()
        game.state = "IN_GAME"
        game.phase = "CLEANUP"
        game.active_player = "player_1"
        game.players["player_1"]["hand"] = [f"card_{i}" for i in range(8)]
        
        game.action_handler.waiting_for_discard = "player_1"
        game.action_handler.handle_discard("conn_1", {
            "type": "DISCARD", 
            "seq_num": 1,
            "card_ids": ["card_0"]
        })
        self.assertEqual(len(game.players["player_1"]["hand"]), 7)
        self.assertIsNone(game.action_handler.waiting_for_discard)
        self.assertEqual(game.turn, 1)  # Advanced to next turn

    def test_deck_empty_win_condition_logic(self):
        game = make_game()
        game.state = "IN_GAME"
        game.players["player_1"]["library"] = []  # Empty library
        game.active_player = "player_1"
        
        # When drawing a card, should trigger game over
        game.turn_engine.do_draw_step()
        self.assertEqual(game.state, "LOBBY")
        
        game_overs = [p for p in game.server.pdus if p.get("type") == "GAME_OVER"]
        self.assertEqual(len(game_overs), 2)
        self.assertEqual(game_overs[0]["reason"], "DECK_EMPTY")
        self.assertEqual(game_overs[0]["winner_id"], "player_2")
        
    def test_simultaneous_life_zero_logic(self):
        game = make_game()
        game.state = "IN_GAME"
        game.players["player_1"]["life"] = 0
        game.players["player_2"]["life"] = 0
        game.active_player = "player_1"
        
        game.priority_manager.check_state_based_actions()
        self.assertEqual(game.state, "LOBBY")
        
        game_overs = [p for p in game.server.pdus if p.get("type") == "GAME_OVER"]
        self.assertEqual(len(game_overs), 2)
        self.assertEqual(game_overs[0]["reason"], "LIFE_ZERO")
        self.assertEqual(game_overs[0]["winner_id"], "player_2")

    def test_counterspell_stack_interaction_logic(self):
        from core.models import StackItem
        game = make_game()
        game.state = "IN_GAME"
        
        # Player 1 casts a bolt
        bolt_item = StackItem("lightning_bolt_001", "player_1", ["player_2"])
        game.stack.append(bolt_item)
        
        # Player 2 casts counterspell targeting the bolt
        counter_item = StackItem("counterspell_001", "player_2", [bolt_item.stack_item_id])
        game.stack.append(counter_item)
        
        # Resolve counterspell
        game.priority_manager.resolve_stack()
        
        # Bolt should be removed from stack, stack should be empty
        self.assertEqual(len(game.stack), 0)
        self.assertEqual(game.players["player_2"]["life"], 20)  # Bolt did not resolve

    def test_combat_damage_end_to_end_logic(self):
        from core.models import Permanent
        game = make_game()
        game.active_player = "player_1"
        atk = Permanent("goblin_guide_001", "player_1", "atk", 0)
        blk = Permanent("grizzly_bears_001", "player_2", "blk", 0)
        game.players["player_1"]["battlefield"] = [atk]
        game.players["player_2"]["battlefield"] = [blk]
        
        game.combat_system.attackers = [{"creature_id": "atk", "target": "player_2"}]
        game.combat_system.blockers = [{"creature_id": "blk", "blocking_id": "atk"}]
        
        game.combat_system.deal_combat_damage()
        game.priority_manager.check_state_based_actions()
        
        self.assertEqual(len(game.players["player_1"]["battlefield"]), 0)
        self.assertEqual(len(game.players["player_2"]["battlefield"]), 0)

if __name__ == "__main__":
    unittest.main()
