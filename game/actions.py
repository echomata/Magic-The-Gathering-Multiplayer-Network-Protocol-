"""Player action handlers."""
from typing import Dict
from core.models import Permanent, StackItem
from game.card_catalog import (
    get_card, is_land, is_permanent, can_play_during_phase,
    is_creature
)
from core.utils import generate_permanent_id, check_mana


class ActionHandler:
    """Handles player actions."""
    
    def __init__(self, game):
        self.game = game
        self.waiting_for_discard = None

    def _pay_mana(self, player_id: str, mana_payment: Dict) -> bool:
        """Verify and tap lands for mana payment, or use floating mana. Return True if successful."""
        floating = dict(self.game.floating_mana.get(player_id, {}))
        lands_to_tap = []
        
        # Try to satisfy the payment
        for color, amount in mana_payment.items():
            if amount <= 0:
                continue
                
            needed = amount
            
            # First use floating mana if any
            if color in floating and floating[color] >= needed:
                floating[color] -= needed
                needed = 0
            elif color in floating and floating[color] > 0:
                needed -= floating[color]
                floating[color] = 0
                
            if needed == 0:
                continue
                
            # Find untapped lands that produce this color
            if color != 'X':
                for perm in self.game.players[player_id].get('battlefield', []):
                    if not perm.tapped and perm.id not in lands_to_tap:
                        card = get_card(perm.card_id)
                        if card and 'mana_' + color in card.get('abilities', []):
                            lands_to_tap.append(perm.id)
                            needed -= 1
                            if needed == 0:
                                break
                if needed > 0:
                    return False
            else:
                for perm in self.game.players[player_id].get('battlefield', []):
                    if not perm.tapped and perm.id not in lands_to_tap:
                        card = get_card(perm.card_id)
                        has_mana_ability = any(ab.startswith('mana_') for ab in card.get('abilities', []))
                        if has_mana_ability:
                            lands_to_tap.append(perm.id)
                            needed -= 1
                            if needed == 0:
                                break
                if needed > 0:
                    return False
                    
        # Apply the tap
        for perm_id in lands_to_tap:
            perm = self.game.find_permanent(perm_id)
            if perm:
                perm.tapped = True
                
        # Update floating mana
        self.game.floating_mana[player_id] = floating
        return True

    def handle_discard(self, conn, pdu: Dict):
        """Handle DISCARD PDU."""
        if self.game.state != "IN_GAME" or self.game.phase != "CLEANUP":
            self.game.send_error(conn, "WRONG_PHASE", "Can only discard in Cleanup step", pdu)
            return

        player_id = self.game.get_player_by_conn(conn)
        if not player_id or player_id != self.waiting_for_discard:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Not your turn to discard", pdu)
            return

        if 'seq_num' not in pdu:
            self.game.send_error(conn, "STALE_ACTION", "Missing seq_num", pdu)
            return

        card_ids = pdu.get('card_ids', [])
        hand = self.game.players[player_id]['hand']
        
        if len(hand) - len(card_ids) > 7:
            self.game.send_error(conn, "ILLEGAL_ACTION", f"Must discard down to 7 cards. Discarding {len(card_ids)} is not enough.", pdu)
            return

        # Verify all cards are in hand
        for card_id in card_ids:
            if card_id not in hand:
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Card {card_id} not in hand", pdu)
                return

        # Execute discard
        for card_id in card_ids:
            hand.remove(card_id)
            self.game.players[player_id]['graveyard'].append(card_id)

        self.game.log(f"Player {player_id} discarded {len(card_ids)} cards")
        self.waiting_for_discard = None
        
        # Cleanup continues
        for pid, pdata in self.game.players.items():
            for perm in pdata.get('battlefield', []):
                perm.damage = 0
                perm._temporary_bonus = {'power': 0, 'toughness': 0}

        self.game.broadcast_game_state()
        self.game.turn_engine.end_turn()

    def handle_cast_spell(self, conn, pdu: Dict):
        """Handle CAST_SPELL PDU."""
        if self.game.state != "IN_GAME":
            self.game.send_error(conn, "WRONG_PHASE", "Cannot cast spells now", pdu)
            return

        player_id = self.game.get_player_by_conn(conn)
        if not player_id:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Unknown player", pdu)
            return

        if player_id != self.game.priority_manager.priority_holder:
            self.game.send_error(conn, "NOT_YOUR_PRIORITY", "You don't have priority", pdu)
            return

        if pdu.get('seq_num') != self.game.priority_manager.priority_seq:
            self.game.send_error(conn, "STALE_ACTION", "Stale priority", pdu)
            return

        card_id = pdu.get('card_id')
        card = get_card(card_id)
        if not card:
            self.game.send_error(conn, "ILLEGAL_ACTION", f"Unknown card: {card_id}", pdu)
            return

        if card_id not in self.game.players[player_id]['hand']:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Card not in hand", pdu)
            return

        if not can_play_during_phase(card, self.game.phase):
            self.game.send_error(conn, "WRONG_PHASE", f"Cannot play {card.get('type')} during {self.game.phase}", pdu)
            return

        mana_payment = pdu.get('mana_payment', {})
        mana_cost = card.get('mana_cost', {})
        if not check_mana(mana_payment, mana_cost):
            self.game.send_error(conn, "INSUFFICIENT_MANA", "Not enough mana", pdu)
            return
            
        if not self._pay_mana(player_id, mana_payment):
            self.game.send_error(conn, "INSUFFICIENT_MANA", "Cannot pay mana with available sources", pdu)
            return

        self.game.players[player_id]['hand'].remove(card_id)

        # All spells, including permanents, go on the stack

        stack_item = StackItem(card_id, player_id, pdu.get('targets', []))
        self.game.stack.append(stack_item)

        self.game.log(f"Player {player_id} cast {card_id}")

        pdu2 = {
            "type": "STACK_PUSH",
            "seq_num": self.game.next_seq(),
            **stack_item.to_pdu()
        }
        self.game.broadcast(pdu2)

        self.game.priority_manager.grant_priority(player_id)

    def handle_play_land(self, conn, pdu: Dict):
        """Handle PLAY_LAND PDU."""
        if self.game.state != "IN_GAME":
            self.game.send_error(conn, "WRONG_PHASE", "Cannot play land now", pdu)
            return

        player_id = self.game.get_player_by_conn(conn)
        if not player_id:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Unknown player", pdu)
            return

        if self.game.land_played_this_turn:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Already played a land this turn", pdu)
            return

        if self.game.phase not in ["PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"]:
            self.game.send_error(conn, "WRONG_PHASE", "Can only play lands in Main Phase", pdu)
            return

        card_id = pdu.get('card_id')
        card = get_card(card_id)
        if not card or not is_land(card):
            self.game.send_error(conn, "ILLEGAL_ACTION", f"Not a land: {card_id}", pdu)
            return

        if card_id not in self.game.players[player_id]['hand']:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Card not in hand", pdu)
            return

        self.game.players[player_id]['hand'].remove(card_id)
        perm = Permanent(card_id, player_id, generate_permanent_id())
        self.game.players[player_id]['battlefield'].append(perm)
        self.game.land_played_this_turn = True

        self.game.log(f"Player {player_id} played land {card_id}")

        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def handle_declare_attackers(self, conn, pdu: Dict):
        """Handle DECLARE_ATTACKERS PDU."""
        if self.game.state != "IN_GAME" or self.game.phase != "DECLARE_ATTACKERS":
            self.game.send_error(conn, "WRONG_PHASE", "Not in Declare Attackers step", pdu)
            return

        player_id = self.game.get_player_by_conn(conn)
        if not player_id or player_id != self.game.active_player:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Only active player can declare attackers", pdu)
            return

        if pdu.get('seq_num') != self.game.priority_manager.priority_seq:
            self.game.send_error(conn, "STALE_ACTION", "Stale priority", pdu)
            return

        self.game.combat_system.attackers = []
        for attack in pdu.get('attackers', []):
            creature_id = attack.get('creature_id')
            target = attack.get('target')

            perm = self.game.find_permanent(creature_id)
            if not perm or perm.controller != player_id:
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Invalid creature: {creature_id}", pdu)
                return

            if not perm.can_attack():
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Creature {creature_id} can't attack", pdu)
                return

            if target not in self.game.players:
                self.game.send_error(conn, "ILLEGAL_TARGET", f"Invalid target: {target}", pdu)
                return

            perm.tapped = True
            self.game.combat_system.attackers.append({"creature_id": creature_id, "target": target})

        self.game.log(f"Player {player_id} declared {len(self.game.combat_system.attackers)} attackers")
        self.game.broadcast_game_state()

        if not self.game.combat_system.attackers:
            self.game.turn_engine.do_end_of_combat()
        else:
            self.game.priority_manager.open_priority_window()

    def handle_declare_blockers(self, conn, pdu: Dict):
        """Handle DECLARE_BLOCKERS PDU."""
        if self.game.state != "IN_GAME" or self.game.phase != "DECLARE_BLOCKERS":
            self.game.send_error(conn, "WRONG_PHASE", "Not in Declare Blockers step", pdu)
            return

        player_id = self.game.get_player_by_conn(conn)
        nap = self.game.get_other_player(self.game.active_player)
        if not player_id or player_id != nap:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Only non-active player can declare blockers", pdu)
            return

        if pdu.get('seq_num') != self.game.priority_manager.priority_seq:
            self.game.send_error(conn, "STALE_ACTION", "Stale priority", pdu)
            return

        self.game.combat_system.blockers = []
        for block in pdu.get('blockers', []):
            creature_id = block.get('creature_id')
            blocking_id = block.get('blocking_id')

            perm = self.game.find_permanent(creature_id)
            if not perm or perm.controller != player_id:
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Invalid creature: {creature_id}", pdu)
                return

            if not perm.can_block():
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Creature {creature_id} can't block", pdu)
                return

            if not any(a.get('creature_id') == blocking_id for a in self.game.combat_system.attackers):
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Attacker {blocking_id} not found", pdu)
                return

            self.game.combat_system.blockers.append({"creature_id": creature_id, "blocking_id": blocking_id})

        self.game.log(f"Player {player_id} declared {len(self.game.combat_system.blockers)} blockers")
        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def handle_assign_damage_order(self, conn, pdu: Dict):
        """Handle ASSIGN_DAMAGE_ORDER PDU."""
        if self.game.state != "IN_GAME" or self.game.phase != "ASSIGN_DAMAGE_ORDER":
            self.game.send_error(conn, "WRONG_PHASE", "Not in Assign Damage Order step", pdu)
            return

        player_id = self.game.get_player_by_conn(conn)
        if not player_id or player_id != self.game.active_player:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Only active player can assign damage order", pdu)
            return

        if pdu.get('seq_num') != self.game.priority_manager.priority_seq:
            self.game.send_error(conn, "STALE_ACTION", "Stale priority", pdu)
            return

        attacker_id = pdu.get('attacker_id')
        blocker_order = pdu.get('blocker_order', [])

        attacker = self.game.find_permanent(attacker_id)
        if not attacker:
            self.game.send_error(conn, "ILLEGAL_ACTION", f"Unknown attacker: {attacker_id}", pdu)
            return

        blockers = [b for b in self.game.combat_system.blockers if b.get('blocking_id') == attacker_id]
        if len(blockers) <= 1:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Not a multi-blocked attacker", pdu)
            return

        for block_id in blocker_order:
            if not any(b.get('creature_id') == block_id for b in blockers):
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Invalid blocker: {block_id}", pdu)
                return

        self.game.combat_system.damage_order[attacker_id] = blocker_order

        all_ordered = True
        for attack in self.game.combat_system.attackers:
            creature_id = attack.get('creature_id')
            blockers = [b for b in self.game.combat_system.blockers if b.get('blocking_id') == creature_id]
            if len(blockers) > 1 and creature_id not in self.game.combat_system.damage_order:
                all_ordered = False
                break

        if all_ordered:
            self.game.turn_engine.do_first_strike_damage()
        else:
            self.game.priority_manager.open_priority_window()

    def handle_activate_ability(self, conn, pdu: Dict):
        """Handle ACTIVATE_ABILITY PDU."""
        player_id = self.game.get_player_by_conn(conn)
        if not player_id:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Unknown player", pdu)
            return

        if player_id != self.game.priority_manager.priority_holder:
            self.game.send_error(conn, "NOT_YOUR_PRIORITY", "You don't have priority", pdu)
            return

        if pdu.get('seq_num') != self.game.priority_manager.priority_seq:
            self.game.send_error(conn, "STALE_ACTION", "Stale priority", pdu)
            return

        source_id = pdu.get('source_id')
        ability_index = pdu.get('ability_index', 0)

        perm = self.game.find_permanent(source_id)
        if not perm:
            self.game.send_error(conn, "ILLEGAL_ACTION", f"Unknown permanent: {source_id}", pdu)
            return

        if perm.controller != player_id:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Can't activate opponent's permanent", pdu)
            return

        card = perm.card_data
        abilities = card.get('abilities', [])

        if ability_index >= len(abilities):
            self.game.send_error(conn, "ILLEGAL_ACTION", "Invalid ability index", pdu)
            return

        ability = abilities[ability_index]
        
        cost_payment = pdu.get('cost_payment', {})
        
        requires_tap = cost_payment.get('tap', False)
        
        if ability.startswith('mana_'):
            requires_tap = True
            
        if requires_tap:
            if perm.tapped:
                self.game.send_error(conn, "ILLEGAL_ACTION", "Permanent is already tapped", pdu)
                return
            perm.tapped = True
            
        mana_payment = cost_payment.get('mana', {})
        if mana_payment:
            if not self._pay_mana(player_id, mana_payment):
                self.game.send_error(conn, "INSUFFICIENT_MANA", "Cannot pay mana with available sources", pdu)
                return

        if ability.startswith('mana_'):
            mana = ability[5:]
            self.game.floating_mana[player_id] = self.game.floating_mana.get(player_id, {})
            for color in mana:
                self.game.floating_mana[player_id][color] = self.game.floating_mana[player_id].get(color, 0) + 1
            self.game.log(f"{player_id} activated mana ability: add {mana}")
            self.game.broadcast_game_state()
            self.game.priority_manager.open_priority_window()
            return

        self.game.log(f"Activated ability {ability} on {source_id}")
        self.game.broadcast_game_state()