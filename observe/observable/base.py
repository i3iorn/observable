from typing import TypeVar

from observe.event.base import Event

T = TypeVar('T')
V = TypeVar('V')


def ObservableClass(cls: T) -> T:
    """Decorator to add event functionality to a class."""

    # Define events
    cls.value_changed = Event(V)
    cls.method_called = Event(str)

    # Intercept method calls
    def get_wrapped_method(func_name, o_method):
        def method_wrapper(self, *args, **kwargs):
            self.method_called.trigger(func_name)
            result = o_method(self, *args, **kwargs)
            return result

        return method_wrapper

    for name, method in cls.__dict__.items():
        if callable(method):
            setattr(cls, name, get_wrapped_method(name, method))

    return cls
