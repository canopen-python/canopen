import time
import unittest
from datetime import datetime
from unittest.mock import patch

import canopen
import canopen.timestamp


class TestTime(unittest.TestCase):

    def test_time_producer(self):
        network = canopen.Network()
        network.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        network.connect(interface="virtual", receive_own_messages=True)
        producer = canopen.timestamp.TimeProducer(network)

        # Test that the epoch is correct
        epoch = datetime.strptime(
            "1984-01-01 00:00:00 +0000", "%Y-%m-%d %H:%M:%S %z"
        ).timestamp()
        self.assertEqual(int(epoch), canopen.timestamp.OFFSET)

        current = time.time()
        with patch("canopen.timestamp.time.time", return_value=current):
            current_in_epoch = current - epoch

            # Test it looking up the current time
            producer.transmit()
            msg = network.bus.recv(1)
            self.assertEqual(msg.arbitration_id, 0x100)
            self.assertEqual(msg.dlc, 6)
            ms, days = canopen.timestamp.TIME_OF_DAY_STRUCT.unpack(msg.data)
            self.assertEqual(days, int(current_in_epoch) // canopen.timestamp.ONE_DAY)
            self.assertEqual(ms, int((current_in_epoch % canopen.timestamp.ONE_DAY) * 1000))

            # Provide a specific time to verify the proper encoding
            faketime = 1_927_999_438  # 2031-02-04 19:23:58
            producer.transmit(faketime)
            msg = network.bus.recv(1)
            self.assertEqual(msg.arbitration_id, 0x100)
            self.assertEqual(msg.dlc, 6)
            self.assertEqual(msg.data, b"\xb0\xa4\x29\x04\x31\x43")

        network.disconnect()


if __name__ == "__main__":
    unittest.main()
