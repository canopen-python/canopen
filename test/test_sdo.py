import struct
import time
import unittest
from unittest.mock import patch
import canopen
import canopen.objectdictionary.datatypes as dt
from can import CanError
from canopen.objectdictionary import ODVariable
from canopen.sdo.constants import (
    ABORT_GENERAL_ERROR,
    ABORT_INVALID_COMMAND_SPECIFIER,
    ABORT_NOT_IN_OD,
    ABORT_TOGGLE_NOT_ALTERNATED,
    CRC_SUPPORTED,
    EXPEDITED,
    REQUEST_BLOCK_UPLOAD,
    REQUEST_DOWNLOAD,
    RESPONSE_ABORTED,
    RESPONSE_DOWNLOAD,
    SDO_STRUCT,
    START_BLOCK_UPLOAD,
)

from .util import DATATYPES_EDS, SAMPLE_EDS


TX = 1
RX = 2


class TestSDOVariables(unittest.TestCase):
    """Some basic assumptions on the behavior of SDO variable objects.

    Mostly what is stated in the API docs.
    """

    def setUp(self):
        node = canopen.LocalNode(1, SAMPLE_EDS)
        self.sdo_node = node.sdo

    def test_record_iter_length(self):
        """Assume the "highest subindex supported" entry is not counted.

        Sub-objects without an OD entry should be skipped as well.
        """
        record = self.sdo_node[0x1018]
        subs = sum(1 for _ in iter(record))
        self.assertEqual(len(record), 3)
        self.assertEqual(subs, 3)

    def test_array_iter_length(self):
        """Assume the "highest subindex supported" entry is not counted."""
        array = self.sdo_node[0x1003]
        subs = sum(1 for _ in iter(array))
        self.assertEqual(len(array), 3)
        self.assertEqual(subs, 3)
        # Simulate more entries getting added dynamically
        array[0].set_data(b'\x08')
        subs = sum(1 for _ in iter(array))
        self.assertEqual(subs, 8)

    def test_array_members_dynamic(self):
        """Check if sub-objects missing from OD entry are generated dynamically."""
        array = self.sdo_node[0x1003]
        for var in array.values():
            self.assertIsInstance(var, canopen.sdo.SdoVariable)

    def test_array_contains_non_int(self):
        """SdoArray.__contains__ should handle non-int types gracefully."""
        array = self.sdo_node[0x1003]
        self.assertNotIn("not an int", array)
        self.assertNotIn(None, array)

    def test_get_variable_not_found(self):
        self.assertIsNone(self.sdo_node.get_variable(0x9999))

    def test_sdo_base_len(self):
        """SdoBase.__len__ returns the number of entries in the OD."""
        self.assertGreater(len(self.sdo_node), 0)

    def test_sdo_base_contains(self):
        """SdoBase.__contains__ checks membership in the OD."""
        self.assertIn(0x1008, self.sdo_node)
        self.assertNotIn(0x9999, self.sdo_node)

    def test_get_variable_sdo_variable(self):
        """get_variable returns an SdoVariable when the entry is a plain variable."""
        var = self.sdo_node.get_variable(0x1008)
        self.assertIsInstance(var, canopen.sdo.SdoVariable)
        self.assertIn("Manufacturer device name", var.name)

    def test_get_variable_record_subindex(self):
        """get_variable returns an SdoVariable for a subindex of a record."""
        var = self.sdo_node.get_variable(0x1018, 1)
        self.assertIsInstance(var, canopen.sdo.SdoVariable)
        self.assertIn("Vendor-ID", var.name)

    def test_sdo_record_repr(self):
        """SdoRecord.__repr__ includes the OD index."""
        r = repr(self.sdo_node[0x1018])
        self.assertIsInstance(r, str)
        self.assertIn("0x1018", r)

    def test_sdo_array_repr(self):
        """SdoArray.__repr__ returns a non-empty string."""
        r = repr(self.sdo_node[0x1003])
        self.assertIsInstance(r, str)
        self.assertIn("0x1003", r)

    def test_sdo_array_contains_int(self):
        """SdoArray.__contains__ returns True for a valid integer subindex."""
        array = self.sdo_node[0x1003]
        self.assertIn(0, array) # Subindex 0 is the "highest subindex supported" entry
        self.assertEqual(array[0].subindex, 0)
        self.assertIn(1, array)
        self.assertEqual(array[1].subindex, 1)
        self.assertIn("Pre-defined error field_1", array[1].name)
        self.assertIn(2, array)
        self.assertEqual(array[2].subindex, 2)
        # actually returns Pre-defined error field_1_2, probably due to comment in EDS: ; [1003sub2] left out for testing?
        # self.assertIn("Pre-defined error field_3", array[2].name) 
        self.assertIn(3, array)
        self.assertEqual(array[3].subindex, 3)
        self.assertIn("Pre-defined error field_3", array[3].name)
        
    def test_sdo_variable_readwriteable(self):
        """SdoVariable.readable returns the od.readable property. Same for writable."""
        var = self.sdo_node[0x1008]
        self.assertIsInstance(var.readable, bool)
        self.assertTrue(var.readable)
        self.assertIsInstance(var.writable, bool)
        self.assertFalse(var.writable)


