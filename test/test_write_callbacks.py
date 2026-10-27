import unittest
from unittest.mock import Mock, patch

import canopen
from canopen.sdo.constants import ABORT_GENERAL_ERROR

from .util import SAMPLE_EDS


class NonBooleanResult:
    def __bool__(self):
        raise AssertionError("Callback results must not be tested for truthiness")


class TestWriteCallbacks(unittest.TestCase):
    def setUp(self):
        self.node = canopen.LocalNode(2, SAMPLE_EDS)

    def test_non_none_results_suppress_new_storage(self):
        for result in (True, False, 0, "", b"", [], NonBooleanResult()):
            with self.subTest(result=type(result).__name__):
                node = canopen.LocalNode(2, SAMPLE_EDS)
                node.add_write_callback(Mock(return_value=result))
                node.set_data(0x2001, 0, b"\x12\x34")
                self.assertNotIn(0x2001, node.data_store)

    def test_optout_does_not_skip_or_reset_later_callbacks(self):
        for result in (True, False):
            with self.subTest(result=result):
                node = canopen.LocalNode(2, SAMPLE_EDS)
                calls = []

                def handle(**kwargs):
                    calls.append(("handle", kwargs["data"]))
                    return result

                def observe(**kwargs):
                    calls.append(("observe", kwargs["data"]))

                node.add_write_callback(handle)
                node.add_write_callback(observe)
                node.set_data(0x2001, 0, b"\x12\x34")
                self.assertEqual(calls, [("handle", b"\x12\x34"),
                                         ("observe", b"\x12\x34")])
                self.assertNotIn(0x2001, node.data_store)

    def test_optout_preserves_existing_store(self):
        self.node.data_store = {0x2001: {0: b"\x01\x00", 1: b"other"},
                                0x2000: {0: b"unchanged"}}
        self.node.add_write_callback(Mock(return_value=True))
        self.node.set_data(0x2001, 0, b"\x02\x00")
        self.assertEqual(self.node.data_store,
                         {0x2001: {0: b"\x01\x00", 1: b"other"},
                          0x2000: {0: b"unchanged"}})

    def test_default_storage_copies_mutable_data(self):
        data = bytearray(b"\x12\x34")
        self.node.set_data(0x2001, 0, data)
        data[:] = b"\x00\x00"
        self.assertEqual(self.node.data_store[0x2001][0], b"\x12\x34")
        self.assertIsInstance(self.node.data_store[0x2001][0], bytes)

    def test_none_results_keep_default_storage_and_callback_arguments(self):
        first, last = Mock(return_value=None), Mock(return_value=None)
        self.node.add_write_callback(first)
        self.node.add_write_callback(last)
        data = b"\x12\x34"
        self.node.set_data(0x2001, 0, data)
        expected = dict(index=0x2001, subindex=0, od=self.node.object_dictionary[0x2001],
                        data=data)
        first.assert_called_once_with(**expected)
        last.assert_called_once_with(**expected)
        self.assertEqual(self.node.data_store[0x2001][0], data)

    def test_callback_abort_still_propagates_before_storage(self):
        self.node.data_store[0x2001] = {0: b"\x01\x00"}
        self.node.add_write_callback(Mock(return_value=True))
        self.node.add_write_callback(
            Mock(side_effect=canopen.SdoAbortedError(ABORT_GENERAL_ERROR)))
        later = Mock(return_value=None)
        self.node.add_write_callback(later)
        with self.assertRaises(canopen.SdoAbortedError) as error:
            self.node.set_data(0x2001, 0, b"\x02\x00")
        self.assertEqual(error.exception.code, ABORT_GENERAL_ERROR)
        later.assert_not_called()
        self.assertEqual(self.node.data_store[0x2001][0], b"\x01\x00")

    def test_validation_still_precedes_callbacks(self):
        callback = Mock(return_value=True)
        self.node.add_write_callback(callback)
        for index, data, code in ((0x2001, b"\x01", 0x06070010),
                                  (0x1000, b"\x00" * 4, 0x06010002),
                                  (0xFFFF, b"\x00", 0x06020000)):
            with self.subTest(index=index):
                with self.assertRaises(canopen.SdoAbortedError) as error:
                    self.node.set_data(index, 0, data, check_writable=True)
                self.assertEqual(error.exception.code, code)
        callback.assert_not_called()
        self.assertEqual(self.node.data_store, {})

    def test_read_callbacks_still_use_first_non_none_result(self):
        first, later = Mock(return_value=13), Mock(return_value=17)
        self.node.add_read_callback(first)
        self.node.add_read_callback(later)
        self.assertEqual(self.node.get_data(0x2001, 0), b"\x0d\x00")
        first.assert_called_once()
        later.assert_not_called()

    def test_local_sdo_custom_storage_round_trip(self):
        application = {}

        def write(index, data, **kwargs):
            application[index] = int.from_bytes(data, "little")
            return False

        self.node.add_write_callback(write)
        self.node.add_read_callback(lambda index, **kwargs: application[index])
        self.node.sdo.download(0x2001, 0, b"\x12\x34")
        self.assertEqual(self.node.sdo.upload(0x2001, 0), b"\x12\x34")
        self.assertEqual(application, {0x2001: 0x3412})
        self.assertNotIn(0x2001, self.node.data_store)

    def test_remote_expedited_and_segmented_sdo_round_trip(self):
        client_network, server_network = canopen.Network(), canopen.Network()
        server_network.add_node(self.node)
        remote = client_network.add_node(2, SAMPLE_EDS)
        remote.sdo.RESPONSE_TIMEOUT = 0.01
        client_network.send_message = lambda can_id, data, remote=False: server_network.notify(
            can_id, data, 0.0)
        server_network.send_message = lambda can_id, data, remote=False: client_network.notify(
            can_id, data, 0.0)
        application, observed = {}, []

        def write(index, data, **kwargs):
            application[index] = bytes(data)
            return 0

        def read(index, **kwargs):
            data = application[index]
            return int.from_bytes(data, "little") if index == 0x2001 else data.decode("ascii")

        self.node.add_write_callback(write)
        self.node.add_write_callback(
            lambda index, data, **kwargs: observed.append((index, bytes(data))))
        self.node.add_read_callback(read)
        for index, data in ((0x2001, b"\x12\x34"),
                            (0x2000, b"A payload longer than one CAN frame")):
            with self.subTest(index=index):
                remote.sdo.download(index, 0, data)
                self.assertEqual(remote.sdo.upload(index, 0), data)
                self.assertEqual(application[index], data)
                self.assertEqual(observed[-1], (index, data))
                self.assertNotIn(index, self.node.data_store)
        self.assertIsNone(client_network.bus)
        self.assertIsNone(server_network.bus)

    def test_builtin_heartbeat_callback_still_runs_with_optout(self):
        self.node.add_write_callback(Mock(return_value=True))
        later = Mock(return_value=None)
        self.node.add_write_callback(later)
        with patch.object(self.node.nmt, "start_heartbeat") as start:
            self.node.set_data(0x1017, 0, b"\x05\x00")
        start.assert_called_once_with(5)
        later.assert_called_once()
        self.assertNotIn(0x1017, self.node.data_store)
