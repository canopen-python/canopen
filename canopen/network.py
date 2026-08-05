from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Coroutine, Iterator, MutableMapping
from contextlib import AsyncExitStack
from typing import Callable, Final, Optional, Union
import sys

import can

from canopen.async_guard import is_async_guarded
from canopen.lss import LssMaster
from canopen.nmt import NmtMaster
from canopen.node import LocalNode, RemoteNode
from canopen.objectdictionary import ObjectDictionary
from canopen.objectdictionary.eds import import_from_node
from canopen.sync import SyncProducer
from canopen.timestamp import TimeProducer

# Use backported TaskGroup and ExceptionGroup for Python < 3.11
if sys.version_info >= (3, 11):
    from builtins import ExceptionGroup
    from asyncio import TaskGroup
else:
    from exceptiongroup import ExceptionGroup
    from taskgroup import TaskGroup

logger = logging.getLogger(__name__)

Callback = Callable[[int, bytearray, float], None]


class Network(MutableMapping):
    """Representation of one CAN bus containing one or more nodes."""

    NOTIFIER_CYCLE: float = 1.0  #: Maximum waiting time for one notifier iteration.
    NOTIFIER_SHUTDOWN_TIMEOUT: float = 5.0  #: Maximum waiting time to stop notifiers.
    FILTER_ERRORS: bool = True  #: If True, exceptions in callbacks will be logged only

    def __init__(self, bus: Optional[can.BusABC] = None):
        """
        :param can.BusABC bus:
            A python-can bus instance to re-use.
        """
        #: A python-can :class:`can.BusABC` instance which is set after
        #: :meth:`canopen.Network.connect` is called
        self.bus = bus
        #: A :class:`~canopen.network.NodeScanner` for detecting nodes
        self.scanner = NodeScanner(self)
        #: List of :class:`can.Listener` objects.
        #: Includes at least MessageListener.
        self.listeners: list[can.Listener] = [MessageListener(self)]
        self.notifier: Optional[can.Notifier] = None
        self.nodes: dict[int, Union[RemoteNode, LocalNode]] = {}
        self.subscribers: dict[int, list[Callback]] = {}
        self.send_lock = threading.Lock()
        #: A task group for managing async tasks. This is used to ensure that
        #: all tasks are properly cleaned up when the network is closed.
        self.taskgroup: TaskGroup = TaskGroup()
        self.thread_id: int = threading.get_ident()
        #: An async exit stack for managing async context managers. This is used
        #: to ensure that all context managers are properly cleaned up when the
        #: network is closed.
        self.exit_stack: AsyncExitStack = AsyncExitStack()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        #: A list of exceptions that have occurred in callbacks. This is used to
        #: ensure that exceptions are not lost
        self.exceptions: list[BaseException] = []
        self.sync = SyncProducer(self)
        self.time = TimeProducer(self)
        self.nmt = NmtMaster(0)
        self.nmt.network = self

        self.lss = LssMaster()
        self.lss.network = self
        self.subscribe(self.lss.LSS_RX_COBID, self.lss.on_message_received)

    def subscribe(self, can_id: int, callback: Callback) -> None:
        """Listen for messages with a specific CAN ID.

        :param can_id:
            The CAN ID to listen for.
        :param callback:
            Function to call when message is received.
        """
        self.subscribers.setdefault(can_id, list())
        if callback not in self.subscribers[can_id]:
            self.subscribers[can_id].append(callback)

    def unsubscribe(self, can_id, callback=None) -> None:
        """Stop listening for message.

        :param int can_id:
            The CAN ID from which to unsubscribe.
        :param callback:
            If given, remove only this callback.  Otherwise all callbacks for
            the CAN ID.
        """
        if callback is not None:
            self.subscribers[can_id].remove(callback)
        if not self.subscribers[can_id] or callback is None:
            del self.subscribers[can_id]

    def connect(self, *args, **kwargs) -> Network:
        """Connect to CAN bus using python-can.

        Arguments are passed directly to :class:`can.BusABC`. Typically these
        may include:

        :param channel:
            Backend specific channel for the CAN interface.
        :param str interface:
            Name of the interface. See
            `python-can manual <https://python-can.readthedocs.io/en/stable/configuration.html#interface-names>`__
            for full list of supported interfaces.
        :param int bitrate:
            Bitrate in bit/s.

        :raises can.CanError:
            When connection fails.
        """
        # If bitrate has not been specified, try to find one node where bitrate
        # has been specified
        if "bitrate" not in kwargs:
            for node in self.nodes.values():
                if node.object_dictionary.bitrate:
                    kwargs["bitrate"] = node.object_dictionary.bitrate
                    break
        if self.bus is None:
            self.bus = can.Bus(*args, **kwargs)
        logger.info("Connected to '%s'", self.bus.channel_info)
        if self.notifier is None:
            # The notifier is started without setting the loop paramter, even
            # when running in async mode. The notifier changes in sublte ways
            # when the loop parameter is set. All callbacks via the Listener
            # interface will be called from the separate rx thread, which is
            # what canopen is designed for. The async mode of the notifier will
            # send all callbacks to the event loop thread, which is not
            # compatible with the blocking locks and queues used in canopen.
            self.notifier = can.Notifier(self.bus, self.listeners, self.NOTIFIER_CYCLE)
        return self

    def disconnect(self) -> None:
        """Disconnect from the CAN bus.

        Must be overridden in a subclass if a custom interface is used.
        """
        for node in self.nodes.values():
            if hasattr(node, "pdo"):
                node.pdo.stop()
        if self.notifier is not None:
            self.notifier.stop(self.NOTIFIER_SHUTDOWN_TIMEOUT)
        if self.bus is not None:
            self.bus.shutdown()
        self.bus = None
        try:
            self.check()
        finally:
            # Release notifier after check
            self.notifier = None

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.disconnect()

    async def __aenter__(self):
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
        else:
            if self.loop != asyncio.get_running_loop():
                raise RuntimeError("Network is running in a different event loop")
        self.thread_id = threading.get_ident()
        try:
            # Enter the async context for the taskgroup and leave it last
            await self.exit_stack.enter_async_context(self.taskgroup)
            # Cleanup the network
            self.exit_stack.callback(self.disconnect)
        except Exception:
            await self.exit_stack.aclose()
            raise
        return self

    async def __aexit__(self, type, value, traceback):
        # Cleanup by running the context managers in reverse order of entry.
        # Please see __aenter__ for list of contexts.
        return await self.exit_stack.__aexit__(type, value, traceback)

    @property
    def is_running_async(self) -> bool:
        """Check if canopen has been connected with async"""
        return self.loop is not None

    def add_node(
        self,
        node: Union[int, RemoteNode, LocalNode],
        object_dictionary: Union[str, ObjectDictionary, None] = None,
        upload_eds: bool = False,
    ) -> Union[RemoteNode, LocalNode]:
        """Add a remote node to the network.

        :param node:
            Can be either an integer representing the node ID, a
            :class:`canopen.RemoteNode` or :class:`canopen.LocalNode` object.
        :param object_dictionary:
            Can be either a string for specifying the path to an
            Object Dictionary file or a
            :class:`canopen.ObjectDictionary` object.
        :param upload_eds:
            Set ``True`` if EDS file should be uploaded from 0x1021.

            .. note::
                Using this option will fail in async mode, since uploading the
                EDS requires blocking SDO transfers during node setup. Use a
                pre-fetched ``object_dictionary`` instead when running under
                asyncio.

            Example of pre-fetching the object dictionary with async:

            .. code-block:: python

                od = await aimport_from_node(node_id, network)
                node = network.add_node(node_id, od)

        :return:
            The Node object that was added.
        """
        if isinstance(node, int):
            if upload_eds:
                logger.info("Trying to read EDS from node %d", node)
                object_dictionary = import_from_node(node, self)
            node = RemoteNode(node, object_dictionary)
        self[node.id] = node
        return node

    def create_node(
        self,
        node: Union[int, LocalNode],
        object_dictionary: Union[str, ObjectDictionary, None] = None,
    ) -> LocalNode:
        """Create a local node in the network.

        :param node:
            An integer representing the node ID.
        :param object_dictionary:
            Can be either a string for specifying the path to an
            Object Dictionary file or a
            :class:`canopen.ObjectDictionary` object.

        :return:
            The Node object that was added.
        """
        if isinstance(node, int):
            node = LocalNode(node, object_dictionary)
        self[node.id] = node
        return node

    def send_message(self, can_id: int, data: bytes, remote: bool = False) -> None:
        """Send a raw CAN message to the network.

        This method may be overridden in a subclass if you need to integrate
        this library with a custom backend.
        It is safe to call this from multiple threads.

        :param int can_id:
            CAN-ID of the message
        :param data:
            Data to be transmitted (anything that can be converted to bytes)
        :param bool remote:
            Set to True to send remote frame

        :raises can.CanError:
            When the message fails to be transmitted
        """
        if not self.bus:
            raise RuntimeError("Not connected to CAN bus")
        msg = can.Message(is_extended_id=can_id > 0x7FF,
                          arbitration_id=can_id,
                          data=data,
                          is_remote_frame=remote)
        with self.send_lock:
            self.bus.send(msg)
        self.check()

    def send_periodic(
        self, can_id: int, data: bytes, period: float, remote: bool = False
    ) -> PeriodicMessageTask:
        """Start sending a message periodically.

        :param can_id:
            CAN-ID of the message
        :param data:
            Data to be transmitted (anything that can be converted to bytes)
        :param period:
            Seconds between each message
        :param remote:
            indicates if the message frame is a remote request to the slave node

        :return:
            An task object with a ``.stop()`` method to stop the transmission
        """
        return PeriodicMessageTask(can_id, data, period, self.bus, remote)

    def notify(self, can_id: int, data: bytearray, timestamp: float) -> None:
        """Feed incoming message to this library.

        If a custom interface is used, this function must be called for each
        message read from the CAN bus.

        :param can_id:
            CAN-ID of the message
        :param data:
            Data part of the message (0 - 8 bytes)
        :param timestamp:
            Timestamp of the message, preferably as a Unix timestamp
        """
        if can_id in self.subscribers:
            self.dispatch_callbacks(self.subscribers[can_id], can_id, data, timestamp)
        self.scanner.on_message_received(can_id)

    def on_error(self, exc: BaseException, ignore_errors: Optional[bool] = None) -> None:
        """Handle any exception in the callbacks.

        With self.FILTER_ERRORS set to True, exceptions in callbacks will be logged
        only, and the program will continue running. This is useful for
        production systems where you want to log errors but not crash the
        entire application due to a single callback failure.

        With self.FILTER_ERRORS set to False, exceptions in callbacks will be raised,
        which will stop the program. This is useful for development and debugging,
        where you want to catch errors early and fix them. This is also
        important for unit tests, as only logging errors may hide problems.

        :param exc:
            The exception that was raised.
        :param ignore_errors:
            If True, exceptions in callbacks will be logged only, and the program
            will continue running. If False, exceptions in callbacks will be raised,
            which will stop the program. If None, the value of self.FILTER_ERRORS
        """
        logger.exception("Exception in callback", exc_info=exc)

        ignore = self.FILTER_ERRORS if ignore_errors is None else ignore_errors
        if not ignore:
            raise exc
        if not ignore_errors:
            # This is when ignore_errors is default None, and self.FILTER_ERRORS
            # must be True. We do not log when the user sets ingore_errors
            # to True.
            self.exceptions.append(exc)

    def dispatch_callbacks(self, callbacks: list[Callable], *args, **kwargs) -> None:
        """Dispatch a list of callbacks with the given arguments.

        :param callbacks:
            List of callbacks to call
        :param args:
            Arguments to pass to the callbacks
        :param kwargs:
            Keyword arguments to pass to the callbacks. The "ignore_errors"
            keyword argument can be used to override the default error handling
            behavior for this specific call. See :meth:`canopen.Network.on_error`
            for details.
        """
        ignore_errors = kwargs.pop("ignore_errors", None)
        for callback in callbacks:
            try:
                result = callback(*args, **kwargs)
                if result is not None and asyncio.iscoroutine(result):
                    if self.loop is None:
                        raise RuntimeError("Network is not running in async mode")

                    # Wrap the coroutine in this function to ensure the
                    # exceptions is either logged or raised, depending on the
                    # value of self.FILTER_ERRORS.
                    async def _error_handler(coro):
                        try:
                            return await coro
                        except Exception as e:
                            self.on_error(e, ignore_errors)

                    # Create the task
                    self.create_task(_error_handler(result))
            except Exception as e:
                self.on_error(e, ignore_errors)

    def create_task(self, coro: Coroutine, *args, **kwarge) -> asyncio.Task:
        """Create an async task.

        This function is thread-safe and can be called from any thread. If
        called from the same thread as the event loop, it will use
        :code:`asyncio.create_task()` directly. If called from a different
        thread, it will use :code:`asyncio.run_coroutine_threadsafe()` to
        schedule the task in the event loop.

        All tasks created with this function is managed by the task group
        in :attr:`canopen.Network.taskgroup`, which takes care of cleaning up
        the tasks when the network is closed and handles exceptions in the tasks.

        :param coro:
            The coroutine to run in the event loop.
        """
        if self.loop is None:
            raise RuntimeError("Network is not running in async mode")

        if threading.get_ident() == self.thread_id:
            # If we are running in the same thread as the event loop
            # asyncio.create_task() can be used directly.
            return self.taskgroup.create_task(coro, *args, **kwarge)

        else:
            # Running in a different thread.
            async def _create_task():
                return self.taskgroup.create_task(coro, *args, **kwarge)
            # Since this is another thread asyncio.get_running_loop() will
            # not work. We need to use the stored event loop.
            future = asyncio.run_coroutine_threadsafe(_create_task(), self.loop)
            # The result() will block until the _create_task() coroutine has
            # been executed and it returns the actual task object.
            return future.result()

    def check(self) -> None:
        """Check that no fatal error has occurred in the receiving thread.

        If an exception caused the thread to terminate, that exception will be
        raised.
        """
        # Swap the list of exceptions to make sure the exceptions is not reported again
        exceptions, self.exceptions = self.exceptions, []

        # Check if the notifier has an exception. This might be the case when
        # FILTER_ERRORS is False
        if self.notifier is not None and (exc := self.notifier.exception) is not None:
            exceptions.append(exc)

        if len(exceptions) == 1:
            logger.error("An error has caused receiving of messages to stop")
            raise exceptions[0]
        if len(exceptions) > 1:
            logger.error("%s errors have caused receiving of messages to stop", len(exceptions))
            raise ExceptionGroup("Multiple exceptions have occurred in callbacks", exceptions)

    def __getitem__(self, node_id: int) -> Union[RemoteNode, LocalNode]:
        return self.nodes[node_id]

    def __setitem__(self, node_id: int, node: Union[RemoteNode, LocalNode]):
        assert node_id == node.id
        if node_id in self.nodes:
            # Remove old callbacks
            self.nodes[node_id].remove_network()
        self.nodes[node_id] = node
        node.associate_network(self)

    def __delitem__(self, node_id: int):
        self.nodes[node_id].remove_network()
        del self.nodes[node_id]

    def __iter__(self) -> Iterator[int]:
        return iter(self.nodes)

    def __len__(self) -> int:
        return len(self.nodes)


