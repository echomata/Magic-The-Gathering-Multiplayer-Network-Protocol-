# MTGNP Project Structure

```
mtgnp/
├── __init__.py          # Package exports
├── __main__.py          # Entry point for python -m mtgnp
├── main.py              # CLI entry point
├── launcher.py          # Script launcher
├── README.md
├── core/                # Core models and utilities
│   ├── __init__.py
│   ├── constants.py     # Constants and configuration
│   ├── game_logger.py   # Game logging/replay functionality
│   ├── models.py        # Data models (Permanent, StackItem, Player)
│   └── utils.py         # Utility functions
├── network/             # Networking components
│   ├── __init__.py
│   ├── client.py        # Client implementation
│   ├── network.py       # Network utilities (encoding/decoding)
│   ├── server.py        # Server implementation
│   └── spectator.py     # Spectator client
└── game/                # Game engine logic
    ├── __init__.py      # Game module exports
    ├── actions.py       # Player action handlers
    ├── card_catalog.py  # Complete card definitions (100+ cards)
    ├── card_effects.py  # Card effect implementations (25+ effects)
    ├── combat.py        # Combat system
    ├── game.py          # Main game orchestrator
    ├── lifecycle.py     # LOBBY, SETUP, MULLIGAN, GAME_OVER
    ├── priority.py      # Priority and stack management
    ├── state.py         # Game state management
    ├── triggers.py      # Triggered abilities manager
    └── turn.py          # Turn and phase engine
```

## File Descriptions

### Root Level Files
| File | Description |
|------|-------------|
| `__init__.py` | Package root, exports all public classes |
| `__main__.py` | Entry point for `python -m mtgnp` |
| `main.py` | CLI entry point with argument parsing |
| `launcher.py` | Script launcher |

### Core Module (`core/`)
| File | Description |
|------|-------------|
| `constants.py` | All constants (ports, timeouts, phases, error codes) |
| `game_logger.py` | Game logging, saving, loading, replay functionality |
| `models.py` | Data models: `Permanent`, `StackItem`, `Player` |
| `utils.py` | Utility functions (shuffle, draw, mana checking, etc.) |

### Network Module (`network/`)
| File | Description |
|------|-------------|
| `client.py` | MTGNP client - connects to server, sends actions, renders state |
| `network.py` | Network utilities: `encode_message`, `decode_message`, `send_pdu` |
| `server.py` | MTGNP server - handles connections and routes PDUs |
| `spectator.py` | Read-only spectator client with history/replay |

### Game Module (`game/`)
| File | Description |
|------|-------------|
| `actions.py` | Player action handlers (cast spell, play land, declare attackers, discard) |
| `card_catalog.py` | Complete card catalog with 100+ cards, card lookup functions |
| `card_effects.py` | All card effect implementations (25+ effects) |
| `combat.py` | Combat system (damage calculation, resolution) |
| `game.py` | Main game orchestrator - coordinates all sub-systems |
| `lifecycle.py` | Game lifecycle (LOBBY, SETUP, MULLIGAN, GAME_OVER) |
| `priority.py` | Priority, stack management, SBA loop, and fizzle logic |
| `state.py` | Game state management (players, permanents, state building) |
| `triggers.py` | Triggered ability manager (ETB, attack, death triggers) |
| `turn.py` | Turn and phase engine (all phases and steps) |

## Running the Project

### Prerequisites
- Python 3.x
- No external dependencies (uses only Python standard library)

### Start Server
```bash
python launcher.py server --port 4444 --verbose
python launcher.py server --port 4444 --verbose --log-file game.log
```

### Start Client (Player 1)
```bash
python launcher.py client --host localhost --port 4444 --player player_1 --deck lightning_bolt_001 lightning_bolt_002 shock_001 mountain_001 mountain_002 goblin_guide_001 --verbose
```

### Start Client (Player 2)
```bash
python launcher.py client --host localhost --port 4444 --player player_2 --deck counterspell_001 island_001 swamp_001 gray_merchant_001 mountain_003 shock_002 --verbose
```

