import unittest
import asyncio

import canopen


class BaseTests:

    class TestTime(unittest.IsolatedAsyncioTestCase):

        use_async: bool

        def setUp(self):
            self.loop = None
            if self.use_async:
                self.loop = asyncio.get_event_loop()

        async def test_time_producer(self):
            network = canopen.Network(loop=self.loop)
            self.addCleanup(network.disconnect)
            network.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
            network.connect(interface="virtual", receive_own_messages=True)
            producer = canopen.timestamp.TimeProducer(network)
            producer.transmit(1486236238)
            msg = network.bus.recv(1)
            network.disconnect()
            self.assertEqual(msg.arbitration_id, 0x100)
            self.assertEqual(msg.dlc, 6)
            self.assertEqual(msg.data, b"\xb0\xa4\x29\x04\x31\x43")


class TestTimeSync(BaseTests.TestTime):
    use_async = False


class TestTimeAsync(BaseTests.TestTime):
    use_async = True


if __name__ == "__main__":
    unittest.main()
