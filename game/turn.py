"""Turn and phase engine."""
from typing import Dict
from core.models import Permanent
from core.utils import generate_permanent_id


class TurnEngine:
    """Manages turn structure and phase transitions."""
    
    def __init__(self, game):
        self.game = game

    def start_turn(self):
        """Start the first turn."""
        self.game.state = "IN_GAME"
        self.game.turn = 1
        self.game.phase = "UNTAP"
        self.game.land_played_this_turn = False
        self.game.stack = []
        self.game.floating_mana = {}

        self.game.log(f"Starting Turn {self.game.turn} - Active player: {self.game.active_player}")

        self.game.broadcast_phase_transition("MULLIGAN", "UNTAP")
        self.do_untap_step()

    def do_untap_step(self):
        """Handle UNTAP step (automatic, no priority)."""
        self.game.phase = "UNTAP"
        self.game.log("UNTAP step")

        for pid, data in self.game.players.items():
            for perm in data.get('battlefield', []):
                if perm.controller == self.game.active_player:
                    perm.tapped = False
                    perm._temporary_bonus = {'power': 0, 'toughness': 0}
                    perm.temporary_abilities.clear()
                    perm._regeneration_shield = 0
                    perm._pacified = False
                    perm._protected = False
                    perm._hexproof = False
                    perm._temporary_protection_color = None
                    perm.summoning_sick = False

        self.game.land_played_this_turn = False
        self.game.floating_mana = {}

        self.game.broadcast_game_state()
        self.do_upkeep_step()

    def do_upkeep_step(self):
        """Handle UPKEEP step."""
        self.game.phase = "UPKEEP"
        self.game.log("UPKEEP step")

        self.game.broadcast_phase_transition("UNTAP", "UPKEEP")
        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def do_draw_step(self):
        """Handle DRAW step."""
        self.game.phase = "DRAW"
        self.game.log("DRAW step")

        self.game.broadcast_phase_transition("UPKEEP", "DRAW")

        if self.game.turn != 1:
            data = self.game.players[self.game.active_player]
            if not data['library']:
                self.game.lifecycle_manager.end_game(
                    self.game.get_other_player(self.game.active_player), "DECK_EMPTY"
                )
                return
            drawn = data['library'].pop()
            data['hand'].append(drawn)
            self.game.log(f"{self.game.active_player} drew {drawn}")

        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def do_precombat_main(self):
        """Handle PRECOMBAT_MAIN phase."""
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.log("PRECOMBAT_MAIN phase")

        self.game.broadcast_phase_transition("DRAW", "PRECOMBAT_MAIN")
        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def do_begin_combat(self):
        """Handle BEGIN_COMBAT step."""
        self.game.phase = "BEGIN_COMBAT"
        self.game.log("BEGIN_COMBAT step")

        self.game.broadcast_phase_transition("PRECOMBAT_MAIN", "BEGIN_COMBAT")
        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def do_declare_attackers(self):
        """Handle DECLARE_ATTACKERS step."""
        self.game.phase = "DECLARE_ATTACKERS"
        self.game.log("DECLARE_ATTACKERS step")

        phase_seq = self.game.broadcast_phase_transition("BEGIN_COMBAT", "DECLARE_ATTACKERS")
        self.game.broadcast_game_state()

        self.game.priority_manager.expect_action(self.game.active_player, phase_seq)

    def do_declare_blockers(self):
        """Handle DECLARE_BLOCKERS step."""
        self.game.phase = "DECLARE_BLOCKERS"
        self.game.log("DECLARE_BLOCKERS step")

        phase_seq = self.game.broadcast_phase_transition("DECLARE_ATTACKERS", "DECLARE_BLOCKERS")
        self.game.broadcast_game_state()

        # Per RFC 9.4: same implicit-request pattern as Declare Attackers.
        nap = self.game.get_other_player(self.game.active_player)
        self.game.priority_manager.expect_action(nap, phase_seq)

    def do_assign_damage_order(self):
        """Handle ASSIGN_DAMAGE_ORDER step."""
        self.game.phase = "ASSIGN_DAMAGE_ORDER"
        self.game.log("ASSIGN_DAMAGE_ORDER step")

        need_order = False
        for attack in self.game.combat_system.attackers:
            creature_id = attack.get('creature_id')
            blockers = [b for b in self.game.combat_system.blockers if b.get('blocking_id') == creature_id]
            if len(blockers) > 1:
                need_order = True
                break

        if not need_order:
            self.do_combat_damage()
            return

        phase_seq = self.game.broadcast_phase_transition("DECLARE_BLOCKERS", "ASSIGN_DAMAGE_ORDER")
        self.game.broadcast_game_state()

        # Per RFC 9.5: same implicit-request pattern.
        self.game.priority_manager.expect_action(self.game.active_player, phase_seq)

    def do_first_strike_damage(self):
        """Handle FIRST_STRIKE_DAMAGE step (optional)."""
        self.game.phase = "FIRST_STRIKE_DAMAGE"
        self.game.log("FIRST_STRIKE_DAMAGE step")

        has_first_strike = False
        all_creatures = []
        for attack in self.game.combat_system.attackers:
            all_creatures.append(attack.get('creature_id'))
        for blocker in self.game.combat_system.blockers:
            all_creatures.append(blocker.get('creature_id'))
            
        for creature_id in all_creatures:
            perm = self.game.find_permanent(creature_id)
            if perm and (perm.has_first_strike() or perm.has_double_strike()):
                has_first_strike = True
                break

        if not has_first_strike:
            self.do_combat_damage()
            return

        self.game.broadcast_phase_transition("ASSIGN_DAMAGE_ORDER", "FIRST_STRIKE_DAMAGE")
        self.game.combat_system.deal_combat_damage(first_strike_only=True)
        self.game.combat_system.first_strike_done = True

        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def do_combat_damage(self):
        """Handle COMBAT_DAMAGE step."""
        self.game.phase = "COMBAT_DAMAGE"
        self.game.log("COMBAT_DAMAGE step")

        prev = "FIRST_STRIKE_DAMAGE" if self.game.combat_system.first_strike_done else "ASSIGN_DAMAGE_ORDER"
        self.game.broadcast_phase_transition(prev, "COMBAT_DAMAGE")
        self.game.combat_system.deal_combat_damage(first_strike_only=False)

        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def do_end_of_combat(self):
        """Handle END_OF_COMBAT step."""
        self.game.phase = "END_OF_COMBAT"
        self.game.log("END_OF_COMBAT step")

        prev = "COMBAT_DAMAGE" if self.game.combat_system.attackers else "DECLARE_ATTACKERS"
        self.game.broadcast_phase_transition(prev, "END_OF_COMBAT")

        self.game.combat_system.attackers = []
        self.game.combat_system.blockers = []
        self.game.combat_system.damage_order = {}
        self.game.combat_system.first_strike_done = False

        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def do_postcombat_main(self):
        """Handle POSTCOMBAT_MAIN phase."""
        self.game.phase = "POSTCOMBAT_MAIN"
        self.game.log("POSTCOMBAT_MAIN phase")

        self.game.broadcast_phase_transition("END_OF_COMBAT", "POSTCOMBAT_MAIN")
        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def do_end_step(self):
        """Handle END_STEP."""
        self.game.phase = "END_STEP"
        self.game.log("END_STEP")

        self.game.broadcast_phase_transition("POSTCOMBAT_MAIN", "END_STEP")
        self.game.broadcast_game_state()
        self.game.priority_manager.open_priority_window()

    def do_cleanup(self):
        """Handle CLEANUP step."""
        self.game.phase = "CLEANUP"
        self.game.log("CLEANUP step")

        self.game.broadcast_phase_transition("END_STEP", "CLEANUP")

        data = self.game.players[self.game.active_player]
        if len(data['hand']) > 7:
            self.game.action_handler.waiting_for_discard = self.game.active_player
            self.game.send_game_state(self.game.active_player)
            self.game.log(f"Waiting for {self.game.active_player} to discard")
            return

        for pid, pdata in self.game.players.items():
            for perm in pdata.get('battlefield', []):
                perm.damage = 0
                perm._temporary_bonus = {'power': 0, 'toughness': 0}
                perm.temporary_abilities.clear()
                perm._regeneration_shield = 0

        self.game.broadcast_game_state()
        self.end_turn()

    def end_turn(self):
        """End the current turn and start the next."""
        self.game.turn += 1
        self.game.active_player = self.game.get_other_player(self.game.active_player)
        self.game.land_played_this_turn = False
        self.game.stack = []
        self.game.floating_mana = {}

        self.game.log(f"Turn {self.game.turn} - Active player: {self.game.active_player}")

        self.game.broadcast_phase_transition("CLEANUP", "UNTAP")
        self.do_untap_step()

    def advance_step(self):
        """Advance to the next step/phase."""
        self.game.log(f"Advancing from {self.game.phase}")

        # Mana remaining in the pool expires when the current step/phase
        # ends. Mana is otherwise represented as an implementation detail
        # because MTGNP clients declare complete payments in their PDUs.
        self.game.floating_mana = {}

        step_handlers = {
            "UPKEEP": self.do_draw_step,
            "DRAW": self.do_precombat_main,
            "PRECOMBAT_MAIN": self.do_begin_combat,
            "BEGIN_COMBAT": self.do_declare_attackers,
            "DECLARE_ATTACKERS": self._handle_attackers_done,
            "DECLARE_BLOCKERS": self.do_assign_damage_order,
            "ASSIGN_DAMAGE_ORDER": self.do_first_strike_damage,
            "FIRST_STRIKE_DAMAGE": self.do_combat_damage,
            "COMBAT_DAMAGE": self.do_end_of_combat,
            "END_OF_COMBAT": self.do_postcombat_main,
            "POSTCOMBAT_MAIN": self.do_end_step,
            "END_STEP": self.do_cleanup,
        }

        handler = step_handlers.get(self.game.phase)
        if handler:
            handler()

    def _handle_attackers_done(self):
        """Handle completion of attackers declaration."""
        if self.game.combat_system.attackers:
            self.do_declare_blockers()
        else:
            self.do_end_of_combat()
