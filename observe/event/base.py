import asyncio
import logging
import multiprocessing
import threading
from copy import copy
from datetime import datetime
from multiprocessing import Process
from threading import Thread
from typing import List, Union, Callable, Any, Dict, Optional, Set, Coroutine, TypeVar, Type

from typing_extensions import TypeVar

from observe import exceptions
from observe.event.fake_lock import FakeLock
from observe.listener import ListenerInterface


T = TypeVar("T")


class Event:
    """
    An base class for events that can be registered to observables.

    Example:
    ```
    class MyEventClass(Object):
        an_event = Event()

    def my_callback():
        print("Callback executed!")

    my_event_class = MyEventClass()
    my_event_class.an_event.register(my_callback)
    my_event_class.an_event.trigger()
    ```
    """
    _lock = FakeLock()
    default_history_limit: int = 100

    def __init__(self, *types: Type) -> None:
        """
        Initializes the Event instance.
        """
        self._listeners: List[Union[Callable, ListenerInterface]] = []
        self._history: List[Dict[str, Any]] = []

        self.logger: logging.Logger = logging.getLogger(__name__)

        self.type_signature = types
        if len(types) == 1:
            globals()[T] = TypeVar("T", bound=types[0])
        else:
            globals()[T] = TypeVar("T", *types)

    @property
    def history(self) -> List[Dict[str, Any]]:
        """
        Returns the history of the threaded_event. The history should contain information about the threaded_event, such as the times it
        was triggered and the arguments that were passed to it.

        Returns:
            List: The history of the threaded_event.

        Example:
        ```
        event = Event()
        event.trigger()
        event.trigger()

        print(event.history)
        ```
        """
        return self._history

    @property
    def lock(self) -> Union[threading.Lock, multiprocessing.Lock, FakeLock]:
        """
        Returns the lock object for thread-safe or processing-safe operations. If you are not running in a threaded or
        processing environment, this should return a FakeLock object. The FakeLock object is required to let the code
        run without errors.

        Returns:
            Union[threading.Lock, multiprocessing.Lock, None]: The lock object.

        Example:
        ```
        event = Event()

        with event._lock:
            print("Event locked")

        print("Event unlocked")
        ```
        """
        return self._lock

    def add_to_history(self, event: "Event", success: bool, *args: List, history_limit: int = -1) -> None:
        """
        Adds an threaded_event to the history.

        Args:
            event (EventInterface): The threaded_event to add to the history.

        Example:
        ```
        event = Event()
        event.add_to_history(event)

        print(event.history)
        event.trigger()
        print(event.history)
        ```
        """
        if history_limit < 0:
            history_limit = self.default_history_limit

        while len(self._history) > history_limit:
            self._history.pop(0)

        history_event = {
            "event": event,
            "time": datetime.now(),
            "args": args,
            "success": success
        }
        self._history.append(history_event)

    def _listener_input_validation(self, callback: Optional[Callable] = None, listener: Optional[ListenerInterface] = None) -> Union[Callable, ListenerInterface]:
        """
        Validates the input for registering a listener.

        Args:
            callback (Callable): The callback function to validate.
            listener (Listener): The listener to validate.

        Returns:
            Callable: The callback function.
            Listener: The listener.

        Raises:
            ValueError: If neither a callback nor a listener is provided.
            ValueError: If both a callback and a listener are provided.
            ValueError: If the listener is not an instance of the Listener class.
            ValueError: If the callback is not a callable function.

        Example:
        ```
        event = Event()
        event._listener_input_validation(callback=my_callback)
        ```
        """
        if (callback is None) == (listener is None):
            raise ValueError("Either callback or listener must be provided, not both.")

        if listener is not None:
            if not isinstance(listener, ListenerInterface):
                raise ValueError("Listener must be an instance of the Listener class.")

        elif callback is not None:
            if not callable(callback):
                raise ValueError("Callback must be a callable function.")

        return listener if listener is not None else callback

    def register(self, callback: Optional[Callable] = None, listener: Optional[ListenerInterface] = None) -> None:
        """
        Register a listener, either in the form of a callback function or a Listener object, to an threaded_event.

        Args:
            callback (Callable): The callback function to register.
            listener (Listener): The listener to register.

        Example:
        ```
        event = Event()
        event.register(my_callback)
        ```
        """
        listening = self._listener_input_validation(callback, listener)

        with self._lock:
            self._listeners.append(listening)

    def unregister(self, callback: Optional[Callable] = None, listener: Optional[ListenerInterface] = None) -> None:
        """
        Unregisters a callback function from a specific threaded_event.

        Args:
            event_name (str): The name of the threaded_event.
            callback (Callable): The callback function to unregister.
            listener (Listener): The listener to unregister.

        Example:
        ```
        event = Event()
        event.unregister(my_callback)

        print(event._listeners)
        ```
        """
        listening = self._listener_input_validation(callback, listener)

        with self._lock:
            self._listeners = [listener for listener in self._listeners if listener != listening]

    def trigger(self, *args: T) -> Coroutine[Any, Any, list[Any]] | list[Thread] | list[Process] | Any:
        """
        Triggers the threaded_event. Needs to be implemented by the subclass. The subclass should call the _trigger method

        Args:
            filter Callable: A function that filters the listeners.
            sort Optional[Callable]: A function that sorts the listeners.
            *args: Positional arguments to pass to the callback functions.
            **kwargs: Keyword arguments to pass to the callback functions.

        Returns:
            Coroutine[Any, Any, list[Any]] | list[Thread] | list[Process] | Any: The result of the triggered callbacks.

        Example:
        ```
        event = Event()
        event.trigger()
        ```
        """
        return self._trigger(*args)

    def _validate_input(self, *args):
        for arg, t in zip(args, self.type_signature, strict=True):
            if not isinstance(arg, t):
                raise exceptions.EventSignalTypeError(f"Event can only be triggered with the signature {self.type_signature}, received {set(type(arg) for arg in args)}")

    def _trigger(
            self,
            *args: T,
            filter: Optional[Callable] = None,
            sort: Optional[Callable] = None,
            run_async: Optional[bool] = False,
            run_threaded: Optional[bool] = False,
            run_multiprocessing: Optional[bool] = False
    ) -> Coroutine[Any, Any, list[Any]] | list[Thread] | list[Process] | Any:
        """
        Triggers all callbacks registered to an threaded_event.

        Args:
            *args: Positional arguments to pass to the callback functions.
            **kwargs: Keyword arguments to pass to the callback functions.

        Returns:
            Coroutine[Any, Any, list[Any]] | list[Thread] | list[Process] | Any: The result of the triggered callbacks.

        Raises:
            ValueError: If more than one of run_async, run_threaded, or run_multiprocessing is True.

        Example:
            Not meant to be called directly. Use the trigger method instead.
        ```
        event = Event()
        event._trigger()
        ```
        """
        if 0 < sum([run_async, run_threaded, run_multiprocessing]) < 1:
            raise ValueError("Exactly one or zero of run_async, run_threaded, or run_multiprocessing must be True.")

        self._validate_input(*args)

        with self._lock:
            listeners = copy(self._listeners)

        if filter is not None:
            listeners = self._filter(listeners, filter)

        if sort is not None:
            listeners = self._sort(listeners, sort)

        if run_async:
            result = self._run_async(listeners, *args)
        elif run_threaded:
            result = self._run_threaded(listeners, *args)
        elif run_multiprocessing:
            result = self._run_multiprocessing(listeners, *args)
        else:
            result = self._run_syncronous(listeners, *args)

        self.add_to_history(self, bool(result), *args)
        return result

    def _handle_listener_exceptions(self, listener: ListenerInterface, exception, *args: Any) -> None:
        """
        Handles exceptions that occur when running a listener.

        Args:
            listener (Listener): The listener that raised the exception.
            exception (Exception): The exception that occurred
            *args: Positional arguments to pass to the error handler.
            **kwargs: Keyword arguments to pass to the error handler.

        Example:
        ```
        event = Event()
        event._handle_listener_exceptions(listener=my_listener)
        ```
        """
        try:
            if isinstance(exception, listener.exceptions):
                listener.error_handler(*args)
            else:
                raise exception
        except Exception as e:
            self.logger.warning(f"Error occurred while handling listener exceptions: {e}. Listener: {listener}. "
                                f"Args: {args}. Listener will be removed.")

            opt = {"listener" if isinstance(listener, ListenerInterface) else "callback": listener}
            self.unregister(**opt)

    def _filter(self, listeners: List[Union[Callable, ListenerInterface]], filter: Optional[Callable] = None) -> Set[ListenerInterface]:
        """
        Filters the listeners based on the filter function.

        Args:
            listeners (List[Union[Callable, Listener]]): A list of listeners to filter and sort.
            filter (Callable): A function that filters the listeners.

        Returns:
            Set[Listener]: A tuple containing the filtered and sorted listeners.

        Example:
        ```
        event = Event()
        event._filter()
        ```
        """
        try:
            return {listener for listener in listeners if filter is None or filter(listener)}
        except Exception as e:
            self.logger.warning(f"Error occurred while filtering listeners: {e}")
            return set(listeners)

    def _sort(self, listeners: List[Union[Callable, ListenerInterface]], sort: Optional[Callable] = None) -> Set[ListenerInterface]:
        """
        Sorts the listeners based on the sort function.

        Args:
            listeners (List[Union[Callable, Listener]]): A list of listeners to filter and sort.
            sort (Callable): A function that sorts the listeners.

        Returns:
            Set[Listener]: A tuple containing the filtered and sorted listeners.
        """
        try:
            return set(sorted(listeners, key=sort) if sort is not None else listeners)
        except Exception as e:
            self.logger.warning(f"Error occurred while sorting listeners: {e}")
            return set(listeners)

    async def _run_async(self, listeners: Set[Union[Callable, ListenerInterface]], *args: Optional[List[Any]]) -> list[Any]:
        """
        Runs the listeners asynchronously.

        Args:
            listeners (Set[Union[Callable, Listener]]): A set of listeners to run.
            *args: Positional arguments to pass to the callback functions.
            **kwargs: Keyword arguments to pass to the callback functions.
        """
        tasks = {asyncio.create_task(listener(*args)) for listener in listeners if isinstance(listener, ListenerInterface)}
        future = await asyncio.gather(*tasks)

        return future

    def _run_threaded(self, listeners: Set[Union[Callable, ListenerInterface]], *args: Optional[List[Any]]) -> list[Thread]:
        """
        Runs the listeners in separate threads.

        Args:
            listeners (Set[Union[Callable, Listener]]): A set of listeners to run.
            *args: Positional arguments to pass to the callback functions.
            **kwargs: Keyword arguments to pass to the callback functions.
        """
        threads = []
        for listener in listeners:
            try:
                thread = threading.Thread(target=listener, args=args)
                thread.start()
                threads.append(thread)
            except Exception as e:
                self._handle_listener_exceptions(listener, e, *args)

        [thread.join() for thread in threads]

        return threads

    def _run_multiprocessing(self, listeners: Set[Union[Callable, ListenerInterface]], *args: Optional[List[Any]]) -> list[Process]:
        """
        Runs the listeners in separate processes.

        Args:
            listeners (Set[Union[Callable, Listener]]): A set of listeners to run.
            *args: Positional arguments to pass to the callback functions.
            **kwargs: Keyword arguments to pass to the callback functions.
        """
        processes = []
        for listener in listeners:
            try:
                process = multiprocessing.Process(target=listener, args=args)
                process.start()
                processes.append(process)
            except Exception as e:
                self._handle_listener_exceptions(listener, e, *args)

        [process.join() for process in processes]

        return processes

    def _run_syncronous(self, listeners: Set[Union[Callable, ListenerInterface]], *args: Optional[List[Any]]) -> list[Any]:
        """
        Runs the listeners synchronously.

        Args:
            listeners (Set[Union[Callable, Listener]]): A set of listeners to run.
            *args: Positional arguments to pass to the callback functions.
            **kwargs: Keyword arguments to pass to the callback functions.
        """
        results = []

        for listener in listeners:
            try:
                results.append(listener(*args))
            except Exception as e:
                self._handle_listener_exceptions(listener, e, *args)

        return results