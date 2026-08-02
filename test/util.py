import asyncio
import contextlib
import os
import tempfile
from collections.abc import Callable, Coroutine
from typing import Optional


DATATYPES_EDS = os.path.join(os.path.dirname(__file__), "datatypes.eds")
SAMPLE_EDS = os.path.join(os.path.dirname(__file__), "sample.eds")


@contextlib.contextmanager
def tmp_file(*args, **kwds):
    with tempfile.NamedTemporaryFile(*args, **kwds) as tmp:
        tmp.close()
        yield tmp


class SupressNotAwaited:
    """This is a small helper to wrap a callable object in a callable object,
    so that we can retrieve the coroutine object to suppress warnings about
    unawaited coroutines.
    """
    def __init__(self, fn: Callable):
        if not asyncio.iscoroutine(fn):
            self._coro: Optional[Coroutine] = None
            self._fn = fn
        else:
            self._coro = fn

    def __call__(self, *args, **kwargs):
        if self._coro is None:
            self._coro = self._fn(*args, **kwargs)
        return self._coro

    def __del__(self):
        """Suppress warnings about unawaited coroutines by closing the
           coroutine object.
        """
        if self._coro is not None:
            self._coro.close()
            self._coro = None
