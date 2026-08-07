"""Game state management."""
from typing import Dict, List, Optional, Any
from core.models import Permanent
from game.card_catalog import get_card


class GameState:
    """Manages the authoritative game state."""
    
    def __init__(self, game):
        self.game = game

    def get_player_by_conn(self, conn) -> Optional[str]:
        """Get player ID by connection."""
        for pid, data in self.game.players.items():
            if data.get('conn') == conn:
                return pid
        return None

    def get_other_player(self, player_id: str) -> Optional[str]:
        """Get the other player ID."""
        for pid in self.game.players:
            if pid != player_id:
                return pid
        return None

    def get_player_data(self, player_id: str) -> Dict:
        """Get player data dictionary."""
        return self.game.players.get(player_id, {})

    def get_player_permanents(self, player_id: str) -> List[Permanent]:
        """Get all permanents controlled by a player."""
        return self.game.players.get(player_id, {}).get('battlefield', [])

    def get_player_hand(self, player_id: str) -> List[str]:
        """Get a player's hand."""
        return self.game.players.get(player_id, {}).get('hand', [])

    def get_player_library(self, player_id: str) -> List[str]:
        """Get a player's library."""
        return self.game.players.get(player_id, {}).get('library', [])

    def find_permanent(self, perm_id: str) -> Optional[Permanent]:
        """Find a permanent by ID."""
        for pid, data in self.game.players.items():
            for perm in data.get('battlefield', []):
                if perm.id == perm_id:
                    return perm
        return None

    def remove_permanent(self, perm_id: str) -> bool:
        """Remove a permanent from the game."""
        for pid, data in self.game.players.items():
            for i, perm in enumerate(data.get('battlefield', [])):
                if perm.id == perm_id:
                    data['graveyard'].append(perm.card_id)
                    data['battlefield'].pop(i)
                    # Trigger death triggers
                    if self.game.trigger_manager:
                        self.game.trigger_manager.check_triggers('DEATH', {'creature': perm_id})
                    return True
        return False

    def get_devotion(self, player_id: str, color: str) -> int:
        """Calculate devotion to a color for a player."""
        devotion = 0
        data = self.game.players.get(player_id, {})
        for perm in data.get('battlefield', []):
            card = get_card(perm.card_id)
            if card and card.get('color') == color:
                devotion += card.get('cmc', 0)
        return devotion

    def build_state_dict(self, player_id: str) -> Dict:
        """Build a personalized GAME_STATE_UPDATE for a player.
        
        Each player sees their own hand but only the opponent's hand count.
        All other zones (battlefield, graveyard, stack) are public.
        """
        state = {
            "turn": self.game.turn,
            "phase": self.game.phase,
            "active_player": self.game.active_player,
            "life_totals": {},
            "hand": {},
            "hand_counts": {},
            "library_counts": {},
            "battlefield": {},
            "graveyard": {},
            "stack": [],
            "land_played_this_turn": self.game.land_played_this_turn
        }

        for pid, data in self.game.players.items():
            state["life_totals"][pid] = data.get('life', 20)

        for pid, data in self.game.players.items():
            if pid == player_id:
                state["hand"][pid] = data.get('hand', [])[:]
            else:
                state["hand_counts"][pid] = len(data.get('hand', []))

        for pid, data in self.game.players.items():
            state["library_counts"][pid] = len(data.get('library', []))

        for pid, data in self.game.players.items():
            state["battlefield"][pid] = [
                p.to_dict(include_controller=False) for p in data.get('battlefield', [])
            ]

        for pid, data in self.game.players.items():
            state["graveyard"][pid] = data.get('graveyard', [])[:]

        state["stack"] = [item.to_pdu() for item in self.game.stack]

        if self.game.priority_manager and self.game.priority_manager.priority_holder:
            state["priority_holder"] = self.game.priority_manager.priority_holder
        else:
            state["priority_holder"] = None

        return state

    def reset(self):
        """Reset game state for a new game, keeping TCP connections alive."""
        self.game.players = {}
        # NOTE: Do NOT clear player_conns — RFC requires TCP connections
        # to be retained after GAME_OVER for session restart.
        self.game.turn = 0
        self.game.active_player = None
        self.game.phase = None
        self.game.state = "LOBBY"
        self.game.land_played_this_turn = False
        self.game.floating_mana = {}
        self.game.stack = []