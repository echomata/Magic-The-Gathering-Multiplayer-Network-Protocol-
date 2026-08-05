"""MTGNP Client implementation."""
import socket
import json
import threading
import time
from typing import Dict, List, Optional

from constants import DEFAULT_PORT, PING_INTERVAL
from network import encode_message, decode_message, send_pdu
from card_catalog import get_card, list_available_cards


class MTGNPClient:
    """MTGNP Client for connecting to and interacting with the server."""
    
    def __init__(self, host: str = 'localhost', port: int = DEFAULT_PORT, verbose: bool = False):
        self.host = host
        self.port = port
        self.verbose = verbose
        self.socket = None
        self.player_id = None
        self.seq_num = 0
        self.running = True
        self.game_state = {}
        self._last_priority_seq = None

    def log(self, msg: str):
        if self.verbose:
            print(f"[CLIENT] {msg}")

    def connect(self):
        """Connect to the server."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        self.log(f"Connected to {self.host}:{self.port}")

        thread = threading.Thread(target=self._receive_loop)
        thread.daemon = True
        thread.start()

        self._start_ping()

    def send_pdu(self, pdu: Dict):
        """Send a PDU to the server."""
        send_pdu(self.socket, pdu, self.verbose)

    def _receive_loop(self):
        """Receive and process PDUs from server."""
        buffer = b''

        try:
            while self.running:
                data = self.socket.recv(4096)
                if not data:
                    break

                buffer += data

                while len(buffer) >= 4:
                    import struct
                    length = struct.unpack('>I', buffer[:4])[0]
                    if len(buffer) < 4 + length:
                        break

                    message_data = buffer[:4+length]
                    buffer = buffer[4+length:]

                    try:
                        pdu = decode_message(message_data)
                        self._handle_pdu(pdu)
                    except json.JSONDecodeError as e:
                        self.log(f"Invalid JSON: {e}")

        except Exception as e:
            self.log(f"Receive loop error: {e}")
        finally:
            self.running = False

    def _handle_pdu(self, pdu: Dict):
        """Handle incoming PDU."""
        if self.verbose:
            print(f"[CLIENT <- SERVER] {json.dumps(pdu, indent=2)}")

        pdu_type = pdu.get('type')

        if pdu_type == 'GAME_STATE_UPDATE':
            self.game_state = pdu.get('state', {})
            self._render_state()
        elif pdu_type == 'PRIORITY_GRANT':
            self._handle_priority(pdu)
        elif pdu_type == 'PHASE_TRANSITION':
            self.log(f"Phase transition: {pdu.get('from_phase')} -> {pdu.get('to_phase')}")
        elif pdu_type == 'ERROR':
            self.log(f"Error: {pdu.get('code')} - {pdu.get('message')}")
        elif pdu_type == 'PONG':
            self.log(f"PONG received (seq={pdu.get('seq_num')})")
        elif pdu_type == 'GAME_OVER':
            self.log(f"GAME OVER! Winner: {pdu.get('winner_id')} (reason: {pdu.get('reason')})")
            self.game_state = {}

    def _handle_priority(self, pdu: Dict):
        """Handle PRIORITY_GRANT PDU."""
        seq_num = pdu.get('seq_num')
        self._last_priority_seq = seq_num

        if pdu.get('player_id') != self.player_id:
            self.log(f"Priority granted to {pdu.get('player_id')} - auto passing")
            self.pass_priority(seq_num)
        else:
            self.log(f"Priority granted to {self.player_id} (seq={seq_num})")

    def _render_state(self):
        """Render the current game state."""
        if not self.game_state:
            return

        phase = self.game_state.get('phase', 'UNKNOWN')
        life_totals = self.game_state.get('life_totals', {})
        hand = self.game_state.get('hand', [])
        hand_counts = self.game_state.get('hand_counts', {})
        battlefield = self.game_state.get('battlefield', {})
        stack = self.game_state.get('stack', [])

        print("\n" + "="*60)
        print(f"  PHASE: {phase}")
        print(f"  Turn: {self.game_state.get('turn', 0)}")
        print(f"  Active Player: {self.game_state.get('active_player', 'Unknown')}")
        print(f"  Life: {life_totals}")
        
        if hand:
            print(f"  Hand ({len(hand)} cards):")
            for i, card_id in enumerate(hand[:10]):
                card = get_card(card_id)
                name = card.get('name') if card else card_id
                print(f"    {i+1}. {name}")
            if len(hand) > 10:
                print(f"    ... and {len(hand) - 10} more cards")
        print(f"  Hand Counts: {hand_counts}")

        if battlefield:
            print("  Battlefield:")
            for pid, perms in battlefield.items():
                if perms:
                    print(f"    {pid}:")
                    for perm in perms:
                        card = get_card(perm.get('card_id'))
                        name = card.get('name') if card else perm.get('card_id')
                        tapped = " (T)" if perm.get('tapped') else ""
                        sick = " (sick)" if perm.get('summoning_sick') else ""
                        power = perm.get('power', '')
                        toughness = perm.get('toughness', '')
                        p_t = f" {power}/{toughness}" if power != '' else ""
                        print(f"      - {name}{tapped}{sick}{p_t}")

        if stack:
            print(f"  Stack: {len(stack)} items")

        print("="*60 + "\n")

    def _start_ping(self):
        """Start periodic ping loop."""
        def ping_loop():
            while self.running:
                time.sleep(PING_INTERVAL)
                if self.running:
                    self.seq_num += 1
                    pdu = {
                        "type": "PING",
                        "seq_num": self.seq_num,
                        "timestamp": int(time.time() * 1000)
                    }
                    self.send_pdu(pdu)

        thread = threading.Thread(target=ping_loop)
        thread.daemon = True
        thread.start()

    # ========================================================================
    # Public API Methods
    # ========================================================================

    def pass_priority(self, seq_num: int = None):
        """Send PRIORITY_PASS."""
        if seq_num is None:
            seq_num = self._last_priority_seq
        pdu = {
            "type": "PRIORITY_PASS",
            "seq_num": seq_num
        }
        self.send_pdu(pdu)

    def send_player_ready(self, player_id: str, deck_list: List[str]):
        """Send PLAYER_READY PDU."""
        self.player_id = player_id
        self.seq_num += 1
        pdu = {
            "type": "PLAYER_READY",
            "seq_num": self.seq_num,
            "player_id": player_id,
            "deck_list": deck_list
        }
        self.send_pdu(pdu)

    def send_mulligan_choice(self, keep: bool, cards_to_bottom: List[str] = None, seq_num: int = None):
        """Send MULLIGAN_CHOICE PDU."""
        if seq_num is None:
            seq_num = self._last_priority_seq or self.seq_num
        pdu = {
            "type": "MULLIGAN_CHOICE",
            "seq_num": seq_num,
            "keep": keep,
            "cards_to_bottom": cards_to_bottom or []
        }
        self.send_pdu(pdu)

    def send_cast_spell(self, card_id: str, targets: List[str], mana_payment: Dict, seq_num: int = None):
        """Send CAST_SPELL PDU."""
        if seq_num is None:
            seq_num = self._last_priority_seq
        pdu = {
            "type": "CAST_SPELL",
            "seq_num": seq_num,
            "card_id": card_id,
            "targets": targets,
            "mana_payment": mana_payment
        }
        self.send_pdu(pdu)

    def send_play_land(self, card_id: str, seq_num: int = None):
        """Send PLAY_LAND PDU."""
        if seq_num is None:
            seq_num = self._last_priority_seq
        pdu = {
            "type": "PLAY_LAND",
            "seq_num": seq_num,
            "card_id": card_id
        }
        self.send_pdu(pdu)

    def send_declare_attackers(self, attackers: List[Dict], seq_num: int = None):
        """Send DECLARE_ATTACKERS PDU."""
        if seq_num is None:
            seq_num = self._last_priority_seq
        pdu = {
            "type": "DECLARE_ATTACKERS",
            "seq_num": seq_num,
            "attackers": attackers
        }
        self.send_pdu(pdu)

    def send_declare_blockers(self, blockers: List[Dict], seq_num: int = None):
        """Send DECLARE_BLOCKERS PDU."""
        if seq_num is None:
            seq_num = self._last_priority_seq
        pdu = {
            "type": "DECLARE_BLOCKERS",
            "seq_num": seq_num,
            "blockers": blockers
        }
        self.send_pdu(pdu)

    def send_concede(self):
        """Send CONCEDE PDU."""
        self.seq_num += 1
        pdu = {
            "type": "CONCEDE",
            "seq_num": self.seq_num,
            "player_id": self.player_id
        }
        self.send_pdu(pdu)

    def close(self):
        """Close the client."""
        self.running = False
        if self.socket:
            self.socket.close()
        self.log("Client closed")