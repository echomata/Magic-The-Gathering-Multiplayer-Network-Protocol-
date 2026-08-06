"""Utility functions for MTGNP."""
import random
import time
from typing import List, Optional

from game.card_catalog import get_card, is_creature, is_land


def shuffle_deck(deck: List[str]) -> List[str]:
    """Shuffle a deck."""
    shuffled = deck[:]
    random.shuffle(shuffled)
    return shuffled


def draw_card(library: List[str]) -> Optional[str]:
    """Draw a card from the library."""
    if not library:
        return None
    return library.pop()


def generate_permanent_id() -> str:
    """Generate a unique permanent ID."""
    return f"perm_{int(time.time()*1000)}_{random.randint(1000, 9999)}"


def generate_stack_id() -> str:
    """Generate a unique stack item ID."""
    return f"stk_{int(time.time()*1000)}_{random.randint(1000, 9999)}"


def check_mana(payment: dict, cost: dict) -> bool:
    """Check if mana payment satisfies cost."""
    # Check colored mana
    for color, amount in cost.items():
        if color == 'X':
            continue
        if payment.get(color, 0) < amount:
            return False
    
    # Check generic mana
    generic_needed = cost.get('X', 0)
    generic_paid = payment.get('X', 0)
    if generic_paid < generic_needed:
        return False
    
    return True


def get_devotion(permanents: List, color: str) -> int:
    """Calculate devotion to a color from a list of permanents."""
    devotion = 0
    for perm in permanents:
        card = get_card(perm.card_id)
        if card and card.get('color') == color:
            devotion += card.get('cmc', 0)
    return devotion


def get_legal_targets(card_id: str, game_state: dict, player_id: str) -> List[str]:
    """Get legal targets for a spell or ability."""
    card = get_card(card_id)
    if not card:
        return []
    
    targets = []
    effect = card.get('effect')
    
    if effect in ['deal_damage', 'deal_damage_to_creature']:
        # Can target players and creatures
        # Add players
        for pid in game_state.get('players', {}):
            if pid != player_id:  # Can't target self for damage
                targets.append(pid)
        
        # Add creatures on battlefield
        for pid, player_data in game_state.get('players', {}).items():
            for perm in player_data.get('battlefield', []):
                if is_creature(get_card(perm.card_id)):
                    targets.append(perm.id)
    
    elif effect == 'counter':
        # Can target spells on the stack
        for item in game_state.get('stack', []):
            targets.append(item.get('stack_item_id'))
    
    return targets