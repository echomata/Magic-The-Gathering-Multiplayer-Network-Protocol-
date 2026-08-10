import sys

with open('game/card_effects.py', 'r') as f:
    content = f.read()

# Patch _handle_deal_damage
content = content.replace('''
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
''', '''
    def _handle_deal_damage(self, cannot_prevent: bool = False) -> Dict:
        """Deal damage to any target."""
        changes = []
        for target in self.targets:
            if target.startswith('player_'):
                player = self.game.get_player_data(target)
                if player:
                    damage = self.effect_value or 3
                    if not cannot_prevent:
                        prevented = min(damage, player.get('_prevent_next_damage', 0))
                        player['_prevent_next_damage'] = max(0, player.get('_prevent_next_damage', 0) - damage)
                        damage -= prevented
                    if damage > 0:
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
                    if not cannot_prevent:
                        prevented = min(damage, getattr(perm, '_prevent_next_damage', 0))
                        perm._prevent_next_damage = max(0, getattr(perm, '_prevent_next_damage', 0) - damage)
                        damage -= prevented
                    if damage > 0:
                        perm.damage += damage
                        changes.append({
                            'type': 'DAMAGE',
                            'target': target,
                            'amount': damage
                        })
        return {'state_changes': changes}
''')

# Patch _handle_deal_damage_to_creature
content = content.replace('''
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
''', '''
    def _handle_deal_damage_to_creature(self) -> Dict:
        """Deal damage only to creatures."""
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm and is_creature(perm.card_data):
                damage = self.effect_value or 4
                prevented = min(damage, getattr(perm, '_prevent_next_damage', 0))
                perm._prevent_next_damage = max(0, getattr(perm, '_prevent_next_damage', 0) - damage)
                damage -= prevented
                if damage > 0:
                    perm.damage += damage
                    changes.append({
                        'type': 'DAMAGE',
                        'target': target,
                        'amount': damage
                    })
        return {'state_changes': changes}
''')

# Patch _handle_deal_damage_no_prevent
content = content.replace('''
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
''', '''
    def _handle_deal_damage_no_prevent(self) -> Dict:
        """Deal damage that can't be prevented."""
        changes = self._handle_deal_damage(cannot_prevent=True).get('state_changes', [])
        # Add cannot prevent flag
        for change in changes:
            change['cannot_prevent'] = True
        # Also prevent life gain for the turn
        for pid in self.game.players:
            self.game.players[pid]['_cannot_gain_life'] = True
        return {'state_changes': changes}
''')

# Patch _handle_deal_damage_no_regen
content = content.replace('''
    def _handle_deal_damage_no_regen(self) -> Dict:
        """Deal damage that can't be regenerated."""
        changes = self._handle_deal_damage().get('state_changes', [])
        for change in changes:
            if change.get('type') == 'DAMAGE':
                change['no_regeneration'] = True
        return {'state_changes': changes}
''', '''
    def _handle_deal_damage_no_regen(self) -> Dict:
        """Deal damage that can't be regenerated."""
        changes = self._handle_deal_damage().get('state_changes', [])
        for change in changes:
            if change.get('type') == 'DAMAGE':
                change['no_regeneration'] = True
                target = change.get('target')
                perm = self.game.find_permanent(target)
                if perm:
                    perm._cannot_regenerate_this_turn = True
        return {'state_changes': changes}
''')

# Patch _handle_swords_to_plowshares
content = content.replace('''
                controller = perm.controller
                self.game.players[controller]['life'] += power
                self.game.remove_permanent(target, to_exile=True)
                changes.append({
                    'type': 'EXILE',
                    'target': target,
                    'life_gain': power,
                    'controller': controller
                })
''', '''
                controller = perm.controller
                if not self.game.players[controller].get('_cannot_gain_life', False):
                    self.game.players[controller]['life'] += power
                    changes.append({
                        'type': 'LIFE_GAIN',
                        'target': controller,
                        'amount': power
                    })
                self.game.remove_permanent(target, to_exile=True)
                changes.append({
                    'type': 'EXILE',
                    'target': target
                })
''')

# Patch _handle_healing_salve
content = content.replace('''
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
''', '''
    def _handle_healing_salve(self) -> Dict:
        """Target player gains 3 life OR prevent next 3 damage."""
        changes = []
        if self.targets:
            target = self.targets[0]
            if target.startswith('player_'):
                if not self.game.players[target].get('_cannot_gain_life', False):
                    self.game.players[target]['life'] += self.effect_value or 3
                    changes.append({
                        'type': 'LIFE_GAIN',
                        'target': target,
                        'amount': self.effect_value or 3
                    })
            else:
                perm = self.game.find_permanent(target)
                if perm:
                    perm._prevent_next_damage = getattr(perm, '_prevent_next_damage', 0) + (self.effect_value or 3)
                changes.append({
                    'type': 'PREVENT_DAMAGE',
                    'target': target,
                    'amount': self.effect_value or 3
                })
        return {'state_changes': changes}
''')

# Patch _handle_gray_merchant
content = content.replace('''
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
''', '''
    def _handle_gray_merchant(self) -> Dict:
        """Each opponent loses X life, you gain X life."""
        changes = []
        devotion = self.game.state_manager.get_devotion(self.controller, 'B')
        
        for pid in self.game.players:
            if pid != self.controller:
                self.game.players[pid]['life'] -= devotion
                changes.append({
                    'type': 'LIFE_LOSS',
                    'target': pid,
                    'amount': devotion
                })
        
        if not self.game.players[self.controller].get('_cannot_gain_life', False):
            self.game.players[self.controller]['life'] += devotion
            changes.append({
                'type': 'LIFE_GAIN',
                'target': self.controller,
                'amount': devotion
            })
        
        return {'state_changes': changes}
''')

# Patch _handle_ping
content = content.replace('''
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
''', '''
    def _handle_ping(self) -> Dict:
        changes = []
        for target in self.targets:
            perm = self.game.find_permanent(target)
            if perm:
                damage = 1
                prevented = min(damage, getattr(perm, '_prevent_next_damage', 0))
                perm._prevent_next_damage = max(0, getattr(perm, '_prevent_next_damage', 0) - damage)
                damage -= prevented
                if damage > 0:
                    perm.damage += damage
                    changes.append({'type': 'DAMAGE', 'target': target, 'amount': damage})
            elif target in self.game.players:
                player = self.game.players[target]
                damage = 1
                prevented = min(damage, player.get('_prevent_next_damage', 0))
                player['_prevent_next_damage'] = max(0, player.get('_prevent_next_damage', 0) - damage)
                damage -= prevented
                if damage > 0:
                    player['life'] -= damage
                    changes.append({'type': 'DAMAGE', 'target': target, 'amount': damage})
        return {'state_changes': changes}
''')

with open('game/card_effects.py', 'w') as f:
    f.write(content)

print("Patched card_effects.py")
