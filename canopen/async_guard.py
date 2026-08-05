""" Utils for async """
import asyncio
import functools
import logging
import threading
import traceback


_ASYNC_GUARDS: dict[int, bool] = {}
"""Per-thread boolean indicating allowance of running blocking functions.

:code:`True` indicates that blocking functions are not allowed to be called
from the current thread.
"""

logger = logging.getLogger(__name__)


def enable_async_guard(enable: bool):
    """Enable or disable the async guard for the current thread.

    :param enable: True to enable the async guard, False to disable it.
    """
    _ASYNC_GUARDS[threading.get_ident()] = enable


def is_async_guarded() -> bool:
    """Check if async guard is enabled for this thread.

    :return: True if async guard is enabled, False otherwise.
    """
    return _ASYNC_GUARDS.get(threading.get_ident(), False)


def ensure_not_async(fn=None, error_message=None):
    """Guard a function from being called from the async main thread.

    This function is used to guard functions that are blocking and should not
    be called from async code. If the function is called while async is
    running, a RuntimeError will be raised.

    Can be used either as a plain decorator, :code:`@ensure_not_async`, or
    called with an extra error message, :code:`@ensure_not_async("message")`.

    :param error_message: Optional message appended to the RuntimeError raised
        when the guard trips.
    """
    if isinstance(fn, str):
        fn, error_message = None, fn

    def decorator(fn):
        @functools.wraps(fn)
        def async_guard_wrap(*args, **kwargs):
            if is_async_guarded():
                st = "".join(traceback.format_stack())
                logger.debug("Traceback:\n%s", st.rstrip())
                msg = ("Calling a blocking function while running async. "
                       f"Function {fn.__qualname__}() "
                       f"in {fn.__code__.co_filename}:{fn.__code__.co_firstlineno}")
                if error_message:
                    msg += f". {error_message}"
                raise RuntimeError(msg)
            return fn(*args, **kwargs)
        return async_guard_wrap

    if fn is not None:
        return decorator(fn)
    return decorator
