"""Combat system."""
from typing import Dict, List


class CombatSystem:
    """Manages combat mechanics."""
    
    def __init__(self, game):
        self.game = game
        self.attackers = []
        self.blockers = []
        self.damage_order = {}
        self.first_strike_done = False

    @staticmethod
    def _deals_damage_in_pass(perm, first_strike_only: bool) -> bool:
        """Whether a creature deals damage in this pass of combat damage.

        Per RFC 9.6/9.7: first-strike (and double-strike) creatures deal
        damage in the First Strike Damage Step. The regular Combat Damage
        Step then deals damage for everyone EXCEPT creatures that have
        first strike but NOT double strike (they already dealt their
        damage). Double-strike creatures deal damage in both steps.
        """
        has_fs = perm.has_first_strike()
        has_ds = perm.has_double_strike()
        if first_strike_only:
            return has_fs or has_ds
        return has_ds or not has_fs

    @staticmethod
    def _damage_is_prevented(source, target) -> bool:
        """Apply the catalog's protection-from-color damage rule."""
        if not source or not target:
            return False
        source_color = source.card_data.get('color', '') if source.card_data else ''
        return target.has_protection_from(source_color)

    def deal_combat_damage(self, first_strike_only: bool = False):
        """Deal combat damage."""
        damage_events = []
        creatures_died = []

        for attack in self.attackers:
            creature_id = attack.get('creature_id')
            target = attack.get('target')
            perm = self.game.find_permanent(creature_id)

            if not perm:
                continue

            if not self._deals_damage_in_pass(perm, first_strike_only):
                continue

            power = perm.get_power()
            blockers = [b for b in self.blockers if b.get('blocking_id') == creature_id]

            if blockers:
                # Per RFC 9.7: "MTGNP 1.0 does not implement trample. A
                # blocked attacker deals its full combat damage to its
                # blocker(s) only, never to the defending player." All of
                # the attacker's power is assigned among its blockers
                # (in damage_order when multiply-blocked); none of it ever
                # reaches the defending player's life total, regardless of
                # whether the card has a "trample" ability tag.
                if len(blockers) > 1 and creature_id in self.damage_order:
                    ordered = self.damage_order[creature_id]
                    remaining_power = power
                    for block_id in ordered:
                        if remaining_power <= 0:
                            break
                        blocker_perm = self.game.find_permanent(block_id)
                        if blocker_perm:
                            damage_to_deal = min(remaining_power, blocker_perm.get_toughness())
                            if not self._damage_is_prevented(perm, blocker_perm):
                                blocker_perm.damage += damage_to_deal
                                if blocker_perm.damage >= blocker_perm.get_toughness():
                                    creatures_died.append(block_id)
                                damage_events.append({
                                    "source": creature_id,
                                    "target": block_id,
                                    "amount": damage_to_deal
                                })
                            remaining_power -= damage_to_deal
                else:
                    for block in blockers:
                        blocker_perm = self.game.find_permanent(block.get('creature_id'))
                        if blocker_perm:
                            assigned_to_blocker = power
                            if not self._damage_is_prevented(perm, blocker_perm):
                                blocker_perm.damage += assigned_to_blocker
                                if blocker_perm.damage >= blocker_perm.get_toughness():
                                    creatures_died.append(block.get('creature_id'))
                                damage_events.append({
                                    "source": creature_id,
                                    "target": block.get('creature_id'),
                                    "amount": assigned_to_blocker
                                })
            else:
                self.game.players[target]['life'] -= power
                damage_events.append({
                    "source": creature_id,
                    "target": target,
                    "amount": power
                })

        for block in self.blockers:
            creature_id = block.get('creature_id')
            blocking_id = block.get('blocking_id')
            perm = self.game.find_permanent(creature_id)

            if not perm:
                continue

            if not self._deals_damage_in_pass(perm, first_strike_only):
                continue

            power = perm.get_power()
            attacker_perm = self.game.find_permanent(blocking_id)
            if attacker_perm:
                if not self._damage_is_prevented(perm, attacker_perm):
                    attacker_perm.damage += power
                    if attacker_perm.damage >= attacker_perm.get_toughness():
                        creatures_died.append(blocking_id)
                    damage_events.append({
                        "source": creature_id,
                        "target": blocking_id,
                        "amount": power
                    })

        # Regeneration (RFC doesn't define this card pool's regenerate
        # mechanic, but game/priority.py's check_state_based_actions()
        # already implements it correctly for non-combat lethal damage;
        # combat damage must respect it too, or "regenerate" creatures
        # would still die whenever combat, not some other effect, deals
        # the lethal damage). A creature with a regeneration shield is
        # untapped->tapped, has its damage removed, and survives; the
        # shield is consumed instead of the creature being destroyed.
        actual_deaths = []
        for creature_id in set(creatures_died):
            perm = self.game.find_permanent(creature_id)
            if perm and perm._regeneration_shield > 0:
                perm._regeneration_shield -= 1
                perm.damage = 0
                perm.tapped = True
                continue
            self.game.remove_permanent(creature_id)
            actual_deaths.append(creature_id)

        pdu = {
            "type": "COMBAT_DAMAGE_RESULT",
            "seq_num": self.game.next_seq(),
            "damage_events": damage_events,
            "life_totals": {pid: data.get('life', 20) for pid, data in self.game.players.items()},
            "creatures_died": actual_deaths
        }
        self.game.broadcast(pdu)

        dead_players = [
            pid for pid, data in self.game.players.items()
            if data.get('life', 20) <= 0
        ]
        if dead_players:
            if len(dead_players) == 2:
                nap = self.game.get_other_player(self.game.active_player)
                self.game.lifecycle_manager.end_game(nap, "LIFE_ZERO")
            else:
                self.game.lifecycle_manager.end_game(
                    self.game.get_other_player(dead_players[0]), "LIFE_ZERO"
                )

    def reset(self):
        """Reset combat state."""
        self.attackers = []
        self.blockers = []
        self.damage_order = {}
        self.first_strike_done = False
