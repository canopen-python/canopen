import logging
import time
import unittest

import can

import canopen

from .util import SAMPLE_EDS


class TestNetwork(unittest.TestCase):

    def setUp(self):
        self.network = canopen.Network()
        self.network.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0

    def test_network_add_node(self):
        # Add using str.
        with self.assertLogs():
            node = self.network.add_node(2, SAMPLE_EDS)
        self.assertEqual(self.network[2], node)
        self.assertEqual(node.id, 2)
        self.assertIsInstance(node, canopen.RemoteNode)

        # Add using OD.
        node = self.network.add_node(3, self.network[2].object_dictionary)
        self.assertEqual(self.network[3], node)
        self.assertEqual(node.id, 3)
        self.assertIsInstance(node, canopen.RemoteNode)

        # Add using RemoteNode.
        with self.assertLogs():
            node = canopen.RemoteNode(4, SAMPLE_EDS)
        self.network.add_node(node)
        self.assertEqual(self.network[4], node)
        self.assertEqual(node.id, 4)
        self.assertIsInstance(node, canopen.RemoteNode)

        # Add using LocalNode.
        with self.assertLogs():
            node = canopen.LocalNode(5, SAMPLE_EDS)
        self.network.add_node(node)
        self.assertEqual(self.network[5], node)
        self.assertEqual(node.id, 5)
        self.assertIsInstance(node, canopen.LocalNode)

        # Verify that we've got the correct number of nodes.
        self.assertEqual(len(self.network), 4)

    def test_network_add_node_upload_eds(self):
        # Will err because we're not connected to a real network.
        with self.assertLogs(level=logging.ERROR):
            self.network.add_node(2, SAMPLE_EDS, upload_eds=True)

    def test_network_create_node(self):
        with self.assertLogs():
            self.network.create_node(2, SAMPLE_EDS)
            self.network.create_node(3, SAMPLE_EDS)
            node = canopen.RemoteNode(4, SAMPLE_EDS)
            self.network.create_node(node)
        self.assertIsInstance(self.network[2], canopen.LocalNode)
        self.assertIsInstance(self.network[3], canopen.LocalNode)
        self.assertIsInstance(self.network[4], canopen.RemoteNode)

    def test_network_check(self):
        self.network.connect(interface="virtual")

        def cleanup():
            # We must clear the fake exception installed below, since
            # .disconnect() implicitly calls .check() during test tear down.
            self.network.notifier.exception = None
            self.network.disconnect()

        self.addCleanup(cleanup)
        self.assertIsNone(self.network.check())

        class Custom(Exception):
            pass

        self.network.notifier.exception = Custom("fake")
        with self.assertRaisesRegex(Custom, "fake"):
            with self.assertLogs(level=logging.ERROR):
                self.network.check()
        with self.assertRaisesRegex(Custom, "fake"):
            with self.assertLogs(level=logging.ERROR):
                self.network.disconnect()

    def test_network_notify(self):
        with self.assertLogs():
            self.network.add_node(2, SAMPLE_EDS)
        node = self.network[2]
        self.network.notify(0x82, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1473418396.0)
        self.assertEqual(len(node.emcy.active), 1)
        self.network.notify(0x702, b'\x05', 1473418396.0)
        self.assertEqual(node.nmt.state, 'OPERATIONAL')
        self.assertListEqual(self.network.scanner.nodes, [2])

    def test_network_send_message(self):
        bus = can.interface.Bus(interface="virtual")
        self.addCleanup(bus.shutdown)

        self.network.connect(interface="virtual")
        self.addCleanup(self.network.disconnect)

        # Send standard ID
        self.network.send_message(0x123, [1, 2, 3, 4, 5, 6, 7, 8])
        msg = bus.recv(1)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.arbitration_id, 0x123)
        self.assertFalse(msg.is_extended_id)
        self.assertSequenceEqual(msg.data, [1, 2, 3, 4, 5, 6, 7, 8])

        # Send extended ID
        self.network.send_message(0x12345, [])
        msg = bus.recv(1)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.arbitration_id, 0x12345)
        self.assertTrue(msg.is_extended_id)

    def test_network_subscribe_unsubscribe(self):
        N_HOOKS = 3
        accumulators = [] * N_HOOKS

        self.network.connect(interface="virtual", receive_own_messages=True)
        self.addCleanup(self.network.disconnect)

        for i in range(N_HOOKS):
            accumulators.append([])
            def hook(*args, i=i):
                accumulators[i].append(args)
            self.network.subscribe(i, hook)

        self.network.notify(0, bytes([1, 2, 3]), 1000)
        self.network.notify(1, bytes([2, 3, 4]), 1001)
        self.network.notify(1, bytes([3, 4, 5]), 1002)
        self.network.notify(2, bytes([4, 5, 6]), 1003)

        self.assertEqual(accumulators[0], [(0, bytes([1, 2, 3]), 1000)])
        self.assertEqual(accumulators[1], [
            (1, bytes([2, 3, 4]), 1001),
            (1, bytes([3, 4, 5]), 1002),
        ])
        self.assertEqual(accumulators[2], [(2, bytes([4, 5, 6]), 1003)])

        self.network.unsubscribe(0)
        # Should not raise an error.
        self.network.unsubscribe(10)
        self.network.notify(0, bytes([7, 7, 7]), 1004)
        # Verify that no new data was added to the accumulator.
        self.assertEqual(accumulators[0], [(0, bytes([1, 2, 3]), 1000)])

    def test_network_subscribe_multiple(self):
        N_HOOKS = 3
        self.network.connect(interface="virtual", receive_own_messages=True)
        self.addCleanup(self.network.disconnect)

        accumulators = []
        hooks = []
        for i in range(N_HOOKS):
            accumulators.append([])
            def hook(*args, i=i):
                accumulators[i].append(args)
            hooks.append(hook)
            self.network.subscribe(0x20, hook)

        self.network.notify(0xaa, bytes([1, 1, 1]), 2000)
        self.network.notify(0x20, bytes([2, 3, 4]), 2001)
        self.network.notify(0xbb, bytes([2, 2, 2]), 2002)
        self.network.notify(0x20, bytes([3, 4, 5]), 2003)
        self.network.notify(0xcc, bytes([3, 3, 3]), 2004)

        BATCH1 = [
            (0x20, bytes([2, 3, 4]), 2001),
            (0x20, bytes([3, 4, 5]), 2003),
        ]
        for n, acc in enumerate(accumulators):
            with self.subTest(hook=n):
                self.assertEqual(acc, BATCH1)

        # Unsubscribe the second hook; dispatch a new message.
        self.network.unsubscribe(0x20, hooks[1])

        BATCH2 = 0x20, bytes([4, 5, 6]), 2005
        self.network.notify(*BATCH2)
        self.assertEqual(accumulators[0], BATCH1 + [BATCH2])
        self.assertEqual(accumulators[1], BATCH1)
        self.assertEqual(accumulators[2], BATCH1 + [BATCH2])

        # Unsubscribe the first hook; dispatch yet another message.
        self.network.unsubscribe(0x20, hooks[0])

        BATCH3 = 0x20, bytes([5, 6, 7]), 2006
        self.network.notify(*BATCH3)
        self.assertEqual(accumulators[0], BATCH1 + [BATCH2])
        self.assertEqual(accumulators[1], BATCH1)
        self.assertEqual(accumulators[2], BATCH1 + [BATCH2] + [BATCH3])

        # Unsubscribe the rest (only one remaining); dispatch a new message.
        self.network.unsubscribe(0x20)
        self.network.notify(0x20, bytes([7, 7, 7]), 2007)
        self.assertEqual(accumulators[0], BATCH1 + [BATCH2])
        self.assertEqual(accumulators[1], BATCH1)
        self.assertEqual(accumulators[2], BATCH1 + [BATCH2] + [BATCH3])

    def test_network_context_manager(self):
        with self.network.connect(interface="virtual"):
            pass
        with self.assertRaisesRegex(RuntimeError, "Not connected"):
            self.network.send_message(0, [])

    def test_network_item_access(self):
        with self.assertLogs():
            self.network.add_node(2, SAMPLE_EDS)
            self.network.add_node(3, SAMPLE_EDS)
        self.assertEqual([2, 3], [node for node in self.network])

        # Check __delitem__.
        del self.network[2]
        self.assertEqual([3], [node for node in self.network])
        with self.assertRaises(KeyError):
            del self.network[2]

        # Check __setitem__.
        old = self.network[3]
        with self.assertLogs():
            new = canopen.Node(3, SAMPLE_EDS)
        self.network[3] = new

        # Check __getitem__.
        self.assertNotEqual(self.network[3], old)
        self.assertEqual([3], [node for node in self.network])

    def test_network_send_periodic(self):
        DATA1 = bytes([1, 2, 3])
        DATA2 = bytes([4, 5, 6])
        COB_ID = 0x123
        PERIOD = 0.01
        TIMEOUT = PERIOD * 10
        self.network.connect(interface="virtual")
        self.addCleanup(self.network.disconnect)

        bus = can.Bus(interface="virtual")
        self.addCleanup(bus.shutdown)

        acc = []

        task = self.network.send_periodic(COB_ID, DATA1, PERIOD)
        self.addCleanup(task.stop)

        def wait_for_periodicity():
            # Check if periodicity is established; flakiness has been observed
            # on macOS.
            end_time = time.time() + TIMEOUT
            while time.time() < end_time:
                if msg := bus.recv(PERIOD):
                    acc.append(msg)
                if len(acc) >= 2:
                    first, last = acc[-2:]
                    delta = last.timestamp - first.timestamp
                    if round(delta, ndigits=2) == PERIOD:
                        return
            self.fail("Timed out")

        # Wait for frames to arrive; then check the result.
        wait_for_periodicity()
        self.assertTrue(all([v.data == DATA1 for v in acc]))

        # Update task data, which may implicitly restart the timer.
        # Wait for frames to arrive; then check the result.
        task.update(DATA2)
        acc.clear()
        wait_for_periodicity()
        # Find the first message with new data, and verify that all subsequent
        # messages also carry the new payload.
        data = [v.data for v in acc]
        self.assertIn(DATA2, data)
        idx = data.index(DATA2)
        self.assertTrue(all([v.data == DATA2 for v in acc[idx:]]))

        # Stop the task.
        task.stop()
        # A message may have been in flight when we stopped the timer,
        # so allow a single failure.
        bus = self.network.bus
        msg = bus.recv(PERIOD)
        if msg is not None:
            self.assertIsNone(bus.recv(PERIOD))