class _UninitializedNetwork(Network):
    """Empty network implementation as a placeholder before actual initialization."""

    def __init__(self, bus: Optional[can.BusABC] = None):
        """Do not initialize attributes, by skipping the parent constructor."""

    def __getattribute__(self, name):
        raise RuntimeError("No actual Network object was assigned, "
                           "try associating to a real network first.")


#: Singleton instance
_UNINITIALIZED_NETWORK: Final[Network] = _UninitializedNetwork()


class PeriodicMessageTask:
    """
    Task object to transmit a message periodically using python-can's
    CyclicSendTask
    """

    def __init__(
        self,
        can_id: int,
        data: bytes,
        period: float,
        bus,
        remote: bool = False,
    ):
        """
        :param can_id:
            CAN-ID of the message
        :param data:
            Data to be transmitted (anything that can be converted to bytes)
        :param period:
            Seconds between each message
        :param can.BusABC bus:
            python-can bus to use for transmission
        """
        self.bus = bus
        self.period = period
        self.msg = can.Message(is_extended_id=can_id > 0x7FF,
                               arbitration_id=can_id,
                               data=data, is_remote_frame=remote)
        self._start()

    def _start(self):
        self._task = self.bus.send_periodic(self.msg, self.period)

    def stop(self):
        """Stop transmission"""
        self._task.stop()

    def update(self, data: bytes) -> None:
        """Update data of message

        :param data:
            New data to transmit
        """
        new_data = bytearray(data)
        old_data = self.msg.data
        self.msg.data = new_data
        if hasattr(self._task, "modify_data"):
            self._task.modify_data(self.msg)
        elif new_data != old_data:
            # Stop and start (will mess up period unfortunately)
            self._task.stop()
            self._start()


