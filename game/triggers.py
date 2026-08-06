"""Triggered ability handling for MTGNP."""
from typing import Dict, List, Optional, Any
from game.card_catalog import get_card, is_creature
from core.models import StackItem


class TriggerManager:
    """Manages triggered abilities."""
    
    def __init__(self, game):
        self.game = game
        self.pending_triggers = []
        self.waiting_for_order = None
        self.waiting_for_choice = None

    def check_triggers(self, event_type: str, event_data: Dict):
        """Check for triggered abilities from a game event."""
        triggers = []
        
        # Check all permanents on battlefield
        for pid, player in self.game.players.items():
            for perm in player.get('battlefield', []):
                card = get_card(perm.card_id)
                if card:
                    trigger = self._get_trigger(card, event_type, event_data, perm)
                    if trigger:
                        triggers.append({
                            'trigger_id': f"trg_{id(trigger)}",
                            'card_id': perm.card_id,
                            'permanent_id': perm.id,
                            'controller': pid,
                            'trigger': trigger,
                            'event': event_type
                        })
        
        if triggers:
            self._process_triggers(triggers)

    def _get_trigger(self, card: Dict, event_type: str, event_data: Dict, perm) -> Optional[Dict]:
        """Check if a card has a trigger for this event."""
        abilities = card.get('abilities', [])
        
        # Enter the battlefield triggers
        if event_type == 'ETB':
            if 'enters_battlefield' in abilities:
                if card.get('effect') == 'gray_merchant':
                    return {
                        'type': 'ETB',
                        'effect': 'gray_merchant',
                        'effect_value': None
                    }
            if 'gravedigger_trigger' in abilities:
                return {
                    'type': 'ETB',
                    'effect': 'return_creature_from_graveyard',
                    'effect_value': None,
                    'optional': True
                }
            if 'bushwhacker_trigger' in abilities:
                # Check if kicked
                if event_data.get('kicked', False):
                    return {
                        'type': 'ETB',
                        'effect': 'bushwhacker_boost',
                        'effect_value': None
                    }
        
        # Attack triggers
        if event_type == 'ATTACK' and 'goblin_guide_trigger' in abilities:
            return {
                'type': 'ATTACK',
                'effect': 'goblin_guide_trigger',
                'effect_value': None
            }
        
        return None

    def _process_triggers(self, triggers: List[Dict]):
        """Process triggered abilities."""
        ap = self.game.active_player
        ap_triggers = [t for t in triggers if t['controller'] == ap]
        nap_triggers = [t for t in triggers if t['controller'] != ap]
        
        # AP triggers go on stack first (resolve last)
        # NAP triggers go on top (resolve first)
        ordered_triggers = ap_triggers + nap_triggers
        
        # If multiple triggers from same player, ask for order
        if len(ap_triggers) > 1:
            self._request_trigger_order(ap, ap_triggers)
            return
        if len(nap_triggers) > 1:
            self._request_trigger_order(nap_triggers[0]['controller'], nap_triggers)
            return
        
        # Put triggers on stack
        for trigger in ordered_triggers:
            self._put_trigger_on_stack(trigger)

    def _request_trigger_order(self, player_id: str, triggers: List[Dict]):
        """Request trigger ordering from player."""
        trigger_ids = [t['trigger_id'] for t in triggers]
        self.waiting_for_order = {
            'player': player_id,
            'triggers': triggers,
            'trigger_ids': trigger_ids
        }
        
        pdu = {
            'type': 'TRIGGER_ORDER',
            'seq_num': self.game.next_seq(),
            'player_id': player_id,
            'trigger_ids': trigger_ids
        }
        self.game.send_to_player(player_id, pdu)

    def handle_trigger_order(self, conn, pdu: Dict):
        """Handle TRIGGER_ORDER_RESPONSE."""
        if not self.waiting_for_order:
            return
        
        player_id = self.game.get_player_by_conn(conn)
        if player_id != self.waiting_for_order['player']:
            return
        
        ordered_ids = pdu.get('ordered_trigger_ids', [])
        triggers = self.waiting_for_order['triggers']
        
        if set(ordered_ids) != set(self.waiting_for_order['trigger_ids']):
            self.game.send_error(conn, 'TRIGGER_ORDER_INVALID', 'Invalid trigger order', pdu)
            return
        
        ordered_triggers = []
        for trigger_id in ordered_ids:
            for t in triggers:
                if t['trigger_id'] == trigger_id:
                    ordered_triggers.append(t)
                    break
        
        for trigger in reversed(ordered_triggers):
            self._put_trigger_on_stack(trigger)
        
        self.waiting_for_order = None

    def _put_trigger_on_stack(self, trigger: Dict):
        """Put a triggered ability on the stack."""
        if trigger.get('trigger', {}).get('optional', False):
            self._request_trigger_choice(trigger)
            return
        
        item = StackItem(trigger['card_id'], trigger['controller'])
        item.item_type = 'TRIGGER_ABILITY'
        item.trigger_data = trigger
        
        self.game.stack.append(item)
        
        pdu = {
            'type': 'STACK_PUSH',
            'seq_num': self.game.next_seq(),
            **item.to_pdu()
        }
        self.game.broadcast(pdu)

    def _request_trigger_choice(self, trigger: Dict):
        """Request optional trigger choice from player."""
        self.waiting_for_choice = {
            'player': trigger['controller'],
            'trigger': trigger
        }
        
        pdu = {
            'type': 'TRIGGER_CHOICE',
            'seq_num': self.game.next_seq(),
            'trigger_id': trigger['trigger_id'],
            'source_id': trigger['permanent_id'],
            'effect_summary': f"Optional trigger: {trigger['card_id']}",
            'requires_target': True if trigger['trigger'].get('effect') == 'return_creature_from_graveyard' else False,
            'legal_targets': self._get_legal_trigger_targets(trigger)
        }
        self.game.send_to_player(trigger['controller'], pdu)

    def _get_legal_trigger_targets(self, trigger: Dict) -> List[str]:
        """Get legal targets for a trigger."""
        if trigger['trigger'].get('effect') == 'return_creature_from_graveyard':
            # Target creature cards in graveyard
            targets = []
            for pid, player in self.game.players.items():
                for card_id in player['graveyard']:
                    card = get_card(card_id)
                    if card and is_creature(card):
                        targets.append(card_id)
            return targets
        return []

    def handle_trigger_choice(self, conn, pdu: Dict):
        """Handle TRIGGER_CHOICE_RESPONSE."""
        if not self.waiting_for_choice:
            return
        
        player_id = self.game.get_player_by_conn(conn)
        if player_id != self.waiting_for_choice['player']:
            return
        
        accept = pdu.get('accept', False)
        trigger = self.waiting_for_choice['trigger']
        
        if accept:
            # For return from graveyard, need target
            if trigger['trigger'].get('effect') == 'return_creature_from_graveyard':
                chosen_target = pdu.get('chosen_target')
                if chosen_target:
                    # Return card from graveyard to hand
                    for pid, player in self.game.players.items():
                        if chosen_target in player['graveyard']:
                            player['graveyard'].remove(chosen_target)
                            player['hand'].append(chosen_target)
                            break
            self._put_trigger_on_stack(trigger)
        else:
            self.game.log(f"Trigger {trigger['trigger_id']} declined")
        
        self.waiting_for_choice = None