class TestSDO(unittest.TestCase):
    """
    Test SDO traffic by example. Most are taken from
    http://www.canopensolutions.com/english/about_canopen/device_configuration_canopen.shtml
    """

    def _send_message(self, can_id, data, remote=False):
        """Will be used instead of the usual Network.send_message method.

        Checks that the message data is according to expected and answers
        with the provided data.
        """
        next_data = self.data.pop(0)
        self.assertEqual(next_data[0], TX, "No transmission was expected")
        self.assertSequenceEqual(data, next_data[1])
        self.assertEqual(can_id, 0x602)
        while self.data and self.data[0][0] == RX:
            self.network.notify(0x582, self.data.pop(0)[1], 0.0)

        self.message_sent = True

    def setUp(self):
        network = canopen.Network()
        network.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        network.send_message = self._send_message
        node = network.add_node(2, SAMPLE_EDS)
        node.sdo.RESPONSE_TIMEOUT = 0.01
        self.network = network

        self.message_sent = False

    def test_expedited_upload(self):
        self.data = [
            (TX, b'\x40\x18\x10\x01\x00\x00\x00\x00'),
            (RX, b'\x43\x18\x10\x01\x04\x00\x00\x00'),
        ]
        vendor_id = self.network[2].sdo[0x1018][1].raw
        self.assertEqual(vendor_id, 4)

        # UNSIGNED8 without padded data part (see issue #5)
        self.data = [
            (TX, b'\x40\x00\x14\x02\x00\x00\x00\x00'),  # upload initiate 0x1400:02
            (RX, b'\x4f\x00\x14\x02\xfe'),              # expedited, size=1
        ]
        trans_type = self.network[2].sdo[0x1400]['Transmission type RPDO 1'].raw
        self.assertEqual(trans_type, 254)

        # Same with padding to a full SDO frame
        self.data = [
            (TX, b'\x40\x00\x14\x02\x00\x00\x00\x00'),  # upload initiate 0x1400:02
            (RX, b'\x42\x00\x14\x02\xfe\x00\x00\x00'),  # expedited, no size indicated
        ]
        trans_type = self.network[2].sdo[0x1400]['Transmission type RPDO 1'].raw
        self.assertEqual(trans_type, 254)
        self.assertTrue(self.message_sent)

    def test_size_not_specified(self):
        self.data = [
            (TX, b'\x40\x00\x14\x02\x00\x00\x00\x00'),
            (RX, b'\x42\x00\x14\x02\xfe\x00\x00\x00'),
        ]
        # This method used to truncate to 1 byte, but returns raw content now
        data = self.network[2].sdo.upload(0x1400, 2)
        self.assertEqual(data, b'\xfe\x00\x00\x00')
        self.assertTrue(self.message_sent)

    def test_expedited_download(self):
        self.data = [
            (TX, b'\x2b\x17\x10\x00\xa0\x0f\x00\x00'),
            (RX, b'\x60\x17\x10\x00\x00\x00\x00\x00'),
        ]
        self.network[2].sdo[0x1017].raw = 4000
        self.assertTrue(self.message_sent)

    def test_segmented_upload(self):
        self.data = [
            (TX, b'\x40\x08\x10\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x08\x10\x00\x1a\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6e\x79\x20\x4e\x6f'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2d\x20\x4d\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6f\x6d\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6e\x73\x20\x21\x00\x00'),
        ]
        device_name = self.network[2].sdo[0x1008].raw
        self.assertEqual(device_name, "Tiny Node - Mega Domains !")

    def test_segmented_upload_too_much_data(self):
        # Server sends 5 bytes, but indicated size 4
        self.data = [
            (TX, b'\x40\x08\x10\x00\x00\x00\x00\x00'),  # upload initiate, 0x1008:00
            (RX, b'\x41\x08\x10\x00\x04\x00\x00\x00'),  # segmented, size indicated, 4 bytes
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),  # upload segment
            (RX, b'\x05\x54\x69\x6E\x79\x20\x00\x00'),  # segment complete, 5 bytes
        ]
        device_name = self.network[2].sdo[0x1008].raw
        self.assertEqual(device_name, "Tiny")

    def test_segmented_upload_toggle_bit_mismatch(self):
        """Server returns wrong toggle bit; client aborts and raises SdoCommunicationError."""
        self.data = [
            (TX, b'\x40\x08\x10\x00\x00\x00\x00\x00'),  # upload initiate 0x1008:00
            (RX, b'\x41\x08\x10\x00\x0a\x00\x00\x00'),  # segmented, size=10
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),  # first segment request, toggle=0
            (RX, b'\x10\x41\x42\x43\x44\x45\x46\x47'),  # server returns toggle=1 (wrong)
            (TX, b'\x80\x00\x00\x00\x00\x00\x03\x05'),  # abort: TOGGLE_NOT_ALTERNATED
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            _ = self.network[2].sdo[0x1008].raw
        self.assertIn("Toggle bit mismatch", str(cm.exception))

    def test_upload_initiate_unexpected_response(self):
        """ReadableStream raises when server response command is not RESPONSE_UPLOAD."""
        self.data = [
            (TX, b'\x40\x18\x10\x01\x00\x00\x00\x00'),  # upload initiate 0x1018:01
            (RX, b'\x20\x18\x10\x01\x00\x00\x00\x00'),  # bad: 0x20 & 0xE0 = 0x20 ≠ 0x40
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            _ = self.network[2].sdo[0x1018][1].raw
        self.assertIn("Unexpected response 0x20", str(cm.exception))

    def test_upload_initiate_wrong_index(self):
        """ReadableStream raises when server responds for a different index."""
        self.data = [
            (TX, b'\x40\x18\x10\x01\x00\x00\x00\x00'),  # upload initiate 0x1018:01
            (RX, b'\x43\x00\x20\x00\x04\x00\x00\x00'),  # response for 0x2000:00 instead
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            _ = self.network[2].sdo[0x1018][1].raw
        self.assertIn("0x2000", str(cm.exception))

    def test_segmented_upload_unexpected_segment_response(self):
        """ReadableStream aborts and raises when segment response command is wrong."""
        self.data = [
            (TX, b'\x40\x08\x10\x00\x00\x00\x00\x00'),  # upload initiate 0x1008:00
            (RX, b'\x41\x08\x10\x00\x0a\x00\x00\x00'),  # segmented, size=10
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),  # segment request, toggle=0
            (RX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),  # bad: 0x60 & 0xE0 = 0x60 ≠ 0x00
            (TX, b'\x80\x00\x00\x00\x01\x00\x04\x05'),  # abort: INVALID_COMMAND_SPECIFIER
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            _ = self.network[2].sdo[0x1008].raw
        self.assertIn("Unexpected response 0x60", str(cm.exception))

    def test_segmented_download_initiate_unexpected_response(self):
        """WritableStream aborts and raises when download initiate response command is wrong."""
        self.data = [
            (TX, b'\x21\x00\x20\x00\x0a\x00\x00\x00'),  # segmented download 0x2000:00, size=10
            (RX, b'\x40\x00\x20\x00\x00\x00\x00\x00'),  # bad: 0x40 ≠ RESPONSE_DOWNLOAD 0x60
            (TX, b'\x80\x00\x00\x00\x01\x00\x04\x05'),  # abort: INVALID_COMMAND_SPECIFIER
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            self.network[2].sdo[0x2000].raw = 'ABCDEFGHIJ'
        self.assertIn("Unexpected response 0x40", str(cm.exception))

    def test_expedited_download_unexpected_response(self):
        """WritableStream aborts and raises when expedited download response command is wrong."""
        self.data = [
            (TX, b'\x2f\x00\x14\x02\xff\x00\x00\x00'),  # expedited download 0x1400:02
            (RX, b'\x40\x00\x14\x02\x00\x00\x00\x00'),  # bad: 0x40 & 0xE0 = 0x40 ≠ 0x60
            (TX, b'\x80\x00\x00\x00\x01\x00\x04\x05'),  # abort: INVALID_COMMAND_SPECIFIER
        ]
        with self.assertRaises(canopen.SdoCommunicationError):
            self.network[2].sdo[0x1400][2].raw = 0xff

    def test_segmented_download_write_unexpected_response(self):
        """WritableStream aborts and raises when the segment download response command is wrong."""
        self.data = [
            (TX, b'\x21\x00\x20\x00\x0d\x00\x00\x00'),  # segmented download 0x2000:00, size=13
            (RX, b'\x60\x00\x20\x00\x00\x00\x00\x00'),  # RESPONSE_DOWNLOAD OK
            (TX, b'\x00\x41\x20\x6c\x6f\x6e\x67\x20'),  # first segment 'A long ', toggle=0
            (RX, b'\x40\x00\x00\x00\x00\x00\x00\x00'),  # bad: 0x40 & 0xE0 = 0x40 ≠ 0x20
            (TX, b'\x80\x00\x00\x00\x01\x00\x04\x05'),  # abort: INVALID_COMMAND_SPECIFIER
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            self.network[2].sdo[0x2000].raw = 'A long string'
        self.assertIn("expected 0x20", str(cm.exception))

    def test_segmented_download(self):
        self.data = [
            (TX, b'\x21\x00\x20\x00\x0d\x00\x00\x00'),
            (RX, b'\x60\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x00\x41\x20\x6c\x6f\x6e\x67\x20'),
            (RX, b'\x20\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x13\x73\x74\x72\x69\x6e\x67\x00'),
            (RX, b'\x30\x00\x20\x00\x00\x00\x00\x00'),
        ]
        self.network[2].sdo["Writable string"].raw = 'A long string'

    def test_block_download(self):
        self.data = [
            (TX, b'\xc6\x00\x20\x00\x1e\x00\x00\x00'),
            (RX, b'\xa4\x00\x20\x00\x7f\x00\x00\x00'),
            (TX, b'\x01\x41\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x02\x79\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x03\x79\x20\x6c\x6f\x6e\x67\x20'),
            (TX, b'\x04\x73\x74\x72\x69\x6e\x67\x2e'),
            (TX, b'\x85\x2e\x2e\x00\x00\x00\x00\x00'),
            (RX, b'\xa2\x05\x7f\x00\x00\x00\x00\x00'),
            (TX, b'\xd5\x45\x69\x00\x00\x00\x00\x00'),
            (RX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'),
        ]
        data = b'A really really long string...'
        with (
            self.network[2]
            .sdo["Writable string"]
            .open('wb', size=len(data), block_transfer=True) as fp
        ):
            fp.write(data)

    def test_block_download_retransmit(self):
        """Server acknowledges only 3 of 5 sequences; client must retransmit the rest."""
        self.data = [
            (TX, b'\xc6\x00\x20\x00\x23\x00\x00\x00'),  # init block download, size=35, CRC
            (RX, b'\xa4\x00\x20\x00\x05\x00\x00\x00'),  # server init resp, blksize=5, CRC
            (TX, b'\x01\x41\x42\x43\x44\x45\x46\x47'),  # seq 1: ABCDEFG
            (TX, b'\x02\x48\x49\x4a\x4b\x4c\x4d\x4e'),  # seq 2: HIJKLMN
            (TX, b'\x03\x4f\x50\x51\x52\x53\x54\x55'),  # seq 3: OPQRSTU
            (TX, b'\x04\x56\x57\x58\x59\x5a\x31\x32'),  # seq 4: VWXYZ12
            (TX, b'\x85\x33\x34\x35\x36\x37\x38\x39'),  # seq 5 (NO_MORE_BLOCKS): 3456789
            (RX, b'\xa2\x03\x05\x00\x00\x00\x00\x00'),  # ack: only 3 received, blksize=5
            (TX, b'\x01\x56\x57\x58\x59\x5a\x31\x32'),  # retransmit seq 1: VWXYZ12
            (TX, b'\x82\x33\x34\x35\x36\x37\x38\x39'),  # retransmit seq 2 (NO_MORE_BLOCKS): 3456789
            (RX, b'\xa2\x02\x05\x00\x00\x00\x00\x00'),  # ack: all 2 received, blksize=5
            (TX, b'\xc1\x80\x00\x00\x00\x00\x00\x00'),  # end block transfer, CRC=0x0080
            (RX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'),  # server confirms end
        ]
        data = b'ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789'
        with (
            self.network[2]
            .sdo["Writable string"]
            .open('wb', size=len(data), block_transfer=True) as fp
        ):
            fp.write(data)

    def test_block_download_initiate_unexpected_response(self):
        """BlockDownloadStream aborts and raises when block download initiate response is wrong."""
        data = b'A really really long string...'  # 30 bytes
        self.data = [
            (TX, b'\xc6\x00\x20\x00\x1e\x00\x00\x00'),  # block download initiate, size=30
            (RX, b'\x40\x00\x20\x00\x00\x00\x00\x00'),  # bad: 0x40 & 0xE0 = 0x40 ≠ 0xA0
            (TX, b'\x80\x00\x00\x00\x01\x00\x04\x05'),  # abort: INVALID_COMMAND_SPECIFIER
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            with self.network[2].sdo["Writable string"].open('wb', size=len(data), block_transfer=True) as fp:
                fp.write(data)
        self.assertIn("Unexpected response 0x40", str(cm.exception))

    def test_block_upload_initiate_unexpected_response(self):
        """BlockUploadStream aborts and raises when block upload initiate response is wrong."""
        self.data = [
            (TX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),  # block upload initiate 0x1008:00
            (RX, b'\x40\x08\x10\x00\x00\x00\x00\x00'),  # bad: 0x40 & 0xE0 = 0x40 ≠ 0xC0
            (TX, b'\x80\x00\x00\x00\x01\x00\x04\x05'),  # abort: INVALID_COMMAND_SPECIFIER
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            with self.network[2].sdo[0x1008].open('rb', block_transfer=True) as fp:
                fp.read()
        self.assertIn("Unexpected response 0x40", str(cm.exception))

    def test_block_download_unsuccessful(self):
        """BlockDownloadStream.close raises when server does not confirm end block transfer."""
        data = b'A really really long string...'  # 30 bytes
        self.data = [
            (TX, b'\xc6\x00\x20\x00\x1e\x00\x00\x00'),
            (RX, b'\xa4\x00\x20\x00\x7f\x00\x00\x00'),
            (TX, b'\x01\x41\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x02\x79\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x03\x79\x20\x6c\x6f\x6e\x67\x20'),
            (TX, b'\x04\x73\x74\x72\x69\x6e\x67\x2e'),
            (TX, b'\x85\x2e\x2e\x00\x00\x00\x00\x00'),
            (RX, b'\xa2\x05\x7f\x00\x00\x00\x00\x00'),
            (TX, b'\xd5\x45\x69\x00\x00\x00\x00\x00'),
            (RX, b'\xa0\x00\x00\x00\x00\x00\x00\x00'),  # bad: END_BLOCK_TRANSFER bit not set
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            with self.network[2].sdo["Writable string"].open('wb', size=len(data), block_transfer=True) as fp:
                fp.write(data)
        self.assertIn("Block download unsuccessful", str(cm.exception))

    def test_block_download_no_crc(self):
        """Block download with request_crc_support=False omits CRC bytes."""
        data = b'A really really long string...'  # 30 bytes
        self.data = [
            (TX, b'\xc2\x00\x20\x00\x1e\x00\x00\x00'),  # init: BLOCK_SIZE_SPECIFIED, no CRC_SUPPORTED
            (RX, b'\xa0\x00\x20\x00\x7f\x00\x00\x00'),  # server resp: blksize=127, no CRC
            (TX, b'\x01\x41\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x02\x79\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x03\x79\x20\x6c\x6f\x6e\x67\x20'),
            (TX, b'\x04\x73\x74\x72\x69\x6e\x67\x2e'),
            (TX, b'\x85\x2e\x2e\x00\x00\x00\x00\x00'),
            (RX, b'\xa2\x05\x7f\x00\x00\x00\x00\x00'),
            (TX, b'\xd5\x00\x00\x00\x00\x00\x00\x00'),  # end: no CRC bytes
            (RX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'),
        ]
        with self.network[2].sdo["Writable string"].open(
                'wb', size=len(data), block_transfer=True, request_crc_support=False) as fp:
            fp.write(data)

    def test_block_download_block_ack_wrong_command(self):
        """BlockDownloadStream._block_ack aborts when the ACK command byte is wrong."""
        data = b'A really really long string...'  # 30 bytes
        self.data = [
            (TX, b'\xc6\x00\x20\x00\x1e\x00\x00\x00'),
            (RX, b'\xa4\x00\x20\x00\x7f\x00\x00\x00'),
            (TX, b'\x01\x41\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x02\x79\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x03\x79\x20\x6c\x6f\x6e\x67\x20'),
            (TX, b'\x04\x73\x74\x72\x69\x6e\x67\x2e'),
            (TX, b'\x85\x2e\x2e\x00\x00\x00\x00\x00'),
            (RX, b'\x62\x05\x7f\x00\x00\x00\x00\x00'),  # bad: 0x62 & 0xE0 = 0x60 != RESPONSE_BLOCK_DOWNLOAD
            (TX, b'\x80\x00\x00\x00\x01\x00\x04\x05'),  # abort INVALID_COMMAND_SPECIFIER
            # close() runs in finally block and sends END_BLOCK_TRANSFER (CRC included, _done=True)
            (TX, b'\xd5\x45\x69\x00\x00\x00\x00\x00'),
            (RX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'),
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            with self.network[2].sdo["Writable string"].open(
                    'wb', size=len(data), block_transfer=True) as fp:
                fp.write(data)
        self.assertIn("Unexpected response 0x62", str(cm.exception))

    def test_block_download_block_ack_no_transfer_response(self):
        """BlockDownloadStream._block_ack aborts when BLOCK_TRANSFER_RESPONSE bit is not set."""
        data = b'A really really long string...'  # 30 bytes
        self.data = [
            (TX, b'\xc6\x00\x20\x00\x1e\x00\x00\x00'),
            (RX, b'\xa4\x00\x20\x00\x7f\x00\x00\x00'),
            (TX, b'\x01\x41\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x02\x79\x20\x72\x65\x61\x6c\x6c'),
            (TX, b'\x03\x79\x20\x6c\x6f\x6e\x67\x20'),
            (TX, b'\x04\x73\x74\x72\x69\x6e\x67\x2e'),
            (TX, b'\x85\x2e\x2e\x00\x00\x00\x00\x00'),
            (RX, b'\xa0\x05\x7f\x00\x00\x00\x00\x00'),  # bad: 0xA0 & 0x3 = 0 != BLOCK_TRANSFER_RESPONSE
            (TX, b'\x80\x00\x00\x00\x01\x00\x04\x05'),  # abort INVALID_COMMAND_SPECIFIER
            (TX, b'\xd5\x45\x69\x00\x00\x00\x00\x00'),  # close() END_BLOCK_TRANSFER (CRC)
            (RX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'),
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            with self.network[2].sdo["Writable string"].open(
                    'wb', size=len(data), block_transfer=True) as fp:
                fp.write(data)
        self.assertIn("block download response", str(cm.exception))

    def test_block_download_wrong_index_response(self):
        """BlockDownloadStream aborts when server responds with wrong index."""
        data = b'A really really long string...'  # 30 bytes
        self.data = [
            (TX, b'\xc6\x00\x20\x00\x1e\x00\x00\x00'),   # init for 0x2000:00
            (RX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),   # server responds for 0x1008:00 (wrong)
            (TX, b'\x80\x00\x00\x00\x00\x00\x00\x08'),   # abort GENERAL_ERROR
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            with self.network[2].sdo["Writable string"].open(
                    'wb', size=len(data), block_transfer=True) as fp:
                fp.write(data)
        self.assertIn("0x1008", str(cm.exception))

    def test_block_upload_wrong_index_response(self):
        """BlockUploadStream raises when server responds with wrong index (no abort sent)."""
        self.data = [
            (TX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),   # initiate for 0x1008:00
            (RX, b'\xc4\x00\x20\x00\x1a\x00\x00\x00'),   # server responds for 0x2000:00 (wrong)
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            with self.network[2].sdo[0x1008].open('rb', block_transfer=True) as fp:
                fp.read()
        self.assertIn("0x2000", str(cm.exception))

    def test_block_upload_end_unexpected_response(self):
        """BlockUploadStream._end_upload aborts when end-of-block response has wrong command."""
        self.data = [
            (TX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),
            (RX, b'\xc6\x08\x10\x00\x1a\x00\x00\x00'),
            (TX, b'\xa3\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x01\x54\x69\x6e\x79\x20\x4e\x6f'),
            (RX, b'\x02\x64\x65\x20\x2d\x20\x4d\x65'),
            (RX, b'\x03\x67\x61\x20\x44\x6f\x6d\x61'),
            (RX, b'\x84\x69\x6e\x73\x20\x21\x00\x00'),
            (TX, b'\xa2\x04\x7f\x00\x00\x00\x00\x00'),
            (RX, b'\x40\x40\xe1\x00\x00\x00\x00\x00'),   # bad: 0x40 & 0xE0 = 0x40 != RESPONSE_BLOCK_UPLOAD
            (TX, b'\x80\x00\x00\x00\x01\x00\x04\x05'),   # abort INVALID_COMMAND_SPECIFIER
        ]
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            with self.network[2].sdo[0x1008].open('r', block_transfer=True) as fp:
                fp.read()
        self.assertIn("Unexpected response 0x40", str(cm.exception))

    def test_segmented_download_zero_length(self):
        self.data = [
            (TX, b'\x21\x00\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x60\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x0F\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x20\x00\x00\x00\x00\x00\x00\x00'),
        ]
        self.network[2].sdo[0x2000].raw = ""
        self.assertTrue(self.message_sent)

    def test_block_upload(self):
        self.data = [
            (TX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),
            (RX, b'\xc6\x08\x10\x00\x1a\x00\x00\x00'),
            (TX, b'\xa3\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x01\x54\x69\x6e\x79\x20\x4e\x6f'),
            (RX, b'\x02\x64\x65\x20\x2d\x20\x4d\x65'),
            (RX, b'\x03\x67\x61\x20\x44\x6f\x6d\x61'),
            (RX, b'\x84\x69\x6e\x73\x20\x21\x00\x00'),
            (TX, b'\xa2\x04\x7f\x00\x00\x00\x00\x00'),
            (RX, b'\xc9\x40\xe1\x00\x00\x00\x00\x00'),
            (TX, b'\xa1\x00\x00\x00\x00\x00\x00\x00')
        ]
        with self.network[2].sdo[0x1008].open('r', block_transfer=True) as fp:
            data = fp.read()
        self.assertEqual(data, 'Tiny Node - Mega Domains !')

    def test_sdo_block_upload_retransmit(self):
        """Trigger a retransmit by only validating a block partially."""
        self.data = [
            (TX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),
            (RX, b'\xc4\x08\x10\x00\x00\x00\x00\x00'),
            (TX, b'\xa3\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x01\x74\x68\x65\x20\x63\x72\x61'),
            (RX, b'\x02\x7a\x79\x20\x66\x6f\x78\x20'),
            (RX, b'\x03\x6a\x75\x6d\x70\x73\x20\x6f'),
            (RX, b'\x04\x76\x65\x72\x20\x74\x68\x65'),
            (RX, b'\x05\x20\x6c\x61\x7a\x79\x20\x64'),
            (RX, b'\x06\x6f\x67\x0a\x74\x68\x65\x20'),
            (RX, b'\x07\x63\x72\x61\x7a\x79\x20\x66'),
            (RX, b'\x08\x6f\x78\x20\x6a\x75\x6d\x70'),
            (RX, b'\x09\x73\x20\x6f\x76\x65\x72\x20'),
            (RX, b'\x0a\x74\x68\x65\x20\x6c\x61\x7a'),
            (RX, b'\x0b\x79\x20\x64\x6f\x67\x0a\x74'),
            (RX, b'\x0c\x68\x65\x20\x63\x72\x61\x7a'),
            (RX, b'\x0d\x79\x20\x66\x6f\x78\x20\x6a'),
            (RX, b'\x0e\x75\x6d\x70\x73\x20\x6f\x76'),
            (RX, b'\x0f\x65\x72\x20\x74\x68\x65\x20'),
            (RX, b'\x10\x6c\x61\x7a\x79\x20\x64\x6f'),
            (RX, b'\x11\x67\x0a\x74\x68\x65\x20\x63'),
            (RX, b'\x12\x72\x61\x7a\x79\x20\x66\x6f'),
            (RX, b'\x13\x78\x20\x6a\x75\x6d\x70\x73'),
            (RX, b'\x14\x20\x6f\x76\x65\x72\x20\x74'),
            (RX, b'\x15\x68\x65\x20\x6c\x61\x7a\x79'),
            (RX, b'\x16\x20\x64\x6f\x67\x0a\x74\x68'),
            (RX, b'\x17\x65\x20\x63\x72\x61\x7a\x79'),
            (RX, b'\x18\x20\x66\x6f\x78\x20\x6a\x75'),
            (RX, b'\x19\x6d\x70\x73\x20\x6f\x76\x65'),
            (RX, b'\x1a\x72\x20\x74\x68\x65\x20\x6c'),
            (RX, b'\x1b\x61\x7a\x79\x20\x64\x6f\x67'),
            (RX, b'\x1c\x0a\x74\x68\x65\x20\x63\x72'),
            (RX, b'\x1d\x61\x7a\x79\x20\x66\x6f\x78'),
            (RX, b'\x1e\x20\x6a\x75\x6d\x70\x73\x20'),
            (RX, b'\x1f\x6f\x76\x65\x72\x20\x74\x68'),
            (RX, b'\x20\x65\x20\x6c\x61\x7a\x79\x20'),
            (RX, b'\x21\x64\x6f\x67\x0a\x74\x68\x65'),
            (RX, b'\x22\x20\x63\x72\x61\x7a\x79\x20'),
            (RX, b'\x23\x66\x6f\x78\x20\x6a\x75\x6d'),
            (RX, b'\x24\x70\x73\x20\x6f\x76\x65\x72'),
            (RX, b'\x25\x20\x74\x68\x65\x20\x6c\x61'),
            (RX, b'\x26\x7a\x79\x20\x64\x6f\x67\x0a'),
            (RX, b'\x27\x74\x68\x65\x20\x63\x72\x61'),
            (RX, b'\x28\x7a\x79\x20\x66\x6f\x78\x20'),
            (RX, b'\x29\x6a\x75\x6d\x70\x73\x20\x6f'),
            (RX, b'\x2a\x76\x65\x72\x20\x74\x68\x65'),
            (RX, b'\x2b\x20\x6c\x61\x7a\x79\x20\x64'),
            (RX, b'\x2c\x6f\x67\x0a\x74\x68\x65\x20'),
            (RX, b'\x2d\x63\x72\x61\x7a\x79\x20\x66'),
            (RX, b'\x2e\x6f\x78\x20\x6a\x75\x6d\x70'),
            (RX, b'\x2f\x73\x20\x6f\x76\x65\x72\x20'),
            (RX, b'\x30\x74\x68\x65\x20\x6c\x61\x7a'),
            (RX, b'\x31\x79\x20\x64\x6f\x67\x0a\x74'),
            (RX, b'\x32\x68\x65\x20\x63\x72\x61\x7a'),
            (RX, b'\x34\x79\x20\x66\x6f\x78\x20\x6a'),  # --> Wrong seqno (x34 instead of x33)
            (RX, b'\x33\x75\x6d\x70\x73\x20\x6f\x76'),  # All the following frames until end of block
            (RX, b'\x35\x65\x72\x20\x74\x68\x65\x20'),  # will be ignored by the client and should be 
            (RX, b'\x36\x6c\x61\x7a\x79\x20\x64\x6f'),  # resent by server.
            (RX, b'\x37\x67\x0a\x74\x68\x65\x20\x63'),  
            (RX, b'\x38\x72\x61\x7a\x79\x20\x66\x6f'),
            (RX, b'\x39\x78\x20\x6a\x75\x6d\x70\x73'),
            (RX, b'\x3a\x20\x6f\x76\x65\x72\x20\x74'),
            (RX, b'\x3b\x68\x65\x20\x6c\x61\x7a\x79'),
            (RX, b'\x3c\x20\x64\x6f\x67\x0a\x74\x68'),
            (RX, b'\x3d\x65\x20\x63\x72\x61\x7a\x79'),
            (RX, b'\x3e\x20\x66\x6f\x78\x20\x6a\x75'),
            (RX, b'\x3f\x6d\x70\x73\x20\x6f\x76\x65'),
            (RX, b'\x40\x72\x20\x74\x68\x65\x20\x6c'),
            (RX, b'\x41\x61\x7a\x79\x20\x64\x6f\x67'),
            (RX, b'\x42\x0a\x74\x68\x65\x20\x63\x72'),
            (RX, b'\x43\x61\x7a\x79\x20\x66\x6f\x78'),
            (RX, b'\x44\x20\x6a\x75\x6d\x70\x73\x20'),
            (RX, b'\x45\x6f\x76\x65\x72\x20\x74\x68'),
            (RX, b'\x46\x65\x20\x6c\x61\x7a\x79\x20'),
            (RX, b'\x47\x64\x6f\x67\x0a\x74\x68\x65'),
            (RX, b'\x48\x20\x63\x72\x61\x7a\x79\x20'),
            (RX, b'\x49\x66\x6f\x78\x20\x6a\x75\x6d'),
            (RX, b'\x4a\x70\x73\x20\x6f\x76\x65\x72'),
            (RX, b'\x4b\x20\x74\x68\x65\x20\x6c\x61'),
            (RX, b'\x4c\x7a\x79\x20\x64\x6f\x67\x0a'),
            (RX, b'\x4d\x74\x68\x65\x20\x63\x72\x61'),
            (RX, b'\x4e\x7a\x79\x20\x66\x6f\x78\x20'),
            (RX, b'\x4f\x6a\x75\x6d\x70\x73\x20\x6f'),
            (RX, b'\x50\x76\x65\x72\x20\x74\x68\x65'),
            (RX, b'\x51\x20\x6c\x61\x7a\x79\x20\x64'),
            (RX, b'\x52\x6f\x67\x0a\x74\x68\x65\x20'),
            (RX, b'\x53\x63\x72\x61\x7a\x79\x20\x66'),
            (RX, b'\x54\x6f\x78\x20\x6a\x75\x6d\x70'),
            (RX, b'\x55\x73\x20\x6f\x76\x65\x72\x20'),
            (RX, b'\x56\x74\x68\x65\x20\x6c\x61\x7a'),
            (RX, b'\x57\x79\x20\x64\x6f\x67\x0a\x74'),
            (RX, b'\x58\x68\x65\x20\x63\x72\x61\x7a'),
            (RX, b'\x59\x79\x20\x66\x6f\x78\x20\x6a'),
            (RX, b'\x5a\x75\x6d\x70\x73\x20\x6f\x76'),
            (RX, b'\x5b\x65\x72\x20\x74\x68\x65\x20'),
            (RX, b'\x5c\x6c\x61\x7a\x79\x20\x64\x6f'),
            (RX, b'\x5d\x67\x0a\x74\x68\x65\x20\x63'),
            (RX, b'\x5e\x72\x61\x7a\x79\x20\x66\x6f'),
            (RX, b'\x5f\x78\x20\x6a\x75\x6d\x70\x73'),
            (RX, b'\x60\x20\x6f\x76\x65\x72\x20\x74'),
            (RX, b'\x61\x68\x65\x20\x6c\x61\x7a\x79'),
            (RX, b'\x62\x20\x64\x6f\x67\x0a\x74\x68'),
            (RX, b'\x63\x65\x20\x63\x72\x61\x7a\x79'),
            (RX, b'\x64\x20\x66\x6f\x78\x20\x6a\x75'),
            (RX, b'\x65\x6d\x70\x73\x20\x6f\x76\x65'),
            (RX, b'\x66\x72\x20\x74\x68\x65\x20\x6c'),
            (RX, b'\x67\x61\x7a\x79\x20\x64\x6f\x67'),
            (RX, b'\x68\x0a\x74\x68\x65\x20\x63\x72'),
            (RX, b'\x69\x61\x7a\x79\x20\x66\x6f\x78'),
            (RX, b'\x6a\x20\x6a\x75\x6d\x70\x73\x20'),
            (RX, b'\x6b\x6f\x76\x65\x72\x20\x74\x68'),
            (RX, b'\x6c\x65\x20\x6c\x61\x7a\x79\x20'),
            (RX, b'\x6d\x64\x6f\x67\x0a\x74\x68\x65'),
            (RX, b'\x6e\x20\x63\x72\x61\x7a\x79\x20'),
            (RX, b'\x6f\x66\x6f\x78\x20\x6a\x75\x6d'),
            (RX, b'\x70\x70\x73\x20\x6f\x76\x65\x72'),
            (RX, b'\x71\x20\x74\x68\x65\x20\x6c\x61'),
            (RX, b'\x72\x7a\x79\x20\x64\x6f\x67\x0a'),
            (RX, b'\x73\x74\x68\x65\x20\x63\x72\x61'),
            (RX, b'\x74\x7a\x79\x20\x66\x6f\x78\x20'),
            (RX, b'\x75\x6a\x75\x6d\x70\x73\x20\x6f'),
            (RX, b'\x76\x76\x65\x72\x20\x74\x68\x65'),
            (RX, b'\x77\x20\x6c\x61\x7a\x79\x20\x64'),
            (RX, b'\x78\x6f\x67\x0a\x74\x68\x65\x20'),
            (RX, b'\x79\x63\x72\x61\x7a\x79\x20\x66'),
            (RX, b'\x7a\x6f\x78\x20\x6a\x75\x6d\x70'),
            (RX, b'\x7b\x73\x20\x6f\x76\x65\x72\x20'),
            (RX, b'\x7c\x74\x68\x65\x20\x6c\x61\x7a'),
            (RX, b'\x7d\x79\x20\x64\x6f\x67\x0a\x74'),
            (RX, b'\x7e\x68\x65\x20\x63\x72\x61\x7a'),
            (RX, b'\x7f\x79\x20\x66\x6f\x78\x20\x6a'),  # --> Last element of block
            (TX, b'\xa2\x32\x7f\x00\x00\x00\x00\x00'),  # --> Last good seqno (x32)
            (RX, b'\x01\x79\x20\x66\x6f\x78\x20\x6a'),  # --> Server starts resending from last acknowledged block
            (RX, b'\x02\x75\x6d\x70\x73\x20\x6f\x76'),
            (RX, b'\x03\x65\x72\x20\x74\x68\x65\x20'),
            (RX, b'\x04\x6c\x61\x7a\x79\x20\x64\x6f'),
            (RX, b'\x05\x67\x0a\x74\x68\x65\x20\x63'),
            (RX, b'\x06\x72\x61\x7a\x79\x20\x66\x6f'),
            (RX, b'\x07\x78\x20\x6a\x75\x6d\x70\x73'),
            (RX, b'\x08\x20\x6f\x76\x65\x72\x20\x74'),
            (RX, b'\x09\x68\x65\x20\x6c\x61\x7a\x79'),
            (RX, b'\x0a\x20\x64\x6f\x67\x0a\x74\x68'),
            (RX, b'\x0b\x65\x20\x63\x72\x61\x7a\x79'),
            (RX, b'\x0c\x20\x66\x6f\x78\x20\x6a\x75'),
            (RX, b'\x0d\x6d\x70\x73\x20\x6f\x76\x65'),
            (RX, b'\x0e\x72\x20\x74\x68\x65\x20\x6c'),
            (RX, b'\x0f\x61\x7a\x79\x20\x64\x6f\x67'),
            (RX, b'\x10\x0a\x74\x68\x65\x20\x63\x72'),
            (RX, b'\x11\x61\x7a\x79\x20\x66\x6f\x78'),
            (RX, b'\x12\x20\x6a\x75\x6d\x70\x73\x20'),
            (RX, b'\x13\x6f\x76\x65\x72\x20\x74\x68'),
            (RX, b'\x14\x65\x20\x6c\x61\x7a\x79\x20'),
            (RX, b'\x15\x64\x6f\x67\x0a\x74\x68\x65'),
            (RX, b'\x16\x20\x63\x72\x61\x7a\x79\x20'),
            (RX, b'\x17\x66\x6f\x78\x20\x6a\x75\x6d'),
            (RX, b'\x18\x70\x73\x20\x6f\x76\x65\x72'),
            (RX, b'\x19\x20\x74\x68\x65\x20\x6c\x61'),
            (RX, b'\x1a\x7a\x79\x20\x64\x6f\x67\x0a'),
            (RX, b'\x1b\x74\x68\x65\x20\x63\x72\x61'),
            (RX, b'\x1c\x7a\x79\x20\x66\x6f\x78\x20'),
            (RX, b'\x1d\x6a\x75\x6d\x70\x73\x20\x6f'),
            (RX, b'\x1e\x76\x65\x72\x20\x74\x68\x65'),
            (RX, b'\x1f\x20\x6c\x61\x7a\x79\x20\x64'),
            (RX, b'\x20\x6f\x67\x0a\x74\x68\x65\x20'),
            (RX, b'\x21\x63\x72\x61\x7a\x79\x20\x66'),
            (RX, b'\x22\x6f\x78\x20\x6a\x75\x6d\x70'),
            (RX, b'\x23\x73\x20\x6f\x76\x65\x72\x20'),
            (RX, b'\x24\x74\x68\x65\x20\x6c\x61\x7a'),
            (RX, b'\x25\x79\x20\x64\x6f\x67\x0a\x74'),
            (RX, b'\x26\x68\x65\x20\x63\x72\x61\x7a'),
            (RX, b'\x27\x79\x20\x66\x6f\x78\x20\x6a'),
            (RX, b'\x28\x75\x6d\x70\x73\x20\x6f\x76'),
            (RX, b'\x29\x65\x72\x20\x74\x68\x65\x20'),
            (RX, b'\x2a\x6c\x61\x7a\x79\x20\x64\x6f'),
            (RX, b'\x2b\x67\x0a\x74\x68\x65\x20\x63'),
            (RX, b'\x2c\x72\x61\x7a\x79\x20\x66\x6f'),
            (RX, b'\x2d\x78\x20\x6a\x75\x6d\x70\x73'),
            (RX, b'\x2e\x20\x6f\x76\x65\x72\x20\x74'),
            (RX, b'\x2f\x68\x65\x20\x6c\x61\x7a\x79'),
            (RX, b'\x30\x20\x64\x6f\x67\x0a\x74\x68'),
            (RX, b'\x31\x65\x20\x63\x72\x61\x7a\x79'),
            (RX, b'\x32\x20\x66\x6f\x78\x20\x6a\x75'),
            (RX, b'\x33\x6d\x70\x73\x20\x6f\x76\x65'),
            (RX, b'\x34\x72\x20\x74\x68\x65\x20\x6c'),
            (RX, b'\x35\x61\x7a\x79\x20\x64\x6f\x67'),
            (RX, b'\x36\x0a\x74\x68\x65\x20\x63\x72'),
            (RX, b'\x37\x61\x7a\x79\x20\x66\x6f\x78'),
            (RX, b'\x38\x20\x6a\x75\x6d\x70\x73\x20'),
            (RX, b'\x39\x6f\x76\x65\x72\x20\x74\x68'),
            (RX, b'\x3a\x65\x20\x6c\x61\x7a\x79\x20'),
            (RX, b'\x3b\x64\x6f\x67\x0a\x74\x68\x65'),
            (RX, b'\x3c\x20\x63\x72\x61\x7a\x79\x20'),
            (RX, b'\x3d\x66\x6f\x78\x20\x6a\x75\x6d'),
            (RX, b'\x3e\x70\x73\x20\x6f\x76\x65\x72'),
            (RX, b'\x3f\x20\x74\x68\x65\x20\x6c\x61'),
            (RX, b'\x40\x7a\x79\x20\x64\x6f\x67\x0a'),
            (RX, b'\x41\x74\x68\x65\x20\x63\x72\x61'),
            (RX, b'\x42\x7a\x79\x20\x66\x6f\x78\x20'),
            (RX, b'\x43\x6a\x75\x6d\x70\x73\x20\x6f'),
            (RX, b'\x44\x76\x65\x72\x20\x74\x68\x65'),
            (RX, b'\x45\x20\x6c\x61\x7a\x79\x20\x64'),
            (RX, b'\x46\x6f\x67\x0a\x74\x68\x65\x20'),
            (RX, b'\x47\x63\x72\x61\x7a\x79\x20\x66'),
            (RX, b'\x48\x6f\x78\x20\x6a\x75\x6d\x70'),
            (RX, b'\x49\x73\x20\x6f\x76\x65\x72\x20'),
            (RX, b'\x4a\x74\x68\x65\x20\x6c\x61\x7a'),
            (RX, b'\x4b\x79\x20\x64\x6f\x67\x0a\x74'),
            (RX, b'\x4c\x68\x65\x20\x63\x72\x61\x7a'),
            (RX, b'\x4d\x79\x20\x66\x6f\x78\x20\x6a'),
            (RX, b'\x4e\x75\x6d\x70\x73\x20\x6f\x76'),
            (RX, b'\x4f\x65\x72\x20\x74\x68\x65\x20'),
            (RX, b'\x50\x6c\x61\x7a\x79\x20\x64\x6f'),
            (RX, b'\x51\x67\x0a\x74\x68\x65\x20\x63'),
            (RX, b'\x52\x72\x61\x7a\x79\x20\x66\x6f'),
            (RX, b'\x53\x78\x20\x6a\x75\x6d\x70\x73'),
            (RX, b'\x54\x20\x6f\x76\x65\x72\x20\x74'),
            (RX, b'\x55\x68\x65\x20\x6c\x61\x7a\x79'),
            (RX, b'\x56\x20\x64\x6f\x67\x0a\x74\x68'),
            (RX, b'\x57\x65\x20\x63\x72\x61\x7a\x79'),
            (RX, b'\x58\x20\x66\x6f\x78\x20\x6a\x75'),
            (RX, b'\x59\x6d\x70\x73\x20\x6f\x76\x65'),
            (RX, b'\x5a\x72\x20\x74\x68\x65\x20\x6c'),
            (RX, b'\x5b\x61\x7a\x79\x20\x64\x6f\x67'),
            (RX, b'\x5c\x0a\x74\x68\x65\x20\x63\x72'),
            (RX, b'\x5d\x61\x7a\x79\x20\x66\x6f\x78'),
            (RX, b'\x5e\x20\x6a\x75\x6d\x70\x73\x20'),
            (RX, b'\x5f\x6f\x76\x65\x72\x20\x74\x68'),
            (RX, b'\x60\x65\x20\x6c\x61\x7a\x79\x20'),
            (RX, b'\x61\x64\x6f\x67\x0a\x74\x68\x65'),
            (RX, b'\x62\x20\x63\x72\x61\x7a\x79\x20'),
            (RX, b'\x63\x66\x6f\x78\x20\x6a\x75\x6d'),
            (RX, b'\x64\x70\x73\x20\x6f\x76\x65\x72'),
            (RX, b'\x65\x20\x74\x68\x65\x20\x6c\x61'),
            (RX, b'\x66\x7a\x79\x20\x64\x6f\x67\x0a'),
            (RX, b'\x67\x74\x68\x65\x20\x63\x72\x61'),
            (RX, b'\x68\x7a\x79\x20\x66\x6f\x78\x20'),
            (RX, b'\x69\x6a\x75\x6d\x70\x73\x20\x6f'),
            (RX, b'\x6a\x76\x65\x72\x20\x74\x68\x65'),
            (RX, b'\x6b\x20\x6c\x61\x7a\x79\x20\x64'),
            (RX, b'\x6c\x6f\x67\x0a\x74\x68\x65\x20'),
            (RX, b'\x6d\x63\x72\x61\x7a\x79\x20\x66'),
            (RX, b'\x6e\x6f\x78\x20\x6a\x75\x6d\x70'),
            (RX, b'\x6f\x73\x20\x6f\x76\x65\x72\x20'),
            (RX, b'\x70\x74\x68\x65\x20\x6c\x61\x7a'),
            (RX, b'\x71\x79\x20\x64\x6f\x67\x0a\x74'),
            (RX, b'\x72\x68\x65\x20\x63\x72\x61\x7a'),
            (RX, b'\x73\x79\x20\x66\x6f\x78\x20\x6a'),
            (RX, b'\x74\x75\x6d\x70\x73\x20\x6f\x76'),
            (RX, b'\x75\x65\x72\x20\x74\x68\x65\x20'),
            (RX, b'\x76\x6c\x61\x7a\x79\x20\x64\x6f'),
            (RX, b'\x77\x67\x0a\x74\x68\x65\x20\x63'),
            (RX, b'\x78\x72\x61\x7a\x79\x20\x66\x6f'),
            (RX, b'\x79\x78\x20\x6a\x75\x6d\x70\x73'),
            (RX, b'\x7a\x20\x6f\x76\x65\x72\x20\x74'),
            (RX, b'\x7b\x68\x65\x20\x6c\x61\x7a\x79'),
            (RX, b'\x7c\x20\x64\x6f\x67\x0a\x74\x68'),
            (RX, b'\x7d\x65\x20\x63\x72\x61\x7a\x79'),
            (RX, b'\x7e\x20\x66\x6f\x78\x20\x6a\x75'),
            (RX, b'\x7f\x6d\x70\x73\x20\x6f\x76\x65'),
            (TX, b'\xa2\x7f\x7f\x00\x00\x00\x00\x00'), # --> This block is acknowledged without issues
            (RX, b'\x01\x72\x20\x74\x68\x65\x20\x6c'),
            (RX, b'\x02\x61\x7a\x79\x20\x64\x6f\x67'),
            (RX, b'\x03\x0a\x74\x68\x65\x20\x63\x72'),
            (RX, b'\x04\x61\x7a\x79\x20\x66\x6f\x78'),
            (RX, b'\x05\x20\x6a\x75\x6d\x70\x73\x20'),
            (RX, b'\x06\x6f\x76\x65\x72\x20\x74\x68'),
            (RX, b'\x07\x65\x20\x6c\x61\x7a\x79\x20'),
            (RX, b'\x08\x64\x6f\x67\x0a\x74\x68\x65'),
            (RX, b'\x09\x20\x63\x72\x61\x7a\x79\x20'),
            (RX, b'\x0a\x66\x6f\x78\x20\x6a\x75\x6d'),
            (RX, b'\x0b\x70\x73\x20\x6f\x76\x65\x72'),
            (RX, b'\x0c\x20\x74\x68\x65\x20\x6c\x61'),
            (RX, b'\x0d\x7a\x79\x20\x64\x6f\x67\x0a'),
            (RX, b'\x0e\x74\x68\x65\x20\x63\x72\x61'),
            (RX, b'\x0f\x7a\x79\x20\x66\x6f\x78\x20'),
            (RX, b'\x10\x6a\x75\x6d\x70\x73\x20\x6f'),
            (RX, b'\x11\x76\x65\x72\x20\x74\x68\x65'),
            (RX, b'\x12\x20\x6c\x61\x7a\x79\x20\x64'),
            (RX, b'\x13\x6f\x67\x0a\x74\x68\x65\x20'),
            (RX, b'\x14\x63\x72\x61\x7a\x79\x20\x66'),
            (RX, b'\x15\x6f\x78\x20\x6a\x75\x6d\x70'),
            (RX, b'\x16\x73\x20\x6f\x76\x65\x72\x20'),
            (RX, b'\x17\x74\x68\x65\x20\x6c\x61\x7a'),
            (RX, b'\x18\x79\x20\x64\x6f\x67\x0a\x74'),
            (RX, b'\x19\x68\x65\x20\x63\x72\x61\x7a'),
            (RX, b'\x1a\x79\x20\x66\x6f\x78\x20\x6a'),
            (RX, b'\x1b\x75\x6d\x70\x73\x20\x6f\x76'),
            (RX, b'\x1c\x65\x72\x20\x74\x68\x65\x20'),
            (RX, b'\x1d\x6c\x61\x7a\x79\x20\x64\x6f'),
            (RX, b'\x1e\x67\x0a\x74\x68\x65\x20\x63'),
            (RX, b'\x1f\x72\x61\x7a\x79\x20\x66\x6f'),
            (RX, b'\x20\x78\x20\x6a\x75\x6d\x70\x73'),
            (RX, b'\x21\x20\x6f\x76\x65\x72\x20\x74'),
            (RX, b'\x22\x68\x65\x20\x6c\x61\x7a\x79'),
            (RX, b'\xa3\x20\x64\x6f\x67\x0a\x00\x00'),
            (TX, b'\xa2\x23\x7f\x00\x00\x00\x00\x00'),
            (RX, b'\xc9\x3b\x49\x00\x00\x00\x00\x00'),
            (TX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'), # --> Transfer ends without issues
        ]
        with self.network[2].sdo[0x1008].open('r', block_transfer=True) as fp:
            data = fp.read()
        self.assertEqual(data, 39 * 'the crazy fox jumps over the lazy dog\n')

    def test_block_upload_wrong_seqno(self):
        """Server sends wrong sequence number first; client must retransmit and recover."""
        self.data = [
            (TX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),  # init block upload
            (RX, b'\xc6\x08\x10\x00\x1a\x00\x00\x00'),  # server init resp, size=26
            (TX, b'\xa3\x00\x00\x00\x00\x00\x00\x00'),  # start upload
            (RX, b'\x02\x54\x69\x6e\x79\x20\x4e\x6f'),  # WRONG: seqno=2 instead of 1
            (TX, b'\xa2\x00\x7f\x00\x00\x00\x00\x00'),  # retransmit request: ack_block ackseq=0
            (RX, b'\x01\x54\x69\x6e\x79\x20\x4e\x6f'),  # seqno=1 "Tiny No"
            (RX, b'\x02\x64\x65\x20\x2d\x20\x4d\x65'),  # seqno=2 "de - Me"
            (RX, b'\x03\x67\x61\x20\x44\x6f\x6d\x61'),  # seqno=3 "ga Doma"
            (RX, b'\x84\x69\x6e\x73\x20\x21\x00\x00'),  # seqno=4 NO_MORE_BLOCKS "ins !"
            (TX, b'\xa2\x04\x7f\x00\x00\x00\x00\x00'),  # ack_block ackseq=4
            (RX, b'\xc9\x40\xe1\x00\x00\x00\x00\x00'),  # end block upload
            (TX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'),  # end ack
        ]
        with self.network[2].sdo[0x1008].open('r', block_transfer=True) as fp:
            data = fp.read()
        self.assertEqual(data, 'Tiny Node - Mega Domains !')

    def test_writable_file(self):
        self.data = [
            (TX, b'\x20\x00\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x60\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x00\x31\x32\x33\x34\x35\x36\x37'),
            (RX, b'\x20\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x1a\x38\x39\x00\x00\x00\x00\x00'),
            (RX, b'\x30\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x0f\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x20\x00\x20\x00\x00\x00\x00\x00'),
        ]
        with self.network[2].sdo["Writable string"].open('wb') as fp:
            fp.write(b'1234')
            fp.write(b'56789')
        self.assertTrue(fp.closed)
        # Write on closed file
        with self.assertRaises(ValueError):
            fp.write(b'123')

    def test_abort(self):
        self.data = [
            (TX, b'\x40\x18\x10\x01\x00\x00\x00\x00'),
            (RX, b'\x80\x18\x10\x01\x11\x00\x09\x06'),
        ]
        with self.assertRaises(canopen.SdoAbortedError) as cm:
            _ = self.network[2].sdo[0x1018][1].raw
        self.assertEqual(cm.exception.code, 0x06090011)

    def test_add_sdo_channel(self):
        client = self.network[2].add_sdo(0x123456, 0x234567)
        self.assertIn(client, self.network[2].sdo_channels)

    def test_send_request_retries_on_can_error(self):
        """send_request retries after a CanError and succeeds on the next attempt."""
        call_count = [0]

        def send_with_one_failure(can_id, data, remote=False):
            call_count[0] += 1
            if call_count[0] == 1:
                raise CanError("Simulated buffer overflow")
            self._send_message(can_id, data, remote)

        self.network[2].sdo.MAX_RETRIES = 2
        self.network.send_message = send_with_one_failure
        self.data = [
            (TX, b'\x40\x18\x10\x01\x00\x00\x00\x00'),
            (RX, b'\x43\x18\x10\x01\x04\x00\x00\x00'),
        ]
        vendor_id = self.network[2].sdo[0x1018][1].raw
        self.assertEqual(vendor_id, 4)
        self.assertEqual(call_count[0], 2)

    def test_send_request_raises_after_retries_exhausted(self):
        """send_request raises CanError when all retries are exhausted."""
        def always_fail(can_id, data, remote=False):
            raise CanError("Simulated buffer overflow")

        self.network[2].sdo.MAX_RETRIES = 1
        self.network.send_message = always_fail
        with self.assertRaises(CanError):
            _ = self.network[2].sdo[0x1018][1].raw

    def test_pause_before_send_delays_message(self):
        """send_request does not send before PAUSE_BEFORE_SEND seconds have elapsed."""
        pause = 0.05
        self.network[2].sdo.PAUSE_BEFORE_SEND = pause
        send_times = []

        def timed_send(can_id, data, remote=False):
            send_times.append(time.monotonic())
            self._send_message(can_id, data, remote)

        self.network.send_message = timed_send
        self.data = [
            (TX, b'\x40\x18\x10\x01\x00\x00\x00\x00'),
            (RX, b'\x43\x18\x10\x01\x04\x00\x00\x00'),
        ]
        start = time.monotonic()
        _ = self.network[2].sdo[0x1018][1].raw
        self.assertTrue(send_times, "send_message was never called")
        elapsed = send_times[0] - start
        self.assertGreaterEqual(elapsed, pause,
            f"Message sent too early: {elapsed:.4f}s < {pause}s pause")

    def test_read_response_empty_queue(self):
        """read_response raises SdoCommunicationError when the response queue is empty."""
        with self.assertRaises(canopen.SdoCommunicationError) as cm:
            self.network[2].sdo.read_response()
        self.assertIn("No SDO response received", str(cm.exception))

    def test_readable_stream_readable(self):
        """ReadableStream.readable() returns True."""
        self.data = [
            (TX, b'\x40\x18\x10\x01\x00\x00\x00\x00'),
            (RX, b'\x43\x18\x10\x01\x04\x00\x00\x00'),
        ]
        with self.network[2].sdo[0x1018][1].open('rb', buffering=0) as fp:
            self.assertTrue(fp.readable())

    def test_readable_stream_tell(self):
        """ReadableStream.tell() tracks position after each segment read."""
        self.data = [
            (TX, b'\x40\x08\x10\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x08\x10\x00\x0e\x00\x00\x00'),  # segmented, size=14
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6e\x79\x20\x4e\x6f'),  # 7 bytes: "Tiny No", toggle=0
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x11\x64\x65\x20\x2d\x20\x4d\x65'),  # 7 bytes: "de - Me", NO_MORE_DATA, toggle=1
        ]
        with self.network[2].sdo[0x1008].open('rb', buffering=0) as fp:
            self.assertEqual(fp.tell(), 0)
            fp.read(7)
            self.assertEqual(fp.tell(), 7)
            fp.read(7)
            self.assertEqual(fp.tell(), 14)

    def test_readable_stream_readinto(self):
        """ReadableStream.readinto() fills a bytearray and returns the byte count."""
        self.data = [
            (TX, b'\x40\x18\x10\x01\x00\x00\x00\x00'),
            (RX, b'\x43\x18\x10\x01\x04\x00\x00\x00'),  # expedited, 4 bytes: value=4
        ]
        buf = bytearray(8)
        with self.network[2].sdo[0x1018][1].open('rb', buffering=0) as fp:
            n = fp.readinto(buf)
        self.assertEqual(n, 4)
        self.assertEqual(buf[:4], b'\x04\x00\x00\x00')

    def test_block_upload_stream_readable(self):
        """BlockUploadStream.readable() returns True."""
        self.data = [
            (TX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),
            (RX, b'\xc6\x08\x10\x00\x1a\x00\x00\x00'),
            (TX, b'\xa3\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x01\x54\x69\x6e\x79\x20\x4e\x6f'),
            (RX, b'\x02\x64\x65\x20\x2d\x20\x4d\x65'),
            (RX, b'\x03\x67\x61\x20\x44\x6f\x6d\x61'),
            (RX, b'\x84\x69\x6e\x73\x20\x21\x00\x00'),
            (TX, b'\xa2\x04\x7f\x00\x00\x00\x00\x00'),
            (RX, b'\xc9\x40\xe1\x00\x00\x00\x00\x00'),
            (TX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'),
        ]
        with self.network[2].sdo[0x1008].open('rb', block_transfer=True, buffering=0) as fp:
            self.assertTrue(fp.readable())
            fp.read()

    def test_block_upload_stream_tell(self):
        """BlockUploadStream.tell() tracks the byte position after reads."""
        self.data = [
            (TX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),
            (RX, b'\xc6\x08\x10\x00\x1a\x00\x00\x00'),
            (TX, b'\xa3\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x01\x54\x69\x6e\x79\x20\x4e\x6f'),
            (RX, b'\x02\x64\x65\x20\x2d\x20\x4d\x65'),
            (RX, b'\x03\x67\x61\x20\x44\x6f\x6d\x61'),
            (RX, b'\x84\x69\x6e\x73\x20\x21\x00\x00'),
            (TX, b'\xa2\x04\x7f\x00\x00\x00\x00\x00'),
            (RX, b'\xc9\x40\xe1\x00\x00\x00\x00\x00'),
            (TX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'),
        ]
        with self.network[2].sdo[0x1008].open('rb', block_transfer=True, buffering=0) as fp:
            self.assertEqual(fp.tell(), 0)
            fp.read(7)  # reads first segment: 7 bytes
            self.assertEqual(fp.tell(), 7)
            fp.read()   # reads remaining 3 segments (7+7+5 = 19 bytes)
            self.assertEqual(fp.tell(), 26)

    def test_block_upload_stream_readinto(self):
        """BlockUploadStream.readinto() fills a bytearray and returns the byte count."""
        self.data = [
            (TX, b'\xa4\x08\x10\x00\x7f\x00\x00\x00'),
            (RX, b'\xc6\x08\x10\x00\x1a\x00\x00\x00'),
            (TX, b'\xa3\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x01\x54\x69\x6e\x79\x20\x4e\x6f'),
            (RX, b'\x02\x64\x65\x20\x2d\x20\x4d\x65'),
            (RX, b'\x03\x67\x61\x20\x44\x6f\x6d\x61'),
            (RX, b'\x84\x69\x6e\x73\x20\x21\x00\x00'),
            (TX, b'\xa2\x04\x7f\x00\x00\x00\x00\x00'),
            (RX, b'\xc9\x40\xe1\x00\x00\x00\x00\x00'),
            (TX, b'\xa1\x00\x00\x00\x00\x00\x00\x00'),
        ]
        buf = bytearray(8)
        with self.network[2].sdo[0x1008].open('rb', block_transfer=True, buffering=0) as fp:
            n = fp.readinto(buf)
            # readinto reads one segment (up to 7 bytes); first segment is "Tiny No"
            self.assertEqual(n, 7)
            self.assertEqual(buf[:7], b'Tiny No')
            fp.read()  # consume remaining segments so close() succeeds

    def test_writable_stream_tell(self):
        """WritableStream.tell() tracks position after each write."""
        self.data = [
            (TX, b'\x20\x00\x20\x00\x00\x00\x00\x00'),  # initiate, no SIZE_SPECIFIED
            (RX, b'\x60\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x00\x41\x20\x6c\x6f\x6e\x67\x20'),  # "A long ", toggle=0, 7 bytes
            (RX, b'\x20\x00\x00\x00\x00\x00\x00\x00'),
            (TX, b'\x12\x73\x74\x72\x69\x6e\x67\x00'),  # "string", toggle=1, 6 bytes
            (RX, b'\x30\x00\x00\x00\x00\x00\x00\x00'),
            (TX, b'\x0f\x00\x00\x00\x00\x00\x00\x00'),  # close() empty final segment
            (RX, b'\x20\x00\x00\x00\x00\x00\x00\x00'),
        ]
        with self.network[2].sdo["Writable string"].open('wb', buffering=0) as fp:
            self.assertEqual(fp.tell(), 0)
            fp.write(b'A long ')
            self.assertEqual(fp.tell(), 7)
            fp.write(b'string')
            self.assertEqual(fp.tell(), 13)


class TestSDOClientDatatypes(unittest.TestCase):
    """Test the SDO client uploads with the different data types in CANopen."""

    def _send_message(self, can_id, data, remote=False):
        """Will be used instead of the usual Network.send_message method.

        Checks that the message data is according to expected and answers
        with the provided data.
        """
        next_data = self.data.pop(0)
        self.assertEqual(next_data[0], TX, 'No transmission was expected')
        self.assertSequenceEqual(data, next_data[1])
        self.assertEqual(can_id, 0x602)
        while self.data and self.data[0][0] == RX:
            self.network.notify(0x582, self.data.pop(0)[1], 0.0)

    def setUp(self):
        network = canopen.Network()
        network.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        network.send_message = self._send_message
        node = network.add_node(2, DATATYPES_EDS)
        node.sdo.RESPONSE_TIMEOUT = 0.01
        self.node = node
        self.network = network

    def test_boolean(self):
        self.data = [
            (TX, b'\x40\x01\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x4f\x01\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.BOOLEAN, 0)
        self.assertEqual(data, b'\xfe')

    def test_unsigned8(self):
        self.data = [
            (TX, b'\x40\x05\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x4f\x05\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED8, 0)
        self.assertEqual(data, b'\xfe')

    def test_unsigned16(self):
        self.data = [
            (TX, b'\x40\x06\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x4b\x06\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED16, 0)
        self.assertEqual(data, b'\xfe\xfd')

    def test_unsigned24(self):
        self.data = [
            (TX, b'\x40\x16\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x47\x16\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED24, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc')

    def test_unsigned32(self):
        self.data = [
            (TX, b'\x40\x07\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x43\x07\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED32, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc\xfb')

    def test_unsigned40(self):
        self.data = [
            (TX, b'\x40\x18\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x18\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x05\xb2\x01\x20\x02\x91\x12\x03'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED40, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91')

    def test_unsigned48(self):
        self.data = [
            (TX, b'\x40\x19\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x19\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x03\xb2\x01\x20\x02\x91\x12\x03'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED48, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91\x12')

    def test_unsigned56(self):
        self.data = [
            (TX, b'\x40\x1a\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x1a\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x01\xb2\x01\x20\x02\x91\x12\x03'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED56, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91\x12\x03')

    def test_unsigned64(self):
        self.data = [
            (TX, b'\x40\x1b\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x1b\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\xb2\x01\x20\x02\x91\x12\x03'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x1d\x19\x21\x70\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED64, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91\x12\x03\x19')

    def test_integer8(self):
        self.data = [
            (TX, b'\x40\x02\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x4f\x02\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER8, 0)
        self.assertEqual(data, b'\xfe')

    def test_integer16(self):
        self.data = [
            (TX, b'\x40\x03\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x4b\x03\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER16, 0)
        self.assertEqual(data, b'\xfe\xfd')

    def test_integer24(self):
        self.data = [
            (TX, b'\x40\x10\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x47\x10\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER24, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc')

    def test_integer32(self):
        self.data = [
            (TX, b'\x40\x04\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x43\x04\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER32, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc\xfb')

    def test_integer40(self):
        self.data = [
            (TX, b'\x40\x12\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x12\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x05\xb2\x01\x20\x02\x91\x12\x03'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER40, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91')

    def test_integer48(self):
        self.data = [
            (TX, b'\x40\x13\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x13\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x03\xb2\x01\x20\x02\x91\x12\x03'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER48, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91\x12')

    def test_integer56(self):
        self.data = [
            (TX, b'\x40\x14\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x14\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x01\xb2\x01\x20\x02\x91\x12\x03'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER56, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91\x12\x03')

    def test_integer64(self):
        self.data = [
            (TX, b'\x40\x15\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x15\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\xb2\x01\x20\x02\x91\x12\x03'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x1d\x19\x21\x70\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER64, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91\x12\x03\x19')

    def test_real32(self):
        self.data = [
            (TX, b'\x40\x08\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x43\x08\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.REAL32, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc\xfb')

    def test_real64(self):
        self.data = [
            (TX, b'\x40\x11\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x11\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\xb2\x01\x20\x02\x91\x12\x03'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x1d\x19\x21\x70\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.REAL64, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91\x12\x03\x19')

    def test_visible_string(self):
        self.data = [
            (TX, b'\x40\x09\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x09\x20\x00\x1a\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6e\x79\x20\x4e\x6f'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2d\x20\x4d\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6f\x6d\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6e\x73\x20\x21\x00\x00'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.VISIBLE_STRING, 0)
        self.assertEqual(data, b'Tiny Node - Mega Domains !')

    def test_unicode_string(self):
        self.data = [
            (TX, b'\x40\x0b\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x0b\x20\x00\x1a\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6e\x79\x20\x4e\x6f'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2d\x20\x4d\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6f\x6d\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6e\x73\x20\x21\x00\x00'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNICODE_STRING, 0)
        self.assertEqual(data, b'Tiny Node - Mega Domains !')

    def test_octet_string(self):
        self.data = [
            (TX, b'\x40\x0a\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x0a\x20\x00\x1a\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6e\x79\x20\x4e\x6f'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2d\x20\x4d\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6f\x6d\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6e\x73\x20\x21\x00\x00'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.OCTET_STRING, 0)
        self.assertEqual(data, b'Tiny Node - Mega Domains !')

    def test_domain(self):
        self.data = [
            (TX, b'\x40\x0f\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x0f\x20\x00\x1a\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6e\x79\x20\x4e\x6f'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2d\x20\x4d\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6f\x6d\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6e\x73\x20\x21\x00\x00'),
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.DOMAIN, 0)
        self.assertEqual(data, b'Tiny Node - Mega Domains !')

    def test_unknown_od_32(self):
        """Test an unknown OD entry of 32 bits (4 bytes)."""
        self.data = [
            (TX, b'\x40\xff\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x43\xff\x20\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x20FF, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc\xfb')

    def test_unknown_od_112(self):
        """Test an unknown OD entry of 112 bits (14 bytes)."""
        self.data = [
            (TX, b'\x40\xff\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\xff\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\xb2\x01\x20\x02\x91\x12\x03'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x11\x19\x21\x70\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x20FF, 0)
        self.assertEqual(
            data, b'\xb2\x01\x20\x02\x91\x12\x03\x19\x21\x70\xfe\xfd\xfc\xfb'
        )

    def test_unknown_datatype32(self):
        """Test an unknown datatype, but known OD, of 32 bits (4 bytes)."""
        # Add fake entry 0x2100 to OD, using fake datatype 0xFF
        if 0x2100 not in self.node.object_dictionary:
            fake_var = ODVariable("Fake", 0x2100)
            fake_var.data_type = 0xFF
            self.node.object_dictionary.add_object(fake_var)
        self.data = [
            (TX, b'\x40\x00\x21\x00\x00\x00\x00\x00'),
            (RX, b'\x43\x00\x21\x00\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2100, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc\xfb')

    def test_unknown_datatype112(self):
        """Test an unknown datatype, but known OD, of 112 bits (14 bytes)."""
        # Add fake entry 0x2100 to OD, using fake datatype 0xFF
        if 0x2100 not in self.node.object_dictionary:
            fake_var = ODVariable("Fake", 0x2100)
            fake_var.data_type = 0xFF
            self.node.object_dictionary.add_object(fake_var)
        self.data = [
            (TX, b'\x40\x00\x21\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x00\x21\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\xb2\x01\x20\x02\x91\x12\x03'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x11\x19\x21\x70\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x2100, 0)
        self.assertEqual(
            data, b'\xb2\x01\x20\x02\x91\x12\x03\x19\x21\x70\xfe\xfd\xfc\xfb'
        )


class TestSdoAbortedError(unittest.TestCase):
    """Unit tests for SdoAbortedError construction and helpers."""

    def test_init_with_int_code(self):
        for code in canopen.SdoAbortedError.CODES:
            exc = canopen.SdoAbortedError(code)
            self.assertEqual(exc.code, code)

    def test_str_known_code(self):
        for code, description in canopen.SdoAbortedError.CODES.items():
            exc = canopen.SdoAbortedError(code)
            self.assertIn(description, str(exc))

    def test_str_unknown_code(self):
        exc = canopen.SdoAbortedError(0xDEADBEEF)
        self.assertIn("0xDEADBEEF", str(exc))

    def test_eq(self):
        for code, description in canopen.SdoAbortedError.CODES.items():
            # Test equality with another instance of the same code, and with the code and description directly
            self.assertEqual(canopen.SdoAbortedError(code),
                             canopen.SdoAbortedError(description))
            self.assertEqual(canopen.SdoAbortedError(code),
                             code)
            self.assertEqual(canopen.SdoAbortedError(code),
                             description)
        
        self.assertNotEqual(canopen.SdoAbortedError(0x06090011),
                            canopen.SdoAbortedError(0x08000000))
        
        self.assertNotEqual(canopen.SdoAbortedError(0x06090011), "Value range of parameter exceeded")

        self.assertFalse(canopen.SdoAbortedError(code) == 0.5)  # Unsupported type for comparison

    def test_init_from_string(self):
        for code, description in canopen.SdoAbortedError.CODES.items():
            exc = canopen.SdoAbortedError(description)
            self.assertEqual(exc.code, code)

    def test_init_from_unknown_string(self):
        with self.assertRaises(ValueError):
            canopen.SdoAbortedError("This description does not exist")


class TestSDOServer(unittest.TestCase):
    """Test the SDO server (LocalNode) directly by injecting raw CAN messages."""

    def setUp(self):
        network = canopen.Network()
        network.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.responses = []
        network.send_message = lambda cobid, data, remote=False: self.responses.append(bytes(data))
        self.local_node = network.create_node(2, SAMPLE_EDS)

    def test_expedited_download_no_size_specified(self):
        """Expedited download without SIZE_SPECIFIED: server defaults to reading 4 bytes."""
        # Command: REQUEST_DOWNLOAD (0x20) | EXPEDITED (0x02) — no SIZE_SPECIFIED
        # Target: 0x1400:01 (COB-ID RPDO1, UNSIGNED32, rw)
        request = bytearray(8)
        index = 0x1400
        subindex = 1
        value = 0x201
        SDO_STRUCT.pack_into(request, 0, REQUEST_DOWNLOAD | EXPEDITED, index, subindex)
        struct.pack_into('<I', request, 4, value)  # value to write
        self.local_node.sdo.on_request(0x602, request, 0.0)
        # Server must reply with RESPONSE_DOWNLOAD for the same index/subindex
        self.assertEqual(len(self.responses), 1)
        command_r, index_r, subindex_r = SDO_STRUCT.unpack(self.responses[0][:4])  # Check that the first 4 bytes are a valid SDO header
        self.assertEqual(command_r, RESPONSE_DOWNLOAD)
        self.assertEqual(index_r, index)
        self.assertEqual(subindex_r, subindex)
        # Value must have been stored
        self.assertEqual(self.local_node.sdo[index][subindex].raw, value)

    def test_segmented_upload_toggle_bit_mismatch(self):
        """Server aborts with TOGGLE_NOT_ALTERNATED when client sends wrong toggle on upload."""
        # Initiate segmented upload for 0x1008:00 (Device Name, 'TEST DEVICE' = 11 bytes)
        self.local_node.sdo.on_request(
            0x602, b'\x40\x08\x10\x00\x00\x00\x00\x00', 0.0)
        # Server should have responded with segmented initiate (not expedited)
        self.assertEqual(len(self.responses), 1)
        self.assertEqual(self.responses[0][0] & EXPEDITED, 0)

        # Send segment request with wrong toggle bit (0x10 instead of 0x00)
        self.local_node.sdo.on_request(
            0x602, b'\x70\x00\x00\x00\x00\x00\x00\x00', 0.0)
        # Server must respond with an abort
        self.assertEqual(len(self.responses), 2)
        cmd, = struct.unpack_from("B", self.responses[1])
        self.assertEqual(cmd, RESPONSE_ABORTED)
        code, = struct.unpack_from("<L", self.responses[1], 4)
        self.assertEqual(code, ABORT_TOGGLE_NOT_ALTERNATED)

    def test_segmented_download_toggle_bit_mismatch(self):
        """Server aborts with TOGGLE_NOT_ALTERNATED when client repeats wrong toggle on download."""
        # Initiate segmented download for 0x2000:00 (Writable string, 13 bytes)
        self.local_node.sdo.on_request(
            0x602, b'\x21\x00\x20\x00\x0d\x00\x00\x00', 0.0)
        self.assertEqual(len(self.responses), 1)

        # First segment correctly (toggle=0): 7 bytes of 'A long '
        self.local_node.sdo.on_request(
            0x602, b'\x00\x41\x20\x6c\x6f\x6e\x67\x20', 0.0)
        self.assertEqual(len(self.responses), 2)

        # Second segment with wrong toggle (0 again, should be 0x10)
        self.local_node.sdo.on_request(
            0x602, b'\x00\x73\x74\x72\x69\x6e\x67\x00', 0.0)
        # Server must respond with an abort
        self.assertEqual(len(self.responses), 3)
        cmd, = struct.unpack_from("B", self.responses[2])
        self.assertEqual(cmd, RESPONSE_ABORTED)
        code, = struct.unpack_from("<L", self.responses[2], 4)
        self.assertEqual(code, ABORT_TOGGLE_NOT_ALTERNATED)

    def test_on_request_key_error_aborts_not_in_od(self):
        """KeyError raised by a handler is caught and server responds with ABORT_NOT_IN_OD."""
        with patch.object(self.local_node, 'get_data', side_effect=KeyError(0x9999)):
            self.local_node.sdo.on_request(
                0x602, b'\x40\x18\x10\x01\x00\x00\x00\x00', 0.0)
        self.assertEqual(len(self.responses), 1)
        cmd, = struct.unpack_from("B", self.responses[0])
        self.assertEqual(cmd, RESPONSE_ABORTED)
        code, = struct.unpack_from("<L", self.responses[0], 4)
        self.assertEqual(code, ABORT_NOT_IN_OD)

    def test_on_request_generic_exception_aborts_general_error(self):
        """An unexpected exception raised by a handler is caught and server aborts with ABORT_GENERAL_ERROR."""
        with patch.object(self.local_node, 'get_data', side_effect=RuntimeError("unexpected")):
            self.local_node.sdo.on_request(
                0x602, b'\x40\x18\x10\x01\x00\x00\x00\x00', 0.0)
        self.assertEqual(len(self.responses), 1)
        cmd, = struct.unpack_from("B", self.responses[0])
        self.assertEqual(cmd, RESPONSE_ABORTED)
        code, = struct.unpack_from("<L", self.responses[0], 4)
        self.assertEqual(code, ABORT_GENERAL_ERROR)

    def test_abort_accepts_sdo_aborted_error_object(self):
        """SdoServer.abort() unwraps an SdoAbortedError argument and uses its code."""
        self.local_node.sdo._index = 0x1018
        self.local_node.sdo._subindex = 0x01
        self.local_node.sdo.abort(canopen.SdoAbortedError(ABORT_NOT_IN_OD))
        self.assertEqual(len(self.responses), 1)
        cmd, = struct.unpack_from("B", self.responses[0])
        self.assertEqual(cmd, RESPONSE_ABORTED)
        code, = struct.unpack_from("<L", self.responses[0], 4)
        self.assertEqual(code, ABORT_NOT_IN_OD)

    def _setup_block_upload_up_data_state(self):
        """Drive the server into BLOCK_STATE_UP_DATA for 0x1008:00 ("TEST DEVICE", 11 bytes).

        Pre-sets _index/_subindex so abort() can construct a valid response frame.
        Returns the number of responses captured so far (3: initiate + 2 data segments).
        """
        self.local_node.sdo._index = 0x1008
        self.local_node.sdo._subindex = 0x00
        # Step 1: block upload initiate — REQUEST_BLOCK_UPLOAD | CRC_SUPPORTED, blocksize=127
        request = bytearray(8)
        SDO_STRUCT.pack_into(request, 0, REQUEST_BLOCK_UPLOAD | CRC_SUPPORTED, 0x1008, 0x00)
        request[4] = 127
        self.local_node.sdo.on_request(0x602, bytes(request), 0.0)
        # Step 2: start block upload — server sends all data segments, state → BLOCK_STATE_UP_DATA
        start_req = bytearray(8)
        start_req[0] = REQUEST_BLOCK_UPLOAD | START_BLOCK_UPLOAD  # 0xA3
        self.local_node.sdo.on_request(0x602, bytes(start_req), 0.0)
        # 1 initiate response + 2 data segments (11 bytes / 7 = 2 blocks) = 3 total
        return len(self.responses)

    def test_process_block_up_data_missing_request_block_upload_raises(self):
        """process_block in UP_DATA state raises when command lacks REQUEST_BLOCK_UPLOAD bits (line 120)."""
        n = self._setup_block_upload_up_data_state()
        self.assertEqual(n, 3)
        # Block-ack command 0x00 has neither REQUEST_BLOCK_UPLOAD (0xA0) set
        with self.assertRaises(canopen.SdoAbortedError):
            self.local_node.sdo.on_request(0x602, b'\x00\x00\x7F\x00\x00\x00\x00\x00', 0.0)
        self.assertEqual(len(self.responses), 4)
        cmd, = struct.unpack_from("B", self.responses[3])
        self.assertEqual(cmd, RESPONSE_ABORTED)
        code, = struct.unpack_from("<L", self.responses[3], 4)
        self.assertEqual(code, ABORT_INVALID_COMMAND_SPECIFIER)

    def test_process_block_up_data_missing_block_transfer_response_raises(self):
        """process_block in UP_DATA state raises when command lacks BLOCK_TRANSFER_RESPONSE bit (line 122)."""
        n = self._setup_block_upload_up_data_state()
        self.assertEqual(n, 3)
        # Command 0xA0 has REQUEST_BLOCK_UPLOAD set but BLOCK_TRANSFER_RESPONSE (0x02) not set
        with self.assertRaises(canopen.SdoAbortedError):
            self.local_node.sdo.on_request(0x602, b'\xA0\x02\x7F\x00\x00\x00\x00\x00', 0.0)
        self.assertEqual(len(self.responses), 4)
        cmd, = struct.unpack_from("B", self.responses[3])
        self.assertEqual(cmd, RESPONSE_ABORTED)
        code, = struct.unpack_from("<L", self.responses[3], 4)
        self.assertEqual(code, ABORT_INVALID_COMMAND_SPECIFIER)


if __name__ == "__main__":
    unittest.main()
