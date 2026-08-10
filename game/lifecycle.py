"""Game lifecycle management: LOBBY, SETUP, MULLIGAN, GAME_OVER."""
import random
from typing import Dict
from core.constants import INITIAL_LIFE, HAND_SIZE, MIN_DECK_SIZE, MAX_DECK_SIZE, RECONNECT_TIMEOUT
from core.models import Permanent
from core.utils import generate_permanent_id


class LifecycleManager:
    """Manages game lifecycle states."""
    
    def __init__(self, game):
        self.game = game
        self.state = game.state
        self.players = game.players
        self.player_conns = game.player_conns

    def handle_player_ready(self, conn, pdu: Dict):
        """Handle PLAYER_READY PDU."""
        player_id = pdu.get('player_id')
        if not player_id or not isinstance(player_id, str):
            self.game.send_error(conn, "ILLEGAL_ACTION", "Invalid player_id", pdu)
            return

        # Reconnect logic during active game
        if self.game.state not in ["LOBBY", "GAME_OVER"]:
            if player_id in self.game.players and self.game.players[player_id].get('conn') is None:
                self.game.players[player_id]['conn'] = conn
                if conn not in self.game.player_conns:
                    self.game.player_conns.append(conn)
                self.game.log(f"Player {player_id} reconnected.")
                self.game.send_game_state(player_id)
                return
            else:
                self.game.send_error(conn, "WRONG_PHASE", "Cannot send PLAYER_READY in current state", pdu)
                return

        existing_pid = self.game.get_player_by_conn(conn)
        if player_id in self.game.players and self.game.players[player_id]['conn'] != conn:
            self.game.send_error(conn, "DUPLICATE_ID", f"Player ID '{player_id}' already claimed", pdu)
            return

        # If connection changes ID, remove old ID
        if existing_pid and existing_pid != player_id:
            del self.game.players[existing_pid]

        deck_list = pdu.get('deck_list', [])
        if not isinstance(deck_list, list):
            self.game.send_error(conn, "ILLEGAL_DECK", "deck_list must be an array", pdu)
            return

        if len(deck_list) < MIN_DECK_SIZE or len(deck_list) > MAX_DECK_SIZE:
            self.game.send_error(conn, "ILLEGAL_DECK",
                               f"Deck must have {MIN_DECK_SIZE}-{MAX_DECK_SIZE} cards", pdu)
            return

        from game.card_catalog import is_legal_card
        seen_cards = set()
        for card_id in deck_list:
            if not is_legal_card(card_id):
                self.game.send_error(conn, "ILLEGAL_DECK", f"Unknown card: {card_id}", pdu)
                return
            if card_id in seen_cards:
                self.game.send_error(conn, "ILLEGAL_DECK", f"Duplicate card instance in deck: {card_id}", pdu)
                return
            seen_cards.add(card_id)

        for other_pid, other_data in self.game.players.items():
            if other_pid != player_id:
                opponent_deck = set(other_data.get('deck', []))
                for card_id in deck_list:
                    if card_id in opponent_deck:
                        self.game.send_error(conn, "ILLEGAL_DECK", f"Card instance already claimed by opponent: {card_id}", pdu)
                        return

        self.game.players[player_id] = {
            'conn': conn,
            'deck': deck_list[:],
            'hand': [],
            'library': [],
            'graveyard': [],
            'exile': [],
            'battlefield': [],
            'life': INITIAL_LIFE,
            'ready': True,
            'ready_to_play': False,
            'mulligan_count': 0,
            'empty_draw_attempted': False
        }

        if conn not in self.game.player_conns:
            self.game.player_conns.append(conn)

        self.game.log(f"Player {player_id} ready with {len(deck_list)} cards")

        waiting_for = [pid for pid in self.game.players if not self.game.players[pid].get('ready', False)]
        if len(self.game.players) == 1:
            waiting_for.append("opponent")

        pdu_response = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": self.game.next_seq(),
            "state": {
                "phase": "LOBBY",
                "players_ready": len(self.game.players),
                "waiting_for": waiting_for
            }
        }
        self.game.broadcast(pdu_response)

        if len(self.game.players) == 2:
            self.start_game_setup()

    def start_game_setup(self):
        """Transition to GAME_SETUP state."""
        self.game.log("Both players ready - starting GAME_SETUP")
        self.game.state = "GAME_SETUP"
        self.game.phase = "GAME_SETUP"

        for pid, data in self.game.players.items():
            library = data['deck'][:]
            random.shuffle(library)
            data['library'] = library
            data['hand'] = [library.pop() for _ in range(min(HAND_SIZE, len(library)))]
            data['life'] = INITIAL_LIFE
            data['battlefield'] = []
            data['graveyard'] = []
            data['mulligan_count'] = 0
            data['ready_to_play'] = False
            data['empty_draw_attempted'] = False

        self.game.active_player = random.choice(list(self.game.players.keys()))
        self.game.log(f"Coin flip: {self.game.active_player} goes first")

        self.game.broadcast_game_state()

        self.game.state = "MULLIGAN"
        self.game.phase = "MULLIGAN"
        self.game.turn = 0

        self.game.broadcast_game_state()
        self.game.log("Entered MULLIGAN state")

    def handle_mulligan_choice(self, conn, pdu: Dict):
        """Handle MULLIGAN_CHOICE PDU."""
        if self.game.state != "MULLIGAN":
            self.game.send_error(conn, "WRONG_PHASE", "Not in MULLIGAN state", pdu)
            return

        player_id = self.game.get_player_by_conn(conn)
        if not player_id:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Unknown player", pdu)
            return

        if pdu.get('seq_num') != self.game.players[player_id].get('last_seq_num'):
            self.game.send_error(conn, "STALE_ACTION", "Stale seq_num", pdu)
            return

        keep = pdu.get('keep', False)
        cards_to_bottom = pdu.get('cards_to_bottom', [])

        if not isinstance(keep, bool):
            self.game.send_error(conn, "ILLEGAL_ACTION", "keep must be boolean", pdu)
            return
        if not isinstance(cards_to_bottom, list):
            self.game.send_error(conn, "ILLEGAL_ACTION", "cards_to_bottom must be an array", pdu)
            return

        data = self.game.players[player_id]
        mulligan_count = data.get('mulligan_count', 0)

        if keep:
            if len(cards_to_bottom) != mulligan_count:
                self.game.send_error(conn, "ILLEGAL_ACTION",
                                   f"Must bottom {mulligan_count} cards", pdu)
                return

            hand = data['hand']
            # Validate the complete choice before changing either zone.
            remaining_hand = hand[:]
            for card_id in cards_to_bottom:
                if card_id not in remaining_hand:
                    self.game.send_error(conn, "ILLEGAL_ACTION",
                                       f"Card {card_id} not in hand", pdu)
                    return
                remaining_hand.remove(card_id)

            for card_id in cards_to_bottom:
                hand.remove(card_id)
            # library.pop() draws from the end, so index 0 is the bottom.
            data['library'][0:0] = cards_to_bottom

            data['ready_to_play'] = True
            self.game.log(f"Player {player_id} kept hand after {mulligan_count} mulligans")

        else:
            if mulligan_count >= 10:
                self.game.send_error(conn, "ILLEGAL_ACTION", "Too many mulligans", pdu)
                return

            library = data['library']
            hand = data['hand']
            library.extend(hand)
            random.shuffle(library)
            hand.clear()
            hand.extend([library.pop() for _ in range(min(HAND_SIZE, len(library)))])
            data['mulligan_count'] = mulligan_count + 1

            self.game.log(f"Player {player_id} took mulligan #{mulligan_count + 1}")
            self.game.send_game_state(player_id)

        all_ready = all(pdata.get('ready_to_play', False) for pdata in self.game.players.values())

        if all_ready:
            self.game.turn_engine.start_turn()

    def end_game(self, winner_id: str, reason: str):
        """End the game and transition to GAME_OVER state."""
        self.game.state = "GAME_OVER"
        self.game.log(f"Game over! {winner_id} wins (reason: {reason})")

        loser_id = self.game.get_other_player(winner_id)

        pdu = {
            "type": "GAME_OVER",
            "seq_num": self.game.next_seq(),
            "winner_id": winner_id,
            "loser_id": loser_id,
            "reason": reason
        }
        self.game.broadcast(pdu)

        self.game.state = "LOBBY"
        self.game.phase = "LOBBY"
        self.game.players = {}
        # Keep TCP connections for session restart
        self.game.turn = 0
        self.game.active_player = None
        self.game.stack = []
        self.game.floating_mana = {}
        self.game.land_played_this_turn = False

        self.game.log("Returned to LOBBY state")

    def handle_disconnect(self, player_id: str):
        """Handle player disconnect."""
        self.game.log(f"Player {player_id} disconnected")

        if self.game.state in ["LOBBY", "GAME_OVER"]:
            if player_id in self.game.players:
                del self.game.players[player_id]
            return

        # Mark as disconnected
        if player_id in self.game.players:
            self.game.players[player_id]['conn'] = None

        import threading
        def timeout_check():
            if self.game.state not in ["LOBBY", "GAME_OVER"]:
                if player_id in self.game.players and self.game.players[player_id].get('conn') is None:
                    winner_id = self.game.get_other_player(player_id)
                    if winner_id:
                        self.end_game(winner_id, "DISCONNECT")
                        
        timer = threading.Timer(RECONNECT_TIMEOUT, timeout_check)
        timer.daemon = True
        timer.start()
