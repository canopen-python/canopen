import time
import unittest
import struct
from unittest.mock import MagicMock, patch

import canopen

from .util import SAMPLE_EDS


class TestSDO(unittest.TestCase):
    """
    Test SDO client and server against each other.
    """

    @classmethod
    def setUpClass(cls):
        cls.network1 = canopen.Network()
        cls.network1.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        cls.network1.connect("test", interface="virtual")
        cls.remote_node = cls.network1.add_node(2, SAMPLE_EDS)

        cls.network2 = canopen.Network()
        cls.network2.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        cls.network2.connect("test", interface="virtual")
        cls.local_node = cls.network2.create_node(2, SAMPLE_EDS)

        cls.remote_node2 = cls.network1.add_node(3, SAMPLE_EDS)

        cls.local_node2 = cls.network2.create_node(3, SAMPLE_EDS)

    @classmethod
    def tearDownClass(cls):
        cls.network1.disconnect()
        cls.network2.disconnect()

    def test_expedited_upload(self):
        self.local_node.sdo[0x1400][1].raw = 0x99
        vendor_id = self.remote_node.sdo[0x1400][1].raw
        self.assertEqual(vendor_id, 0x99)

    def test_block_download(self):
        data = b"BLOCK DOWNLOAD TEST DATA"
        # Write data using block download
        with self.remote_node.sdo[0x2000].open('wb', size=len(data), block_transfer=True) as fp:
            fp.write(data)
        # Read back using block upload (client requests upload from server)
        with self.remote_node.sdo[0x2000].open('rb', block_transfer=True) as fp:
            read_data = fp.read()
        self.assertEqual(read_data, data)

    def test_block_upload_multi_block(self):
        """Block tranfer of bulk data using multiple blocks. Each block can transfer up to 127 segments of 7 bytes (889 bytes)"""
        # 70 * 28 = 1960 bytes, exceeds one block (127 segments * 7 bytes = 889 bytes)
        data = b"Lorem ipsum dolor sit amet. " * 70
        self.local_node.sdo[0x2000].raw = data.decode("latin-1")
        with self.remote_node.sdo[0x2000].open('rb', block_transfer=True) as fp:
            read_data = fp.read()
        self.assertEqual(read_data, data)

    def test_process_block_up_data_wrong_ackseq(self):
        """
        Test that when client acks with wrong seqno, server rolls back data_uploaded to data_successful_upload
        (the start of the current block) and asks for retransmit.
        """
        server = self.local_node.sdo
        server._index = 0x2000
        server._subindex = 0

        mock_block = MagicMock()
        mock_block.state = canopen.sdo.constants.BLOCK_STATE_UP_DATA  # 0x12
        mock_block.last_seqno = 127          # server sent seqno 1..127
        mock_block.data_uploaded = 889       # 127 * 7, end of first block
        mock_block.data_successful_upload = 0
        mock_block.size = 1960               # two blocks worth, transfer not done
        mock_block.get_upload_blocks.return_value = []
        server.sdo_block = mock_block

        # command = REQUEST_BLOCK_UPLOAD (0xA0) | BLOCK_TRANSFER_RESPONSE (0x02) = 0xA2
        # ackseq = 0 (wrong: last_seqno was 127), newblk = 127
        request = bytearray(struct.pack("<BBB", 0xA2, 0, 127) + b'\x00' * 5)
        with patch.object(server, 'send_response'):
            server.on_request(0x601, request, 0.0)

        # data_uploaded must have been rolled back to data_successful_upload (0)
        self.assertEqual(mock_block.data_uploaded, 0)
        # server must have asked for a retransmit block
        mock_block.get_upload_blocks.assert_called_once()
        # clean up — leave server in a known state for subsequent tests
        server.sdo_block = None

    def test_block_upload_invalid_blksize(self):
        """
        Test that when client initiates block upload with invalid blksize=0, server aborts with "Invalid block size" (0x05040002).
        """
        server = self.local_node.sdo
        server._index = 0x2000
        server._subindex = 0
        server.sdo_block = None

        # REQUEST_BLOCK_UPLOAD (0xA0) with sub-command=0 (INITIATE), index=0x2000, subindex=0, blksize=0
        request = bytearray(struct.pack("<BHB", 0xA0, 0x2000, 0) + b'\x00' * 4)
        request[4] = 0  # blksize = 0, invalid

        sent = []
        with patch.object(server, 'send_response', side_effect=lambda r: sent.append(bytes(r))):
            server.on_request(0x601, request, 0.0)

        # Server should have sent an abort response (SdoAbortedError caught in on_request)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], 0x80)  # RESPONSE_ABORTED

    def test_block_download_not_supported(self):
        # Try block download to an object that should not support it (e.g., a constant string)
        data = b"TEST DEVICE"
        with self.assertRaises(canopen.SdoAbortedError) as context:
            with self.remote_node.sdo[0x1008].open('wb',
                                                   size=len(data),
                                                   block_transfer=True) as fp:
                fp.write(data)
        # Accept both possible abort codes for unsupported block download
        self.assertIn(context.exception.code, [0x05040001, 0x05040003, 0x06010002])

    def test_expedited_upload_default_value_visible_string(self):
        device_name = self.remote_node.sdo["Manufacturer device name"].raw
        self.assertEqual(device_name, "TEST DEVICE")

    def test_expedited_upload_default_value_real(self):
        sampling_rate = self.remote_node.sdo["Sensor Sampling Rate (Hz)"].raw
        self.assertAlmostEqual(sampling_rate, 5.2, places=2)

    def test_upload_zero_length(self):
        self.local_node.sdo["Manufacturer device name"].raw = b""
        with self.assertRaises(canopen.SdoAbortedError) as error:
            self.remote_node.sdo["Manufacturer device name"].data
        # Should be No data available
        self.assertEqual(error.exception.code, 0x0800_0024)

    def test_segmented_upload(self):
        self.local_node.sdo["Manufacturer device name"].raw = "Some cool device"
        device_name = self.remote_node.sdo["Manufacturer device name"].data
        self.assertEqual(device_name, b"Some cool device")

    def test_expedited_download(self):
        self.remote_node.sdo[0x2004].raw = 0xfeff
        value = self.local_node.sdo[0x2004].raw
        self.assertEqual(value, 0xfeff)

    def test_expedited_download_wrong_datatype(self):
        # Try to write 32 bit in integer16 type
        with self.assertRaises(canopen.SdoAbortedError) as error:
            self.remote_node.sdo.download(0x2001, 0x0, bytes([10, 10, 10, 10]))
        self.assertEqual(error.exception.code, 0x06070010)
        # Try to write normal 16 bit word, should be ok
        self.remote_node.sdo.download(0x2001, 0x0, bytes([10, 10]))
        value = self.remote_node.sdo.upload(0x2001, 0x0)
        self.assertEqual(value, bytes([10, 10]))

    def test_segmented_download(self):
        self.remote_node.sdo[0x2000].raw = "Another cool device"
        value = self.local_node.sdo[0x2000].data
        self.assertEqual(value, b"Another cool device")

    def test_slave_send_heartbeat(self):
        # Setting the heartbeat time should trigger heartbeating
        # to start
        self.remote_node.sdo["Producer heartbeat time"].raw = 100
        state = self.remote_node.nmt.wait_for_heartbeat()
        self.local_node.nmt.stop_heartbeat()
        # The NMT master will change the state INITIALISING (0)
        # to PRE-OPERATIONAL (127)
        self.assertEqual(state, 'PRE-OPERATIONAL')

    def test_nmt_state_initializing_to_preoper(self):
        # Initialize the heartbeat timer
        self.local_node.sdo["Producer heartbeat time"].raw = 100
        self.local_node.nmt.stop_heartbeat()
        # This transition shall start the heartbeating
        self.local_node.nmt.state = 'INITIALISING'
        self.local_node.nmt.state = 'PRE-OPERATIONAL'
        state = self.remote_node.nmt.wait_for_heartbeat()
        self.local_node.nmt.stop_heartbeat()
        self.assertEqual(state, 'PRE-OPERATIONAL')

    def test_receive_abort_request(self):
        self.remote_node.sdo.abort(0x0504_0003)  # Invalid sequence number
        # Line below is just so that we are sure the client have received the abort
        # before we do the check
        time.sleep(0.1)
        self.assertEqual(self.local_node.sdo.last_received_error, 0x0504_0003)

    def test_start_remote_node(self):
        self.remote_node.nmt.state = 'OPERATIONAL'
        # Line below is just so that we are sure the client have received the command
        # before we do the check
        time.sleep(0.1)
        slave_state = self.local_node.nmt.state
        self.assertEqual(slave_state, 'OPERATIONAL')

    def test_two_nodes_on_the_bus(self):
        self.local_node.sdo["Manufacturer device name"].raw = "Some cool device"
        device_name = self.remote_node.sdo["Manufacturer device name"].data
        self.assertEqual(device_name, b"Some cool device")

        self.local_node2.sdo["Manufacturer device name"].raw = "Some cool device2"
        device_name = self.remote_node2.sdo["Manufacturer device name"].data
        self.assertEqual(device_name, b"Some cool device2")

    def test_on_request_block_generic_exception(self):
        """Test unexpected exception in block processing is handled by aborting the transfer and resetting the block state."""
        server = self.local_node.sdo
        # Provide valid index/subindex so abort() can pack the response frame
        server._index = 0x2000
        server._subindex = 0

        mock_block = MagicMock()
        mock_block.state = canopen.sdo.constants.BLOCK_STATE_DL_DATA  # BLOCK_STATE_DL_DATA — non-NONE, keeps branch alive
        server.sdo_block = mock_block

        with patch.object(server, 'process_block', side_effect=RuntimeError("unexpected")):
            with self.assertRaises(RuntimeError):
                server.on_request(0x601, bytearray(8), 0.0)

        self.assertIsNone(server.sdo_block)

    def test_process_block_abort_command(self):
        """Client sends abort (0x80) during block transfer; server clears sdo_block and sends no response."""
        server = self.local_node.sdo

        mock_block = MagicMock()
        mock_block.state = canopen.sdo.constants.BLOCK_STATE_DL_DATA  # BLOCK_STATE_DL_DATA — active block state
        server.sdo_block = mock_block

        sent = []
        with patch.object(server, 'send_response', side_effect=lambda r: sent.append(bytes(r))):
            # SDO_ABORT_STRUCT = "<BHBI": command, index, subindex, abort_code
            abort_frame = bytearray(struct.pack("<BHBI", 0x80, 0x2000, 0, 0x05040003))
            server.on_request(0x601, abort_frame, 0.0)

        self.assertIsNone(server.sdo_block)
        self.assertEqual(sent, [])  # server does not reply to an abort
        
    def test_on_request_unknown_command(self):
        """CCS with no matching command triggers abort(0x05040001)."""
        server = self.local_node.sdo
        server._index = 0
        server._subindex = 0

        sent = []
        with patch.object(server, 'send_response', side_effect=lambda r: sent.append(bytes(r))):
            # 0xE0 = CCS 7 (0b111 << 5), not a valid command
            server.on_request(0x601, bytearray([0xE0, 0, 0, 0, 0, 0, 0, 0]), 0.0)

        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], 0x80)  # RESPONSE_ABORTED = 4 << 5

        abort_code, = struct.unpack_from("<L", sent[0], 4)
        self.assertEqual(abort_code, 0x05040001)

    def test_abort(self):
        with self.assertRaises(canopen.SdoAbortedError) as cm:
            _ = self.remote_node.sdo.upload(0x1234, 0)
        # Should be Object does not exist
        self.assertEqual(cm.exception.code, 0x06020000)

        with self.assertRaises(canopen.SdoAbortedError) as cm:
            _ = self.remote_node.sdo.upload(0x1018, 100)
        # Should be Subindex does not exist
        self.assertEqual(cm.exception.code, 0x06090011)

        with self.assertRaises(canopen.SdoAbortedError) as cm:
            _ = self.remote_node.sdo[0x1001].data
        # Should be Resource not available
        self.assertEqual(cm.exception.code, 0x060A0023)

    def _some_read_callback(self, **kwargs):
        self._kwargs = kwargs
        if kwargs["index"] == 0x1003:
            return 0x0201

    def _some_write_callback(self, **kwargs):
        self._kwargs = kwargs

    def test_callbacks(self):
        self.local_node.add_read_callback(self._some_read_callback)
        self.local_node.add_write_callback(self._some_write_callback)

        data = self.remote_node.sdo.upload(0x1003, 5)
        self.assertEqual(data, b"\x01\x02\x00\x00")
        self.assertEqual(self._kwargs["index"], 0x1003)
        self.assertEqual(self._kwargs["subindex"], 5)

        self.remote_node.sdo.download(0x1017, 0, b"\x03\x04")
        self.assertEqual(self._kwargs["index"], 0x1017)
        self.assertEqual(self._kwargs["subindex"], 0)
        self.assertEqual(self._kwargs["data"], b"\x03\x04")


