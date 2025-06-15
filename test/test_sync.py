import threading
import unittest
import asyncio

import can

import canopen


PERIOD = 0.01
TIMEOUT = PERIOD * 10


class TestSync(unittest.IsolatedAsyncioTestCase):

    __test__ = False  # This is a base class, tests should not be run directly.
    use_async: bool

    def setUp(self):
        loop = None
        if self.use_async:
            loop = asyncio.get_event_loop()

        self.net = canopen.Network(loop=loop)
        self.net.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.net.connect(interface="virtual")
        self.sync = canopen.sync.SyncProducer(self.net)
        self.rxbus = can.Bus(interface="virtual", loop=loop)

    def tearDown(self):
        self.net.disconnect()
        self.rxbus.shutdown()

    async def test_sync_producer_transmit(self):
        self.sync.transmit()
        msg = self.rxbus.recv(TIMEOUT)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.arbitration_id, 0x80)
        self.assertEqual(msg.dlc, 0)

    async def test_sync_producer_transmit_count(self):
        self.sync.transmit(2)
        msg = self.rxbus.recv(TIMEOUT)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.arbitration_id, 0x80)
        self.assertEqual(msg.dlc, 1)
        self.assertEqual(msg.data, b"\x02")

    async def test_sync_producer_start_invalid_period(self):
        with self.assertRaises(ValueError):
            self.sync.start(0)

    async def test_sync_producer_start(self):
        self.sync.start(PERIOD)
        self.addCleanup(self.sync.stop)

        acc = []
        condition = threading.Condition()

        def hook(id_, data, ts):
            item = id_, data, ts
            acc.append(item)
            condition.notify()

        def periodicity():
            # Check if periodicity has been established.
            if len(acc) > 2:
                delta = acc[-1][2] - acc[-2][2]
                return round(delta, ndigits=1) == PERIOD

        # Sample messages.
        with condition:
            condition.wait_for(periodicity, TIMEOUT)
        for msg in acc:
            self.assertIsNotNone(msg)
            self.assertEqual(msg[0], 0x80)
            self.assertEqual(msg[1], b"")

        self.sync.stop()
        # A message may have been in flight when we stopped the timer,
        # so allow a single failure.
        msg = self.rxbus.recv(TIMEOUT)
        if msg is not None:
            self.assertIsNone(self.net.bus.recv(TIMEOUT))


class TestSyncSync(TestSync):
    """ Test the functions in synchronous mode. """
    __test__ = True
    use_async = False


class TestSyncAsync(TestSync):
    """ Test the functions in asynchronous mode. """
    __test__ = True
    use_async = True


if __name__ == "__main__":
    unittest.main()
