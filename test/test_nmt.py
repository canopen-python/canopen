import threading
import time
import unittest

import can
import canopen
from canopen.nmt import COMMAND_TO_STATE, NMT_STATES, NMT_COMMANDS, NmtError
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


class TestNmtMaster(unittest.TestCase):
    NODE_ID = 2
    PERIOD = 0.01
    TIMEOUT = PERIOD * 10

    def setUp(self):
        net = canopen.Network()
        net.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        net.connect(interface="virtual")
        with self.assertLogs():
            node = net.add_node(self.NODE_ID, SAMPLE_EDS)

        self.bus = can.Bus(interface="virtual")
        self.net = net
        self.node = node

    def tearDown(self):
        self.net.disconnect()
        self.bus.shutdown()

    def dispatch_heartbeat(self, code):
        cob_id = 0x700 + self.NODE_ID
        hb = can.Message(arbitration_id=cob_id, data=[code])
        self.bus.send(hb)

    def test_nmt_master_no_heartbeat(self):
        with self.assertRaisesRegex(NmtError, "heartbeat"):
            self.node.nmt.wait_for_heartbeat(self.TIMEOUT)
        with self.assertRaisesRegex(NmtError, "boot-up"):
            self.node.nmt.wait_for_bootup(self.TIMEOUT)

    def test_nmt_master_on_heartbeat(self):
        # Skip the special INITIALISING case.
        for code in [st for st in NMT_STATES if st != 0]:
            with self.subTest(code=code):
                t = threading.Timer(0.01, self.dispatch_heartbeat, args=(code,))
                t.start()
                self.addCleanup(t.join)
                actual = self.node.nmt.wait_for_heartbeat(0.1)
                expected = NMT_STATES[code]
                self.assertEqual(actual, expected)

    def test_nmt_master_wait_for_bootup(self):
        t = threading.Timer(0.01, self.dispatch_heartbeat, args=(0x00,))
        t.start()
        self.addCleanup(t.join)
        self.node.nmt.wait_for_bootup(self.TIMEOUT)
        self.assertEqual(self.node.nmt.state, "PRE-OPERATIONAL")

    def test_nmt_master_on_heartbeat_initialising(self):
        t = threading.Timer(0.01, self.dispatch_heartbeat, args=(0x00,))
        t.start()
        self.addCleanup(t.join)
        state = self.node.nmt.wait_for_heartbeat(self.TIMEOUT)
        self.assertEqual(state, "PRE-OPERATIONAL")

    def test_nmt_master_on_heartbeat_unknown_state(self):
        t = threading.Timer(0.01, self.dispatch_heartbeat, args=(0xcb,))
        t.start()
        self.addCleanup(t.join)
        state = self.node.nmt.wait_for_heartbeat(self.TIMEOUT)
        # Expect the high bit to be masked out, and a formatted string to
        # be returned.
        self.assertEqual(state, "UNKNOWN STATE '75'")

    def test_nmt_master_add_heartbeat_callback(self):
        event = threading.Event()
        state = None
        def hook(st):
            nonlocal state
            state = st
            event.set()
        self.node.nmt.add_heartbeat_callback(hook)

        self.dispatch_heartbeat(0x7f)
        self.assertTrue(event.wait(self.TIMEOUT))
        self.assertEqual(state, 127)

    def test_nmt_master_node_guarding(self):
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


class TestNmtSlave(unittest.TestCase):
    def setUp(self):
        self.network1 = canopen.Network()
        self.network1.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.network1.connect("test", interface="virtual")
        with self.assertLogs():
            self.remote_node = self.network1.add_node(2, SAMPLE_EDS)

        self.network2 = canopen.Network()
        self.network2.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.network2.connect("test", interface="virtual")
        with self.assertLogs():
            self.local_node = self.network2.create_node(2, SAMPLE_EDS)
            self.remote_node2 = self.network1.add_node(3, SAMPLE_EDS)
            self.local_node2 = self.network2.create_node(3, SAMPLE_EDS)

    def tearDown(self):
        self.network1.disconnect()
        self.network2.disconnect()

    def test_start_two_remote_nodes(self):
        self.remote_node.nmt.state = "OPERATIONAL"
        # Line below is just so that we are sure the client have received the command
        # before we do the check
        time.sleep(0.1)
        slave_state = self.local_node.nmt.state
        self.assertEqual(slave_state, "OPERATIONAL")

        self.remote_node2.nmt.state = "OPERATIONAL"
        # Line below is just so that we are sure the client have received the command
        # before we do the check
        time.sleep(0.1)
        slave_state = self.local_node2.nmt.state
        self.assertEqual(slave_state, "OPERATIONAL")

    def test_stop_two_remote_nodes_using_broadcast(self):
        # This is a NMT broadcast "Stop remote node"
        # ie. set the node in STOPPED state
        self.network1.send_message(0, [2, 0])

        # Line below is just so that we are sure the slaves have received the command
        # before we do the check
        time.sleep(0.1)
        slave_state = self.local_node.nmt.state
        self.assertEqual(slave_state, "STOPPED")
        slave_state = self.local_node2.nmt.state
        self.assertEqual(slave_state, "STOPPED")

    def test_heartbeat(self):
        self.assertEqual(self.remote_node.nmt.state, "INITIALISING")
        self.assertEqual(self.local_node.nmt.state, "INITIALISING")
        self.local_node.nmt.state = "OPERATIONAL"
        self.local_node.sdo[0x1017].raw = 100
        time.sleep(0.2)
        self.assertEqual(self.remote_node.nmt.state, "OPERATIONAL")

        self.local_node.nmt.stop_heartbeat()


if __name__ == "__main__":
    unittest.main()
