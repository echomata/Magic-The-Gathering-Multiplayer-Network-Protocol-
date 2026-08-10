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
        self.pending_trigger_groups = []

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

        if event_type == 'SPELL_CAST' and 'prowess' in abilities:
            spell = get_card(event_data.get('spell'))
            if spell and spell.get('type') not in {'Creature', 'Artifact Creature'}:
                return {
                    'type': 'SPELL_CAST',
                    'effect': 'prowess',
                    'effect_value': None
                }

        if event_type == 'TARGETED' and 'illusion' in abilities:
            if event_data.get('target') == perm.id:
                return {
                    'type': 'TARGETED',
                    'effect': 'illusion_sacrifice',
                    'effect_value': None
                }
        
        return None

    def _process_triggers(self, triggers: List[Dict]):
        """Process triggered abilities."""
        ap = self.game.active_player
        ap_triggers = [t for t in triggers if t['controller'] == ap]
        nap_triggers = [t for t in triggers if t['controller'] != ap]
        
        # AP triggers are placed first, then NAP triggers. Each controller
        # orders their own simultaneous triggers before the next group.
        self.pending_trigger_groups = [group for group in (ap_triggers, nap_triggers) if group]
        self._continue_trigger_groups()

    def _continue_trigger_groups(self):
        while self.pending_trigger_groups and not self.is_waiting():
            group = self.pending_trigger_groups.pop(0)
            if len(group) > 1:
                self._request_trigger_order(group[0]['controller'], group)
                return
            self._put_trigger_on_stack(group[0])


    def resolve_trigger(self, trigger_data: Dict) -> Dict:
        changes = []
        effect = trigger_data.get('effect')
        
        if effect == 'bushwhacker_boost':
            for perm in self.game.players[trigger_data['controller']]['battlefield']:
                perm._temporary_bonus['power'] = perm._temporary_bonus.get('power', 0) + 1
                if not perm.has_haste():
                    perm.temporary_abilities.add('haste')
        
        elif effect == 'prowess':
            perm_id = trigger_data.get('source', trigger_data.get('permanent_id'))
            perm = self.game.find_permanent(perm_id)
            if perm:
                perm._temporary_bonus['power'] = perm._temporary_bonus.get('power', 0) + 1
                perm._temporary_bonus['toughness'] = perm._temporary_bonus.get('toughness', 0) + 1
                
        elif effect == 'illusion_sacrifice':
            perm_id = trigger_data.get('source', trigger_data.get('permanent_id'))
            if self.game.remove_permanent(perm_id):
                changes.append({'type': 'DESTROY', 'target': perm_id})
                
        elif effect == 'goblin_guide_trigger':
            target_player = self.game.get_other_player(trigger_data['controller'])
            if target_player:
                pdata = self.game.players[target_player]
                if pdata['library']:
                    top_card_id = pdata['library'][-1]
                    changes.append({'type': 'REVEAL', 'player': target_player, 'card': top_card_id})
                    from game.card_catalog import get_card, is_land
                    top_card = get_card(top_card_id)
                    if top_card and is_land(top_card):
                        drawn = pdata['library'].pop()
                        pdata['hand'].append(drawn)
                        changes.append({'type': 'DRAW', 'player': target_player, 'card': drawn})
                        
        elif effect == 'gravedigger_trigger':
            player = self.game.players[trigger_data['controller']]
            chosen = trigger_data.get('trigger', {}).get('chosen_target')
            candidates = [chosen] if chosen else list(player['graveyard'])
            for cid in candidates:
                if cid not in player['graveyard']:
                    continue
                from game.card_catalog import get_card, is_creature
                c = get_card(cid)
                if c and is_creature(c):
                    player['graveyard'].remove(cid)
                    card = cid
                    player['hand'].append(card)
                    changes.append({'type': 'RETURN_TO_HAND', 'player': trigger_data['controller'], 'card': card})
                    break

        elif effect == 'gray_merchant':
            devotion = self.game.state_manager.get_devotion(trigger_data['controller'], 'B')
            if devotion > 0:
                drain_total = 0
                for pid, pdata in self.game.players.items():
                    if pid != trigger_data['controller']:
                        pdata['life'] -= devotion
                        drain_total += devotion
                        changes.append({'type': 'DAMAGE', 'target': pid, 'amount': devotion})
                if drain_total > 0:
                    self.game.players[trigger_data['controller']]['life'] += drain_total
                    changes.append({'type': 'HEAL', 'target': trigger_data['controller'], 'amount': drain_total})

        return {'state_changes': changes}

    def is_waiting(self) -> bool:
        """Check if server is waiting for a trigger decision."""
        return self.waiting_for_order is not None or self.waiting_for_choice is not None

    def _request_trigger_order(self, player_id: str, triggers: List[Dict]):
        """Request trigger ordering from player."""
        trigger_ids = [t['trigger_id'] for t in triggers]
        seq_num = self.game.next_seq()
        self.waiting_for_order = {
            'player': player_id,
            'triggers': triggers,
            'trigger_ids': trigger_ids,
            'seq_num': seq_num
        }
        
        pdu = {
            'type': 'TRIGGER_ORDER',
            'seq_num': seq_num,
            'player_id': player_id,
            'trigger_ids': trigger_ids
        }
        self.game.send_to_player(player_id, pdu)

    def handle_trigger_order(self, conn, pdu: Dict):
        """Handle TRIGGER_ORDER_RESPONSE."""
        if not self.waiting_for_order:
            self.game.send_error(conn, 'TRIGGER_ORDER_INVALID', 'No trigger order is pending', pdu)
            return
        
        player_id = self.game.get_player_by_conn(conn)
        if player_id != self.waiting_for_order['player']:
            self.game.send_error(conn, 'TRIGGER_ORDER_INVALID',
                                 'This player does not control the pending triggers', pdu)
            return
            
        if pdu.get('seq_num') != self.waiting_for_order['seq_num']:
            self.game.send_error(conn, "STALE_ACTION", "Stale seq_num", pdu)
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
        
        if not self.is_waiting():
            self._continue_trigger_groups()
        if not self.is_waiting() and not self.pending_trigger_groups:
            self.game.broadcast_game_state()
            self.game.priority_manager.open_priority_window()

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
        seq_num = self.game.next_seq()
        self.waiting_for_choice = {
            'player': trigger['controller'],
            'trigger': trigger,
            'seq_num': seq_num
        }
        
        pdu = {
            'type': 'TRIGGER_CHOICE',
            'seq_num': seq_num,
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
            self.game.send_error(conn, 'TRIGGER_CHOICE_INVALID', 'No trigger choice is pending', pdu)
            return
        
        player_id = self.game.get_player_by_conn(conn)
        if player_id != self.waiting_for_choice['player']:
            self.game.send_error(conn, 'TRIGGER_CHOICE_INVALID',
                                 'This player does not control the pending trigger', pdu)
            return
            
        if pdu.get('seq_num') != self.waiting_for_choice['seq_num']:
            self.game.send_error(conn, "STALE_ACTION", "Stale seq_num", pdu)
            return
            
        trigger = self.waiting_for_choice['trigger']
        if pdu.get('trigger_id') != trigger['trigger_id']:
            self.game.send_error(conn, "TRIGGER_CHOICE_INVALID", "Invalid trigger_id", pdu)
            return
        
        accept = pdu.get('accept', False)
        requires_target = trigger['trigger'].get('effect') == 'return_creature_from_graveyard'
        
        if accept:
            chosen_target = pdu.get('chosen_target')
            if requires_target and chosen_target not in self._get_legal_trigger_targets(trigger):
                self.game.send_error(conn, 'TRIGGER_CHOICE_INVALID', 'A legal target is required', pdu)
                return
            if not requires_target and chosen_target is not None:
                self.game.send_error(conn, 'TRIGGER_CHOICE_INVALID', 'This trigger does not accept a target', pdu)
                return
            non_optional_trigger = dict(trigger)
            non_optional_trigger['trigger'] = dict(trigger['trigger'])
            non_optional_trigger['trigger']['optional'] = False
            if chosen_target:
                non_optional_trigger['trigger']['chosen_target'] = chosen_target
            self._put_trigger_on_stack(non_optional_trigger)
        else:
            self.game.log(f"Trigger {trigger['trigger_id']} declined")
        
        self.waiting_for_choice = None
        
        if not self.is_waiting():
            self._continue_trigger_groups()
        if not self.is_waiting() and not self.pending_trigger_groups:
            self.game.broadcast_game_state()
            self.game.priority_manager.open_priority_window()
