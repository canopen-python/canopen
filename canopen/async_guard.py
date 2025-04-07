""" Utils for async """

import functools
from typing import Optional, Callable

TSentinel = Callable[[], bool]

# NOTE: Global, but needed to be able to use ensure_not_async() in
#       decorator context.
_ASYNC_SENTINEL: Optional[TSentinel] = None


def set_async_sentinel(fn: TSentinel):
    """ Register a function to validate if async is running """
    global _ASYNC_SENTINEL
    _ASYNC_SENTINEL = fn


def ensure_not_async(fn):
    """ Decorator that will ensure that the function is not called if async
        is running.
    """

    @functools.wraps(fn)
    def async_guard(*args, **kwargs):
        global _ASYNC_SENTINEL
        if _ASYNC_SENTINEL:
            if _ASYNC_SENTINEL():
                raise RuntimeError("Calling a blocking function while running async")
        return fn(*args, **kwargs)
    return async_guard
