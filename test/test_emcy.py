import logging
import threading
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

import can

import canopen
from canopen.emcy import EmcyError


TIMEOUT = 0.1


class TestEmcy(unittest.TestCase):
    def setUp(self):
        self.emcy = canopen.emcy.EmcyConsumer()

    def check_error(self, err, code, reg, data, ts):
        self.assertIsInstance(err, EmcyError)
        self.assertIsInstance(err, Exception)
        self.assertEqual(err.code, code)
        self.assertEqual(err.register, reg)
        self.assertEqual(err.data, data)
        self.assertAlmostEqual(err.timestamp, ts)

    def test_emcy_consumer_on_emcy(self):
        acc1 = []
        acc2 = []
        self.emcy.add_callback(lambda err: acc1.append(err))
        self.emcy.add_callback(lambda err: acc2.append(err))

        self.emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)

        self.assertEqual(len(self.emcy.log), 1)
        self.assertEqual(len(self.emcy.active), 1)

        error = self.emcy.log[0]
        self.assertEqual(self.emcy.active[0], error)
        for err in error, acc1[0], acc2[0]:
            self.check_error(
                error, code=0x2001, reg=0x02,
                data=bytes([0, 1, 2, 3, 4]), ts=1000,
            )

        self.emcy.on_emcy(0x81, b'\x10\x90\x01\x04\x03\x02\x01\x00', 2000)
        self.assertEqual(len(self.emcy.log), 2)
        self.assertEqual(len(self.emcy.active), 2)

        error = self.emcy.log[1]
        self.assertEqual(self.emcy.active[1], error)
        for err in error, acc1[1], acc2[1]:
            self.check_error(
                error, code=0x9010, reg=0x01,
                data=bytes([4, 3, 2, 1, 0]), ts=2000,
            )

        self.emcy.on_emcy(0x81, b'\x00\x00\x00\x00\x00\x00\x00\x00', 2000)
        self.assertEqual(len(self.emcy.log), 3)
        self.assertEqual(len(self.emcy.active), 0)

    def test_emcy_consumer_reset(self):
        self.emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)
        self.emcy.on_emcy(0x81, b'\x10\x90\x01\x04\x03\x02\x01\x00', 2000)
        self.assertEqual(len(self.emcy.log), 2)
        self.assertEqual(len(self.emcy.active), 2)

        self.emcy.reset()
        self.assertEqual(len(self.emcy.log), 0)
        self.assertEqual(len(self.emcy.active), 0)

    def test_emcy_consumer_wait(self):
        PAUSE = TIMEOUT / 2

        def push_err():
            self.emcy.on_emcy(0x81, b'\x01\x20\x01\x01\x02\x03\x04\x05', 100)

        def check_err(err):
            self.assertIsNotNone(err)
            self.check_error(
                err, code=0x2001, reg=1,
                data=bytes([1, 2, 3, 4, 5]), ts=100,
            )

        @contextmanager
        def timer(func):
            t = threading.Timer(PAUSE, func)
            try:
                yield t
            finally:
                t.join(TIMEOUT)

        self.assertIsNone(self.emcy.wait(timeout=TIMEOUT))

        with timer(push_err) as t:
            with self.assertLogs(level=logging.INFO):
                t.start()
                err = self.emcy.wait(timeout=TIMEOUT)
        check_err(err)

        with timer(push_err) as t:
            with self.assertLogs(level=logging.INFO):
                t.start()
                err = self.emcy.wait(0x2001, TIMEOUT)
        check_err(err)

        with timer(push_err) as t:
            t.start()
            self.assertIsNone(self.emcy.wait(0x9000, TIMEOUT))

        def push_reset():
            self.emcy.on_emcy(0x81, b'\x00\x00\x00\x00\x00\x00\x00\x00', 100)

        with timer(push_reset) as t:
            t.start()
            self.assertIsNone(self.emcy.wait(0x9000, TIMEOUT))

    def test_emcy_consumer_initialization(self):
        """Test EmcyConsumer initialization state."""
        consumer = canopen.emcy.EmcyConsumer()
        self.assertEqual(consumer.log, [])
        self.assertEqual(consumer.active, [])
        self.assertEqual(consumer.callbacks, [])
        self.assertIsInstance(consumer.emcy_received, threading.Condition)

    def test_emcy_consumer_multiple_callbacks(self):
        """Test adding multiple callbacks and their execution order."""
        call_order = []
        
        def callback1(err):
            call_order.append('callback1')
        
        def callback2(err):
            call_order.append('callback2')
        
        def callback3(err):
            call_order.append('callback3')
        
        self.emcy.add_callback(callback1)
        self.emcy.add_callback(callback2)
        self.emcy.add_callback(callback3)
        
        self.emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)
        
        self.assertEqual(call_order, ['callback1', 'callback2', 'callback3'])
        self.assertEqual(len(self.emcy.callbacks), 3)

    def test_emcy_consumer_callback_exception_handling(self):
        """Test that callback exceptions don't break other callbacks or the system."""
        successful_callbacks = []
        
        def failing_callback(err):
            raise ValueError("Test exception in callback")
        
        def successful_callback1(err):
            successful_callbacks.append('success1')
        
        def successful_callback2(err):
            successful_callbacks.append('success2')
        
        self.emcy.add_callback(successful_callback1)
        self.emcy.add_callback(failing_callback)
        self.emcy.add_callback(successful_callback2)
        
        with self.assertRaises(ValueError):
            self.emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)
        
    def test_emcy_consumer_error_reset_variants(self):
        """Test different error reset code patterns."""
        self.emcy.on_emcy(0x81, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)
        self.emcy.on_emcy(0x81, b'\x10\x90\x01\x04\x03\x02\x01\x00', 2000)
        self.assertEqual(len(self.emcy.active), 2)
        
        self.emcy.on_emcy(0x81, b'\x00\x00\x00\x00\x00\x00\x00\x00', 3000)
        self.assertEqual(len(self.emcy.active), 0)
        
        self.emcy.on_emcy(0x81, b'\x01\x30\x02\x00\x01\x02\x03\x04', 4000)
        self.assertEqual(len(self.emcy.active), 1)
        
        self.emcy.on_emcy(0x81, b'\x99\x00\x01\x00\x00\x00\x00\x00', 5000)
        self.assertEqual(len(self.emcy.active), 0)

    def test_emcy_consumer_wait_timeout_edge_cases(self):
        """Test wait method with various timeout scenarios."""
        result = self.emcy.wait(timeout=0)
        self.assertIsNone(result)
        
        result = self.emcy.wait(timeout=0.001)
        self.assertIsNone(result)

    def test_emcy_consumer_wait_concurrent_errors(self):
        """Test wait method when multiple errors arrive concurrently."""
        def push_multiple_errors():
            self.emcy.on_emcy(0x81, b'\x01\x20\x01\x01\x02\x03\x04\x05', 100)
            self.emcy.on_emcy(0x81, b'\x02\x20\x01\x01\x02\x03\x04\x05', 101)
            self.emcy.on_emcy(0x81, b'\x03\x20\x01\x01\x02\x03\x04\x05', 102)

        t = threading.Timer(TIMEOUT / 2, push_multiple_errors)
        with self.assertLogs(level=logging.INFO):
            t.start()
            err = self.emcy.wait(0x2003, timeout=TIMEOUT)
        t.join(TIMEOUT)
        
        self.assertIsNotNone(err)
        self.assertEqual(err.code, 0x2003)

    def test_emcy_consumer_wait_time_expiry_during_execution(self):
        """Test wait method when time expires while processing."""
        def push_err_with_delay():
            import time
            time.sleep(TIMEOUT * 1.5)
            self.emcy.on_emcy(0x81, b'\x01\x20\x01\x01\x02\x03\x04\x05', 100)

        t = threading.Timer(TIMEOUT / 4, push_err_with_delay)
        t.start()
        
        result = self.emcy.wait(timeout=TIMEOUT)
        t.join(TIMEOUT * 2)
        
        self.assertIsNone(result)


