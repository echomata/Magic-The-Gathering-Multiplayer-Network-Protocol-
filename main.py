"""CLI entry point for MTGNP with bonus features."""
import argparse
import sys
import json
import os

from core.constants import DEFAULT_PORT
from network.server import MTGNPServer
from network.client import MTGNPClient
from network.spectator import SpectatorClient
from game.card_catalog import list_available_cards, get_card
from core.game_logger import GameLogger


def print_card_summary():
    """Print a summary of available cards."""
    summary = list_available_cards()
    
    print("\n" + "="*60)
    print("MTGNP Card Catalog Summary")
    print("="*60)
    print(f"Total Cards: {summary['total']}")
    
    print("\nBy Type:")
    for ct, count in sorted(summary['by_type'].items()):
        print(f"  {ct}: {count}")
    
    print("\nBy Color:")
    color_names = {'W': 'White', 'U': 'Blue', 'B': 'Black', 'R': 'Red', 'G': 'Green', 'C': 'Colorless'}
    for color, count in sorted(summary['by_color'].items()):
        name = color_names.get(color, color)
        print(f"  {name}: {count}")
    print("="*60 + "\n")


def run_client_interactive(client):
    """Run interactive client mode."""
    print("\nMTGNP Client - Interactive Mode")
    print("Commands:")
    print("  help         - Show this help")
    print("  hand         - Show your hand")
    print("  state        - Show full game state")
    print("  pass         - Pass priority")
    print("  concede      - Concede the game")
    print("  cast <card> [targets...] - Cast a spell")
    print("  activate <source_id> <ability_index> [targets...] - Activate ability")
    print("  land <card>  - Play a land")
    print("  attack <id> [target] - Declare attacker")
    print("  block <id> <attacker> - Declare blocker")
    print("  order_damage <attacker_id> <blocker_id>... - Assign damage order")
    print("  discard <id1> [id2...] - Discard cards")
    print("  mulligan keep [id1...] - Keep hand (bottom N cards)")
    print("  mulligan redraw        - Take a mulligan")
    print("  trigger order <id1> <id2>... - Order triggers")
    print("  trigger keep [target]        - Keep optional trigger")
    print("  trigger decline              - Decline optional trigger")
    print("  list         - List available cards")
    print("  quit/exit    - Exit client")
    print()

    try:
        while client.running:
            cmd = input("\n> ").strip()
            if not cmd:
                continue
            
            parts = cmd.split()
            command = parts[0].lower()
            
            if command in ['quit', 'exit']:
                break
            elif command == 'help':
                print("Commands: help, hand, state, pass, concede, mulligan, cast, activate, land, attack, block, order_damage, discard, trigger, list, quit")
            elif command == 'hand':
                hand = client.game_state.get('hand', {}).get(client.player_id, [])
                print(f"Hand ({len(hand)} cards):")
                for i, card_id in enumerate(hand):
                    from game.card_catalog import get_card
                    card = get_card(card_id)
                    name = card.get('name') if card else card_id
                    print(f"  {i+1}. {name}")
            elif command == 'state':
                print(json.dumps(client.game_state, indent=2))
            elif command == 'pass':
                client.pass_priority()
                print("Passed priority")
            elif command == 'concede':
                client.send_concede()
                print("Conceded game")
            elif command == 'list':
                print_card_summary()
            elif command == 'mulligan' and len(parts) >= 2:
                subcommand = parts[1].lower()
                if subcommand == 'keep':
                    cards_to_bottom = parts[2:] if len(parts) > 2 else []
                    client.send_mulligan_choice(True, cards_to_bottom)
                    print(f"Keeping hand, bottoming: {cards_to_bottom}")
                elif subcommand == 'redraw':
                    client.send_mulligan_choice(False)
                    print("Taking a mulligan")
                else:
                    print("Usage: mulligan keep [card_ids...] OR mulligan redraw")
            elif command == 'cast' and len(parts) >= 2:
                card_id = parts[1]
                targets = parts[2:] if len(parts) > 2 else []
                # Look up the card's actual mana cost instead of assuming
                # every spell costs a single red mana. (Cost keys are
                # color letters plus "X" for generic, matching the RFC.)
                card = get_card(card_id)
                mana_payment = dict(card.get('mana_cost', {})) if card else {}
                client.send_cast_spell(card_id, targets, mana_payment)
                print(f"Casting {card_id} paying {mana_payment}")
            elif command == 'activate' and len(parts) >= 3:
                source_id = parts[1]
                ability_index = int(parts[2])
                targets = parts[3:] if len(parts) > 3 else []
                cost_payment = {"tap": False, "mana": {}} 
                client.send_activate_ability(source_id, ability_index, targets, cost_payment)
                print(f"Activating ability {ability_index} on {source_id}")
            elif command == 'land' and len(parts) >= 2:
                card_id = parts[1]
                client.send_play_land(card_id)
                print(f"Playing land {card_id}")
            elif command == 'attack' and len(parts) >= 2:
                creature_id = parts[1]
                target = parts[2] if len(parts) > 2 else None
                attackers = [{"creature_id": creature_id, "target": target or "player_2"}]
                client.send_declare_attackers(attackers)
                print(f"Declared {creature_id} as attacker")
            elif command == 'block' and len(parts) >= 3:
                creature_id = parts[1]
                blocking_id = parts[2]
                blockers = [{"creature_id": creature_id, "blocking_id": blocking_id}]
                client.send_declare_blockers(blockers)
                print(f"Declared {creature_id} blocking {blocking_id}")
            elif command == 'order_damage' and len(parts) >= 3:
                attacker_id = parts[1]
                blocker_order = parts[2:]
                client.send_assign_damage_order(attacker_id, blocker_order)
                print(f"Assigning damage order for {attacker_id}: {blocker_order}")
            elif command == 'discard' and len(parts) >= 2:
                card_ids = parts[1:]
                client.send_discard(card_ids)
                print(f"Discarding {card_ids}")
            elif command == 'trigger' and len(parts) >= 2:
                subcommand = parts[1].lower()
                if subcommand == 'order' and len(parts) >= 3:
                    trigger_ids = parts[2:]
                    client.send_trigger_order_response(trigger_ids)
                    print(f"Sent trigger order: {trigger_ids}")
                elif subcommand == 'keep':
                    target = parts[2] if len(parts) > 2 else None
                    client.send_trigger_choice_response(True, target)
                    print(f"Kept trigger, target: {target}")
                elif subcommand == 'decline':
                    client.send_trigger_choice_response(False)
                    print("Declined trigger")
                else:
                    print("Unknown trigger subcommand. Use 'trigger order <ids>', 'trigger keep [target]', or 'trigger decline'")
            else:
                print(f"Unknown command: {command}")

    except KeyboardInterrupt:
        pass


