from typing import TypeVar, Any

from observe.event.base import Event

T = TypeVar('T')
V = TypeVar('V', str, int, float, bool, list, dict, tuple, set, object)


def ObservableClass(cls: T) -> T:
    """Decorator to add event functionality to a class."""

    # Define events
    cls.value_changed = Event(str, V)
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

    # Intercept attribute changes
    def get_wrapped_setattr(o_setattr):
        def setattr_wrapper(self, name, value):
            o_setattr(self, name, value)
            self.value_changed.trigger(name, value)

        return setattr_wrapper

    setattr(cls, '__setattr__', get_wrapped_setattr(cls.__setattr__))

    return cls


def ObservableMethod(func: T) -> T:
    """Decorator to add event functionality to a method."""

    def method_wrapper(self, *args, **kwargs):
        self.method_called.trigger(func.__name__)
        result = func(self, *args, **kwargs)
        return result

    return method_wrapper


def Observe(cls: Any) -> Any:
    """Decorator to add event functionality to a class."""
    if isinstance(cls, type):
        return ObservableClass(cls)
    else:
        return ObservableMethod(cls)