import threading
import time
import unittest
import asyncio

import can

import canopen
from canopen.async_guard import AllowBlocking
from canopen.nmt import COMMAND_TO_STATE, NMT_COMMANDS, NMT_STATES, NmtError

from .util import SAMPLE_EDS


class TestNmtBase(unittest.TestCase):

    def setUp(self):
        node_id = 2
        self.node_id = node_id
        self.nmt = canopen.nmt.NmtBase(node_id)

    def test_send_command(self):
        dataset = (
            "OPERATIONAL",
            "PRE-OPERATIONAL",
            "SLEEP",
            "STANDBY",
            "STOPPED",
        )
        for cmd in dataset:
            with self.subTest(cmd=cmd):
                code = NMT_COMMANDS[cmd]
                self.nmt.send_command(code)
                expected = NMT_STATES[COMMAND_TO_STATE[code]]
                self.assertEqual(self.nmt.state, expected)

    def test_state_getset(self):
        for state in NMT_STATES.values():
            with self.subTest(state=state):
                self.nmt.state = state
                self.assertEqual(self.nmt.state, state)

    def test_state_set_invalid(self):
        with self.assertRaisesRegex(ValueError, "INVALID"):
            self.nmt.state = "INVALID"


class TestNmtMaster(unittest.IsolatedAsyncioTestCase):
    NODE_ID = 2
    PERIOD = 0.01
    TIMEOUT = PERIOD * 10

    __test__ = False  # This is a base class, tests should not be run directly.
    use_async: bool

    def setUp(self):
        loop = None
        if self.use_async:
            loop = asyncio.get_event_loop()

        net = canopen.Network(loop=loop)
        net.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        net.connect(interface="virtual")
        with self.assertLogs():
            with AllowBlocking():
                node = net.add_node(self.NODE_ID, SAMPLE_EDS)

        self.bus = can.Bus(interface="virtual", loop=loop)
        self.net = net
        self.node = node

    def tearDown(self):
        self.net.disconnect()
        self.bus.shutdown()

    def dispatch_heartbeat(self, code):
        cob_id = 0x700 + self.NODE_ID
        hb = can.Message(arbitration_id=cob_id, data=[code])
        self.bus.send(hb)

    async def test_nmt_master_no_heartbeat(self):
        with self.assertRaisesRegex(NmtError, "heartbeat"):
            if self.use_async:
                await self.node.nmt.await_for_heartbeat(self.TIMEOUT)
            else:
                self.node.nmt.wait_for_heartbeat(self.TIMEOUT)
        with self.assertRaisesRegex(NmtError, "boot-up"):
            if self.use_async:
                await self.node.nmt.await_for_bootup(self.TIMEOUT)
            else:
                self.node.nmt.wait_for_bootup(self.TIMEOUT)

    async def test_nmt_master_on_heartbeat(self):
        # Skip the special INITIALISING case.
        for code in [st for st in NMT_STATES if st != 0]:
            with self.subTest(code=code):
                t = threading.Timer(0.01, self.dispatch_heartbeat, args=(code,))
                t.start()
                self.addCleanup(t.join)
                if self.use_async:
                    actual = await self.node.nmt.await_for_heartbeat(0.1)
                else:
                    actual = self.node.nmt.wait_for_heartbeat(0.1)
                expected = NMT_STATES[code]
                self.assertEqual(actual, expected)

    async def test_nmt_master_wait_for_bootup(self):
        t = threading.Timer(0.01, self.dispatch_heartbeat, args=(0x00,))
        t.start()
        self.addCleanup(t.join)
        if self.use_async:
            await self.node.nmt.await_for_bootup(self.TIMEOUT)
        else:
            self.node.nmt.wait_for_bootup(self.TIMEOUT)
        self.assertEqual(self.node.nmt.state, "PRE-OPERATIONAL")

    async def test_nmt_master_on_heartbeat_initialising(self):
        t = threading.Timer(0.01, self.dispatch_heartbeat, args=(0x00,))
        t.start()
        self.addCleanup(t.join)
        if self.use_async:
            state = await self.node.nmt.await_for_heartbeat(self.TIMEOUT)
        else:
            state = self.node.nmt.wait_for_heartbeat(self.TIMEOUT)
        self.assertEqual(state, "PRE-OPERATIONAL")

    async def test_nmt_master_on_heartbeat_unknown_state(self):
        t = threading.Timer(0.01, self.dispatch_heartbeat, args=(0xcb,))
        t.start()
        self.addCleanup(t.join)
        if self.use_async:
            state = await self.node.nmt.await_for_heartbeat(self.TIMEOUT)
        else:
            state = self.node.nmt.wait_for_heartbeat(self.TIMEOUT)
        # Expect the high bit to be masked out, and a formatted string to
        # be returned.
        self.assertEqual(state, "UNKNOWN STATE '75'")

    async def test_nmt_master_add_heartbeat_callback(self):
        event = threading.Event()
        state = None
        def hook(st):
            nonlocal state
            state = st
            event.set()
        self.node.nmt.add_heartbeat_callback(hook)

        self.dispatch_heartbeat(0x7f)
        if self.use_async:
            await asyncio.to_thread(event.wait, self.TIMEOUT)
        else:
            self.assertTrue(event.wait(self.TIMEOUT))
        self.assertEqual(state, 127)

    async def test_nmt_master_node_guarding(self):
        self.node.nmt.start_node_guarding(self.PERIOD)
        msg = self.bus.recv(self.TIMEOUT)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.arbitration_id, 0x700 + self.NODE_ID)
        self.assertEqual(msg.dlc, 0)

        self.node.nmt.stop_node_guarding()
        # A message may have been in flight when we stopped the timer,
        # so allow a single failure.
        msg = self.bus.recv(self.TIMEOUT)
        if msg is not None:
            self.assertIsNone(self.bus.recv(self.TIMEOUT))


