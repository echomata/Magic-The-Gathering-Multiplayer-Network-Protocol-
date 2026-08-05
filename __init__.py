# __init__.py (root level)
"""MTGNP - Magic: The Gathering Multiplayer Network Protocol Implementation."""

__version__ = '1.0.0'
__all__ = [
    'MTGNPServer',
    'MTGNPClient',
    'SpectatorClient',
    'Game',
    'Permanent',
    'StackItem',
    'Player',
    'CardEffect',
    'TriggerManager',
    'GameLogger',
    'list_available_cards',
    'get_card',
]

from server import MTGNPServer
from client import MTGNPClient
from spectator import SpectatorClient
from game.game import Game
from models import Permanent, StackItem, Player
from card_effects import CardEffect
from triggers import TriggerManager
from game_logger import GameLogger
from card_catalog import list_available_cards, get_card