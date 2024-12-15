import functools

test_var = "Who dis"

def super_decorator(func):
    """A decorator that does nothing and simply returns the function."""
    func.contains_view = True
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print('Wrappity Wrapped')
        return func(*args, **kwargs)
    return wrapper

@super_decorator
def my_sweet_func():
    print('Hello World')
    print(test_var)