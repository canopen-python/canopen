import logging
import threading
import unittest
from contextlib import contextmanager

import can

import canopen


TIMEOUT = 0.1


@contextmanager
def mock_rx_thread(consumer: canopen.emcy.EmcyConsumer, func):
    t = threading.Thread(target=func)
    try:
        with consumer.emcy_received:
            t.start()
            yield t
    finally:
        t.join(TIMEOUT)


class TestEmcy(unittest.TestCase):

    def check_error(self, err, code, reg, data, ts):
        self.assertIsInstance(err, canopen.emcy.EmcyError)
        self.assertIsInstance(err, Exception)
        self.assertEqual(err.code, code)
        self.assertEqual(err.register, reg)
        self.assertEqual(err.data, data)
        self.assertAlmostEqual(err.timestamp, ts)

    def test_emcy_consumer_on_emcy(self):
        """Make sure multiple callbacks receive the same information."""
        emcy = canopen.emcy.EmcyConsumer()
        acc1 = []
        acc2 = []
        emcy.add_callback(lambda err: acc1.append(err))
        emcy.add_callback(lambda err: acc2.append(err))

        emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)

        self.assertEqual(len(emcy.log), 1)
        self.assertEqual(len(emcy.active), 1)

        error = emcy.log[0]
        self.assertEqual(emcy.active[0], error)
        for err in error, acc1[0], acc2[0]:
            self.check_error(
                error, code=0x2001, reg=0x02,
                data=bytes([0, 1, 2, 3, 4]), ts=1000,
            )

        emcy.on_emcy(0x81, b'\x10\x90\x01\x04\x03\x02\x01\x00', 2000)
        self.assertEqual(len(emcy.log), 2)
        self.assertEqual(len(emcy.active), 2)

        error = emcy.log[1]
        self.assertEqual(emcy.active[1], error)
        for err in error, acc1[1], acc2[1]:
            self.check_error(
                error, code=0x9010, reg=0x01,
                data=bytes([4, 3, 2, 1, 0]), ts=2000,
            )

        emcy.on_emcy(0x81, b'\x00\x00\x00\x00\x00\x00\x00\x00', 2000)
        self.assertEqual(len(emcy.log), 3)
        self.assertEqual(len(emcy.active), 0)

    def test_emcy_consumer_reset(self):
        emcy = canopen.emcy.EmcyConsumer()
        emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)
        emcy.on_emcy(0x81, b'\x10\x90\x01\x04\x03\x02\x01\x00', 2000)
        self.assertEqual(len(emcy.log), 2)
        self.assertEqual(len(emcy.active), 2)

        emcy.reset()
        self.assertEqual(len(emcy.log), 0)
        self.assertEqual(len(emcy.active), 0)

    def test_emcy_consumer_wait(self):
        emcy = canopen.emcy.EmcyConsumer()

        def push_err():
            emcy.on_emcy(0x81, b'\x01\x20\x01\x01\x02\x03\x04\x05', 100)

        def check_err(err):
            self.assertIsNotNone(err)
            self.check_error(
                err, code=0x2001, reg=1,
                data=bytes([1, 2, 3, 4, 5]), ts=100,
            )

        # Check unfiltered wait, on timeout.
        self.assertIsNone(emcy.wait(timeout=TIMEOUT))

        # Check unfiltered wait, on success.
        with (
            self.assertLogs(level=logging.INFO),
            mock_rx_thread(emcy, push_err),
        ):
            check_err(emcy.wait(timeout=TIMEOUT))

        # Check filtered wait, on success.
        with (
            self.assertLogs(level=logging.INFO),
            mock_rx_thread(emcy, push_err),
        ):
            check_err(emcy.wait(0x2001, TIMEOUT))

        # Check filtered wait, on timeout.
        with mock_rx_thread(emcy, push_err):
            self.assertIsNone(emcy.wait(0x9000, TIMEOUT))

        def push_reset():
            emcy.on_emcy(0x81, b'\x00\x00\x00\x00\x00\x00\x00\x00', 100)

        with mock_rx_thread(emcy, push_reset):
            self.assertIsNone(emcy.wait(0x9000, TIMEOUT))

    def test_emcy_consumer_multiple_callbacks(self):
        """Test adding multiple callbacks and their execution order."""
        emcy = canopen.emcy.EmcyConsumer()
        call_order = []
        emcy.add_callback(lambda err: call_order.append('callback1'))
        emcy.add_callback(lambda err: call_order.append('callback2'))
        emcy.add_callback(lambda err: call_order.append('callback3'))
        emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)
        self.assertEqual(call_order, ['callback1', 'callback2', 'callback3'])

    def test_emcy_consumer_callback_exception_handling(self):
        """Test that callback exceptions don't break other callbacks or the system."""
        emcy = canopen.emcy.EmcyConsumer()
        successful_callbacks = []
        emcy.add_callback(lambda err: successful_callbacks.append('success1'))
        emcy.add_callback(
            lambda err: exec('raise ValueError("Test exception in callback")')
        )
        emcy.add_callback(lambda err: successful_callbacks.append('success2'))
        emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)
        self.assertEqual(successful_callbacks, ['success1', 'success2'])

    def test_emcy_consumer_error_reset_variants(self):
        """Test different error reset code patterns."""
        emcy = canopen.emcy.EmcyConsumer()
        emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)
        emcy.on_emcy(0x81, b'\x10\x90\x01\x04\x03\x02\x01\x00', 2000)
        self.assertEqual(len(emcy.active), 2)
        emcy.on_emcy(0x81, b'\x00\x00\x00\x00\x00\x00\x00\x00', 3000)
        self.assertEqual(len(emcy.active), 0)
        emcy.on_emcy(0x81, b'\x01\x30\x02\x00\x01\x02\x03\x04', 4000)
        self.assertEqual(len(emcy.active), 1)
        emcy.on_emcy(0x81, b'\x99\x00\x01\x00\x00\x00\x00\x00', 5000)
        self.assertEqual(len(emcy.active), 0)

    def test_emcy_consumer_wait_timeout_edge_cases(self):
        """Test wait method with various timeout scenarios."""
        emcy = canopen.emcy.EmcyConsumer()
        result = emcy.wait(timeout=0)
        self.assertIsNone(result)
        result = emcy.wait(timeout=0.001)
        self.assertIsNone(result)

    def test_emcy_consumer_wait_concurrent_errors(self):
        """Test wait method when multiple errors arrive concurrently."""
        emcy = canopen.emcy.EmcyConsumer()

        def push_multiple_errors():
            emcy.on_emcy(0x81, b'\x01\x20\x01\x01\x02\x03\x04\x05', 100)
            emcy.on_emcy(0x81, b'\x02\x20\x01\x01\x02\x03\x04\x05', 101)
            emcy.on_emcy(0x81, b'\x03\x20\x01\x01\x02\x03\x04\x05', 102)

        with (
            self.assertLogs(level=logging.INFO),
            mock_rx_thread(emcy, push_multiple_errors),
        ):
            err = emcy.wait(0x2003, timeout=TIMEOUT)
        self.assertIsNotNone(err)
        self.assertEqual(err.code, 0x2003)


