from .base import Event
from .types import EventTypes


class EventFactory:
    @staticmethod
    def create_event(*args, event_type: EventTypes = None) -> Event:
        if event_type == EventTypes.THREADED:
            from .thread import ThreadedEvent
            return ThreadedEvent(*args)
        elif event_type == EventTypes.ASYNC:
            from .asyncronous import AsyncEvent
            return AsyncEvent(*args)
        elif event_type == EventTypes.MULTIPROCESSING:
            from .multiprocessing import MultiprocessingEvent
            return MultiprocessingEvent(*args)
        else:
            from .base import Event
            return Event(*args)
