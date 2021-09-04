import types
from functools import wraps

from stripe.error import StripeError

from platform_lib.exceptions import StripeException


def stripe_error_handler(klass):
    """
    Class decorator for StripeAPI. Decorates each public method with try-except block.
    Throws custom exception "StripeException".
     """
    for key in dir(klass):
        method = getattr(klass, key)
        if isinstance(method, types.FunctionType) and not method.__name__.startswith('__'):
            wrapped = __stripe_error_handler(method)
            setattr(klass, key, wrapped)
    return klass


def __stripe_error_handler(func):
    if hasattr(func, 'stripe_error_handler'):  # Only decorate once
        return func

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except StripeError as ex:
            raise StripeException(str(ex))

    wrapper.stripe_error_handler = True
    return wrapper
