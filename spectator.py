"""Spectator client for MTGNP."""
import time
from typing import Dict

from client import MTGNPClient


class SpectatorClient(MTGNPClient):
    """A read-only spectator client."""
    
    def __init__(self, host='localhost', port=4444, verbose=False):
        super().__init__(host, port, verbose)
        self.is_spectator = True
        self.game_history = []
        self.spectator_id = "spectator"

    def send_player_ready(self, player_id: str, deck_list: list):
        """Spectator doesn't send PLAYER_READY."""
        self.log("Spectator mode - cannot send PLAYER_READY")
        
    def send_mulligan_choice(self, keep: bool, cards_to_bottom: list = None, seq_num: int = None):
        """Spectator doesn't send MULLIGAN_CHOICE."""
        self.log("Spectator mode - cannot send MULLIGAN_CHOICE")

    def send_cast_spell(self, card_id: str, targets: list, mana_payment: dict, seq_num: int = None):
        """Spectator doesn't send CAST_SPELL."""
        self.log("Spectator mode - cannot send CAST_SPELL")

    def send_play_land(self, card_id: str, seq_num: int = None):
        """Spectator doesn't send PLAY_LAND."""
        self.log("Spectator mode - cannot send PLAY_LAND")

    def send_declare_attackers(self, attackers: list, seq_num: int = None):
        """Spectator doesn't send DECLARE_ATTACKERS."""
        self.log("Spectator mode - cannot send DECLARE_ATTACKERS")

    def send_declare_blockers(self, blockers: list, seq_num: int = None):
        """Spectator doesn't send DECLARE_BLOCKERS."""
        self.log("Spectator mode - cannot send DECLARE_BLOCKERS")

    def send_concede(self):
        """Spectator doesn't send CONCEDE."""
        self.log("Spectator mode - cannot send CONCEDE")

    def _handle_pdu(self, pdu: Dict):
        """Handle incoming PDU with history tracking."""
        self.game_history.append({
            'timestamp': time.time(),
            'pdu': pdu
        })
        
        if len(self.game_history) > 1000:
            self.game_history = self.game_history[-500:]
        
        super()._handle_pdu(pdu)

    def get_history(self) -> list:
        """Get game history."""
        return self.game_history

    def save_history(self, filename: str):
        """Save game history to file."""
        import json
        with open(filename, 'w') as f:
            json.dump(self.game_history, f, indent=2)
        self.log(f"Game history saved to {filename}")

    def load_history(self, filename: str):
        """Load game history from file."""
        import json
        with open(filename, 'r') as f:
            self.game_history = json.load(f)
        self.log(f"Game history loaded from {filename}")
        
        # Replay the loaded history
        for entry in self.game_history:
            super()._handle_pdu(entry['pdu'])

    def replay(self, speed: float = 1.0):
        """Replay game history."""
        self.log(f"Replaying history at {speed}x speed")
        for entry in self.game_history:
            if self.verbose:
                print(f"[REPLAY] {entry.get('timestamp')}")
            super()._handle_pdu(entry['pdu'])
            time.sleep(0.5 / speed)