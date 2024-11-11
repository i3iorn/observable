import logging
from observe.observable.base import ObservableClass

@ObservableClass
class Integer(int):
    def __new__(cls, value):
        return super(Integer, cls).__new__(cls, value)

def on_value_changed(value):
    logging.info(f'Value changed to {value}')

my_class = Integer(5)
my_class.value_changed.register(on_value_changed)

print(my_class)
my_class += 1
print(my_class)