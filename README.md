# MTGNP Project Structure

```
mtgnp/
├── __init__.py          # Package exports
├── __main__.py          # Entry point for python -m mtgnp
├── card_catalog.py      # Complete card definitions (100+ cards)
├── card_effects.py      # Card effect implementations (25+ effects)
├── client.py            # Client implementation
├── constants.py         # Constants and configuration
├── game_logger.py       # Game logging/replay functionality
├── main.py              # CLI entry point
├── models.py            # Data models (Permanent, StackItem, Player)
├── network.py           # Network utilities (encoding/decoding)
├── server.py            # Server implementation
├── spectator.py         # Spectator client
├── triggers.py          # Triggered abilities manager
├── utils.py             # Utility functions
└── game/
    ├── __init__.py      # Game module exports
    ├── actions.py       # Player action handlers
    ├── combat.py        # Combat system
    ├── game.py          # Main game orchestrator
    ├── lifecycle.py     # LOBBY, SETUP, MULLIGAN, GAME_OVER
    ├── priority.py      # Priority and stack management
    ├── state.py         # Game state management
    └── turn.py          # Turn and phase engine
```

## File Descriptions

### Root Level Files

| File | Description |
|------|-------------|
| `__init__.py` | Package root, exports all public classes |
| `__main__.py` | Entry point for `python -m mtgnp` |
| `card_catalog.py` | Complete card catalog with 100+ cards, card lookup functions |
| `card_effects.py` | All card effect implementations (25+ effects) |
| `client.py` | MTGNP client - connects to server, sends actions, renders state |
| `constants.py` | All constants (ports, timeouts, phases, error codes) |
| `game_logger.py` | Game logging, saving, loading, replay functionality |
| `main.py` | CLI entry point with argument parsing |
| `models.py` | Data models: `Permanent`, `StackItem`, `Player` |
| `network.py` | Network utilities: `encode_message`, `decode_message`, `send_pdu` |
| `server.py` | MTGNP server - handles connections and routes PDUs |
| `spectator.py` | Read-only spectator client with history/replay |
| `triggers.py` | Triggered ability manager (ETB, attack, death triggers) |
| `utils.py` | Utility functions (shuffle, draw, mana checking, etc.) |

### Game Submodule Files

| File | Description |
|------|-------------|
| `game/__init__.py` | Game module exports |
| `game/actions.py` | Player action handlers (cast spell, play land, declare attackers) |
| `game/combat.py` | Combat system (damage calculation, resolution) |
| `game/game.py` | Main game orchestrator - coordinates all sub-systems |
| `game/lifecycle.py` | Game lifecycle (LOBBY, SETUP, MULLIGAN, GAME_OVER) |
| `game/priority.py` | Priority and stack management |
| `game/state.py` | Game state management (players, permanents, state building) |
| `game/turn.py` | Turn and phase engine (all phases and steps) |

## Running the Project

### Start Server
```bash
python -m mtgnp server --verbose
python -m mtgnp server --verbose --log-file game.log
```

### Start Client (Player 1)
```bash
python -m mtgnp client --player player_1 --deck lightning_bolt_001 lightning_bolt_002 shock_001 mountain_001 mountain_002 goblin_guide_001 --verbose
```

### Start Client (Player 2)
```bash
python -m mtgnp client --player player_2 --deck counterspell_001 island_001 swamp_001 gray_merchant_001 mountain_003 shock_002 --verbose
```

### Start Spectator
```bash
python -m mtgnp spectator --verbose
```

### List Available Cards
```bash
python -m mtgnp client --list-cards
```

## Client Commands

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

## Bonus Features

| Feature | Points | File |
|---------|--------|------|
| Full Card Effects | 10 | `card_effects.py` |
| Triggered Abilities | 5 | `triggers.py` |
| Spectator Client | 5 | `spectator.py` |
| Game Logging/Replay | 5 | `game_logger.py` |
| Interactive UI | 5 | `client.py`, `main.py` |

## Requirements

- Python lol what did u expect hashsasha
- No external dependencies (uses only Python standard library)

## Project Statistics

- **Total Files**: 22
- **Card Catalog**: 100+ unique cards
- **Card Effects**: 25+ implemented
- **Game Phases**: 14 phases/steps
- **Error Codes**: 11 defined
- **PDU Types**: 25 defined
