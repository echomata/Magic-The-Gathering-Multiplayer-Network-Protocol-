"""Game logging and replay functionality."""
import json
import time
from typing import Dict, List, Optional


class GameLogger:
    """Logs game events for replay and analysis."""
    
    def __init__(self):
        self.events = []
        self.metadata = {
            'start_time': time.time(),
            'game_version': '1.0.0'
        }
    
    def log_event(self, event_type: str, data: Dict):
        """Log a game event."""
        self.events.append({
            'timestamp': time.time(),
            'type': event_type,
            'data': data
        })
    
    def log_pdu(self, direction: str, pdu: Dict):
        """Log a PDU."""
        self.events.append({
            'timestamp': time.time(),
            'type': 'PDU',
            'direction': direction,
            'pdu': pdu
        })

    def save(self, filename: str):
        """Save log to file."""
        data = {
            'metadata': self.metadata,
            'events': self.events
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self, filename: str):
        """Load log from file."""
        with open(filename, 'r') as f:
            data = json.load(f)
        self.metadata = data.get('metadata', {})
        self.events = data.get('events', [])

    def get_events_by_type(self, event_type: str) -> List[Dict]:
        """Get events of a specific type."""
        return [e for e in self.events if e.get('type') == event_type]

    def get_events_by_turn(self, turn: int) -> List[Dict]:
        """Get events for a specific turn."""
        return [e for e in self.events if e.get('data', {}).get('turn') == turn]

    def get_event_count(self) -> int:
        """Get total event count."""
        return len(self.events)

    def summarize(self) -> Dict:
        """Get summary statistics."""
        pdu_count = len(self.get_events_by_type('PDU'))
        turn_count = len(set(e.get('data', {}).get('turn', 0) for e in self.events if 'turn' in e.get('data', {})))
        
        return {
            'total_events': len(self.events),
            'pdu_count': pdu_count,
            'turn_count': turn_count,
            'duration': time.time() - self.metadata.get('start_time', time.time())
        }

    def get_state_at_time(self, timestamp: float) -> Optional[Dict]:
        """Get game state at a specific timestamp."""
        last_state = None
        for event in self.events:
            if event['timestamp'] > timestamp:
                break
            if event.get('type') == 'PDU':
                pdu = event.get('pdu', {})
                if pdu.get('type') == 'GAME_STATE_UPDATE':
                    last_state = pdu.get('state')
        return last_state

    def get_turn_events(self, turn: int) -> List[Dict]:
        """Get all events for a specific turn."""
        return [e for e in self.events if e.get('data', {}).get('turn') == turn]

    def get_player_actions(self, player_id: str) -> List[Dict]:
        """Get all actions taken by a specific player."""
        actions = []
        for event in self.events:
            if event.get('type') == 'PDU':
                pdu = event.get('pdu', {})
                if pdu.get('type') in ['CAST_SPELL', 'PLAY_LAND', 'DECLARE_ATTACKERS', 
                                       'DECLARE_BLOCKERS', 'PRIORITY_PASS', 'CONCEDE']:
                    if pdu.get('player_id') == player_id:
                        actions.append(event)
        return actions

    def export_text(self, filename: str):
        """Export log as human-readable text."""
        with open(filename, 'w') as f:
            f.write(f"MTGNP Game Log\n")
            f.write(f"Start Time: {time.ctime(self.metadata.get('start_time', 0))}\n")
            f.write(f"Version: {self.metadata.get('game_version', 'unknown')}\n")
            f.write("="*60 + "\n\n")
            
            for event in self.events:
                timestamp = time.ctime(event['timestamp'])
                if event['type'] == 'PDU':
                    direction = event.get('direction', 'UNKNOWN')
                    pdu_type = event['pdu'].get('type', 'UNKNOWN')
                    f.write(f"[{timestamp}] {direction} {pdu_type}\n")
                    f.write(f"  {json.dumps(event['pdu'], indent=2)}\n\n")
                else:
                    f.write(f"[{timestamp}] {event['type']}: {event['data']}\n\n")