### Start Spectator
```bash
python launcher.py spectator --host localhost --port 4444 --verbose
```

### List Available Cards
```bash
python launcher.py --list-cards
```

### Deck Requirements
- Minimum deck size: 1 card
- Maximum deck size: 50 cards
- Cards must be valid card IDs from the catalog
- See full card list with `--list-cards`

### Client Commands
| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `hand` | Show your hand |
| `state` | Show full game state |
| `pass` | Pass priority |
| `concede` | Concede the game |
| `cast <card_id> [targets...]` | Cast a spell |
| `land <card_id>` | Play a land |
| `attack <creature_id> [target]` | Declare attacker |
| `block <creature_id> <attacker_id>` | Declare blocker |
| `discard <id1> [id2...]` | Discard cards (used during Cleanup step) |
| `list` | List available cards |
| `quit`/`exit` | Exit client |

## Spectator Commands
| Command | Description |
|---------|-------------|
| `state` | Show game state |
| `history` | Show history count |
| `save <file>` | Save history to file |
| `load <file>` | Load history from file |
| `replay` | Replay game |
| `quit`/`exit` | Exit spectator |

## Project Statistics
- **Total Files**: 22
- **Card Catalog**: 100+ unique cards
- **Card Effects**: 25+ implemented
- **Game Phases**: 14 phases/steps
- **Error Codes**: 11 defined
- **PDU Types**: 26 defined

## Work Distribution Matrix

| Task / Feature | Member 1 | Member 2 | Member 3 | Member 4 |
|---|---|---|---|---|
| TCP Server: connection handling, framing, dispatch | | | | |
| Game lifecycle: LOBBY, GAME_SETUP, MULLIGAN logic | | | | |
| Turn & phase engine (all phases/steps, transitions) | | | | |
| Priority & Stack logic, spell/ability resolution | | | | |
| Combat system (attackers, blockers, damage) | | | | |
| Client implementation & state rendering | | | | |
| PDU serialisation/deserialisation (all 25 PDU types) | | | | |
| Error handling, PING/PONG heartbeat, disconnect logic | | | | |
| Verbose mode (client + server PDU logging, toggle on/off) | | | | |
| Testing & interoperability | | | | |
| README / documentation / AI disclosure | | | | |

## AI Usage
*(Describe all AI tools used such as ChatGPT, GitHub Copilot, Claude, etc., and detail how they were used to assist in this machine problem).*

## Bonus Features Implemented (Full Card Effects)
To fulfill the 10-point Bonus criteria for "Implementation of all Card Abilities and Effects", we successfully implemented several mechanics defined in the Master Card List that require extending the base MTGNP 1.0 specifications:
1. **Kicker Mechanics**: We modified the `CAST_SPELL` and `STACK_PUSH` PDUs to include optional `kicked` (boolean) and `kicker_payment` (object) fields to fully support cards like *Goblin Bushwhacker* and *Vines of Vastwood*.
2. **Regeneration (Replacement Effects)**: Despite the RFC base limitation against replacement effects, we implemented a `_regeneration_shield` system to accurately support *Troll Ascetic*, *Doom Blade*, and *Terror*.
3. **Target Parameter Choices**: We extended the `ACTIVATE_ABILITY` and `STACK_PUSH` PDUs to accept an optional `ability_params` or `chosen_color` field to support *Mother of Runes*, which requires the controller to choose a specific protection color on activation.

## Known Limitations / Deviations from RFC
While the MTGNP 1.0 protocol is fully compliant in its base state, a few keyword abilities present on catalog cards are **not required by the RFC** and are therefore omitted from the game logic:
- **Flying / Evasion**: Any creature can currently block a flyer.
- **Vigilance**: Attacking still taps the creature.
- **Madness / Suspend**: Tagged on some cards but there are no PDU fields or code paths to invoke them.
- **Trample**: Intentionally absent, as the RFC (Section 1) explicitly excludes it from MTGNP 1.0.
