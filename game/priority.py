"""Priority and stack management."""
from typing import Dict, Set
from models import StackItem
from card_effects import execute_card_effect
from utils import generate_permanent_id, generate_stack_id
from card_catalog import is_permanent, get_card


class PriorityManager:
    """Manages priority and the stack."""
    
    def __init__(self, game):
        self.game = game
        self.priority_holder = None
        self.priority_seq = None
        self.passed_players = set()

    def grant_priority(self, player_id: str):
        """Grant priority to a player."""
        self.priority_holder = player_id
        self.priority_seq = self.game.next_seq()
        self.passed_players = set()

        pdu = {
            "type": "PRIORITY_GRANT",
            "player_id": player_id,
            "seq_num": self.priority_seq,
            "time_limit_ms": 60000
        }
        self.game.send_to_player(player_id, pdu)

    def open_priority_window(self):
        """Open a priority window for the current phase."""
        if self.game.state != "IN_GAME":
            return

        self.game.log(f"Opening priority window in {self.game.phase}")
        self.grant_priority(self.game.active_player)

    def handle_priority_pass(self, conn, pdu: Dict):
        """Handle PRIORITY_PASS PDU."""
        player_id = self.game.get_player_by_conn(conn)
        if not player_id:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Unknown player", pdu)
            return

        if player_id != self.priority_holder:
            self.game.send_error(conn, "NOT_YOUR_PRIORITY", "You don't have priority", pdu)
            return

        if pdu.get('seq_num') != self.priority_seq:
            self.game.send_error(conn, "STALE_ACTION", "Stale priority", pdu)
            return

        self.passed_players.add(player_id)
        self.game.log(f"Player {player_id} passed priority")

        if len(self.passed_players) >= len(self.game.players):
            if self.game.stack:
                self.resolve_stack()
            else:
                self.game.turn_engine.advance_step()

    def resolve_stack(self):
        """Resolve the top item on the stack."""
        if not self.game.stack:
            self.game.turn_engine.advance_step()
            return

        item = self.game.stack.pop()
        self.game.log(f"Resolving stack item: {item.card_id}")

        card = get_card(item.card_id)
        if card:
            effect = card.get('effect')
            if effect:
                result = execute_card_effect(self.game, item.card_id, item.controller, item.targets)
                if result.get('error'):
                    self.game.log(f"Effect error: {result['error']}")

                if result.get('state_changes'):
                    for change in result['state_changes']:
                        if change.get('type') == 'DESTROY' or change.get('type') == 'DAMAGE':
                            self.game.trigger_manager.check_triggers('SPELL_RESOLVED', {
                                'effect': effect,
                                'targets': item.targets
                            })
            else:
                if is_permanent(card):
                    from models import Permanent
                    perm = Permanent(
                        item.card_id,
                        item.controller,
                        generate_permanent_id(),
                        self.game.turn
                    )
                    self.game.players[item.controller]['battlefield'].append(perm)
                    self.game.trigger_manager.check_triggers('ETB', {
                        'permanent': perm,
                        'kicked': False
                    })

        pdu = {
            "type": "STACK_RESOLVE",
            "seq_num": self.game.next_seq(),
            "stack_item_id": item.stack_item_id,
            "result": "RESOLVED",
            "state_changes": []
        }
        self.game.broadcast(pdu)

        for pid, data in self.game.players.items():
            if data.get('life', 20) <= 0:
                self.game.lifecycle_manager.end_game(
                    self.game.get_other_player(pid), "LIFE_ZERO"
                )
                return

        self.game.broadcast_game_state()
        self.open_priority_window()

    def reset(self):
        """Reset priority state."""
        self.priority_holder = None
        self.priority_seq = None
        self.passed_players = set()