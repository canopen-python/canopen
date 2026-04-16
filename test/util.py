import contextlib
import os
import tempfile


DATATYPES_EDS = os.path.join(os.path.dirname(__file__), "datatypes.eds")
SAMPLE_EDS = os.path.join(os.path.dirname(__file__), "sample.eds")


@contextlib.contextmanager
def tmp_file(*args, **kwds):
    with tempfile.NamedTemporaryFile(*args, **kwds) as tmp:
        tmp.close()
        yield tmp