class TestNmtMasterSync(TestNmtMaster):
    """ Run tests in non-asynchronous mode. """
    __test__ = True
    use_async = False


class TestNmtMasterAsync(TestNmtMaster):
    """ Run tests in asynchronous mode. """
    __test__ = True
    use_async = True


class TestNmtSlave(unittest.IsolatedAsyncioTestCase):

    __test__ = False  # This is a base class, tests should not be run directly.
    use_async: bool

    def setUp(self):
        loop = None
        if self.use_async:
            loop = asyncio.get_event_loop()

        self.network1 = canopen.Network(loop=loop)
        self.network1.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.network1.connect("test", interface="virtual")
        with self.assertLogs():
            with AllowBlocking():
                self.remote_node = self.network1.add_node(2, SAMPLE_EDS)

        self.network2 = canopen.Network(loop=loop)
        self.network2.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.network2.connect("test", interface="virtual")
        with self.assertLogs():
            self.local_node = self.network2.create_node(2, SAMPLE_EDS)
            with AllowBlocking():
                self.remote_node2 = self.network1.add_node(3, SAMPLE_EDS)
            self.local_node2 = self.network2.create_node(3, SAMPLE_EDS)

    def tearDown(self):
        self.network1.disconnect()
        self.network2.disconnect()

    async def test_start_two_remote_nodes(self):
        self.remote_node.nmt.state = "OPERATIONAL"
        # Line below is just so that we are sure the client have received the command
        # before we do the check
        if self.use_async:
            await asyncio.sleep(0.1)
        else:
            time.sleep(0.1)
        slave_state = self.local_node.nmt.state
        self.assertEqual(slave_state, "OPERATIONAL")

        self.remote_node2.nmt.state = "OPERATIONAL"
        # Line below is just so that we are sure the client have received the command
        # before we do the check
        if self.use_async:
            await asyncio.sleep(0.1)
        else:
            time.sleep(0.1)
        slave_state = self.local_node2.nmt.state
        self.assertEqual(slave_state, "OPERATIONAL")

    async def test_stop_two_remote_nodes_using_broadcast(self):
        # This is a NMT broadcast "Stop remote node"
        # ie. set the node in STOPPED state
        self.network1.send_message(0, [2, 0])

        # Line below is just so that we are sure the slaves have received the command
        # before we do the check
        if self.use_async:
            await asyncio.sleep(0.1)
        else:
            time.sleep(0.1)
        slave_state = self.local_node.nmt.state
        self.assertEqual(slave_state, "STOPPED")
        slave_state = self.local_node2.nmt.state
        self.assertEqual(slave_state, "STOPPED")

    async def test_heartbeat(self):
        self.assertEqual(self.remote_node.nmt.state, "INITIALISING")
        self.assertEqual(self.local_node.nmt.state, "INITIALISING")
        self.local_node.nmt.state = "OPERATIONAL"
        if self.use_async:
            await self.local_node.sdo[0x1017].aset_raw(100)
            await asyncio.sleep(0.2)
        else:
            self.local_node.sdo[0x1017].raw = 100
            time.sleep(0.2)
        self.assertEqual(self.remote_node.nmt.state, "OPERATIONAL")

        self.local_node.nmt.stop_heartbeat()


class TestNmtSlaveSync(TestNmtSlave):
    """ Run tests in non-asynchronous mode. """
    __test__ = True
    use_async = False


class TestNmtSlaveAsync(TestNmtSlave):
    """ Run tests in asynchronous mode. """
    __test__ = True
    use_async = True


if __name__ == "__main__":
    unittest.main()