class TestEmcyError(unittest.TestCase):
    def test_emcy_error(self):
        error = EmcyError(0x2001, 0x02, b'\x00\x01\x02\x03\x04', 1000)
        self.assertEqual(error.code, 0x2001)
        self.assertEqual(error.data, b'\x00\x01\x02\x03\x04')
        self.assertEqual(error.register, 2)
        self.assertEqual(error.timestamp, 1000)

    def test_emcy_str(self):
        def check(code, expected):
            err = EmcyError(code, 1, b'', 1000)
            actual = str(err)
            self.assertEqual(actual, expected)

        check(0x2001, "Code 0x2001, Current")
        check(0x3abc, "Code 0x3ABC, Voltage")
        check(0x0234, "Code 0x0234")
        check(0xbeef, "Code 0xBEEF")

    def test_emcy_get_desc(self):
        def check(code, expected):
            err = EmcyError(code, 1, b'', 1000)
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

    def test_emcy_error_initialization_types(self):
        """Test EmcyError initialization with various data types."""
        error = EmcyError(0x1000, 0, b'', 123.456)
        self.assertEqual(error.code, 0x1000)
        self.assertEqual(error.register, 0)
        self.assertEqual(error.data, b'')
        self.assertEqual(error.timestamp, 123.456)
        
        error = EmcyError(0xFFFF, 0xFF, b'\xFF' * 5, float('inf'))
        self.assertEqual(error.code, 0xFFFF)
        self.assertEqual(error.register, 0xFF)
        self.assertEqual(error.data, b'\xFF' * 5)
        self.assertEqual(error.timestamp, float('inf'))

    def test_emcy_error_str_edge_cases(self):
        """Test string representation with edge cases."""
        error = EmcyError(0x0000, 0, b'', 1000)
        self.assertEqual(str(error), "Code 0x0000, Error Reset / No Error")
        
        error = EmcyError(0x0001, 0, b'', 1000)
        self.assertEqual(str(error), "Code 0x0001, Error Reset / No Error")
        
        error = EmcyError(0x0100, 0, b'', 1000)
        self.assertEqual(str(error), "Code 0x0100")
        
        error = EmcyError(0xFFFF, 0, b'', 1000)
        self.assertEqual(str(error), "Code 0xFFFF, Device Specific")

    def test_emcy_error_get_desc_boundary_conditions(self):
        """Test get_desc method with boundary conditions."""
        def check(code, expected):
            err = EmcyError(code, 1, b'', 1000)
            actual = err.get_desc()
            self.assertEqual(actual, expected)
        
        check(0x0000, "Error Reset / No Error")
        check(0x00FF, "Error Reset / No Error")
        check(0x0100, "")
        
        check(0x0FFF, "")
        check(0x1000, "Generic Error")
        check(0x10FF, "Generic Error")
        check(0x1100, "")
        
        check(0x1FFF, "")
        check(0x2000, "Current")
        check(0x2FFF, "Current")
        check(0x3000, "Voltage")
        
        check(0x4FFF, "Temperature")
        check(0x5000, "Device Hardware")
        check(0x50FF, "Device Hardware")
        check(0x5100, "")

    def test_emcy_error_inheritance(self):
        """Test that EmcyError properly inherits from Exception."""
        error = EmcyError(0x1000, 0, b'', 1000)
        
        self.assertIsInstance(error, Exception)
        
        with self.assertRaises(EmcyError):
            raise error
        
        try:
            raise error
        except Exception as e:
            self.assertIsInstance(e, EmcyError)
            self.assertEqual(e.code, 0x1000)


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
        self.assertIsNotNone(msg)
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

    def test_emcy_producer_initialization(self):
        """Test EmcyProducer initialization."""
        producer = canopen.emcy.EmcyProducer(0x123)
        self.assertEqual(producer.cob_id, 0x123)
        network = producer.network
        self.assertIsNotNone(network)

    def test_emcy_producer_send_edge_cases(self):
        """Test EmcyProducer send method with edge cases."""
        def check(*args, res):
            self.emcy.send(*args)
            self.check_response(res)
        
        check(0xFFFF, 0xFF, b'\xFF\xFF\xFF\xFF\xFF', 
              res=b'\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF')
        
        check(0x0000, 0x00, b'', 
              res=b'\x00\x00\x00\x00\x00\x00\x00\x00')
        
        check(0x1234, 0x56, b'\xAB\xCD', 
              res=b'\x34\x12\x56\xAB\xCD\x00\x00\x00')
        
        check(0x1234, 0x56, b'\xAB\xCD\xEF\x12\x34', 
              res=b'\x34\x12\x56\xAB\xCD\xEF\x12\x34')

    def test_emcy_producer_reset_edge_cases(self):
        """Test EmcyProducer reset method with edge cases."""
        def check(*args, res):
            self.emcy.reset(*args)
            self.check_response(res)
        
        check(0xFF, res=b'\x00\x00\xFF\x00\x00\x00\x00\x00')
        
        check(0xFF, b'\xFF\xFF\xFF\xFF\xFF', 
              res=b'\x00\x00\xFF\xFF\xFF\xFF\xFF\xFF')
        
        check(0x12, b'\xAB\xCD', 
              res=b'\x00\x00\x12\xAB\xCD\x00\x00\x00')

    def test_emcy_producer_network_assignment(self):
        """Test EmcyProducer network assignment and usage."""
        producer = canopen.emcy.EmcyProducer(0x100)
        initial_network = producer.network
        
        producer.network = self.net
        self.assertEqual(producer.network, self.net)
        
        producer.send(0x1000)
        msg = self.rxbus.recv(TIMEOUT)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.arbitration_id, 0x100)

    def test_emcy_producer_struct_packing(self):
        """Test that the EMCY_STRUCT packing works correctly."""
        from canopen.emcy import EMCY_STRUCT
        
        packed = EMCY_STRUCT.pack(0x1234, 0x56, b'\xAB\xCD\xEF\x12\x34')
        expected = b'\x34\x12\x56\xAB\xCD\xEF\x12\x34'
        self.assertEqual(packed, expected)
        
        code, register, data = EMCY_STRUCT.unpack(expected)
        self.assertEqual(code, 0x1234)
        self.assertEqual(register, 0x56)
        self.assertEqual(data, b'\xAB\xCD\xEF\x12\x34')
        
        packed = EMCY_STRUCT.pack(0x1234, 0x56, b'\xAB')
        expected = b'\x34\x12\x56\xAB\x00\x00\x00\x00'
        self.assertEqual(packed, expected)


