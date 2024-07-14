import inspect
import re

def get_method_name(prefix: str = '', suffix: str = '', level: int = 1) -> str:
    """
    Get the name of the method at a specified level of nesting in the call stack, with
    optional prefix and suffix filtering.
    
    :param level: The level of nesting (1 for immediate caller, 2 for caller's caller, etc.)
    :param prefix: Optional prefix to filter the method name with
    :param suffix: Optional suffix to filter the method name with
    :return: The name of the method at the specified level, filtered by prefix and suffix if provided
    """

    frame = inspect.currentframe()
    try:
        for _ in range(level):
            frame = frame.f_back
        method_name = frame.f_code.co_name
        pattern = f'{re.escape(prefix)}(.*){re.escape(suffix)}'
        match = re.match(pattern, method_name)
        if match:
            return match.group(1)
        else:
            return method_name
    finally:
        del frame  # Avoid reference cycles