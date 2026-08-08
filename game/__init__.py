"""Game package exports with lazy imports to avoid circular dependencies."""

__all__ = [
    'Game', 'GameState', 'TurnEngine', 'CombatSystem',
    'PriorityManager', 'ActionHandler', 'LifecycleManager',
]


def __getattr__(name):
    modules = {
        'Game': ('game.game', 'Game'),
        'GameState': ('game.state', 'GameState'),
        'TurnEngine': ('game.turn', 'TurnEngine'),
        'CombatSystem': ('game.combat', 'CombatSystem'),
        'PriorityManager': ('game.priority', 'PriorityManager'),
        'ActionHandler': ('game.actions', 'ActionHandler'),
        'LifecycleManager': ('game.lifecycle', 'LifecycleManager'),
    }
    if name not in modules:
        raise AttributeError(name)
    module_name, attr = modules[name]
    from importlib import import_module
    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value
