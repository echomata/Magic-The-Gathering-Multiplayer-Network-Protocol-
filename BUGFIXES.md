# Bug Fixes Applied

This document lists every fix applied to the original submission, why each was
necessary, and how each was verified. Useful source material for your
README's "known limitations / deviations from the RFC" section and for
answering demo questions about what changed and why.

All fixes were verified either with a direct unit-level check or by running
the actual server plus scripted `MTGNPClient` instances through a real game
(LOBBY -> MULLIGAN -> land -> spell cast -> combat -> damage) over a real
TCP connection.

## Critical (game-breaking)

1. **Client crash on any hand data** (`network/client.py`, `main.py`)
   `_render_state()` and the `hand` CLI command treated `state['hand']` as a
   flat list. Per the RFC (10.2.2) and `game/state.py`, it's an object keyed
   by `player_id`. Slicing a dict (`hand[:10]`) raised `KeyError`, which
   silently killed the client's receive thread on the very first
   hand-containing `GAME_STATE_UPDATE` (i.e. almost immediately in any real
   game), because the outer exception handler in `_receive_loop` isn't
   verbose-gated. Fixed by pulling out `hand.get(self.player_id, [])`.

2. **Basic land ID padding mismatch** (`game/card_catalog.py`)
   Basic lands were instanced as `mountain_01` (2-digit) while every other
   card, the RFC's own examples, and the official card list spreadsheet use
   3-digit IDs (`mountain_001`). This silently broke any deck list written
   in the standard format and would have broken interoperability with any
   other group's RFC-compliant client/server. Fixed by removing the special
   case; all cards now use `{base_id}_{i:03d}`.

3. **Generic mana cost key mismatch** (`game/card_catalog.py`)
   Card costs used `"generic"` as the dict key, but the RFC (10.2.7) and
   this codebase's own `_pay_mana()` both use `"X"`. `check_mana()` only
   special-cased `"X"`, so any RFC-compliant `mana_payment` for a card with
   a generic-mana component was rejected with `INSUFFICIENT_MANA`. Fixed by
   renaming every `"generic"` key to `"X"` in the catalog (27 cards).

4. **Mana dorks / Sol Ring never entered the battlefield**
   (`game/priority.py`)
   `resolve_stack()` checked `card.get('effect')` before `is_permanent()`.
   Llanowar Elves, Elvish Mystic, and Sol Ring all define a top-level
   `"effect": "mana"` field (describing their *activated* tap ability), so
   casting them incorrectly ran the one-shot mana effect and skipped
   creating a `Permanent` entirely - the creature/artifact just vanished
   instead of joining the battlefield. Fixed by checking `is_permanent()`
   first; permanents always enter the battlefield, regardless of whether
   they also define a later activated-ability effect. Verified live: Sol
   Ring / Llanowar Elves now correctly appear on the battlefield after
   resolving.

5. **Permanent IDs didn't match their card instance IDs**
   (`game/priority.py`, `game/actions.py`, `game/card_effects.py`)
   `Permanent` objects were assigned a randomly generated ID
   (`perm_<timestamp>_<rand>`) instead of using their own card instance ID.
   The RFC is explicit (10.2.2): *"Each permanent id matches its card
   instance id from the original deck_list."* Every RFC example references
   permanents this way (e.g. `"creature_id": "goblin_guide_001"`). This
   silently broke `DECLARE_ATTACKERS`, `DECLARE_BLOCKERS`, and
   `ACTIVATE_ABILITY` for any spec-compliant client (`ILLEGAL_ACTION:
   Invalid creature`). Fixed at all three `Permanent(...)` construction
   sites to use `card_id` as the permanent ID. Verified live: declaring a
   creature as an attacker by its card ID now succeeds and correctly taps
   it.

## Significant (incorrect game outcomes)

