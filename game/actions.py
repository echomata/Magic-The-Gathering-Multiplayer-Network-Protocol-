"""Player action handlers."""
from typing import Dict
from core.models import Permanent, StackItem
from game.card_catalog import (
    get_card, is_land, is_permanent, can_play_during_phase,
    is_creature, is_instant, is_artifact, is_enchantment
)
from core.utils import check_mana


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

    def _validate_spell_targets(self, card: Dict, targets: list, player_id: str) -> str:
        """Validate target count and card-specific target restrictions."""
        if not isinstance(targets, list):
            return "targets must be an array"

        effect = card.get('effect')
        base_id = card.get('base_id', '')
        # Permanents/creatures with no spell effect do not target anything.
        # Only effects that explicitly require a target should be subject to
        # the one-target validation below.
        needs_target = effect not in {None, 'ponder', 'dark_ritual', 'gray_merchant', 'mana'}
        if needs_target and len(targets) != 1:
            return "This spell requires exactly one target"
        if not needs_target and targets:
            return "This spell does not accept targets"
        if not targets:
            return None

        target = targets[0]
        perm = self.game.find_permanent(target)
        target_player = target in self.game.players
        target_card = perm.card_data if perm else None

        player_only = base_id in {'lava_spike', 'mind_rot'}
        creature_only = base_id in {
            'flame_slash', 'unsummon', 'giant_growth', 'vines_of_vastwood',
            'swords_to_plowshares', 'path_to_exile', 'terror', 'doom_blade',
            'pacifism'
        }
        stack_only = base_id in {'counterspell', 'cancel', 'negate', 'mana_leak'}
        graveyard_card = base_id in {'raise_dead'}
        artifact_or_enchantment = base_id in {'naturalize'}

        if stack_only:
            if not target.startswith('stk_') or not any(i.stack_item_id == target for i in self.game.stack):
                return "Target is not a spell on the stack"
            if base_id == 'negate':
                item = next(i for i in self.game.stack if i.stack_item_id == target)
                target_card = get_card(item.card_id)
                if is_creature(target_card):
                    return "Negate cannot target creature spells"
            return None
        if graveyard_card:
            if not any(target in p.get('graveyard', []) for p in self.game.players.values()):
                return "Target is not a creature card in a graveyard"
            target_card = get_card(target)
            if not target_card or not is_creature(target_card):
                return "Target is not a creature card"
            return None
        if player_only and not target_player:
            return "This spell can only target a player"
        if creature_only and (not perm or not is_creature(target_card)):
            return "This spell must target a creature"
        if perm and perm.controller != player_id:
            if getattr(perm, '_hexproof', False) or 'hexproof' in perm.card_data.get('abilities', []):
                return "Target has hexproof"
        if perm and perm.has_protection_from(card.get('color', '')) and perm.controller != player_id:
            return "Target has protection from this spell's color"
        if artifact_or_enchantment and (not perm or not (is_artifact(target_card) or is_enchantment(target_card))):
            return "This spell must target an artifact or enchantment"
        if effect in {'deal_damage', 'deal_damage_no_prevent', 'deal_damage_no_regen'} and not (target_player or perm):
            return "Invalid damage target"
        if effect == 'healing_salve' and not (target_player or perm):
            return "Invalid Healing Salve target"
        if effect == 'mind_rot' and not target_player:
            return "Mind Rot must target a player"
        return None

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
        if not isinstance(card_id, str):
            self.game.send_error(conn, "ILLEGAL_ACTION", "card_id must be a string", pdu)
            return
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

        # Sorcery-speed restriction: sorceries, creatures, enchantments, and
        # artifacts may only be cast by the active player, during a main
        # phase, with an empty stack (RFC Figure 4: "sorcery speed for AP").
        # Instants are exempt and may be cast by either player, any time
        # they hold priority.
        if not is_instant(card):
            if player_id != self.game.active_player:
                self.game.send_error(conn, "WRONG_PHASE",
                                   "Only the active player may cast at sorcery speed", pdu)
                return
            if self.game.stack:
                self.game.send_error(conn, "WRONG_PHASE",
                                   "Cannot cast at sorcery speed while the stack is not empty", pdu)
                return

        targets = pdu.get('targets', [])
        if not isinstance(targets, list):
            self.game.send_error(conn, "ILLEGAL_TARGET", "targets must be an array", pdu)
            return
        target_error = self._validate_spell_targets(card, targets, player_id)
        if target_error:
            self.game.send_error(conn, "ILLEGAL_TARGET", target_error, pdu)
            return

        kicked = bool(pdu.get('kicked', False))
        kicker_payment = pdu.get('kicker_payment', {})
        if kicked:
            if not isinstance(kicker_payment, dict):
                self.game.send_error(conn, "ILLEGAL_ACTION", "kicker_payment must be an object", pdu)
                return
            if 'kicker_1R' in card.get('abilities', []):
                kicker_cost = {'R': 1, 'X': 1}
            elif 'kicker_G' in card.get('abilities', []):
                kicker_cost = {'G': 1}
            else:
                self.game.send_error(conn, "ILLEGAL_ACTION", "This card has no kicker", pdu)
                return
            if not check_mana(kicker_payment, kicker_cost):
                self.game.send_error(conn, "INSUFFICIENT_MANA", "Kicker payment is insufficient", pdu)
                return
        elif kicker_payment:
            self.game.send_error(conn, "ILLEGAL_ACTION", "kicker_payment requires kicked=true", pdu)
            return

        mana_payment = pdu.get('mana_payment', {})
        if not isinstance(mana_payment, dict):
            self.game.send_error(conn, "ILLEGAL_ACTION", "mana_payment must be an object", pdu)
            return
        mana_cost = card.get('mana_cost', {})
        if not check_mana(mana_payment, mana_cost):
            self.game.send_error(conn, "INSUFFICIENT_MANA", "Not enough mana", pdu)
            return
            
        total_payment = dict(mana_payment)
        if kicked:
            for color, amount in kicker_payment.items():
                total_payment[color] = total_payment.get(color, 0) + amount

        if not self._pay_mana(player_id, total_payment):
            self.game.send_error(conn, "INSUFFICIENT_MANA", "Cannot pay mana with available sources", pdu)
            return

        self.game.players[player_id]['hand'].remove(card_id)

        # All spells, including permanents, go on the stack

        
        stack_item = StackItem(card_id, player_id, pdu.get('targets', []), kicked=kicked)
        self.game.stack.append(stack_item)

        # Triggers are checked after the spell is on the stack so triggered
        # abilities are placed above it and resolve first.
        self.game.trigger_manager.check_triggers('SPELL_CAST', {
            'spell': card_id,
            'controller': player_id
        })
        for t in targets:
            if self.game.find_permanent(t):
                self.game.trigger_manager.check_triggers('TARGETED', {
                    'target': t,
                    'source': card_id
                })

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

        if player_id != self.game.priority_manager.priority_holder:
            self.game.send_error(conn, "NOT_YOUR_PRIORITY", "You don't have priority", pdu)
            return

        if pdu.get('seq_num') != self.game.priority_manager.priority_seq:
            self.game.send_error(conn, "STALE_ACTION", "Stale priority", pdu)
            return

        if player_id != self.game.active_player:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Only the active player can play lands", pdu)
            return

        if self.game.land_played_this_turn:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Already played a land this turn", pdu)
            return

        if self.game.phase not in ["PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"]:
            self.game.send_error(conn, "WRONG_PHASE", "Can only play lands in Main Phase", pdu)
            return

        if self.game.stack:
            self.game.send_error(conn, "WRONG_PHASE",
                               "Cannot play a land while the stack is not empty", pdu)
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
        # Per RFC 10.2.2, a permanent's id is its own card instance id.
        perm = Permanent(card_id, player_id, card_id)
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

            if any(a.get('creature_id') == creature_id for a in self.game.combat_system.attackers):
                self.game.send_error(conn, "ILLEGAL_ACTION", "Creature declared more than once", pdu)
                return

            if not perm.can_attack():
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Creature {creature_id} can't attack", pdu)
                return

            if target not in self.game.players:
                self.game.send_error(conn, "ILLEGAL_TARGET", f"Invalid target: {target}", pdu)
                return

            if not perm.has_vigilance():
                perm.tapped = True
            self.game.combat_system.attackers.append({"creature_id": creature_id, "target": target})

        self.game.log(f"Player {player_id} declared {len(self.game.combat_system.attackers)} attackers")
        self.game.broadcast_game_state()

        if not self.game.combat_system.attackers:
            self.game.turn_engine.do_end_of_combat()
        else:
            for attack in self.game.combat_system.attackers:
                self.game.trigger_manager.check_triggers('ATTACK', {
                    'attacker': attack.get('creature_id'),
                    'target': attack.get('target')
                })
            
            if not self.game.trigger_manager.is_waiting():
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
        used_blockers = set()
        for block in pdu.get('blockers', []):
            creature_id = block.get('creature_id')
            blocking_id = block.get('blocking_id')

            perm = self.game.find_permanent(creature_id)
            if not perm or perm.controller != player_id:
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Invalid creature: {creature_id}", pdu)
                return

            if creature_id in used_blockers:
                self.game.send_error(conn, "ILLEGAL_ACTION", "A creature can block only once", pdu)
                return
            used_blockers.add(creature_id)

            if not perm.can_block():
                self.game.send_error(conn, "ILLEGAL_ACTION", f"Creature {creature_id} can't block", pdu)
                return

            attacker_perm = self.game.find_permanent(blocking_id)
            if attacker_perm and attacker_perm.has_flying() and not perm.has_flying():
                self.game.send_error(conn, "ILLEGAL_ACTION", "Only flying creatures can block a flyer", pdu)
                return
            if attacker_perm and attacker_perm.has_protection_from(perm.card_data.get('color', '')):
                self.game.send_error(conn, "ILLEGAL_ACTION", "Creature cannot block because of protection", pdu)
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

        if not isinstance(ability_index, int) or ability_index < 0 or ability_index >= len(abilities):
            self.game.send_error(conn, "ILLEGAL_ACTION", "Invalid ability index", pdu)
            return

        ability = abilities[ability_index]
        allowed_abilities = {
            'loot', 'ping', 'ping_artifact', 'mill', 'assassinate',
            'protection_giver', 'regenerate'
        }
        if not ability.startswith('mana_') and ability not in allowed_abilities:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Ability is not activated by this PDU", pdu)
            return
        
        cost_payment = pdu.get('cost_payment', {})
        if not isinstance(cost_payment, dict):
            self.game.send_error(conn, "ILLEGAL_ACTION", "cost_payment must be an object", pdu)
            return
        mana_payment = cost_payment.get('mana', {})
        targets = pdu.get('targets', [])
        if not isinstance(mana_payment, dict):
            self.game.send_error(conn, "ILLEGAL_ACTION", "cost_payment.mana must be an object", pdu)
            return
        if not isinstance(targets, list):
            self.game.send_error(conn, "ILLEGAL_TARGET", "targets must be an array", pdu)
            return

        required_tap = ability.startswith('mana_') or ability in {
            'loot', 'ping', 'ping_artifact', 'assassinate',
            'protection_giver', 'mill'
        }
        required_mana = {
            'mill': {'X': 2},
            'ping_artifact': {'X': 3},
            'regenerate': {'G': 1, 'X': 1},
        }.get(ability, {})
        if bool(cost_payment.get('tap', False)) != required_tap:
            self.game.send_error(conn, "ILLEGAL_ACTION", "Incorrect tap cost for activated ability", pdu)
            return
        if not check_mana(mana_payment, required_mana):
            self.game.send_error(conn, "INSUFFICIENT_MANA", "Activated ability cost is insufficient", pdu)
            return
        if not isinstance(mana_payment, dict):
            self.game.send_error(conn, "ILLEGAL_ACTION", "cost_payment.mana must be an object", pdu)
            return
        if not isinstance(targets, list):
            self.game.send_error(conn, "ILLEGAL_TARGET", "targets must be an array", pdu)
            return
        if ability in {'ping', 'ping_artifact', 'assassinate', 'mill', 'protection_giver', 'regenerate'} and len(targets) != 1:
            self.game.send_error(conn, "ILLEGAL_TARGET", "This ability requires exactly one target", pdu)
            return
        if ability == 'loot' and targets:
            self.game.send_error(conn, "ILLEGAL_TARGET", "This ability has no targets", pdu)
            return
        if ability == 'mill' and targets[0] not in self.game.players:
            self.game.send_error(conn, "ILLEGAL_TARGET", "Mill must target a player", pdu)
            return
        if ability in {'ping', 'ping_artifact'}:
            target_perm = self.game.find_permanent(targets[0])
            if targets[0] not in self.game.players and not target_perm:
                self.game.send_error(conn, "ILLEGAL_TARGET", "Invalid ping target", pdu)
                return

        if ability == 'assassinate':
            target_perm = self.game.find_permanent(targets[0])
            if not target_perm or not target_perm.tapped or not is_creature(target_perm.card_data):
                self.game.send_error(conn, "ILLEGAL_TARGET", "Assassinate must target a tapped creature", pdu)
                return
        if ability == 'protection_giver':
            target_perm = self.game.find_permanent(targets[0])
            if not target_perm or target_perm.controller != player_id or not is_creature(target_perm.card_data):
                self.game.send_error(conn, "ILLEGAL_TARGET", "Protection must target your creature", pdu)
                return
            if pdu.get('chosen_color') not in {'W', 'U', 'B', 'R', 'G'}:
                self.game.send_error(conn, "ILLEGAL_ACTION", "chosen_color must be W, U, B, R, or G", pdu)
                return
        if ability == 'regenerate':
            target_perm = self.game.find_permanent(targets[0])
            if target_perm is not perm:
                self.game.send_error(conn, "ILLEGAL_TARGET", "Regenerate must target its source", pdu)
                return
                
        if targets:
            target_perm = self.game.find_permanent(targets[0])
            if target_perm and target_perm.controller != player_id:
                if target_perm.has_hexproof():
                    self.game.send_error(conn, "ILLEGAL_TARGET", "Target has hexproof", pdu)
                    return
                source_color = perm.card_data.get('color', '') if perm.card_data else ''
                if target_perm.has_protection_from(source_color):
                    self.game.send_error(conn, "ILLEGAL_TARGET", "Target has protection from this source's color", pdu)
                    return

        requires_tap = cost_payment.get('tap', False)
        
        if ability.startswith('mana_'):
            requires_tap = True
            
        if requires_tap:
            if perm.tapped:
                self.game.send_error(conn, "ILLEGAL_ACTION", "Permanent is already tapped", pdu)
                return
            if perm.summoning_sick and is_creature(perm.card_data) and not perm.has_haste():
                self.game.send_error(conn, "ILLEGAL_ACTION", "Creature has summoning sickness", pdu)
                return
        if mana_payment:
            if not self._pay_mana(player_id, mana_payment):
                self.game.send_error(conn, "INSUFFICIENT_MANA", "Cannot pay mana with available sources", pdu)
                return

        if requires_tap:
            perm.tapped = True

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
        
        stack_item = StackItem(perm.card_id, player_id, targets)
        stack_item.item_type = "ABILITY"
        stack_item.source_id = source_id
        stack_item.ability = ability
        if ability == 'protection_giver':
            stack_item.ability_params = {'chosen_color': pdu.get('chosen_color')}
        self.game.stack.append(stack_item)

        pdu2 = {
            "type": "STACK_PUSH",
            "seq_num": self.game.next_seq(),
            **stack_item.to_pdu()
        }
        self.game.broadcast(pdu2)
        
        self.game.priority_manager.grant_priority(player_id)
