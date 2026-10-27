import unittest

import canopen

from .util import SAMPLE_EDS


class _Task:
    def __init__(self):
        self.stops = 0

    def stop(self):
        self.stops += 1


class _ModifyingTask(_Task):
    def __init__(self):
        super().__init__()
        self.updates = []

    def modify_data(self, message):
        self.updates.append(bytes(message.data))


class _RecordingBus:
    def __init__(self, supports_modify=False):
        self.supports_modify = supports_modify
        self.payloads = []
        self.periods = []
        self.metadata = []
        self.tasks = []

    def send_periodic(self, message, period):
        # Model a backend that snapshots the payload when scheduling it.
        self.payloads.append(bytes(message.data))
        self.periods.append(period)
        self.metadata.append((message.arbitration_id, message.is_extended_id,
                              message.is_remote_frame, message.dlc))
        task = _ModifyingTask() if self.supports_modify else _Task()
        self.tasks.append(task)
        return task


class TestPeriodicPayload(unittest.TestCase):
    def setUp(self):
        self.network = canopen.Network()
        self.bus = _RecordingBus()
        self.network.bus = self.bus

    def test_first_mutable_update_and_repeated_updates(self):
        data = bytearray([1, 2])
        task = self.network.send_periodic(0x123, data, 0.1)
        self.addCleanup(task.stop)
        data[0] = 3
        task.update(data)
        self.assertEqual(self.bus.payloads, [b'\x01\x02', b'\x03\x02'])
        self.assertEqual(self.bus.tasks[0].stops, 1)

        task.update(data)
        self.assertEqual(len(self.bus.tasks), 2)
        self.assertEqual(self.bus.tasks[1].stops, 0)
        data[0] = 4
        task.update(data)
        self.assertEqual(self.bus.payloads[-1], b'\x04\x02')
        self.assertEqual(self.bus.tasks[1].stops, 1)
        self.assertEqual(self.bus.periods, [0.1, 0.1, 0.1])

    def test_unchanged_initial_data_does_not_restart(self):
        data = bytearray([1, 2])
        task = self.network.send_periodic(0x123, data, 0.1)
        self.addCleanup(task.stop)
        task.update(data)
        task.update(bytes(data))
        self.assertEqual(self.bus.payloads, [b'\x01\x02'])
        self.assertEqual(self.bus.tasks[0].stops, 0)

    def test_modify_data_keeps_original_task(self):
        self.bus.supports_modify = True
        data = bytearray([1, 2])
        task = self.network.send_periodic(0x123, data, 0.1)
        self.addCleanup(task.stop)
        data[0] = 3
        task.update(data)
        task.update(data)
        self.assertEqual(len(self.bus.tasks), 1)
        self.assertEqual(self.bus.tasks[0].updates, [b'\x03\x02', b'\x03\x02'])
        self.assertEqual(self.bus.tasks[0].stops, 0)

    def test_one_shot_input_is_consumed_once(self):
        data = iter([1, 2])
        task = self.network.send_periodic(0x123, data, 0.1)
        self.addCleanup(task.stop)
        self.assertEqual(self.bus.payloads, [b'\x01\x02'])
        self.assertEqual(list(data), [])
        task.update([3, 4])
        self.assertEqual(self.bus.payloads[-1], b'\x03\x04')

    def test_normalized_payload_and_frame_metadata(self):
        for can_id in (0x123, 0x812):
            for data in (b'\x01\x02', [1, 2], (1, 2), memoryview(b'\x01\x02')):
                with self.subTest(can_id=can_id, data=data):
                    task = self.network.send_periodic(can_id, data, 0.25)
                    self.assertEqual(self.bus.payloads[-1], b'\x01\x02')
                    self.assertEqual(self.bus.periods[-1], 0.25)
                    self.assertEqual(self.bus.metadata[-1], (can_id, can_id > 0x7FF, False, 2))
                    task.stop()

    def test_empty_and_remote_normalization(self):
        class UnreadablePayload:
            def __iter__(self):
                raise AssertionError("Remote frame data must not be consumed")

        for data, remote in ((None, False), (None, True), (UnreadablePayload(), True)):
            with self.subTest(remote=remote, data=data):
                task = self.network.send_periodic(0x123, data, 0.1, remote=remote)
                self.assertEqual(self.bus.payloads[-1], b'')
                self.assertEqual(self.bus.metadata[-1], (0x123, False, remote, 0))
                task.stop()

    def test_rpdo_first_raw_update_restarts_fallback(self):
        node = self.network.add_node(1, SAMPLE_EDS)
        pdo = node.rpdo[1]
        pdo.clear()
        pdo.cob_id = 0x201
        pdo.add_variable('INTEGER16 value')
        pdo['INTEGER16 value'].raw = 0x0102
        pdo.start(0.1)
        self.addCleanup(pdo.stop)
        pdo['INTEGER16 value'].raw = 0x0304
        self.assertEqual(self.bus.payloads, [b'\x02\x01', b'\x04\x03'])
        self.assertEqual(self.bus.tasks[0].stops, 1)
        pdo.update()
        self.assertEqual(len(self.bus.tasks), 2)

    def test_rpdo_first_bitfield_update_restarts_fallback(self):
        node = self.network.add_node(1, SAMPLE_EDS)
        pdo = node.rpdo[1]
        pdo.clear()
        pdo.cob_id = 0x201
        pdo.add_variable('UNSIGNED8 value', length=4)
        pdo['UNSIGNED8 value'].raw = 1
        pdo.start(0.1)
        self.addCleanup(pdo.stop)
        pdo['UNSIGNED8 value'].raw = 2
        self.assertEqual(self.bus.payloads, [b'\x01', b'\x02'])
        self.assertEqual(self.bus.tasks[0].stops, 1)