class TestSdoBlock(unittest.TestCase):
    """Unit tests for _SdoBlock internals."""

    def test_update_state_backwards_raises(self):
        """Line 462: update_state raises when new_state < current state."""
        mock_node = MagicMock()
        # command = REQUEST_BLOCK_DOWNLOAD (0xC0) | BLOCK_SIZE_SPECIFIED (0x02) = 0xC2
        request = struct.pack("<BHBI", 0xC2, 0x2000, 0, 10)
        block = canopen.sdo.server._SdoBlock(mock_node, request, is_download=True)
        block.update_state(canopen.sdo.constants.BLOCK_STATE_DL_DATA)
        with self.assertRaises(canopen.sdo.exceptions.SdoAbortedError):
            block.update_state(canopen.sdo.constants.BLOCK_STATE_DL_DATA - 1)

    def test_finalize_download_no_padding(self):
        """Line 527: finalize_download with n=0 returns full buffer."""
        mock_node = MagicMock()
        request = struct.pack("<BHBI", 0xC2, 0x2000, 0, 7)
        block = canopen.sdo.server._SdoBlock(mock_node, request, is_download=True)
        block.append_download_data(b"ABCDEFG")
        result = block.finalize_download(0)
        self.assertEqual(result, b"ABCDEFG")


class TestPDO(unittest.TestCase):
    """
    Test PDO slave.
    """

    @classmethod
    def setUpClass(cls):
        cls.network1 = canopen.Network()
        cls.network1.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        cls.network1.connect("test", interface="virtual")
        cls.remote_node = cls.network1.add_node(2, SAMPLE_EDS)

        cls.network2 = canopen.Network()
        cls.network2.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        cls.network2.connect("test", interface="virtual")
        cls.local_node = cls.network2.create_node(2, SAMPLE_EDS)

    @classmethod
    def tearDownClass(cls):
        cls.network1.disconnect()
        cls.network2.disconnect()

    def test_read(self):
        # TODO: Do some more checks here. Currently it only tests that they
        # can be called without raising an error.
        self.remote_node.pdo.read()
        self.local_node.pdo.read()

    def test_save(self):
        # TODO: Do some more checks here. Currently it only tests that they
        # can be called without raising an error.
        self.remote_node.pdo.save()
        self.local_node.pdo.save()


if __name__ == "__main__":
    unittest.main()