class TestScanner(unittest.TestCase):
    TIMEOUT = 0.1

    def setUp(self):
        self.scanner = canopen.network.NodeScanner()

    def test_scanner_on_message_received(self):
        # Emergency frames should be recognized.
        self.scanner.on_message_received(0x081)
        # Heartbeats should be recognized.
        self.scanner.on_message_received(0x703)
        # Tx PDOs should be recognized, but not Rx PDOs.
        self.scanner.on_message_received(0x185)
        self.scanner.on_message_received(0x206)
        self.scanner.on_message_received(0x287)
        self.scanner.on_message_received(0x308)
        self.scanner.on_message_received(0x389)
        self.scanner.on_message_received(0x40a)
        self.scanner.on_message_received(0x48b)
        self.scanner.on_message_received(0x50c)
        # SDO responses from .search() should be recognized,
        # but not SDO requests.
        self.scanner.on_message_received(0x58d)
        self.scanner.on_message_received(0x50e)
        self.assertListEqual(self.scanner.nodes, [1, 3, 5, 7, 9, 11, 13])

    def test_scanner_reset(self):
        self.scanner.nodes = [1, 2, 3]  # Mock scan.
        self.scanner.reset()
        self.assertListEqual(self.scanner.nodes, [])

    def test_scanner_search_no_network(self):
        with self.assertRaisesRegex(RuntimeError, "Network is required"):
            self.scanner.search()

    def test_scanner_search(self):
        rxbus = can.Bus(interface="virtual")
        self.addCleanup(rxbus.shutdown)

        txbus = can.Bus(interface="virtual")
        self.addCleanup(txbus.shutdown)

        net = canopen.Network(txbus)
        net.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        net.connect()
        self.addCleanup(net.disconnect)

        self.scanner.network = net
        self.scanner.search()

        payload = bytes([64, 0, 16, 0, 0, 0, 0, 0])
        acc = [rxbus.recv(self.TIMEOUT) for _ in range(127)]
        for node_id, msg in enumerate(acc, start=1):
            with self.subTest(node_id=node_id):
                self.assertIsNotNone(msg)
                self.assertEqual(msg.arbitration_id, 0x600 + node_id)
                self.assertEqual(msg.data, payload)
        # Check that no spurious packets were sent.
        self.assertIsNone(rxbus.recv(self.TIMEOUT))

    def test_scanner_search_limit(self):
        bus = can.Bus(interface="virtual", receive_own_messages=True)
        net = canopen.Network(bus)
        net.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        net.connect()
        self.addCleanup(net.disconnect)

        self.scanner.network = net
        self.scanner.search(limit=1)

        msg = bus.recv(self.TIMEOUT)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.arbitration_id, 0x601)
        # Check that no spurious packets were sent.
        self.assertIsNone(bus.recv(self.TIMEOUT))


if __name__ == "__main__":
    unittest.main()