class MessageListener(can.Listener):
    """Listens for messages on CAN bus and feeds them to a Network instance.

    :param network:
        The network to notify on new messages.
    """

    def __init__(self, network: Network):
        self.network = network
        self._warning_logged = False

    def on_message_received(self, msg):

        if not self._warning_logged:
            self._warning_logged = True
            if is_async_guarded():
                logger.warning(
                    "MessageListener.on_message_received() called from async mainloop. "
                    "This may affect the async performance."
                )

        if msg.is_error_frame or msg.is_remote_frame:
            return

        try:
            self.network.notify(msg.arbitration_id, msg.data, msg.timestamp)
        except Exception as e:
            # Exceptions in any callbaks should not affect CAN processing
            self.network.on_error(e)

    def stop(self) -> None:
        """Override abstract base method to release any resources."""


class NodeScanner:
    """Observes which nodes are present on the bus.

    Listens for the following messages:
     - Heartbeat (0x700)
     - SDO response (0x580)
     - TxPDO (0x180, 0x280, 0x380, 0x480)
     - EMCY (0x80)

    :param canopen.Network network:
        The network to use when doing active searching.
    """

    SERVICES = (0x700, 0x580, 0x180, 0x280, 0x380, 0x480, 0x80)

    def __init__(self, network: Optional[Network] = None):
        if network is None:
            network = _UNINITIALIZED_NETWORK
        self.network: Network = network
        #: A :class:`list` of nodes discovered
        self.nodes: list[int] = []

    def on_message_received(self, can_id: int):
        service = can_id & 0x780
        node_id = can_id & 0x7F
        if node_id not in self.nodes and node_id != 0 and service in self.SERVICES:
            self.nodes.append(node_id)

    def reset(self):
        """Clear list of found nodes."""
        self.nodes = []

    def search(self, limit: int = 127) -> None:
        """Search for nodes by sending SDO requests to all node IDs."""
        sdo_req = b"\x40\x00\x10\x00\x00\x00\x00\x00"
        for node_id in range(1, limit + 1):
            self.network.send_message(0x600 + node_id, sdo_req)