class TestEmcyIntegration(unittest.TestCase):
    """Integration tests for EMCY producer and consumer."""
    
    def setUp(self):
        self.txbus = can.Bus(interface="virtual")
        self.rxbus = can.Bus(interface="virtual")
        self.net = canopen.Network(self.txbus)
        self.net.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.net.connect()
        
        self.producer = canopen.emcy.EmcyProducer(0x081)
        self.producer.network = self.net
        
        self.consumer = canopen.emcy.EmcyConsumer()
        
    def tearDown(self):
        self.net.disconnect()
        self.txbus.shutdown()
        self.rxbus.shutdown()
    
    def test_producer_consumer_integration(self):
        """Test that producer and consumer work together."""
        received_errors = []
        self.consumer.add_callback(lambda err: received_errors.append(err))
        
        self.producer.send(0x2001, 0x02, b'\x01\x02\x03\x04\x05')
        
        msg = self.rxbus.recv(TIMEOUT)
        self.assertIsNotNone(msg)
        
        self.consumer.on_emcy(msg.arbitration_id, msg.data, msg.timestamp)
        
        self.assertEqual(len(received_errors), 1)
        self.assertEqual(len(self.consumer.log), 1)
        self.assertEqual(len(self.consumer.active), 1)
        
        error = received_errors[0]
        self.assertEqual(error.code, 0x2001)
        self.assertEqual(error.register, 0x02)
        self.assertEqual(error.data, b'\x01\x02\x03\x04\x05')
    
    def test_producer_reset_consumer_integration(self):
        """Test producer reset clears consumer active errors."""
        self.consumer.on_emcy(0x081, b'\x01\x20\x02\x00\x01\x02\x03\x04', 1000)
        self.assertEqual(len(self.consumer.active), 1)
        
        self.producer.reset()
        
        msg = self.rxbus.recv(TIMEOUT)
        self.assertIsNotNone(msg)
        
        self.consumer.on_emcy(msg.arbitration_id, msg.data, msg.timestamp)
        
        self.assertEqual(len(self.consumer.active), 0)
        self.assertEqual(len(self.consumer.log), 2)


if __name__ == "__main__":
    unittest.main()
    