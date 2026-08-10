"""Priority and stack management."""
import threading
from typing import Dict, Set
from core.models import StackItem
from game.card_effects import execute_card_effect
from game.card_catalog import is_permanent, get_card


class PriorityManager:
    """Manages priority and the stack."""
    
    def __init__(self, game):
        self.game = game
        self.priority_holder = None
        self.priority_seq = None
        self.passed_players = set()
        self._timer = None
        self.implicit_mode = False

    def _timeout_callback(self, player_id: str, seq_num: int):
        """Called when a player fails to respond in time."""
        if self.priority_holder == player_id and self.priority_seq == seq_num:
            self.game.log(f"Priority timeout for player {player_id}")
            self.game.lifecycle_manager.end_game(
                self.game.get_other_player(player_id), "DISCONNECT"
            )

    def grant_priority(self, player_id: str, keep_passes: bool = False):
        """Grant priority to a player."""
        self.implicit_mode = False
        self.priority_holder = player_id
        self.priority_seq = self.game.next_seq()
        if not keep_passes:
            self.passed_players = set()

        pdu = {
            "type": "PRIORITY_GRANT",
            "player_id": player_id,
            "seq_num": self.priority_seq,
            "time_limit_ms": 60000
        }
        self.game.send_to_player(player_id, pdu)
        
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(60.0, self._timeout_callback, args=[player_id, self.priority_seq])
        self._timer.start()

    def expect_action(self, player_id: str, seq_num: int):
        self.implicit_mode = True
        self.priority_holder = player_id
        self.priority_seq = seq_num
        self.passed_players = set()

        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(60.0, self._timeout_callback, args=[player_id, seq_num])
        self._timer.start()

    def regrant_priority(self, player_id: str):
        if self.priority_holder != player_id:
            return

        if self.implicit_mode:
            return

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
        else:
            other_player = self.game.get_other_player(player_id)
            self.grant_priority(other_player, keep_passes=True)

    def _is_target_legal(self, target: str) -> bool:
        if target.startswith("player_"):
            return target in self.game.players
        elif target.startswith("stk_"):
            return any(item.stack_item_id == target for item in self.game.stack)
        else:
            return self.game.find_permanent(target) is not None

    def check_state_based_actions(self):
        """Check and apply state-based actions until none remain."""
        actions_taken = True
        while actions_taken:
            actions_taken = False
            # 1. Players with 0 or less life lose
            dead_players = []
            for pid, data in list(self.game.players.items()):
                if data.get('life', 20) <= 0:
                    dead_players.append(pid)
                    
            if dead_players:
                if len(dead_players) == 2:
                    # Both players reach zero life simultaneously, AP loses
                    nap = self.game.get_other_player(self.game.active_player)
                    self.game.lifecycle_manager.end_game(nap, "LIFE_ZERO")
                else:
                    self.game.lifecycle_manager.end_game(
                        self.game.get_other_player(dead_players[0]), "LIFE_ZERO"
                    )
                return

            # Drawing from an empty library is a game-loss condition. Card
            # effects mark the attempted draw during resolution, then this
            # SBA pass applies the authoritative GAME_OVER result.
            empty_draw_players = [
                pid for pid, data in self.game.players.items()
                if data.get('empty_draw_attempted', False)
            ]
            if empty_draw_players:
                loser = empty_draw_players[0]
                self.game.lifecycle_manager.end_game(
                    self.game.get_other_player(loser), "DECK_EMPTY"
                )
                return
            
            # 2. Creatures with toughness <= 0 or damage >= toughness die
            creatures_to_destroy = []
            for pid, data in self.game.players.items():
                for perm in data.get('battlefield', []):
                    from game.card_catalog import is_creature, get_card
                    card = get_card(perm.card_id)
                    if card and is_creature(card):
                        if (perm.get_toughness() > 0 and perm.damage >= perm.get_toughness()) and perm._regeneration_shield:
                            perm._regeneration_shield -= 1
                            perm.damage = 0
                            perm.tapped = True
                            self.game.combat_system.remove_from_combat(perm.id)
                            actions_taken = True
                            continue
                        if perm.get_toughness() <= 0 or perm.damage >= perm.get_toughness():
                            creatures_to_destroy.append(perm.id)
            
            for perm_id in creatures_to_destroy:
                if self.game.remove_permanent(perm_id):
                    actions_taken = True

    def resolve_stack(self):
        """Resolve the top item on the stack."""
        if not self.game.stack:
            self.game.turn_engine.advance_step()
            return

        item = self.game.stack.pop()
        
        # FIZZLE CHECK
        if item.targets:
            legal_targets = [t for t in item.targets if self._is_target_legal(t)]
            if not legal_targets:
                self.game.log(f"Stack item {item.stack_item_id} fizzled (no legal targets)")
                pdu = {
                    "type": "STACK_RESOLVE",
                    "seq_num": self.game.next_seq(),
                    "stack_item_id": item.stack_item_id,
                    "result": "FIZZLE",
                    "state_changes": []
                }
                self.game.broadcast(pdu)
                self.check_state_based_actions()
                self.open_priority_window()
                return

        self.game.log(f"Resolving stack item: {item.card_id}")
        state_changes = []

        if item.item_type == "ABILITY":
            from game.card_effects import execute_card_effect
            result = execute_card_effect(self.game, item.card_id, item.controller, item.targets, ability=item.ability, kicked=item.kicked, ability_params=item.ability_params)
            if result.get('error'):
                self.game.log(f"Effect error: {result['error']}")
            if result.get('state_changes'):
                state_changes.extend(result['state_changes'])
        elif item.item_type == "TRIGGER_ABILITY":
            trigger = item.trigger_data
            result = self.game.trigger_manager.resolve_trigger(trigger)
            if result.get('state_changes'):
                state_changes.extend(result['state_changes'])
        else:
            card = get_card(item.card_id)
            if card:
                if is_permanent(card):
                    from core.models import Permanent
                    perm = Permanent(
                        item.card_id,
                        item.controller,
                        item.card_id,
                        self.game.turn
                    )
                    self.game.players[item.controller]['battlefield'].append(perm)
                    state_changes.append({
                        "type": "PERMANENT_ENTERS",
                        "card_id": item.card_id,
                        "controller": item.controller
                    })
                    self.game.trigger_manager.check_triggers('ETB', {
                        'permanent': perm,
                        'kicked': item.kicked
                    })
                else:
                    effect = card.get('effect')
                    if effect:
                        from game.card_effects import execute_card_effect
                        result = execute_card_effect(self.game, item.card_id, item.controller, item.targets, kicked=item.kicked)
                        if result.get('error'):
                            self.game.log(f"Effect error: {result['error']}")
        
                        if result.get('state_changes'):
                            state_changes.extend(result['state_changes'])
                            for change in result['state_changes']:
                                if change.get('type') == 'DESTROY' or change.get('type') == 'DAMAGE':
                                    self.game.trigger_manager.check_triggers('SPELL_RESOLVED', {
                                        'effect': effect,
                                        'targets': item.targets
                                    })

        for change in state_changes:
            if 'type' in change:
                change['change_type'] = change.pop('type')

        pdu = {
            "type": "STACK_RESOLVE",
            "seq_num": self.game.next_seq(),
            "stack_item_id": item.stack_item_id,
            "result": "RESOLVED",
            "state_changes": state_changes
        }
        self.game.broadcast(pdu)

        self.check_state_based_actions()

        if self.game.state == "IN_GAME":  # Ensure game didn't end from SBA
            if not self.game.trigger_manager.is_waiting():
                self.game.broadcast_game_state()
                self.open_priority_window()

    def reset(self):
        """Reset priority state."""
        self.priority_holder = None
        self.priority_seq = None
        self.passed_players = set()
        if self._timer:
            self._timer.cancel()
            self._timer = None