class TestEmcyError(unittest.TestCase):

    def test_emcy_error(self):
        error = canopen.emcy.EmcyError(0x2001, 0x02, b'\x00\x01\x02\x03\x04', 1000)
        self.assertEqual(error.code, 0x2001)
        self.assertEqual(error.data, b'\x00\x01\x02\x03\x04')
        self.assertEqual(error.register, 2)
        self.assertEqual(error.timestamp, 1000)

    def test_emcy_str(self):
        def check(code, expected):
            err = canopen.emcy.EmcyError(code, 1, b'', 1000)
            actual = str(err)
            self.assertEqual(actual, expected)

        check(0x2001, "Code 0x2001, Current")
        check(0x3abc, "Code 0x3ABC, Voltage")
        check(0x0234, "Code 0x0234")
        check(0xbeef, "Code 0xBEEF")

    def test_emcy_get_desc(self):
        def check(code, expected):
            err = canopen.emcy.EmcyError(code, 1, b'', 1000)
            actual = err.get_desc()
            self.assertEqual(actual, expected)

        check(0x0000, "Error Reset / No Error")
        check(0x00ff, "Error Reset / No Error")
        check(0x0100, "")
        check(0x1000, "Generic Error")
        check(0x10ff, "Generic Error")
        check(0x1100, "")
        check(0x2000, "Current")
        check(0x2fff, "Current")
        check(0x3000, "Voltage")
        check(0x3fff, "Voltage")
        check(0x4000, "Temperature")
        check(0x4fff, "Temperature")
        check(0x5000, "Device Hardware")
        check(0x50ff, "Device Hardware")
        check(0x5100, "")
        check(0x6000, "Device Software")
        check(0x6fff, "Device Software")
        check(0x7000, "Additional Modules")
        check(0x70ff, "Additional Modules")
        check(0x7100, "")
        check(0x8000, "Monitoring")
        check(0x8fff, "Monitoring")
        check(0x9000, "External Error")
        check(0x90ff, "External Error")
        check(0x9100, "")
        check(0xf000, "Additional Functions")
        check(0xf0ff, "Additional Functions")
        check(0xf100, "")
        check(0xff00, "Device Specific")
        check(0xffff, "Device Specific")


