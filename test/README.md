# Canopen unit tests

This directory contains the unittests for the canopoen library. canopen use
`unittest` as the framework for testing.


## Testing without async

If writing a test that doesn't require or depend on async features, tests
can be written as.

```python
class TestVariable(unittest.TestCase):
    ...
```

See [`test_variable.py`](`test_variable.py`) as an example


## Testing with async

Since this library supports usage with async support and with regular blocking
calls, the unit tests must test both cases. This does requre a little bit more
setup in the testing.

First create a base class that is intended to be run twice, once without async
and once with async enabled.

```python
from .async_tests import DualSyncAsyncTestCase

class TestEmcy(DualSyncAsyncTestCase):
    __test__ = False  # This is a base class that shall not run directly

    # The following attrobutes are available:
    #    async_test: bool  # Flag if async testing is running
    #    loop: Optional[asyncio.AbstractEventLoop]  # The loop in async mode,
    #                                               # `None` in regular mode.

    def setUp(self):
        super().setUp()  # Make sure this is called when overriding `setUp`
        # ... do your setup

    # Any tests that doesn't depend on async, can be written as regular
    # test methods
    def test_emcy_error(self):
       self.assertEqual(...)

    # Any tests that requre async, use `async def`
    async def test_method(self):
        if self.async_test:
            # This is when async is enabled.
            await some_async_command()
        else:
            # This is when async is not running
            some_regular_command()
```

To run this class, two instances of the test class must be created. One with
async and one without:

```python
class TestEmcySync(TestEmcy):
    """Run the tests in non-asynchronous mode."""
    __test__ = True     # This is test to run
    async_test = False  # Not async mode

class TestEmcyAsync(TestEmcy):
    """Run the tests in asynchronous mode."""
    __test__ = True    # This is tests to run
    async_test = True  # In async mode
```

This results in two sets of the same tests, `TestEmcySync`, where async is not
enabled and `TestEmcyAsync` where async is enabled.

There is nothing special about these two runs, except the value of
`self.async_test` and `self.loop`. 

```python
    async def test_method(self):
        if self.async_test:
            # This is when async is enabled.
            await some_async_command()
        else:
            # This is when async is not running
            some_regular_command()
```

What the sync and async does, is run this test function twice, once with
`self.async_test` False and then a second time with `self.async_test` True.
It is the resposibility of the unittests to decide if there is a need to
differentiate the test flow between the two run.


### Setting up a Network instance in async

`Network()` is the main component that have difference between usage in sync
and async mode. To use network proper in async, it's async context must be
entered in the test.

Say that `setUp()` contains `self.network = Network()` then the following can
be added to enter and exits its async context:

```python
    async def asyncSetUp(self):
        if self.async_test:
            await self.network.__aenter__()

    async def asyncTearDown(self):
        if self.async_test:
            await self.network.__aexit__(None, None, None)
```


### Async or regular test function?

When writing tests, should I use `async def` or just `def`?

If not making any async operations with `async` or `await` there is no need
to mark the function as `async def`. Note that the function will be run in both
sync and async mode even if its not a coroutine.


### Excluding async from a test

The easiest way is to do:

```python
def test_something(self):
    if self.async_test:
        self.skipTest("Async is not supported because ...")
```
