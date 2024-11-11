import threading
from typing import Any, Dict

from observe.event.base import Event


class ThreadedEvent(Event):
    _lock = threading.Lock()

    def trigger(self, *args: Any, **kwargs: Dict) -> None:
        self._trigger(*args, run_threaded=True, **kwargs)
