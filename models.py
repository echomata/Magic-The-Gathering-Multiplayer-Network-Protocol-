"""Data models for MTGNP game state."""
from typing import Dict, Optional

from card_catalog import get_card, is_creature, card_has_haste, card_has_first_strike


class Permanent:
    """Represents a permanent on the battlefield."""
    
    def __init__(self, card_id: str, controller: str, permanent_id: str, turn: int = 0):
        self.id = permanent_id
        self.card_id = card_id
        self.controller = controller
        self.tapped = False
        self.damage = 0
        self.summoning_sick = True
        self.entered_turn = turn
        self.card_data = get_card(card_id)
        self.attached_to = None  # For auras
        self.counter = 0  # For +1/+1 counters etc.
        self._power_bonus = 0
        self._toughness_bonus = 0
        self._temporary_bonus = {'power': 0, 'toughness': 0}
        self._protected = False
        self._pacified = False

    def to_dict(self, include_controller: bool = True) -> Dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "id": self.id,
            "card_id": self.card_id,
            "tapped": self.tapped,
            "damage": self.damage,
        }
        if is_creature(self.card_data):
            power = self.get_power()
            toughness = self.get_toughness()
            result.update({
                "power": power,
                "toughness": toughness,
                "summoning_sick": self.summoning_sick
            })
        if include_controller:
            result["controller"] = self.controller
        if self.attached_to:
            result["attached_to"] = self.attached_to
        return result

    def can_attack(self) -> bool:
        """Check if this permanent can attack."""
        if not is_creature(self.card_data):
            return False
        if self.tapped:
            return False
        if self.summoning_sick and not card_has_haste(self.card_data):
            return False
        if self._pacified:
            return False
        return True

    def can_block(self) -> bool:
        """Check if this permanent can block."""
        if not is_creature(self.card_data):
            return False
        if self.tapped:
            return False
        if self._pacified:
            return False
        return True

    def get_power(self) -> int:
        """Get current power including modifiers."""
        base = self.card_data.get('power', 0)
        return base + self._power_bonus + self._temporary_bonus.get('power', 0)

    def get_toughness(self) -> int:
        """Get current toughness including modifiers."""
        base = self.card_data.get('toughness', 0)
        return base + self._toughness_bonus + self._temporary_bonus.get('toughness', 0)

    def add_power_toughness(self, power: int, toughness: int):
        """Add power/toughness bonuses."""
        self._power_bonus += power
        self._toughness_bonus += toughness

    def has_first_strike(self) -> bool:
        """Check if this creature has first strike."""
        return card_has_first_strike(self.card_data)


class StackItem:
    """Represents an item on the stack."""
    
    def __init__(self, card_id: str, controller: str, targets: list = None):
        self.stack_item_id = f"stk_{id(self)}"
        self.card_id = card_id
        self.controller = controller
        self.targets = targets or []
        self.item_type = "SPELL"
        self.trigger_data = None
        
        card = get_card(card_id)
        if card:
            card_type = card.get('type')
            if card_type in ['Creature', 'Artifact Creature', 'Enchantment', 'Artifact']:
                self.item_type = "PERMANENT"
        self.resolved = False

    def to_pdu(self) -> Dict:
        """Convert to PDU dictionary."""
        return {
            "stack_item_id": self.stack_item_id,
            "item_type": self.item_type,
            "source": self.card_id,
            "targets": self.targets,
            "controller": self.controller
        }


class Player:
    """Represents a player in the game."""
    
    def __init__(self, player_id: str, conn=None, deck: list = None):
        self.id = player_id
        self.conn = conn
        self.deck = deck or []
        self.hand = []
        self.library = []
        self.graveyard = []
        self.battlefield = []
        self.life = 20
        self.ready = False
        self.ready_to_play = False
        self.mulligan_count = 0
        self.land_played = 0
        self._has_priority = False
        self._cannot_gain_life = False

    @property
    def has_priority(self) -> bool:
        return self._has_priority

    @has_priority.setter
    def has_priority(self, value: bool):
        self._has_priority = value

    def to_dict(self, include_hand: bool = True) -> Dict:
        """Convert player state to dictionary."""
        result = {
            "id": self.id,
            "life": self.life,
            "hand_count": len(self.hand),
            "library_count": len(self.library),
            "graveyard_count": len(self.graveyard),
            "battlefield": [p.to_dict() for p in self.battlefield]
        }
        if include_hand:
            result["hand"] = self.hand[:]
        return result