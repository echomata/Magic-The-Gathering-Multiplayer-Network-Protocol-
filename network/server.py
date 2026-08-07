"""MTGNP Server implementation."""
import socket
import threading
import json
from typing import Dict, Optional

from core.constants import DEFAULT_PORT
from game.game import Game
from network.network import send_pdu, decode_message


class MTGNPServer:
    """MTGNP Server handling connections and routing PDUs."""
    
    def __init__(self, port: int = DEFAULT_PORT, verbose: bool = False):
        self.port = port
        self.verbose = verbose
        self.socket = None
        self.game = Game(self, verbose)
        self.running = True

    def log(self, msg: str):
        if self.verbose:
            print(f"[SERVER] {msg}")

    def send_pdu(self, conn, pdu: Dict):
        """Send a PDU to a client."""
        send_pdu(conn, pdu, self.verbose)

    def send_error(self, conn, code: str, message: str, rejected_action: Dict = None):
        """Send an ERROR PDU."""
        pdu = {
            "type": "ERROR",
            "seq_num": self.game.next_seq(),
            "code": code,
            "message": message
        }
        if rejected_action:
            pdu["rejected_action"] = rejected_action
        self.send_pdu(conn, pdu)

    def start(self):
        """Start the server."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('0.0.0.0', self.port))
        self.socket.listen(5)

        self.log(f"Server listening on port {self.port}")
        print(f"\nMTGNP Server running on port {self.port}")
        print("Waiting for players...\n")

        try:
            while self.running:
                conn, addr = self.socket.accept()
                self.log(f"New connection from {addr}")

                if len(self.game.player_conns) >= 2:
                    self.log("Refusing connection - game full")
                    conn.close()
                    continue

                thread = threading.Thread(target=self._handle_client, args=(conn, addr))
                thread.daemon = True
                thread.start()

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.shutdown()

    def _handle_client(self, conn, addr):
        """Handle a single client connection."""
        buffer = b''

        try:
            while self.running:
                data = conn.recv(4096)
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
                        self._route_pdu(conn, pdu)
                    except json.JSONDecodeError as e:
                        self.log(f"Invalid JSON: {e}")
                        self.send_error(conn, "INVALID_JSON", f"Invalid JSON: {e}")

        except Exception as e:
            self.log(f"Client {addr} error: {e}")
        finally:
            self._handle_client_disconnect(conn)
            conn.close()

    def _route_pdu(self, conn, pdu: Dict):
        """Route a PDU to the appropriate handler."""
        if self.verbose:
            print(f"[SERVER <- {conn.getpeername()}] {json.dumps(pdu, indent=2)}")

        pdu_type = pdu.get('type')

        handlers = {
            'PLAYER_READY': self.game.lifecycle_manager.handle_player_ready,
            'MULLIGAN_CHOICE': self.game.lifecycle_manager.handle_mulligan_choice,
            'PRIORITY_PASS': self.game.priority_manager.handle_priority_pass,
            'CAST_SPELL': self.game.action_handler.handle_cast_spell,
            'PLAY_LAND': self.game.action_handler.handle_play_land,
            'DECLARE_ATTACKERS': self.game.action_handler.handle_declare_attackers,
            'DECLARE_BLOCKERS': self.game.action_handler.handle_declare_blockers,
            'ASSIGN_DAMAGE_ORDER': self.game.action_handler.handle_assign_damage_order,
            'ACTIVATE_ABILITY': self.game.action_handler.handle_activate_ability,
            'DISCARD': self.game.action_handler.handle_discard,
            'TRIGGER_ORDER_RESPONSE': self.game.trigger_manager.handle_trigger_order,
            'TRIGGER_CHOICE_RESPONSE': self.game.trigger_manager.handle_trigger_choice,
            'CONCEDE': lambda c, p: self._handle_concede(c, p),
            'PING': lambda c, p: self._handle_ping(c, p),
        }

        handler = handlers.get(pdu_type)
        if handler:
            handler(conn, pdu)
        else:
            self.send_error(conn, "UNKNOWN_TYPE", f"Unknown PDU type: {pdu_type}", pdu)

    def _handle_concede(self, conn, pdu: Dict):
        """Handle CONCEDE PDU."""
        player_id = self.game.get_player_by_conn(conn)
        if not player_id:
            self.send_error(conn, "ILLEGAL_ACTION", "Unknown player", pdu)
            return

        winner_id = self.game.get_other_player(player_id)
        if winner_id:
            self.game.lifecycle_manager.end_game(winner_id, "CONCEDE")

    def _handle_ping(self, conn, pdu: Dict):
        """Handle PING PDU."""
        pong_pdu = {
            "type": "PONG",
            "seq_num": pdu.get('seq_num', 0),
            "timestamp": pdu.get('timestamp', 0)
        }
        self.send_pdu(conn, pong_pdu)

    def _handle_client_disconnect(self, conn):
        """Handle client disconnection."""
        player_id = self.game.get_player_by_conn(conn)
        if player_id:
            self.game.lifecycle_manager.handle_disconnect(player_id)

        if conn in self.game.player_conns:
            self.game.player_conns.remove(conn)

    def shutdown(self):
        """Shutdown the server."""
        self.running = False
        if self.socket:
            self.socket.close()
        self.log("Server shutdown")