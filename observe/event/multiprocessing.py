import multiprocessing
from typing import Any, Dict

from observe.event.base import Event


class MultiprocessingEvent(Event):
    _lock = multiprocessing.Lock()

    def trigger(self, *args: Any, **kwargs: Dict) -> None:
        self._trigger(*args, run_multiprocessing=True, **kwargs)
