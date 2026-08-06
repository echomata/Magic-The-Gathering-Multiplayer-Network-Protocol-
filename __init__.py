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

from network.server import MTGNPServer
from network.client import MTGNPClient
from network.spectator import SpectatorClient
from game.game import Game
from core.models import Permanent, StackItem, Player
from game.card_effects import CardEffect
from game.triggers import TriggerManager
from core.game_logger import GameLogger
from game.card_catalog import list_available_cards, get_card