6. **First-strike creatures dealt damage twice** (`game/combat.py`,
   `core/models.py`, `game/card_catalog.py`)
   The regular Combat Damage Step didn't exclude creatures that already
   dealt damage in the First Strike Step, so first-strikers dealt damage in
   *both* passes. Added proper double-strike support
   (`card_has_double_strike`, `Permanent.has_double_strike()`) and fixed the
   pass logic so: vanilla creatures only deal damage in the regular step,
   first-strikers only in the first-strike step, and double-strikers in
   both - matching RFC 9.6/9.7 exactly. Verified with a unit test against
   all three cases.

7. **Sorcery-speed timing wasn't enforced** (`game/actions.py`)
   `can_play_during_phase()` only checked the phase name, not who holds
   priority or whether the stack is empty. This let the non-active player
   cast sorcery-speed spells (creatures, sorceries, enchantments,
   artifacts) whenever they held priority during the active player's main
   phase - a violation of RFC Figure 4 ("sorcery speed for AP"). Fixed by
   requiring `player_id == active_player` and an empty stack for anything
   that isn't an instant. Applied the same stack-empty rule to `PLAY_LAND`.

## RFC-conformance risk (worked internally, but not spec-literal)

8. **`DECLARE_ATTACKERS` / `DECLARE_BLOCKERS` / `ASSIGN_DAMAGE_ORDER`
   seq_num mechanism** (`game/priority.py`, `game/turn.py`,
   `network/client.py`)
   The RFC states no `PRIORITY_GRANT` PDU is defined for these steps - the
   client should echo the seq_num of the `PHASE_TRANSITION` that announced
   the step. This implementation instead sent an (unspecified) extra
   `PRIORITY_GRANT` and validated against that. Internally consistent, but
   would reject a strictly RFC-compliant client from another group (and
   vice versa). Fixed: added `PriorityManager.expect_action()`, which sets
   up the same validation state without sending a PDU; the client now
   tracks `_last_phase_transition_seq` and echoes that. Verified live
   end-to-end (attack declared and correctly tapped, block declared, damage
   resolved, all using the PHASE_TRANSITION's seq_num with no
   `STALE_ACTION`).

## Minor

9. Wall of Stone (and anything with **Defender**) could illegally attack -
   `card_has_defender()` existed but was never called. Wired into
   `Permanent.can_attack()`.
10. CLI's `cast` command hardcoded `mana_payment = {'R': 1}` regardless of
    the card being cast. Now looks up the real cost from the catalog.
11. `RECONNECT_TIMEOUT` constant (30s) was defined but unused; the
    disconnect handler hardcoded `10.0`. Now uses the constant.
12. Removed a dead branch in the client's `_handle_priority` (an
    auto-pass-if-not-mine case that could never trigger, since the server
    only ever sends `PRIORITY_GRANT` to the actual priority holder).
13. `core/utils.py` imported `game.card_catalog` at module load time,
    creating a circular-import trap if `core.utils`/`core.models` were ever
    imported before `network.*`/`game.*` in a fresh process (doesn't affect
    any real entry point, but is fragile). Made the import lazy.
14. Removed now-unused `generate_permanent_id`/`generate_stack_id` imports
    left over after fix #5.

## Known gaps - not fixed (documented, not required by the RFC)

These keyword abilities are set on cards in the catalog but aren't wired
into any game logic. None of them are part of the MTGNP protocol spec
itself (the RFC doesn't mention them), so treat these as bonus-scope, not
bugs:

- **Flying / evasion**: any creature can currently block a flyer.
- **Vigilance**: attacking still taps the creature.
- **Hexproof / Protection**: a `_protected` flag is set by Vines of
  Vastwood's effect but never checked anywhere targeting is validated.
- **Kicker / Madness / Suspend**: tagged on a couple of cards but there's no
  PDU field or code path to actually invoke them.
- **Trample** is intentionally absent - the RFC (section 1) explicitly
  excludes it from MTGNP 1.0, so this is correct, not a gap.

If you want any of these implemented, they're meaningfully larger feature
additions (each touches target validation and/or combat blocking logic in
several places) rather than one-line fixes, so budget real time for them.
