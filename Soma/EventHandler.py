from enum import Enum
from typing import Callable


class EventHandler:
    def __init__(self, events: dict[str, tuple[bool, Callable]]):
        self.events = events

    def event_is_pending(self, event: Enum) -> bool:
        return self.events[event.name][0]

    def prepare_event_trigger(self, event: Enum):
        self.events[event.name] = (True, self.events[event.name][1])

    def handle_events(self):
        for event, (triggered, callback) in self.events.items():
            if triggered and callback:
                callback()
                self.events[event] = (False, callback)
        pass
