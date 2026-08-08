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
        # True while we're waiting on an "implicit request" action (e.g.
        # DECLARE_ATTACKERS) rather than a genuine priority window. Per the
        # RFC, no PRIORITY_GRANT PDU is defined for those steps - the
        # PHASE_TRANSITION itself is the signal, and the client echoes ITS
        # seq_num. See expect_action().
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
        """Record that we're waiting for an implicit-request action PDU
        (DECLARE_ATTACKERS, DECLARE_BLOCKERS, or ASSIGN_DAMAGE_ORDER)
        WITHOUT sending a PRIORITY_GRANT PDU, per RFC sections 9.3/9.4/9.5:
        "This transition implicitly signals ... no separate request PDU is
        defined." The client is expected to echo the seq_num of the
        PHASE_TRANSITION PDU that announced the step (passed in here).
        """
        self.implicit_mode = True
        self.priority_holder = player_id
        self.priority_seq = seq_num
        self.passed_players = set()

        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(60.0, self._timeout_callback, args=[player_id, seq_num])
        self._timer.start()

    def regrant_priority(self, player_id: str):
        """Re-prompt a player with the SAME seq_num after an error.

        For a genuine priority window this re-sends PRIORITY_GRANT (per RFC
        section 11). For an implicit-request step (implicit_mode), no PDU
        is defined for re-prompting, so we rely on the ERROR PDU itself
        (which already carries the rejected action) and simply keep waiting
        - the client can just retry with the same seq_num.
        """
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
            
            # 2. Creatures with toughness <= 0 or damage >= toughness die
            creatures_to_destroy = []
            for pid, data in self.game.players.items():
                for perm in data.get('battlefield', []):
                    from game.card_catalog import is_creature, get_card
                    card = get_card(perm.card_id)
                    if card and is_creature(card):
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

        card = get_card(item.card_id)
        if card:
            # Permanents (creatures, artifacts, enchantments, lands) always
            # enter the battlefield when their spell resolves, even if they
            # also define a top-level "effect" (that field describes a
            # later ACTIVATED ability, e.g. tapping for mana - it is not
            # what happens on cast). Checking is_permanent() first fixes
            # mana dorks (Llanowar Elves, Elvish Mystic) and Sol Ring, which
            # were previously resolving as one-shot effects and never
            # actually joining the battlefield.
            if is_permanent(card):
                from core.models import Permanent
                # Per RFC 10.2.2: "Each permanent id matches its card
                # instance id from the original deck_list." Use the card's
                # own instance ID (e.g. "goblin_guide_001") as the
                # permanent's battlefield ID - NOT a freshly generated one -
                # so that DECLARE_ATTACKERS/DECLARE_BLOCKERS/
                # ACTIVATE_ABILITY/etc. (which all reference permanents by
                # this ID, per every RFC example) can actually find it.
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
                    'kicked': False
                })
            else:
                effect = card.get('effect')
                if effect:
                    result = execute_card_effect(self.game, item.card_id, item.controller, item.targets)
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