def run_spectator(host, port, verbose):
    """Run spectator mode."""
    client = SpectatorClient(host=host, port=port, verbose=verbose)
    client.connect()
    client.log("Spectator mode - watching game")
    
    try:
        while client.running:
            cmd = input("\n[spectator] > ").strip()
            if not cmd:
                continue
            
            parts = cmd.split()
            command = parts[0].lower()
            
            if command in ['quit', 'exit']:
                break
            elif command == 'state':
                print(json.dumps(client.game_state, indent=2))
            elif command == 'history':
                history = client.get_history()
                print(f"History: {len(history)} events")
            elif command == 'save' and len(parts) >= 2:
                client.save_history(parts[1])
            elif command == 'load' and len(parts) >= 2:
                client.load_history(parts[1])
            elif command == 'replay':
                client.replay()
            elif command == 'help':
                print("Commands: help, state, history, save <file>, load <file>, replay, quit")
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description='MTGNP Implementation with Bonus Features')
    parser.add_argument('mode', choices=['server', 'client', 'spectator'], nargs='?',
                       help='Run as server, client, or spectator')
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Port')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose mode')
    parser.add_argument('--player', help='Player ID (client mode)')
    parser.add_argument('--deck', nargs='+', help='Deck list (client mode)')
    parser.add_argument('--list-cards', action='store_true', help='List available cards')
    parser.add_argument('--log-file', help='Log file for game events')

    args = parser.parse_args()

    if args.list_cards:
        print_card_summary()
        return

    if not args.mode:
        parser.print_help()
        return

    if args.mode == 'server':
        server = MTGNPServer(port=args.port, verbose=args.verbose)
        if args.log_file:
            server.game.game_logger = GameLogger()
        try:
            server.start()
        except KeyboardInterrupt:
            print("\nServer stopped")
    elif args.mode == 'spectator':
        run_spectator(args.host, args.port, args.verbose)
    else:
        client = MTGNPClient(host=args.host, port=args.port, verbose=args.verbose)
        client.connect()

        if args.player and args.deck:
            client.send_player_ready(args.player, args.deck)
            print(f"Player {args.player} ready with {len(args.deck)} cards")

        run_client_interactive(client)
        client.close()


if __name__ == '__main__':
    main()