"""Complete card effect implementations for MTGNP."""
from typing import Dict, List, Optional, Any
from game.card_catalog import get_card, is_creature, is_land, is_permanent, is_artifact, is_enchantment
from core.models import Permanent


class CardEffect:
    """Base class for card effects."""
    
    def __init__(self, game, card_id: str, controller: str, targets: List[str] = None, ability: str = None, kicked: bool = False, ability_params: Dict = None):
        self.game = game
        self.card_id = card_id
        self.controller = controller
        self.targets = targets or []
        self.card = get_card(card_id)
        self.effect_name = self.card.get('effect') if self.card else None
        self.effect_value = self.card.get('effect_value') if self.card else None
        self.ability = ability
        self.kicked = kicked
        self.ability_params = ability_params or {}

    def execute(self) -> Dict:
        """Execute the card effect. Returns state changes."""
        if not self.card:
            return {'error': 'Unknown card'}
        
        effect_handlers = {
            'deal_damage': self._handle_deal_damage,
            'deal_damage_to_creature': self._handle_deal_damage_to_creature,
            'deal_damage_no_prevent': self._handle_deal_damage_no_prevent,
            'deal_damage_no_regen': self._handle_deal_damage_no_regen,
            'counter': self._handle_counter,
            'counter_noncreature': self._handle_counter_noncreature,
            'mana_leak': self._handle_mana_leak,
            'return_to_hand': self._handle_return_to_hand,
            'ponder': self._handle_ponder,
            'giant_growth': self._handle_giant_growth,
            'rampant_growth': self._handle_rampant_growth,
            'naturalize': self._handle_naturalize,
            'vines_of_vastwood': self._handle_vines_of_vastwood,
            'swords_to_plowshares': self._handle_swords_to_plowshares,
            'path_to_exile': self._handle_path_to_exile,
            'healing_salve': self._handle_healing_salve,
            'pacifism': self._handle_pacifism,
            'dark_ritual': self._handle_dark_ritual,
            'terror': self._handle_terror,
            'doom_blade': self._handle_doom_blade,
            'raise_dead': self._handle_raise_dead,
            'mind_rot': self._handle_mind_rot,
            'gray_merchant': self._handle_gray_merchant,
            'mana': self._handle_mana,
            'ping': self._handle_ping,
            'ping_artifact': self._handle_ping_artifact,
            'loot': self._handle_loot,
            'mill': self._handle_mill,
            'assassinate': self._handle_assassinate,
            'protection_giver': self._handle_protection_giver,
            'regenerate': self._handle_regenerate,
        }
        
        handler = effect_handlers.get(self.ability or self.effect_name)
        if handler:
            return handler()
        
        return {'error': f'Unknown effect: {self.effect_name}'}

    def _handle_deal_damage(self) -> Dict:
        """Deal damage to any target."""
        changes = []
        for target in self.targets:
            if target.startswith('player_'):
                player = self.game.get_player_data(target)
                if player:
                    damage = self.effect_value or 3
                    player['life'] -= damage
                    changes.append({
                        'type': 'DAMAGE',
                        'target': target,
                        'amount': damage
                    })
            else:
                perm = self.game.find_permanent(target)
                if perm:
                    damage = self.effect_value or 3
                    perm.damage += damage
                    if perm.damage >= perm.get_toughness():
                        self.game.remove_permanent(target)
                        changes.append({
                            'type': 'DESTROY',
                            'target': target
                        })
                    changes.append({
                        'type': 'DAMAGE',
                        'target': target,
                        'amount': damage
                    })
        return {'state_changes': changes}

    def _handle_deal_damage_to_creature(self) -> Dict:
        """Deal damage only to creatures."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and is_creature(perm.card_data):
                damage = self.effect_value or 4
                perm.damage += damage
                if perm.damage >= perm.get_toughness():
                    self.game.remove_permanent(target)
                    changes.append({
                        'type': 'DESTROY',
                        'target': target
                    })
                changes.append({
                    'type': 'DAMAGE',
                    'target': target,
                    'amount': damage
                })
        return {'state_changes': changes}

    def _handle_deal_damage_no_prevent(self) -> Dict:
        """Deal damage that can't be prevented."""
        changes = self._handle_deal_damage().get('state_changes', [])
        # Add cannot prevent flag
        for change in changes:
            change['cannot_prevent'] = True
        # Also prevent life gain for the turn
        for pid in self.game.players:
            self.game.players[pid]['_cannot_gain_life'] = True
        return {'state_changes': changes}

    def _handle_deal_damage_no_regen(self) -> Dict:
        """Deal damage that can't be regenerated."""
        changes = self._handle_deal_damage().get('state_changes', [])
        for change in changes:
            if change.get('type') == 'DAMAGE':
                change['no_regeneration'] = True
        return {'state_changes': changes}

    def _handle_counter(self) -> Dict:
        """Counter target spell."""
        changes = []
        for target in self.targets:
            for i, item in enumerate(self.game.stack):
                if item.stack_item_id == target:
                    self.game.stack.pop(i)
                    changes.append({
                        'type': 'COUNTER',
                        'target': target
                    })
                    break
        return {'state_changes': changes}

    def _handle_counter_noncreature(self) -> Dict:
        """Counter target noncreature spell."""
        changes = []
        for target in self.targets:
            for i, item in enumerate(self.game.stack):
                if item.stack_item_id == target:
                    card = get_card(item.card_id)
                    if card and not is_creature(card):
                        self.game.stack.pop(i)
                        changes.append({
                            'type': 'COUNTER',
                            'target': target
                        })
                    break
        return {'state_changes': changes}

    def _handle_mana_leak(self) -> Dict:
        """Counter target spell unless controller pays {3}."""
        changes = []
        for target in self.targets:
            for item in self.game.stack:
                if item.stack_item_id == target:
                    controller = item.controller
                    # Check if controller has floating mana to pay
                    floating = self.game.floating_mana.get(controller, {})
                    total_mana = sum(floating.values())
                    if total_mana < 3:
                        self.game.stack.remove(item)
                        changes.append({
                            'type': 'COUNTER',
                            'target': target
                        })
                    break
        return {'state_changes': changes}

    def _handle_return_to_hand(self) -> Dict:
        """Return target creature to its owner's hand."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and is_creature(perm.card_data):
                owner = perm.controller
                self.game.players[owner]['hand'].append(perm.card_id)
                self.game.remove_permanent(target)
                changes.append({
                    'type': 'RETURN_TO_HAND',
                    'target': target,
                    'owner': owner
                })
        return {'state_changes': changes}

    def _handle_ponder(self) -> Dict:
        """Look at top 3 cards, arrange, draw."""
        changes = []
        player = self.game.get_player_data(self.controller)
        library = player['library']
        
        # Look at top 3
        top_cards = library[-3:] if len(library) >= 3 else library[:]
        changes.append({
            'type': 'PONDER',
            'player': self.controller,
            'top_cards': top_cards
        })
        
        # In simplified version, just draw one
        if library:
            drawn = library.pop()
            player['hand'].append(drawn)
            changes.append({
                'type': 'DRAW',
                'player': self.controller,
                'card': drawn
            })
        return {'state_changes': changes}

    def _handle_giant_growth(self) -> Dict:
        """Target creature gets +3/+3 until end of turn."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm:
                perm._temporary_bonus['power'] = perm._temporary_bonus.get('power', 0) + 3
                perm._temporary_bonus['toughness'] = perm._temporary_bonus.get('toughness', 0) + 3
                changes.append({
                    'type': 'PUMP',
                    'target': target,
                    'power': 3,
                    'toughness': 3,
                    'until_end_turn': True
                })
        return {'state_changes': changes}

    def _handle_rampant_growth(self) -> Dict:
        """Search library for a basic land and put it onto battlefield tapped."""
        changes = []
        player = self.game.get_player_data(self.controller)
        library = player['library']
        
        for i, card_id in enumerate(library):
            card = get_card(card_id)
            if card and is_land(card):
                library.pop(i)
                # Per RFC 10.2.2, a permanent's id is its own card instance id.
                perm = Permanent(card_id, self.controller, card_id)
                perm.tapped = True
                player['battlefield'].append(perm)
                changes.append({
                    'type': 'SEARCH',
                    'player': self.controller,
                    'card': card_id,
                    'tapped': True
                })
                break
        return {'state_changes': changes}

    def _handle_naturalize(self) -> Dict:
        """Destroy target artifact or enchantment."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm:
                card = get_card(perm.card_id)
                if card and (is_artifact(card) or is_enchantment(card)):
                    self.game.remove_permanent(target)
                    changes.append({
                        'type': 'DESTROY',
                        'target': target
                    })
        return {'state_changes': changes}

    def _handle_vines_of_vastwood(self) -> Dict:
        """Give hexproof and optionally +4/+4."""
        changes = []
        kicked = self.kicked
        
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm:
                perm._hexproof = True
                changes.append({
                    'type': 'PROTECT',
                    'target': target
                })
                if kicked:
                    perm._temporary_bonus['power'] = perm._temporary_bonus.get('power', 0) + 4
                    perm._temporary_bonus['toughness'] = perm._temporary_bonus.get('toughness', 0) + 4
                    changes.append({
                        'type': 'PUMP',
                        'target': target,
                        'power': 4,
                        'toughness': 4,
                        'until_end_turn': True
                    })
        return {'state_changes': changes}

    def _handle_swords_to_plowshares(self) -> Dict:
        """Exile target creature, controller gains life equal to power."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and is_creature(perm.card_data):
                power = perm.get_power()
                controller = perm.controller
                self.game.players[controller]['life'] += power
                self.game.remove_permanent(target, to_exile=True)
                changes.append({
                    'type': 'EXILE',
                    'target': target,
                    'life_gain': power,
                    'controller': controller
                })
        return {'state_changes': changes}

    def _handle_path_to_exile(self) -> Dict:
        """Exile target creature, controller may search for a basic land."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and is_creature(perm.card_data):
                controller = perm.controller
                self.game.remove_permanent(target, to_exile=True)
                
                player = self.game.get_player_data(controller)
                library = player['library']
                for i, card_id in enumerate(library):
                    card = get_card(card_id)
                    if card and is_land(card):
                        library.pop(i)
                        land_perm = Permanent(card_id, controller, card_id)
                        land_perm.tapped = True
                        player['battlefield'].append(land_perm)
                        changes.append({
                            'type': 'SEARCH',
                            'player': controller,
                            'card': card_id,
                            'tapped': True
                        })
                        break
                
                changes.append({
                    'type': 'EXILE',
                    'target': target
                })
        return {'state_changes': changes}

    def _handle_healing_salve(self) -> Dict:
        """Target player gains 3 life OR prevent next 3 damage."""
        changes = []
        if self.targets:
            target = self.targets[0]
            if target.startswith('player_'):
                self.game.players[target]['life'] += self.effect_value or 3
                changes.append({
                    'type': 'LIFE_GAIN',
                    'target': target,
                    'amount': self.effect_value or 3
                })
            else:
                changes.append({
                    'type': 'PREVENT_DAMAGE',
                    'target': target,
                    'amount': self.effect_value or 3
                })
        return {'state_changes': changes}

    def _handle_pacifism(self) -> Dict:
        """Enchanted creature can't attack or block."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and is_creature(perm.card_data):
                perm._pacified = True
                changes.append({
                    'type': 'PACIFISM',
                    'target': target
                })
        return {'state_changes': changes}

    def _handle_dark_ritual(self) -> Dict:
        """Add BBB mana."""
        if not hasattr(self.game, 'floating_mana'):
            self.game.floating_mana = {}
        self.game.floating_mana[self.controller] = self.game.floating_mana.get(self.controller, {})
        self.game.floating_mana[self.controller]['B'] = self.game.floating_mana[self.controller].get('B', 0) + 3
        return {
            'state_changes': [{
                'type': 'MANA_ADD',
                'player': self.controller,
                'mana': {'B': 3}
            }]
        }

    def _handle_terror(self) -> Dict:
        """Destroy target nonartifact, nonblack creature."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and is_creature(perm.card_data):
                card = get_card(perm.card_id)
                if card and card.get('color') != 'B' and not is_artifact(card):
                    self.game.remove_permanent(target)
                    changes.append({
                        'type': 'DESTROY',
                        'target': target
                    })
        return {'state_changes': changes}

    def _handle_doom_blade(self) -> Dict:
        """Destroy target nonblack creature."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and is_creature(perm.card_data):
                card = get_card(perm.card_id)
                if card and card.get('color') != 'B':
                    self.game.remove_permanent(target)
                    changes.append({
                        'type': 'DESTROY',
                        'target': target
                    })
        return {'state_changes': changes}

    def _handle_raise_dead(self) -> Dict:
        """Return target creature card from graveyard to hand."""
        changes = []
        for target in self.targets:
            for pid, player in self.game.players.items():
                if target in player['graveyard']:
                    player['graveyard'].remove(target)
                    player['hand'].append(target)
                    changes.append({
                        'type': 'RETURN_TO_HAND',
                        'target': target,
                        'player': pid
                    })
                    break
        return {'state_changes': changes}

    def _handle_mind_rot(self) -> Dict:
        """Target player discards two cards."""
        changes = []
        for target in self.targets:
            if target.startswith('player_'):
                player = self.game.get_player_data(target)
                if player:
                    hand = player['hand']
                    discards = []
                    for _ in range(min(2, len(hand))):
                        if hand:
                            discarded = hand.pop()
                            player['graveyard'].append(discarded)
                            discards.append(discarded)
                    if discards:
                        changes.append({
                            'type': 'DISCARD',
                            'player': target,
                            'cards': discards
                        })
        return {'state_changes': changes}

    def _handle_gray_merchant(self) -> Dict:
        """Each opponent loses X life, you gain X life."""
        changes = []
        devotion = 0
        player = self.game.get_player_data(self.controller)
        for perm in player.get('battlefield', []):
            card = get_card(perm.card_id)
            if card and card.get('color') == 'B':
                devotion += card.get('cmc', 0)
        
        for pid in self.game.players:
            if pid != self.controller:
                self.game.players[pid]['life'] -= devotion
                changes.append({
                    'type': 'LIFE_LOSS',
                    'target': pid,
                    'amount': devotion
                })
        
        self.game.players[self.controller]['life'] += devotion
        changes.append({
            'type': 'LIFE_GAIN',
            'target': self.controller,
            'amount': devotion
        })
        
        return {'state_changes': changes}

    def _handle_mana(self) -> Dict:
        """Add mana."""
        mana = self.effect_value
        if not hasattr(self.game, 'floating_mana'):
            self.game.floating_mana = {}
        self.game.floating_mana[self.controller] = self.game.floating_mana.get(self.controller, {})
        for color in mana:
            self.game.floating_mana[self.controller][color] = self.game.floating_mana[self.controller].get(color, 0) + 1
        return {
            'state_changes': [{
                'type': 'MANA_ADD',
                'player': self.controller,
                'mana': {color: 1 for color in mana}
            }]
        }

    def _handle_ping(self) -> Dict:
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm:
                perm.damage += 1
                changes.append({'type': 'DAMAGE', 'target': target, 'amount': 1})
                if perm.damage >= perm.get_toughness():
                    self.game.remove_permanent(target)
                    changes.append({'type': 'DESTROY', 'target': target})
            elif target in self.game.players:
                self.game.players[target]['life'] -= 1
                changes.append({'type': 'DAMAGE', 'target': target, 'amount': 1})
        return {'state_changes': changes}

    def _handle_ping_artifact(self) -> Dict:
        return self._handle_ping()

    def _handle_loot(self) -> Dict:
        player = self.game.get_player_data(self.controller)
        changes = []
        if player['library']:
            drawn = player['library'].pop()
            player['hand'].append(drawn)
            changes.append({'type': 'DRAW', 'player': self.controller, 'card': drawn})
        if player['hand']:
            discarded = player['hand'].pop()
            player['graveyard'].append(discarded)
            changes.append({'type': 'DISCARD', 'player': self.controller, 'cards': [discarded]})
        return {'state_changes': changes}

    def _handle_mill(self) -> Dict:
        changes = []
        for target in self.targets:
            player = self.game.get_player_data(target)
            if player:
                cards = []
                for _ in range(2):
                    if not player['library']:
                        break
                    card = player['library'].pop()
                    player['graveyard'].append(card)
                    cards.append(card)
                changes.append({'type': 'MILL', 'target': target, 'cards': cards})
        return {'state_changes': changes}

    def _handle_assassinate(self) -> Dict:
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and perm.tapped:
                self.game.remove_permanent(target)
                changes.append({'type': 'DESTROY', 'target': target})
        return {'state_changes': changes}

    def _handle_protection_giver(self) -> Dict:
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and perm.controller == self.controller:
                perm._temporary_protection_color = self.ability_params.get('chosen_color')
                changes.append({'type': 'PROTECT', 'target': target})
        return {'state_changes': changes}

    def _handle_regenerate(self) -> Dict:
        perm = self.game.find_permanent(self.targets[0]) if self.targets else None
        if not perm:
            return {'error': 'Invalid regeneration target'}
        perm._regeneration_shield += 1
        return {'state_changes': [{'type': 'REGENERATION_SHIELD', 'target': perm.id}]}


def execute_card_effect(game, card_id: str, controller: str, targets: List[str] = None, ability: str = None, kicked: bool = False, ability_params: Dict = None) -> Dict:
    """Execute a card effect."""
    effect = CardEffect(game, card_id, controller, targets, ability=ability, kicked=kicked, ability_params=ability_params)
    return effect.execute()
