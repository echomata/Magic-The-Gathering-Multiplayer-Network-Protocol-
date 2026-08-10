import unittest
from game.game import Game
from core.models import Permanent
from game.card_effects import execute_card_effect
from game.card_catalog import get_card

def make_game():
    game = Game(None)
    game.players = {
        "player_1": {
            "conn": None, "deck": [], "hand": [], "library": [], "graveyard": [], "exile": [],
            "battlefield": [], "life": 20, "ready": True, "ready_to_play": True,
            "mulligan_count": 0, "land_played": 0, "_has_priority": False
        },
        "player_2": {
            "conn": None, "deck": [], "hand": [], "library": [], "graveyard": [], "exile": [],
            "battlefield": [], "life": 20, "ready": True, "ready_to_play": True,
            "mulligan_count": 0, "land_played": 0, "_has_priority": False
        }
    }
    game.active_player = "player_1"
    game.state = "IN_GAME"
    game.phase = "MAIN_1"
    return game

class BonusFeaturesTests(unittest.TestCase):
    def test_protection_white_knight(self):
        game = make_game()
        # White Knight has protection from black
        knight = Permanent("white_knight_001", "player_1", "knight", 1)
        game.players["player_1"]["battlefield"].append(knight)
        
        # Test protection in models
        self.assertTrue(knight.has_protection_from("B"))
        self.assertFalse(knight.has_protection_from("R"))

    def test_devotion_calculation(self):
        game = make_game()
        # Gray Merchant has CMC 5 but Devotion to Black is 2 ({B}{B})
        merchant = Permanent("gray_merchant_001", "player_1", "merchant", 1)
        game.players["player_1"]["battlefield"].append(merchant)
        
        devotion = game.state_manager.get_devotion("player_1", "B")
        self.assertEqual(devotion, 2, "Devotion should only count colored mana symbols, not CMC")

    def test_incinerate_blocks_regeneration(self):
        game = make_game()
        troll = Permanent("troll_ascetic_001", "player_2", "troll", 1)
        troll._regeneration_shield = 1
        game.players["player_2"]["battlefield"].append(troll)
        
        # Incinerate deals 3 damage and prevents regeneration
        execute_card_effect(game, "incinerate_001", "player_1", ["troll"])
        
        # Verify the flag is set
        self.assertTrue(troll._cannot_regenerate_this_turn)
        
        # Run state-based actions
        game.priority_manager.check_state_based_actions()
        
        # Troll should be destroyed despite regeneration shield
        self.assertNotIn(troll, game.players["player_2"]["battlefield"])

    def test_skullcrack_prevents_life_gain(self):
        game = make_game()
        game.players["player_1"]["life"] = 10
        
        # Skullcrack deals damage and prevents life gain
        execute_card_effect(game, "skullcrack_001", "player_2", ["player_1"])
        
        # Player 1 should be at 7 life
        self.assertEqual(game.players["player_1"]["life"], 7)
        self.assertTrue(game.players["player_1"].get("_cannot_gain_life"))
        
        # Healing Salve targets player 1
        execute_card_effect(game, "healing_salve_001", "player_1", ["player_1"])
        
        # Life should STILL be 7 because of Skullcrack
        self.assertEqual(game.players["player_1"]["life"], 7)

    def test_healing_salve_prevents_damage(self):
        game = make_game()
        game.players["player_1"]["life"] = 10
        
        bear = Permanent("grizzly_bears_001", "player_1", "bear", 1)
        game.players["player_1"]["battlefield"].append(bear)
        
        execute_card_effect(game, "healing_salve_001", "player_1", ["bear"])
        
        # Verify shield is on the bear
        self.assertEqual(bear._prevent_next_damage, 3)
        
        # Lightning Bolt the bear
        execute_card_effect(game, "lightning_bolt_001", "player_2", ["bear"])
        
        # Damage should be prevented
        self.assertEqual(bear.damage, 0)
        self.assertEqual(bear._prevent_next_damage, 0)

    def test_doom_blade_allows_regeneration(self):
        game = make_game()
        troll = Permanent("troll_ascetic_001", "player_2", "troll", 1)
        troll._regeneration_shield = 1
        game.players["player_2"]["battlefield"].append(troll)
        
        # Doom Blade destroys target nonblack creature
        execute_card_effect(game, "doom_blade_001", "player_1", ["troll"])
        
        # Troll should survive because of the shield
        self.assertIn(troll, game.players["player_2"]["battlefield"])
        self.assertEqual(troll._regeneration_shield, 0)
        self.assertTrue(troll.tapped)

    def test_terror_prevents_regeneration(self):
        game = make_game()
        troll = Permanent("troll_ascetic_001", "player_2", "troll", 1)
        troll._regeneration_shield = 1
        game.players["player_2"]["battlefield"].append(troll)
        
        # Terror destroys target nonartifact, nonblack creature, and CANNOT BE REGENERATED
        execute_card_effect(game, "terror_001", "player_1", ["troll"])
        
        # Troll should be destroyed
        self.assertNotIn(troll, game.players["player_2"]["battlefield"])

if __name__ == '__main__':
    unittest.main()
