from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


class ListenerInterface(ABC):
    """
    An abstract base class for listeners that can be registered to observables.
    """
    def __call__(self, *args, **kwargs):
        """
        Calls the event_handler method when the listener is called.
        """
        self.event_handler(*args, **kwargs)

    @property
    @abstractmethod
    def exceptions(self) -> Tuple:
        """
        A list of exceptions that are expected to be raised by the listener.

        Returns:
            A list of exceptions that are expected to be raised by the listener.
        """
        pass

    @abstractmethod
    def error_handler(self, *args: Any, **kwargs: Dict) -> None:
        """
        Handles errors that occur during threaded_event notification.

        Args:
            *args: Positional arguments to pass to the error handler.
            **kwargs: Keyword arguments to pass to the error handler.
        """
        pass

    @abstractmethod
    def event_handler(self, *args: Any, **kwargs: Dict) -> None:
        """
        Notifies the listener about an threaded_event.

        Args:
            *args: Positional arguments to pass to the listener.
            **kwargs: Keyword arguments to pass to the listener.
        """
        pass
