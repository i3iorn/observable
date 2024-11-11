from enum import Enum


class EventTypes(Enum):
    EVENT = "event"
    THREADED = "threaded"
    ASYNC = "async"
    MULTIPROCESSING = "multiprocessing"
