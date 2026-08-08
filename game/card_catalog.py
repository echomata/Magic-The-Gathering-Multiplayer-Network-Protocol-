"""Complete card catalog for MTGNP."""

# Master Card Definitions - Each card type with its properties
MASTER_CARDS = {
    # Lands
    "mountain": {"name": "Mountain", "type": "Land", "subtype": "Basic Mountain", "color": "R", "cmc": 0, 
                 "mana_cost": {}, "power": None, "toughness": None, "abilities": ["mana_R"], 
                 "effect": "mana", "effect_value": "R", "copies": 20},
    "forest": {"name": "Forest", "type": "Land", "subtype": "Basic Forest", "color": "G", "cmc": 0, 
               "mana_cost": {}, "power": None, "toughness": None, "abilities": ["mana_G"], 
               "effect": "mana", "effect_value": "G", "copies": 20},
    "plains": {"name": "Plains", "type": "Land", "subtype": "Basic Plains", "color": "W", "cmc": 0, 
               "mana_cost": {}, "power": None, "toughness": None, "abilities": ["mana_W"], 
               "effect": "mana", "effect_value": "W", "copies": 20},
    "island": {"name": "Island", "type": "Land", "subtype": "Basic Island", "color": "U", "cmc": 0, 
               "mana_cost": {}, "power": None, "toughness": None, "abilities": ["mana_U"], 
               "effect": "mana", "effect_value": "U", "copies": 20},
    "swamp": {"name": "Swamp", "type": "Land", "subtype": "Basic Swamp", "color": "B", "cmc": 0, 
              "mana_cost": {}, "power": None, "toughness": None, "abilities": ["mana_B"], 
              "effect": "mana", "effect_value": "B", "copies": 20},
    
    # Red Spells
    "lightning_bolt": {"name": "Lightning Bolt", "type": "Instant", "subtype": "", "color": "R", "cmc": 1, 
                       "mana_cost": {"R": 1}, "power": None, "toughness": None, "abilities": [], 
                       "effect": "deal_damage", "effect_value": 3, "copies": 4},
    "shock": {"name": "Shock", "type": "Instant", "subtype": "", "color": "R", "cmc": 1, 
              "mana_cost": {"R": 1}, "power": None, "toughness": None, "abilities": [], 
              "effect": "deal_damage", "effect_value": 2, "copies": 4},
    "lava_spike": {"name": "Lava Spike", "type": "Sorcery", "subtype": "", "color": "R", "cmc": 1, 
                   "mana_cost": {"R": 1}, "power": None, "toughness": None, "abilities": [], 
                   "effect": "deal_damage", "effect_value": 3, "copies": 4},
    "flame_slash": {"name": "Flame Slash", "type": "Sorcery", "subtype": "", "color": "R", "cmc": 1, 
                    "mana_cost": {"R": 1}, "power": None, "toughness": None, "abilities": [], 
                    "effect": "deal_damage_to_creature", "effect_value": 4, "copies": 4},
    "searing_spear": {"name": "Searing Spear", "type": "Instant", "subtype": "", "color": "R", "cmc": 2, 
                      "mana_cost": {"R": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
                      "effect": "deal_damage", "effect_value": 3, "copies": 4},
    "skullcrack": {"name": "Skullcrack", "type": "Instant", "subtype": "", "color": "R", "cmc": 2, 
                   "mana_cost": {"R": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
                   "effect": "deal_damage_no_prevent", "effect_value": 3, "copies": 4},
    "rift_bolt": {"name": "Rift Bolt", "type": "Sorcery", "subtype": "", "color": "R", "cmc": 3, 
                  "mana_cost": {"R": 1, "X": 2}, "power": None, "toughness": None, 
                  "abilities": ["suspend_1_R"], "effect": "deal_damage", "effect_value": 3, "copies": 4},
    "incinerate": {"name": "Incinerate", "type": "Instant", "subtype": "", "color": "R", "cmc": 2, 
                   "mana_cost": {"R": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
                   "effect": "deal_damage_no_regen", "effect_value": 3, "copies": 4},
    
    # Red Creatures
    "goblin_guide": {"name": "Goblin Guide", "type": "Creature", "subtype": "Goblin Scout", "color": "R", "cmc": 1, 
                     "mana_cost": {"R": 1}, "power": 2, "toughness": 2, 
                     "abilities": ["haste", "goblin_guide_trigger", "enters_battlefield"], 
                     "effect": None, "effect_value": None, "copies": 4},
    "goblin_bushwhacker": {"name": "Goblin Bushwhacker", "type": "Creature", "subtype": "Goblin Warrior", "color": "R", "cmc": 1, 
                           "mana_cost": {"R": 1}, "power": 1, "toughness": 1, 
                           "abilities": ["kicker_1R", "bushwhacker_trigger", "enters_battlefield"], 
                           "effect": None, "effect_value": None, "copies": 4},
    "reckless_wurm": {"name": "Reckless Wurm", "type": "Creature", "subtype": "Wurm", "color": "R", "cmc": 5, 
                      "mana_cost": {"R": 1, "X": 3}, "power": 4, "toughness": 4, 
                      "abilities": ["trample", "madness_2R", "enters_battlefield"], 
                      "effect": None, "effect_value": None, "copies": 4},
    "monastery_swiftspear": {"name": "Monastery Swiftspear", "type": "Creature", "subtype": "Human Monk", "color": "R", "cmc": 1, 
                             "mana_cost": {"R": 1}, "power": 1, "toughness": 2, 
                             "abilities": ["haste", "prowess", "enters_battlefield"], 
                             "effect": None, "effect_value": None, "copies": 4},
    "wall_of_stone": {"name": "Wall of Stone", "type": "Creature", "subtype": "Wall", "color": "R", "cmc": 3, 
                      "mana_cost": {"R": 2, "X": 1}, "power": 0, "toughness": 8, 
                      "abilities": ["defender", "enters_battlefield"], 
                      "effect": None, "effect_value": None, "copies": 4},
    
    # Blue Spells
    "counterspell": {"name": "Counterspell", "type": "Instant", "subtype": "", "color": "U", "cmc": 2, 
                     "mana_cost": {"U": 2}, "power": None, "toughness": None, "abilities": [], 
                     "effect": "counter", "effect_value": None, "copies": 4},
    "cancel": {"name": "Cancel", "type": "Instant", "subtype": "", "color": "U", "cmc": 3, 
               "mana_cost": {"U": 2, "X": 1}, "power": None, "toughness": None, "abilities": [], 
               "effect": "counter", "effect_value": None, "copies": 4},
    "unsummon": {"name": "Unsummon", "type": "Instant", "subtype": "", "color": "U", "cmc": 1, 
                 "mana_cost": {"U": 1}, "power": None, "toughness": None, "abilities": [], 
                 "effect": "return_to_hand", "effect_value": None, "copies": 4},
    "ponder": {"name": "Ponder", "type": "Sorcery", "subtype": "", "color": "U", "cmc": 1, 
               "mana_cost": {"U": 1}, "power": None, "toughness": None, "abilities": [], 
               "effect": "ponder", "effect_value": None, "copies": 4},
    "negate": {"name": "Negate", "type": "Instant", "subtype": "", "color": "U", "cmc": 2, 
               "mana_cost": {"U": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
               "effect": "counter_noncreature", "effect_value": None, "copies": 4},
    "mana_leak": {"name": "Mana Leak", "type": "Instant", "subtype": "", "color": "U", "cmc": 2, 
                  "mana_cost": {"U": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
                  "effect": "mana_leak", "effect_value": 3, "copies": 4},
    
    # Blue Creatures
    "merfolk_looter": {"name": "Merfolk Looter", "type": "Creature", "subtype": "Merfolk Rogue", "color": "U", "cmc": 2, 
                       "mana_cost": {"U": 1, "X": 1}, "power": 1, "toughness": 1, 
                       "abilities": ["loot", "enters_battlefield"], 
                       "effect": None, "effect_value": None, "copies": 4},
    "prodigal_sorcerer": {"name": "Prodigal Sorcerer", "type": "Creature", "subtype": "Human Wizard", "color": "U", "cmc": 3, 
                          "mana_cost": {"U": 1, "X": 2}, "power": 1, "toughness": 1, 
                          "abilities": ["ping", "enters_battlefield"], 
                          "effect": None, "effect_value": None, "copies": 4},
    "air_elemental": {"name": "Air Elemental", "type": "Creature", "subtype": "Elemental", "color": "U", "cmc": 5, 
                      "mana_cost": {"U": 2, "X": 3}, "power": 4, "toughness": 4, 
                      "abilities": ["flying", "enters_battlefield"], 
                      "effect": None, "effect_value": None, "copies": 4},
    "phantasmal_bear": {"name": "Phantasmal Bear", "type": "Creature", "subtype": "Bear Illusion", "color": "U", "cmc": 1, 
                        "mana_cost": {"U": 1}, "power": 2, "toughness": 2, 
                        "abilities": ["illusion", "enters_battlefield"], 
                        "effect": None, "effect_value": None, "copies": 4},
    
    # Green Spells
    "giant_growth": {"name": "Giant Growth", "type": "Instant", "subtype": "", "color": "G", "cmc": 1, 
                     "mana_cost": {"G": 1}, "power": None, "toughness": None, "abilities": [], 
                     "effect": "giant_growth", "effect_value": 3, "copies": 4},
    "rampant_growth": {"name": "Rampant Growth", "type": "Sorcery", "subtype": "", "color": "G", "cmc": 2, 
                       "mana_cost": {"G": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
                       "effect": "rampant_growth", "effect_value": None, "copies": 4},
    "naturalize": {"name": "Naturalize", "type": "Instant", "subtype": "", "color": "G", "cmc": 2, 
                   "mana_cost": {"G": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
                   "effect": "naturalize", "effect_value": None, "copies": 4},
    "vines_of_vastwood": {"name": "Vines of Vastwood", "type": "Instant", "subtype": "", "color": "G", "cmc": 1, 
                          "mana_cost": {"G": 1}, "power": None, "toughness": None, 
                          "abilities": ["kicker_G"], "effect": "vines_of_vastwood", "effect_value": 4, "copies": 4},
    
    # Green Creatures
    "llanowar_elves": {"name": "Llanowar Elves", "type": "Creature", "subtype": "Elf Druid", "color": "G", "cmc": 1, 
                       "mana_cost": {"G": 1}, "power": 1, "toughness": 1, 
                       "abilities": ["mana_G", "enters_battlefield"], 
                       "effect": "mana", "effect_value": "G", "copies": 4},
    "elvish_mystic": {"name": "Elvish Mystic", "type": "Creature", "subtype": "Elf Druid", "color": "G", "cmc": 1, 
                      "mana_cost": {"G": 1}, "power": 1, "toughness": 1, 
                      "abilities": ["mana_G", "enters_battlefield"], 
                      "effect": "mana", "effect_value": "G", "copies": 4},
    "grizzly_bears": {"name": "Grizzly Bears", "type": "Creature", "subtype": "Bear", "color": "G", "cmc": 2, 
                      "mana_cost": {"G": 1, "X": 1}, "power": 2, "toughness": 2, 
                      "abilities": ["enters_battlefield"], 
                      "effect": None, "effect_value": None, "copies": 4},
    "leatherback_baloth": {"name": "Leatherback Baloth", "type": "Creature", "subtype": "Beast", "color": "G", "cmc": 3, 
                           "mana_cost": {"G": 3}, "power": 4, "toughness": 5, 
                           "abilities": ["enters_battlefield"], 
                           "effect": None, "effect_value": None, "copies": 4},
    "troll_ascetic": {"name": "Troll Ascetic", "type": "Creature", "subtype": "Troll Shaman", "color": "G", "cmc": 3, 
                      "mana_cost": {"G": 2, "X": 1}, "power": 3, "toughness": 2, 
                      "abilities": ["hexproof", "regenerate", "enters_battlefield"], 
                      "effect": None, "effect_value": None, "copies": 4},
    
    # White Spells
    "swords_to_plowshares": {"name": "Swords to Plowshares", "type": "Instant", "subtype": "", "color": "W", "cmc": 1, 
                             "mana_cost": {"W": 1}, "power": None, "toughness": None, "abilities": [], 
                             "effect": "swords_to_plowshares", "effect_value": None, "copies": 4},
    "path_to_exile": {"name": "Path to Exile", "type": "Instant", "subtype": "", "color": "W", "cmc": 1, 
                      "mana_cost": {"W": 1}, "power": None, "toughness": None, "abilities": [], 
                      "effect": "path_to_exile", "effect_value": None, "copies": 4},
    "healing_salve": {"name": "Healing Salve", "type": "Instant", "subtype": "", "color": "W", "cmc": 1, 
                      "mana_cost": {"W": 1}, "power": None, "toughness": None, "abilities": [], 
                      "effect": "healing_salve", "effect_value": 3, "copies": 4},
    "pacifism": {"name": "Pacifism", "type": "Enchantment", "subtype": "Aura", "color": "W", "cmc": 2, 
                 "mana_cost": {"W": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
                 "effect": "pacifism", "effect_value": None, "copies": 4},
    
    # White Creatures
    "white_knight": {"name": "White Knight", "type": "Creature", "subtype": "Human Knight", "color": "W", "cmc": 2, 
                     "mana_cost": {"W": 2}, "power": 2, "toughness": 2, 
                     "abilities": ["first_strike", "protection_black", "enters_battlefield"], 
                     "effect": None, "effect_value": None, "copies": 4},
    "serra_angel": {"name": "Serra Angel", "type": "Creature", "subtype": "Angel", "color": "W", "cmc": 5, 
                    "mana_cost": {"W": 2, "X": 3}, "power": 4, "toughness": 4, 
                    "abilities": ["flying", "vigilance", "enters_battlefield"], 
                    "effect": None, "effect_value": None, "copies": 4},
    "savannah_lions": {"name": "Savannah Lions", "type": "Creature", "subtype": "Cat", "color": "W", "cmc": 1, 
                       "mana_cost": {"W": 1}, "power": 2, "toughness": 1, 
                       "abilities": ["enters_battlefield"], 
                       "effect": None, "effect_value": None, "copies": 4},
    "mother_of_runes": {"name": "Mother of Runes", "type": "Creature", "subtype": "Human Cleric", "color": "W", "cmc": 1, 
                        "mana_cost": {"W": 1}, "power": 1, "toughness": 1, 
                        "abilities": ["protection_giver", "enters_battlefield"], 
                        "effect": None, "effect_value": None, "copies": 4},
    
    # Black Spells
    "dark_ritual": {"name": "Dark Ritual", "type": "Instant", "subtype": "", "color": "B", "cmc": 1, 
                    "mana_cost": {"B": 1}, "power": None, "toughness": None, "abilities": [], 
                    "effect": "dark_ritual", "effect_value": None, "copies": 4},
    "terror": {"name": "Terror", "type": "Instant", "subtype": "", "color": "B", "cmc": 2, 
               "mana_cost": {"B": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
               "effect": "terror", "effect_value": None, "copies": 4},
    "doom_blade": {"name": "Doom Blade", "type": "Instant", "subtype": "", "color": "B", "cmc": 2, 
                   "mana_cost": {"B": 1, "X": 1}, "power": None, "toughness": None, "abilities": [], 
                   "effect": "doom_blade", "effect_value": None, "copies": 4},
    "raise_dead": {"name": "Raise Dead", "type": "Sorcery", "subtype": "", "color": "B", "cmc": 1, 
                   "mana_cost": {"B": 1}, "power": None, "toughness": None, "abilities": [], 
                   "effect": "raise_dead", "effect_value": None, "copies": 4},
    "mind_rot": {"name": "Mind Rot", "type": "Sorcery", "subtype": "", "color": "B", "cmc": 3, 
                 "mana_cost": {"B": 1, "X": 2}, "power": None, "toughness": None, "abilities": [], 
                 "effect": "mind_rot", "effect_value": None, "copies": 4},
    
    # Black Creatures
    "gray_merchant": {"name": "Gray Merchant of Asphodel", "type": "Creature", "subtype": "Zombie", "color": "B", "cmc": 5, 
                      "mana_cost": {"B": 2, "X": 3}, "power": 2, "toughness": 4, 
                      "abilities": ["devotion_black", "lifedrain", "enters_battlefield"], 
                      "effect": "gray_merchant", "effect_value": 0, "copies": 4},
    "gravedigger": {"name": "Gravedigger", "type": "Creature", "subtype": "Zombie", "color": "B", "cmc": 4, 
                    "mana_cost": {"B": 1, "X": 3}, "power": 2, "toughness": 2, 
                    "abilities": ["gravedigger_trigger", "enters_battlefield"], 
                    "effect": None, "effect_value": None, "copies": 4},
    "royal_assassin": {"name": "Royal Assassin", "type": "Creature", "subtype": "Human Assassin", "color": "B", "cmc": 3, 
                       "mana_cost": {"B": 2, "X": 1}, "power": 1, "toughness": 1, 
                       "abilities": ["assassinate", "enters_battlefield"], 
                       "effect": None, "effect_value": None, "copies": 4},
    "black_knight": {"name": "Black Knight", "type": "Creature", "subtype": "Human Knight", "color": "B", "cmc": 2, 
                     "mana_cost": {"B": 2}, "power": 2, "toughness": 2, 
                     "abilities": ["first_strike", "protection_white", "enters_battlefield"], 
                     "effect": None, "effect_value": None, "copies": 4},
    
    # Colorless Artifacts
    "sol_ring": {"name": "Sol Ring", "type": "Artifact", "subtype": "", "color": "C", "cmc": 1, 
                 "mana_cost": {"X": 1}, "power": None, "toughness": None, 
                 "abilities": ["mana_CC"], "effect": "mana", "effect_value": "CC", "copies": 4},
    "ornithopter": {"name": "Ornithopter", "type": "Artifact Creature", "subtype": "Thopter", "color": "C", "cmc": 0, 
                    "mana_cost": {}, "power": 0, "toughness": 2, 
                    "abilities": ["flying", "enters_battlefield"], 
                    "effect": None, "effect_value": None, "copies": 4},
    "millstone": {"name": "Millstone", "type": "Artifact", "subtype": "", "color": "C", "cmc": 2, 
                  "mana_cost": {"X": 2}, "power": None, "toughness": None, 
                  "abilities": ["mill"], "effect": None, "effect_value": None, "copies": 4},
    "rod_of_ruin": {"name": "Rod of Ruin", "type": "Artifact", "subtype": "", "color": "C", "cmc": 4, 
                    "mana_cost": {"X": 4}, "power": None, "toughness": None, 
                    "abilities": ["ping_artifact"], "effect": None, "effect_value": None, "copies": 4},
}

# Generate individual card instances (card_id -> master card reference)
CARD_CATALOG = {}


def generate_card_instances():
    """Generate all card instances from master card definitions."""
    for base_id, card_data in MASTER_CARDS.items():
        copies = card_data.get('copies', 1)
        for i in range(1, copies + 1):
            # All card instance IDs use 3-digit, zero-padded suffixes
            # (e.g. "mountain_001"), matching the RFC's examples and the
            # official card list. Basic lands are NOT a special case.
            instance_id = f"{base_id}_{i:03d}"
            
            CARD_CATALOG[instance_id] = {
                "name": card_data["name"],
                "type": card_data["type"],
                "subtype": card_data.get("subtype", ""),
                "color": card_data["color"],
                "cmc": card_data["cmc"],
                "mana_cost": card_data["mana_cost"],
                "power": card_data.get("power"),
                "toughness": card_data.get("toughness"),
                "abilities": card_data.get("abilities", []),
                "effect": card_data.get("effect"),
                "effect_value": card_data.get("effect_value"),
                "base_id": base_id
            }


generate_card_instances()


def get_card(card_id: str) -> dict:
    """Get card data from catalog."""
    return CARD_CATALOG.get(card_id)


def get_master_card(card_id: str) -> dict:
    """Get master card data from base ID."""
    card = get_card(card_id)
    if card:
        base_id = card.get('base_id')
        return MASTER_CARDS.get(base_id)
    return None


def is_creature(card: dict) -> bool:
    return card.get('type') in ['Creature', 'Artifact Creature']


def is_land(card: dict) -> bool:
    return card.get('type') == 'Land'


def is_instant(card: dict) -> bool:
    return card.get('type') == 'Instant'


def is_sorcery(card: dict) -> bool:
    return card.get('type') == 'Sorcery'


def is_enchantment(card: dict) -> bool:
    return card.get('type') == 'Enchantment'


def is_artifact(card: dict) -> bool:
    return card.get('type') == 'Artifact'


def is_permanent(card: dict) -> bool:
    return card.get('type') in ['Creature', 'Artifact Creature', 'Enchantment', 'Artifact', 'Land']


def card_has_haste(card: dict) -> bool:
    return 'haste' in card.get('abilities', [])


def card_has_flying(card: dict) -> bool:
    return 'flying' in card.get('abilities', [])


def card_has_first_strike(card: dict) -> bool:
    return 'first_strike' in card.get('abilities', [])


def card_has_double_strike(card: dict) -> bool:
    return 'double_strike' in card.get('abilities', [])


def card_has_defender(card: dict) -> bool:
    return 'defender' in card.get('abilities', [])


def card_produces_mana(card: dict) -> str:
    abilities = card.get('abilities', [])
    for ability in abilities:
        if ability.startswith('mana_'):
            return ability[5:]  # Return the color(s)
    return None


def can_play_during_phase(card: dict, phase: str) -> bool:
    """Check if card can be played during the current phase."""
    card_type = card.get('type')
    
    if is_land(card):
        return phase in ["PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"]
    
    if is_instant(card):
        return True  # Instants can be played anytime with priority
    
    if is_sorcery(card) or is_enchantment(card) or card_type == 'Creature' or card_type == 'Artifact Creature':
        return phase in ["PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"]
    
    return True  # Default to allowed


def is_legal_card(card_id: str) -> bool:
    """Check if a card ID is in the catalog."""
    return card_id in CARD_CATALOG


def get_card_type(card_id: str) -> str:
    """Get the type of a card."""
    card = get_card(card_id)
    return card.get('type') if card else None


def list_available_cards() -> dict:
    """Get a summary of available cards."""
    card_types = {}
    colors = {}
    
    for card_id, card in CARD_CATALOG.items():
        card_type = card.get('type', 'Unknown')
        color = card.get('color', 'Unknown')
        card_types[card_type] = card_types.get(card_type, 0) + 1
        colors[color] = colors.get(color, 0) + 1
    
    return {
        "total": len(CARD_CATALOG),
        "by_type": card_types,
        "by_color": colors
    }