class TestEmcyProducer(unittest.TestCase):

    def setUp(self):
        self.txbus = can.Bus(interface="virtual")
        self.rxbus = can.Bus(interface="virtual")
        self.net = canopen.Network(self.txbus)
        self.net.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.net.connect()
        self.emcy = canopen.emcy.EmcyProducer(0x80 + 1)
        self.emcy.network = self.net

    def tearDown(self):
        self.net.disconnect()
        self.txbus.shutdown()
        self.rxbus.shutdown()

    def check_response(self, expected):
        msg = self.rxbus.recv(TIMEOUT)
        assert msg is not None
        actual = msg.data
        self.assertEqual(actual, expected)

    def test_emcy_producer_send(self):
        def check(*args, res):
            self.emcy.send(*args)
            self.check_response(res)

        check(0x2001, res=b'\x01\x20\x00\x00\x00\x00\x00\x00')
        check(0x2001, 0x2, res=b'\x01\x20\x02\x00\x00\x00\x00\x00')
        check(0x2001, 0x2, b'\x2a', res=b'\x01\x20\x02\x2a\x00\x00\x00\x00')

    def test_emcy_producer_reset(self):
        def check(*args, res):
            self.emcy.reset(*args)
            self.check_response(res)

        check(res=b'\x00\x00\x00\x00\x00\x00\x00\x00')
        check(3, res=b'\x00\x00\x03\x00\x00\x00\x00\x00')
        check(3, b"\xaa\xbb", res=b'\x00\x00\x03\xaa\xbb\x00\x00\x00')

    def test_emcy_producer_send_edge_cases(self):
        self.emcy.send(0xFFFF, 0xFF, b'\xFF\xFF\xFF\xFF\xFF')
        self.check_response(b'\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF')
        self.emcy.send(0x0000, 0x00)
        self.check_response(b'\x00\x00\x00\x00\x00\x00\x00\x00')
        self.emcy.send(0x1234, 0x56, b'\xAB\xCD')
        self.check_response(b'\x34\x12\x56\xAB\xCD\x00\x00\x00')
        self.emcy.send(0x1234, 0x56, b'\xAB\xCD\xEF\x12\x34')
        self.check_response(b'\x34\x12\x56\xAB\xCD\xEF\x12\x34')

    def test_emcy_producer_reset_edge_cases(self):
        self.emcy.reset(0xFF)
        self.check_response(b'\x00\x00\xFF\x00\x00\x00\x00\x00')
        self.emcy.reset(0xFF, b'\xFF\xFF\xFF\xFF\xFF')
        self.check_response(b'\x00\x00\xFF\xFF\xFF\xFF\xFF\xFF')
        self.emcy.reset(0x12, b'\xAB\xCD')
        self.check_response(b'\x00\x00\x12\xAB\xCD\x00\x00\x00')


class TestEmcyIntegration(unittest.TestCase):
    """Integration tests for EMCY producer and consumer."""

    def setUp(self):
        self.txbus = can.Bus(interface="virtual")
        self.rxbus = can.Bus(interface="virtual")
        self.net = canopen.Network(self.txbus)
        self.net.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.net.connect()
        self.rx_net = canopen.Network(self.rxbus)
        self.rx_net.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.rx_net.connect()
        self.producer = canopen.emcy.EmcyProducer(0x081)
        self.producer.network = self.net
        self.consumer = canopen.emcy.EmcyConsumer()
        self.rx_net.subscribe(0x081, self.consumer.on_emcy)

    def tearDown(self):
        self.net.disconnect()
        self.rx_net.disconnect()
        self.txbus.shutdown()
        self.rxbus.shutdown()

    def test_producer_consumer_integration(self):
        """Test that producer and consumer work together."""
        received_errors = []
        self.consumer.add_callback(lambda err: received_errors.append(err))
        with (
            self.assertLogs(level=logging.INFO),
            mock_rx_thread(
                self.consumer,
                lambda: self.producer.send(0x2001, 0x02, b'\x01\x02\x03\x04\x05'),
            ),
        ):
            err = self.consumer.wait(0x2001, timeout=TIMEOUT)
        self.assertIsNotNone(err)
        self.assertEqual(err.code, 0x2001)
        self.assertEqual(err.register, 0x02)
        self.assertEqual(err.data, b'\x01\x02\x03\x04\x05')
        self.assertEqual(received_errors, [err])

    def test_producer_reset_consumer_integration(self):
        """Test producer reset clears consumer active errors."""
        with (
            self.assertLogs(level=logging.INFO),
            mock_rx_thread(
                self.consumer,
                lambda: self.producer.send(0x2001, 0x02, b'\x01\x02\x03\x04\x05'),
            ),
        ):
            self.consumer.wait(0x2001, timeout=TIMEOUT)
        self.assertEqual(len(self.consumer.active), 1)
        with (
            self.assertLogs(level=logging.INFO),
            mock_rx_thread(self.consumer, self.producer.reset),
        ):
            self.assertIsNotNone(self.consumer.wait(timeout=TIMEOUT))
        self.assertEqual(len(self.consumer.active), 0)
        self.assertEqual(len(self.consumer.log), 2)


if __name__ == "__main__":
    unittest.main()
