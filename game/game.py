"""Main game class orchestrating all game components."""
from game.state import GameState
from game.turn import TurnEngine
from game.combat import CombatSystem
from game.priority import PriorityManager
from game.actions import ActionHandler
from game.lifecycle import LifecycleManager
from triggers import TriggerManager


class Game:
    """Main game class orchestrating all game components."""
    
    def __init__(self, server, verbose: bool = False):
        self.server = server
        self.verbose = verbose
        
        # Initialize components
        self.state = "LOBBY"
        self.phase = None
        self.players = {}
        self.player_conns = []
        self.turn = 0
        self.active_player = None
        self.stack = []
        self.seq_num = 0
        self.land_played_this_turn = False
        self.floating_mana = {}
        
        # Game sub-systems
        self.state_manager = GameState(self)
        self.turn_engine = TurnEngine(self)
        self.combat_system = CombatSystem(self)
        self.priority_manager = PriorityManager(self)
        self.action_handler = ActionHandler(self)
        self.lifecycle_manager = LifecycleManager(self)
        self.trigger_manager = TriggerManager(self)
        
        # Reference shortcuts
        self.game_logger = None

    def next_seq(self) -> int:
        """Increment and return the next sequence number."""
        self.seq_num += 1
        return self.seq_num

    def get_player_by_conn(self, conn):
        """Get player ID by connection."""
        return self.state_manager.get_player_by_conn(conn)

    def get_other_player(self, player_id: str):
        """Get the other player ID."""
        return self.state_manager.get_other_player(player_id)

    def get_player_data(self, player_id: str):
        """Get player data dictionary."""
        return self.state_manager.get_player_data(player_id)

    def find_permanent(self, perm_id: str):
        """Find a permanent by ID."""
        return self.state_manager.find_permanent(perm_id)

    def remove_permanent(self, perm_id: str):
        """Remove a permanent from the game."""
        return self.state_manager.remove_permanent(perm_id)

    def log(self, msg: str):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[SERVER] {msg}")
        if self.game_logger:
            self.game_logger.log_event('LOG', {'message': msg})

    def broadcast(self, pdu: Dict):
        """Send PDU to all connected players."""
        for conn in self.player_conns:
            self.server.send_pdu(conn, pdu)
        if self.game_logger:
            self.game_logger.log_pdu('BROADCAST', pdu)

    def send_to_player(self, player_id: str, pdu: Dict):
        """Send PDU to a specific player."""
        if player_id in self.players:
            self.server.send_pdu(self.players[player_id]['conn'], pdu)
            if self.game_logger:
                self.game_logger.log_pdu(f'SEND_TO_{player_id}', pdu)

    def send_error(self, conn, code: str, message: str, rejected_action: Dict = None):
        """Send an ERROR PDU."""
        self.server.send_error(conn, code, message, rejected_action)

    def build_game_state(self, player_id: str) -> Dict:
        """Build a personalized GAME_STATE_UPDATE for a player."""
        return self.state_manager.build_state_dict(player_id)

    def send_game_state(self, player_id: str) -> int:
        """Send personalized GAME_STATE_UPDATE to a player."""
        state = self.build_game_state(player_id)
        pdu = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": self.next_seq(),
            "state": state
        }
        self.send_to_player(player_id, pdu)
        return pdu['seq_num']

    def broadcast_game_state(self):
        """Send personalized GAME_STATE_UPDATE to all players."""
        for pid in self.players:
            self.send_game_state(pid)

    def broadcast_phase_transition(self, from_phase: str, to_phase: str) -> int:
        """Broadcast a PHASE_TRANSITION PDU."""
        pdu = {
            "type": "PHASE_TRANSITION",
            "seq_num": self.next_seq(),
            "from_phase": from_phase,
            "to_phase": to_phase,
            "active_player": self.active_player,
            "turn": self.turn
        }
        self.broadcast(pdu)
        return pdu['seq_num']