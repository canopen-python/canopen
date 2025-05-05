import unittest

import canopen
import canopen.objectdictionary.datatypes as dt
from canopen.objectdictionary import ODVariable

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
            (RX, b'\x43\x18\x10\x01\x04\x00\x00\x00')
        ]
        vendor_id = self.network[2].sdo[0x1018][1].raw
        self.assertEqual(vendor_id, 4)

        # UNSIGNED8 without padded data part (see issue #5)
        self.data = [
            (TX, b'\x40\x00\x14\x02\x00\x00\x00\x00'),
            (RX, b'\x4f\x00\x14\x02\xfe')
        ]
        trans_type = self.network[2].sdo[0x1400]['Transmission type RPDO 1'].raw
        self.assertEqual(trans_type, 254)
        self.assertTrue(self.message_sent)

    def test_size_not_specified(self):
        self.data = [
            (TX, b'\x40\x00\x14\x02\x00\x00\x00\x00'),
            (RX, b'\x42\x00\x14\x02\xfe\x00\x00\x00')
        ]
        # Make sure the size of the data is 1 byte
        data = self.network[2].sdo.upload(0x1400, 2)
        self.assertEqual(data, b'\xfe')
        self.assertTrue(self.message_sent)

    def test_expedited_download(self):
        self.data = [
            (TX, b'\x2b\x17\x10\x00\xa0\x0f\x00\x00'),
            (RX, b'\x60\x17\x10\x00\x00\x00\x00\x00')
        ]
        self.network[2].sdo[0x1017].raw = 4000
        self.assertTrue(self.message_sent)

    def test_segmented_upload(self):
        self.data = [
            (TX, b'\x40\x08\x10\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x08\x10\x00\x1A\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6E\x79\x20\x4E\x6F'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2D\x20\x4D\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6F\x6D\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6E\x73\x20\x21\x00\x00')
        ]
        device_name = self.network[2].sdo[0x1008].raw
        self.assertEqual(device_name, "Tiny Node - Mega Domains !")

    def test_segmented_download(self):
        self.data = [
            (TX, b'\x21\x00\x20\x00\x0d\x00\x00\x00'),
            (RX, b'\x60\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x00\x41\x20\x6c\x6f\x6e\x67\x20'),
            (RX, b'\x20\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x13\x73\x74\x72\x69\x6e\x67\x00'),
            (RX, b'\x30\x00\x20\x00\x00\x00\x00\x00')
        ]
        self.network[2].sdo['Writable string'].raw = 'A long string'

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
            (RX, b'\xa1\x00\x00\x00\x00\x00\x00\x00')
        ]
        data = b'A really really long string...'
        with self.network[2].sdo['Writable string'].open(
            'wb', size=len(data), block_transfer=True) as fp:
            fp.write(data)

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
        """Send 'the crazy fox jumps over the lazy dog\n' multiple times 
        and trigger a retransmit by only validating a block partially.
        """
        self.data = [
            (TX, b"\xa4\x08\x10\x00\x7f\x00\x00\x00"),
            (RX, b"\xc4\x08\x10\x00\x00\x00\x00\x00"),
            (TX, b"\xa3\x00\x00\x00\x00\x00\x00\x00"),
            (RX, b"\x01\x74\x68\x65\x20\x63\x72\x61"),
            (RX, b"\x02\x7a\x79\x20\x66\x6f\x78\x20"),
            (RX, b"\x03\x6a\x75\x6d\x70\x73\x20\x6f"),
            (RX, b"\x04\x76\x65\x72\x20\x74\x68\x65"),
            (RX, b"\x05\x20\x6c\x61\x7a\x79\x20\x64"),
            (RX, b"\x06\x6f\x67\x0a\x74\x68\x65\x20"),
            (RX, b"\x07\x63\x72\x61\x7a\x79\x20\x66"),
            (RX, b"\x08\x6f\x78\x20\x6a\x75\x6d\x70"),
            (RX, b"\x09\x73\x20\x6f\x76\x65\x72\x20"),
            (RX, b"\x0a\x74\x68\x65\x20\x6c\x61\x7a"),
            (RX, b"\x0b\x79\x20\x64\x6f\x67\x0a\x74"),
            (RX, b"\x0c\x68\x65\x20\x63\x72\x61\x7a"),
            (RX, b"\x0d\x79\x20\x66\x6f\x78\x20\x6a"),
            (RX, b"\x0e\x75\x6d\x70\x73\x20\x6f\x76"),
            (RX, b"\x0f\x65\x72\x20\x74\x68\x65\x20"),
            (RX, b"\x10\x6c\x61\x7a\x79\x20\x64\x6f"),
            (RX, b"\x11\x67\x0a\x74\x68\x65\x20\x63"),
            (RX, b"\x12\x72\x61\x7a\x79\x20\x66\x6f"),
            (RX, b"\x13\x78\x20\x6a\x75\x6d\x70\x73"),
            (RX, b"\x14\x20\x6f\x76\x65\x72\x20\x74"),
            (RX, b"\x15\x68\x65\x20\x6c\x61\x7a\x79"),
            (RX, b"\x16\x20\x64\x6f\x67\x0a\x74\x68"),
            (RX, b"\x17\x65\x20\x63\x72\x61\x7a\x79"),
            (RX, b"\x18\x20\x66\x6f\x78\x20\x6a\x75"),
            (RX, b"\x19\x6d\x70\x73\x20\x6f\x76\x65"),
            (RX, b"\x1a\x72\x20\x74\x68\x65\x20\x6c"),
            (RX, b"\x1b\x61\x7a\x79\x20\x64\x6f\x67"),
            (RX, b"\x1c\x0a\x74\x68\x65\x20\x63\x72"),
            (RX, b"\x1d\x61\x7a\x79\x20\x66\x6f\x78"),
            (RX, b"\x1e\x20\x6a\x75\x6d\x70\x73\x20"),
            (RX, b"\x1f\x6f\x76\x65\x72\x20\x74\x68"),
            (RX, b"\x20\x65\x20\x6c\x61\x7a\x79\x20"),
            (RX, b"\x21\x64\x6f\x67\x0a\x74\x68\x65"),
            (RX, b"\x22\x20\x63\x72\x61\x7a\x79\x20"),
            (RX, b"\x23\x66\x6f\x78\x20\x6a\x75\x6d"),
            (RX, b"\x24\x70\x73\x20\x6f\x76\x65\x72"),
            (RX, b"\x25\x20\x74\x68\x65\x20\x6c\x61"),
            (RX, b"\x26\x7a\x79\x20\x64\x6f\x67\x0a"),
            (RX, b"\x27\x74\x68\x65\x20\x63\x72\x61"),
            (RX, b"\x28\x7a\x79\x20\x66\x6f\x78\x20"),
            (RX, b"\x29\x6a\x75\x6d\x70\x73\x20\x6f"),
            (RX, b"\x2a\x76\x65\x72\x20\x74\x68\x65"),
            (RX, b"\x2b\x20\x6c\x61\x7a\x79\x20\x64"),
            (RX, b"\x2c\x6f\x67\x0a\x74\x68\x65\x20"),
            (RX, b"\x2d\x63\x72\x61\x7a\x79\x20\x66"),
            (RX, b"\x2e\x6f\x78\x20\x6a\x75\x6d\x70"),
            (RX, b"\x2f\x73\x20\x6f\x76\x65\x72\x20"),
            (RX, b"\x30\x74\x68\x65\x20\x6c\x61\x7a"),
            (RX, b"\x31\x79\x20\x64\x6f\x67\x0a\x74"),
            (RX, b"\x32\x68\x65\x20\x63\x72\x61\x7a"),
            (RX, b"\x34\x79\x20\x66\x6f\x78\x20\x6a"),
            (RX, b"\x34\x75\x6d\x70\x73\x20\x6f\x76"),  # --> Wrong seqno (x34 instead of x33)
            (RX, b"\x35\x65\x72\x20\x74\x68\x65\x20"),  # All the following frames until end of block
            (RX, b"\x36\x6c\x61\x7a\x79\x20\x64\x6f"),  # will be ignored by the client and should be 
            (RX, b"\x37\x67\x0a\x74\x68\x65\x20\x63"),  # resent by server.
            (RX, b"\x38\x72\x61\x7a\x79\x20\x66\x6f"),
            (RX, b"\x39\x78\x20\x6a\x75\x6d\x70\x73"),
            (RX, b"\x3a\x20\x6f\x76\x65\x72\x20\x74"),
            (RX, b"\x3b\x68\x65\x20\x6c\x61\x7a\x79"),
            (RX, b"\x3c\x20\x64\x6f\x67\x0a\x74\x68"),
            (RX, b"\x3d\x65\x20\x63\x72\x61\x7a\x79"),
            (RX, b"\x3e\x20\x66\x6f\x78\x20\x6a\x75"),
            (RX, b"\x3f\x6d\x70\x73\x20\x6f\x76\x65"),
            (RX, b"\x40\x72\x20\x74\x68\x65\x20\x6c"),
            (RX, b"\x41\x61\x7a\x79\x20\x64\x6f\x67"),
            (RX, b"\x42\x0a\x74\x68\x65\x20\x63\x72"),
            (RX, b"\x43\x61\x7a\x79\x20\x66\x6f\x78"),
            (RX, b"\x44\x20\x6a\x75\x6d\x70\x73\x20"),
            (RX, b"\x45\x6f\x76\x65\x72\x20\x74\x68"),
            (RX, b"\x46\x65\x20\x6c\x61\x7a\x79\x20"),
            (RX, b"\x47\x64\x6f\x67\x0a\x74\x68\x65"),
            (RX, b"\x48\x20\x63\x72\x61\x7a\x79\x20"),
            (RX, b"\x49\x66\x6f\x78\x20\x6a\x75\x6d"),
            (RX, b"\x4a\x70\x73\x20\x6f\x76\x65\x72"),
            (RX, b"\x4b\x20\x74\x68\x65\x20\x6c\x61"),
            (RX, b"\x4c\x7a\x79\x20\x64\x6f\x67\x0a"),
            (RX, b"\x4d\x74\x68\x65\x20\x63\x72\x61"),
            (RX, b"\x4e\x7a\x79\x20\x66\x6f\x78\x20"),
            (RX, b"\x4f\x6a\x75\x6d\x70\x73\x20\x6f"),
            (RX, b"\x50\x76\x65\x72\x20\x74\x68\x65"),
            (RX, b"\x51\x20\x6c\x61\x7a\x79\x20\x64"),
            (RX, b"\x52\x6f\x67\x0a\x74\x68\x65\x20"),
            (RX, b"\x53\x63\x72\x61\x7a\x79\x20\x66"),
            (RX, b"\x54\x6f\x78\x20\x6a\x75\x6d\x70"),
            (RX, b"\x55\x73\x20\x6f\x76\x65\x72\x20"),
            (RX, b"\x56\x74\x68\x65\x20\x6c\x61\x7a"),
            (RX, b"\x57\x79\x20\x64\x6f\x67\x0a\x74"),
            (RX, b"\x58\x68\x65\x20\x63\x72\x61\x7a"),
            (RX, b"\x59\x79\x20\x66\x6f\x78\x20\x6a"),
            (RX, b"\x5a\x75\x6d\x70\x73\x20\x6f\x76"),
            (RX, b"\x5b\x65\x72\x20\x74\x68\x65\x20"),
            (RX, b"\x5c\x6c\x61\x7a\x79\x20\x64\x6f"),
            (RX, b"\x5d\x67\x0a\x74\x68\x65\x20\x63"),
            (RX, b"\x5e\x72\x61\x7a\x79\x20\x66\x6f"),
            (RX, b"\x5f\x78\x20\x6a\x75\x6d\x70\x73"),
            (RX, b"\x60\x20\x6f\x76\x65\x72\x20\x74"),
            (RX, b"\x61\x68\x65\x20\x6c\x61\x7a\x79"),
            (RX, b"\x62\x20\x64\x6f\x67\x0a\x74\x68"),
            (RX, b"\x63\x65\x20\x63\x72\x61\x7a\x79"),
            (RX, b"\x64\x20\x66\x6f\x78\x20\x6a\x75"),
            (RX, b"\x65\x6d\x70\x73\x20\x6f\x76\x65"),
            (RX, b"\x66\x72\x20\x74\x68\x65\x20\x6c"),
            (RX, b"\x67\x61\x7a\x79\x20\x64\x6f\x67"),
            (RX, b"\x68\x0a\x74\x68\x65\x20\x63\x72"),
            (RX, b"\x69\x61\x7a\x79\x20\x66\x6f\x78"),
            (RX, b"\x6a\x20\x6a\x75\x6d\x70\x73\x20"),
            (RX, b"\x6b\x6f\x76\x65\x72\x20\x74\x68"),
            (RX, b"\x6c\x65\x20\x6c\x61\x7a\x79\x20"),
            (RX, b"\x6d\x64\x6f\x67\x0a\x74\x68\x65"),
            (RX, b"\x6e\x20\x63\x72\x61\x7a\x79\x20"),
            (RX, b"\x6f\x66\x6f\x78\x20\x6a\x75\x6d"),
            (RX, b"\x70\x70\x73\x20\x6f\x76\x65\x72"),
            (RX, b"\x71\x20\x74\x68\x65\x20\x6c\x61"),
            (RX, b"\x72\x7a\x79\x20\x64\x6f\x67\x0a"),
            (RX, b"\x73\x74\x68\x65\x20\x63\x72\x61"),
            (RX, b"\x74\x7a\x79\x20\x66\x6f\x78\x20"),
            (RX, b"\x75\x6a\x75\x6d\x70\x73\x20\x6f"),
            (RX, b"\x76\x76\x65\x72\x20\x74\x68\x65"),
            (RX, b"\x77\x20\x6c\x61\x7a\x79\x20\x64"),
            (RX, b"\x78\x6f\x67\x0a\x74\x68\x65\x20"),
            (RX, b"\x79\x63\x72\x61\x7a\x79\x20\x66"),
            (RX, b"\x7a\x6f\x78\x20\x6a\x75\x6d\x70"),
            (RX, b"\x7b\x73\x20\x6f\x76\x65\x72\x20"),
            (RX, b"\x7c\x74\x68\x65\x20\x6c\x61\x7a"),
            (RX, b"\x7d\x79\x20\x64\x6f\x67\x0a\x74"),
            (RX, b"\x7e\x68\x65\x20\x63\x72\x61\x7a"),
            (RX, b"\x7f\x79\x20\x66\x6f\x78\x20\x6a"),  # --> Last element of block
            (TX, b"\xa2\x32\x7f\x00\x00\x00\x00\x00"),  # --> Last good seqno (x32)
            (RX, b"\x01\x79\x20\x66\x6f\x78\x20\x6a"),  # --> Server starts resending from last acknowledged block
            (RX, b"\x02\x75\x6d\x70\x73\x20\x6f\x76"),
            (RX, b"\x03\x65\x72\x20\x74\x68\x65\x20"),
            (RX, b"\x04\x6c\x61\x7a\x79\x20\x64\x6f"),
            (RX, b"\x05\x67\x0a\x74\x68\x65\x20\x63"),
            (RX, b"\x06\x72\x61\x7a\x79\x20\x66\x6f"),
            (RX, b"\x07\x78\x20\x6a\x75\x6d\x70\x73"),
            (RX, b"\x08\x20\x6f\x76\x65\x72\x20\x74"),
            (RX, b"\x09\x68\x65\x20\x6c\x61\x7a\x79"),
            (RX, b"\x0a\x20\x64\x6f\x67\x0a\x74\x68"),
            (RX, b"\x0b\x65\x20\x63\x72\x61\x7a\x79"),
            (RX, b"\x0c\x20\x66\x6f\x78\x20\x6a\x75"),
            (RX, b"\x0d\x6d\x70\x73\x20\x6f\x76\x65"),
            (RX, b"\x0e\x72\x20\x74\x68\x65\x20\x6c"),
            (RX, b"\x0f\x61\x7a\x79\x20\x64\x6f\x67"),
            (RX, b"\x10\x0a\x74\x68\x65\x20\x63\x72"),
            (RX, b"\x11\x61\x7a\x79\x20\x66\x6f\x78"),
            (RX, b"\x12\x20\x6a\x75\x6d\x70\x73\x20"),
            (RX, b"\x13\x6f\x76\x65\x72\x20\x74\x68"),
            (RX, b"\x14\x65\x20\x6c\x61\x7a\x79\x20"),
            (RX, b"\x15\x64\x6f\x67\x0a\x74\x68\x65"),
            (RX, b"\x16\x20\x63\x72\x61\x7a\x79\x20"),
            (RX, b"\x17\x66\x6f\x78\x20\x6a\x75\x6d"),
            (RX, b"\x18\x70\x73\x20\x6f\x76\x65\x72"),
            (RX, b"\x19\x20\x74\x68\x65\x20\x6c\x61"),
            (RX, b"\x1a\x7a\x79\x20\x64\x6f\x67\x0a"),
            (RX, b"\x1b\x74\x68\x65\x20\x63\x72\x61"),
            (RX, b"\x1c\x7a\x79\x20\x66\x6f\x78\x20"),
            (RX, b"\x1d\x6a\x75\x6d\x70\x73\x20\x6f"),
            (RX, b"\x1e\x76\x65\x72\x20\x74\x68\x65"),
            (RX, b"\x1f\x20\x6c\x61\x7a\x79\x20\x64"),
            (RX, b"\x20\x6f\x67\x0a\x74\x68\x65\x20"),
            (RX, b"\x21\x63\x72\x61\x7a\x79\x20\x66"),
            (RX, b"\x22\x6f\x78\x20\x6a\x75\x6d\x70"),
            (RX, b"\x23\x73\x20\x6f\x76\x65\x72\x20"),
            (RX, b"\x24\x74\x68\x65\x20\x6c\x61\x7a"),
            (RX, b"\x25\x79\x20\x64\x6f\x67\x0a\x74"),
            (RX, b"\x26\x68\x65\x20\x63\x72\x61\x7a"),
            (RX, b"\x27\x79\x20\x66\x6f\x78\x20\x6a"),
            (RX, b"\x28\x75\x6d\x70\x73\x20\x6f\x76"),
            (RX, b"\x29\x65\x72\x20\x74\x68\x65\x20"),
            (RX, b"\x2a\x6c\x61\x7a\x79\x20\x64\x6f"),
            (RX, b"\x2b\x67\x0a\x74\x68\x65\x20\x63"),
            (RX, b"\x2c\x72\x61\x7a\x79\x20\x66\x6f"),
            (RX, b"\x2d\x78\x20\x6a\x75\x6d\x70\x73"),
            (RX, b"\x2e\x20\x6f\x76\x65\x72\x20\x74"),
            (RX, b"\x2f\x68\x65\x20\x6c\x61\x7a\x79"),
            (RX, b"\x30\x20\x64\x6f\x67\x0a\x74\x68"),
            (RX, b"\x31\x65\x20\x63\x72\x61\x7a\x79"),
            (RX, b"\x32\x20\x66\x6f\x78\x20\x6a\x75"),
            (RX, b"\x33\x6d\x70\x73\x20\x6f\x76\x65"),
            (RX, b"\x34\x72\x20\x74\x68\x65\x20\x6c"),
            (RX, b"\x35\x61\x7a\x79\x20\x64\x6f\x67"),
            (RX, b"\x36\x0a\x74\x68\x65\x20\x63\x72"),
            (RX, b"\x37\x61\x7a\x79\x20\x66\x6f\x78"),
            (RX, b"\x38\x20\x6a\x75\x6d\x70\x73\x20"),
            (RX, b"\x39\x6f\x76\x65\x72\x20\x74\x68"),
            (RX, b"\x3a\x65\x20\x6c\x61\x7a\x79\x20"),
            (RX, b"\x3b\x64\x6f\x67\x0a\x74\x68\x65"),
            (RX, b"\x3c\x20\x63\x72\x61\x7a\x79\x20"),
            (RX, b"\x3d\x66\x6f\x78\x20\x6a\x75\x6d"),
            (RX, b"\x3e\x70\x73\x20\x6f\x76\x65\x72"),
            (RX, b"\x3f\x20\x74\x68\x65\x20\x6c\x61"),
            (RX, b"\x40\x7a\x79\x20\x64\x6f\x67\x0a"),
            (RX, b"\x41\x74\x68\x65\x20\x63\x72\x61"),
            (RX, b"\x42\x7a\x79\x20\x66\x6f\x78\x20"),
            (RX, b"\x43\x6a\x75\x6d\x70\x73\x20\x6f"),
            (RX, b"\x44\x76\x65\x72\x20\x74\x68\x65"),
            (RX, b"\x45\x20\x6c\x61\x7a\x79\x20\x64"),
            (RX, b"\x46\x6f\x67\x0a\x74\x68\x65\x20"),
            (RX, b"\x47\x63\x72\x61\x7a\x79\x20\x66"),
            (RX, b"\x48\x6f\x78\x20\x6a\x75\x6d\x70"),
            (RX, b"\x49\x73\x20\x6f\x76\x65\x72\x20"),
            (RX, b"\x4a\x74\x68\x65\x20\x6c\x61\x7a"),
            (RX, b"\x4b\x79\x20\x64\x6f\x67\x0a\x74"),
            (RX, b"\x4c\x68\x65\x20\x63\x72\x61\x7a"),
            (RX, b"\x4d\x79\x20\x66\x6f\x78\x20\x6a"),
            (RX, b"\x4e\x75\x6d\x70\x73\x20\x6f\x76"),
            (RX, b"\x4f\x65\x72\x20\x74\x68\x65\x20"),
            (RX, b"\x50\x6c\x61\x7a\x79\x20\x64\x6f"),
            (RX, b"\x51\x67\x0a\x74\x68\x65\x20\x63"),
            (RX, b"\x52\x72\x61\x7a\x79\x20\x66\x6f"),
            (RX, b"\x53\x78\x20\x6a\x75\x6d\x70\x73"),
            (RX, b"\x54\x20\x6f\x76\x65\x72\x20\x74"),
            (RX, b"\x55\x68\x65\x20\x6c\x61\x7a\x79"),
            (RX, b"\x56\x20\x64\x6f\x67\x0a\x74\x68"),
            (RX, b"\x57\x65\x20\x63\x72\x61\x7a\x79"),
            (RX, b"\x58\x20\x66\x6f\x78\x20\x6a\x75"),
            (RX, b"\x59\x6d\x70\x73\x20\x6f\x76\x65"),
            (RX, b"\x5a\x72\x20\x74\x68\x65\x20\x6c"),
            (RX, b"\x5b\x61\x7a\x79\x20\x64\x6f\x67"),
            (RX, b"\x5c\x0a\x74\x68\x65\x20\x63\x72"),
            (RX, b"\x5d\x61\x7a\x79\x20\x66\x6f\x78"),
            (RX, b"\x5e\x20\x6a\x75\x6d\x70\x73\x20"),
            (RX, b"\x5f\x6f\x76\x65\x72\x20\x74\x68"),
            (RX, b"\x60\x65\x20\x6c\x61\x7a\x79\x20"),
            (RX, b"\x61\x64\x6f\x67\x0a\x74\x68\x65"),
            (RX, b"\x62\x20\x63\x72\x61\x7a\x79\x20"),
            (RX, b"\x63\x66\x6f\x78\x20\x6a\x75\x6d"),
            (RX, b"\x64\x70\x73\x20\x6f\x76\x65\x72"),
            (RX, b"\x65\x20\x74\x68\x65\x20\x6c\x61"),
            (RX, b"\x66\x7a\x79\x20\x64\x6f\x67\x0a"),
            (RX, b"\x67\x74\x68\x65\x20\x63\x72\x61"),
            (RX, b"\x68\x7a\x79\x20\x66\x6f\x78\x20"),
            (RX, b"\x69\x6a\x75\x6d\x70\x73\x20\x6f"),
            (RX, b"\x6a\x76\x65\x72\x20\x74\x68\x65"),
            (RX, b"\x6b\x20\x6c\x61\x7a\x79\x20\x64"),
            (RX, b"\x6c\x6f\x67\x0a\x74\x68\x65\x20"),
            (RX, b"\x6d\x63\x72\x61\x7a\x79\x20\x66"),
            (RX, b"\x6e\x6f\x78\x20\x6a\x75\x6d\x70"),
            (RX, b"\x6f\x73\x20\x6f\x76\x65\x72\x20"),
            (RX, b"\x70\x74\x68\x65\x20\x6c\x61\x7a"),
            (RX, b"\x71\x79\x20\x64\x6f\x67\x0a\x74"),
            (RX, b"\x72\x68\x65\x20\x63\x72\x61\x7a"),
            (RX, b"\x73\x79\x20\x66\x6f\x78\x20\x6a"),
            (RX, b"\x74\x75\x6d\x70\x73\x20\x6f\x76"),
            (RX, b"\x75\x65\x72\x20\x74\x68\x65\x20"),
            (RX, b"\x76\x6c\x61\x7a\x79\x20\x64\x6f"),
            (RX, b"\x77\x67\x0a\x74\x68\x65\x20\x63"),
            (RX, b"\x78\x72\x61\x7a\x79\x20\x66\x6f"),
            (RX, b"\x79\x78\x20\x6a\x75\x6d\x70\x73"),
            (RX, b"\x7a\x20\x6f\x76\x65\x72\x20\x74"),
            (RX, b"\x7b\x68\x65\x20\x6c\x61\x7a\x79"),
            (RX, b"\x7c\x20\x64\x6f\x67\x0a\x74\x68"),
            (RX, b"\x7d\x65\x20\x63\x72\x61\x7a\x79"),
            (RX, b"\x7e\x20\x66\x6f\x78\x20\x6a\x75"),
            (RX, b"\x7f\x6d\x70\x73\x20\x6f\x76\x65"),
            (TX, b"\xa2\x7f\x7f\x00\x00\x00\x00\x00"), # --> This block is acknlowedged without issues
            (RX, b"\x01\x72\x20\x74\x68\x65\x20\x6c"),
            (RX, b"\x02\x61\x7a\x79\x20\x64\x6f\x67"),
            (RX, b"\x03\x0a\x74\x68\x65\x20\x63\x72"),
            (RX, b"\x04\x61\x7a\x79\x20\x66\x6f\x78"),
            (RX, b"\x05\x20\x6a\x75\x6d\x70\x73\x20"),
            (RX, b"\x06\x6f\x76\x65\x72\x20\x74\x68"),
            (RX, b"\x07\x65\x20\x6c\x61\x7a\x79\x20"),
            (RX, b"\x08\x64\x6f\x67\x0a\x74\x68\x65"),
            (RX, b"\x09\x20\x63\x72\x61\x7a\x79\x20"),
            (RX, b"\x0a\x66\x6f\x78\x20\x6a\x75\x6d"),
            (RX, b"\x0b\x70\x73\x20\x6f\x76\x65\x72"),
            (RX, b"\x0c\x20\x74\x68\x65\x20\x6c\x61"),
            (RX, b"\x0d\x7a\x79\x20\x64\x6f\x67\x0a"),
            (RX, b"\x0e\x74\x68\x65\x20\x63\x72\x61"),
            (RX, b"\x0f\x7a\x79\x20\x66\x6f\x78\x20"),
            (RX, b"\x10\x6a\x75\x6d\x70\x73\x20\x6f"),
            (RX, b"\x11\x76\x65\x72\x20\x74\x68\x65"),
            (RX, b"\x12\x20\x6c\x61\x7a\x79\x20\x64"),
            (RX, b"\x13\x6f\x67\x0a\x74\x68\x65\x20"),
            (RX, b"\x14\x63\x72\x61\x7a\x79\x20\x66"),
            (RX, b"\x15\x6f\x78\x20\x6a\x75\x6d\x70"),
            (RX, b"\x16\x73\x20\x6f\x76\x65\x72\x20"),
            (RX, b"\x17\x74\x68\x65\x20\x6c\x61\x7a"),
            (RX, b"\x18\x79\x20\x64\x6f\x67\x0a\x74"),
            (RX, b"\x19\x68\x65\x20\x63\x72\x61\x7a"),
            (RX, b"\x1a\x79\x20\x66\x6f\x78\x20\x6a"),
            (RX, b"\x1b\x75\x6d\x70\x73\x20\x6f\x76"),
            (RX, b"\x1c\x65\x72\x20\x74\x68\x65\x20"),
            (RX, b"\x1d\x6c\x61\x7a\x79\x20\x64\x6f"),
            (RX, b"\x1e\x67\x0a\x74\x68\x65\x20\x63"),
            (RX, b"\x1f\x72\x61\x7a\x79\x20\x66\x6f"),
            (RX, b"\x20\x78\x20\x6a\x75\x6d\x70\x73"),
            (RX, b"\x21\x20\x6f\x76\x65\x72\x20\x74"),
            (RX, b"\x22\x68\x65\x20\x6c\x61\x7a\x79"),
            (RX, b"\xa3\x20\x64\x6f\x67\x0a\x00\x00"),
            (TX, b"\xa2\x23\x7f\x00\x00\x00\x00\x00"),
            (RX, b"\xc9\x3b\x49\x00\x00\x00\x00\x00"),
            (TX, b"\xa1\x00\x00\x00\x00\x00\x00\x00"), # --> Transfer ends without issues
        ]
        data = []
        with self.network[2].sdo[0x1008].open("r", block_transfer=True) as fp:
            data = fp.read()
        assert data == 39 * "the crazy fox jumps over the lazy dog\n"

    def test_writable_file(self):
        self.data = [
            (TX, b'\x20\x00\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x60\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x00\x31\x32\x33\x34\x35\x36\x37'),
            (RX, b'\x20\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x1a\x38\x39\x00\x00\x00\x00\x00'),
            (RX, b'\x30\x00\x20\x00\x00\x00\x00\x00'),
            (TX, b'\x0f\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x20\x00\x20\x00\x00\x00\x00\x00')
        ]
        with self.network[2].sdo['Writable string'].open('wb') as fp:
            fp.write(b'1234')
            fp.write(b'56789')
        self.assertTrue(fp.closed)
        # Write on closed file
        with self.assertRaises(ValueError):
            fp.write(b'123')

    def test_abort(self):
        self.data = [
            (TX, b'\x40\x18\x10\x01\x00\x00\x00\x00'),
            (RX, b'\x80\x18\x10\x01\x11\x00\x09\x06')
        ]
        with self.assertRaises(canopen.SdoAbortedError) as cm:
            _ = self.network[2].sdo[0x1018][1].raw
        self.assertEqual(cm.exception.code, 0x06090011)

    def test_add_sdo_channel(self):
        client = self.network[2].add_sdo(0x123456, 0x234567)
        self.assertIn(client, self.network[2].sdo_channels)


class TestSDOClientDatatypes(unittest.TestCase):
    """Test the SDO client uploads with the different data types in CANopen."""

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
            (RX, b'\x4f\x01\x20\x00\xfe\xfd\xfc\xfb')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.BOOLEAN, 0)
        self.assertEqual(data, b'\xfe')

    def test_unsigned8(self):
        self.data = [
            (TX, b'\x40\x05\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x4f\x05\x20\x00\xfe\xfd\xfc\xfb')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED8, 0)
        self.assertEqual(data, b'\xfe')

    def test_unsigned16(self):
        self.data = [
            (TX, b'\x40\x06\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x4b\x06\x20\x00\xfe\xfd\xfc\xfb')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED16, 0)
        self.assertEqual(data, b'\xfe\xfd')

    def test_unsigned24(self):
        self.data = [
            (TX, b'\x40\x16\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x47\x16\x20\x00\xfe\xfd\xfc\xfb')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNSIGNED24, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc')

    def test_unsigned32(self):
        self.data = [
            (TX, b'\x40\x07\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x43\x07\x20\x00\xfe\xfd\xfc\xfb')
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
            (RX, b'\x4f\x02\x20\x00\xfe\xfd\xfc\xfb')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER8, 0)
        self.assertEqual(data, b'\xfe')

    def test_integer16(self):
        self.data = [
            (TX, b'\x40\x03\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x4b\x03\x20\x00\xfe\xfd\xfc\xfb')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER16, 0)
        self.assertEqual(data, b'\xfe\xfd')

    def test_integer24(self):
        self.data = [
            (TX, b'\x40\x10\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x47\x10\x20\x00\xfe\xfd\xfc\xfb')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.INTEGER24, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc')

    def test_integer32(self):
        self.data = [
            (TX, b'\x40\x04\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x43\x04\x20\x00\xfe\xfd\xfc\xfb')
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
            (RX, b'\x43\x08\x20\x00\xfe\xfd\xfc\xfb')
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
            (RX, b'\x41\x09\x20\x00\x1A\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6E\x79\x20\x4E\x6F'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2D\x20\x4D\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6F\x6D\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6E\x73\x20\x21\x00\x00')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.VISIBLE_STRING, 0)
        self.assertEqual(data, b'Tiny Node - Mega Domains !')

    def test_unicode_string(self):
        self.data = [
            (TX, b'\x40\x0b\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x0b\x20\x00\x1A\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6E\x79\x20\x4E\x6F'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2D\x20\x4D\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6F\x6D\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6E\x73\x20\x21\x00\x00')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.UNICODE_STRING, 0)
        self.assertEqual(data, b'Tiny Node - Mega Domains !')

    def test_octet_string(self):
        self.data = [
            (TX, b'\x40\x0a\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x0a\x20\x00\x1A\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6E\x79\x20\x4E\x6F'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2D\x20\x4D\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6F\x6D\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6E\x73\x20\x21\x00\x00')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.OCTET_STRING, 0)
        self.assertEqual(data, b'Tiny Node - Mega Domains !')

    def test_domain(self):
        self.data = [
            (TX, b'\x40\x0f\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\x0f\x20\x00\x1A\x00\x00\x00'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x54\x69\x6E\x79\x20\x4E\x6F'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x10\x64\x65\x20\x2D\x20\x4D\x65'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\x67\x61\x20\x44\x6F\x6D\x61'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x15\x69\x6E\x73\x20\x21\x00\x00')
        ]
        data = self.network[2].sdo.upload(0x2000 + dt.DOMAIN, 0)
        self.assertEqual(data, b'Tiny Node - Mega Domains !')

    def test_unknown_od_32(self):
        """Test an unknown OD entry of 32 bits (4 bytes)."""
        self.data = [
            (TX, b'\x40\xFF\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x43\xFF\x20\x00\xfe\xfd\xfc\xfb')
        ]
        data = self.network[2].sdo.upload(0x20FF, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc\xfb')

    def test_unknown_od_112(self):
        """Test an unknown OD entry of 112 bits (14 bytes)."""
        self.data = [
            (TX, b'\x40\xFF\x20\x00\x00\x00\x00\x00'),
            (RX, b'\x41\xFF\x20\x00\xfe\xfd\xfc\xfb'),
            (TX, b'\x60\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x00\xb2\x01\x20\x02\x91\x12\x03'),
            (TX, b'\x70\x00\x00\x00\x00\x00\x00\x00'),
            (RX, b'\x11\x19\x21\x70\xfe\xfd\xfc\xfb'),
        ]
        data = self.network[2].sdo.upload(0x20FF, 0)
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91\x12\x03\x19\x21\x70\xfe\xfd\xfc\xfb')

    def test_unknown_datatype32(self):
        """Test an unknown datatype, but known OD, of 32 bits (4 bytes)."""
        return  # FIXME: Disabled temporarily until datatype conditionals are fixed, see #436
        # Add fake entry 0x2100 to OD, using fake datatype 0xFF
        if 0x2100 not in self.node.object_dictionary:
            fake_var = ODVariable("Fake", 0x2100)
            fake_var.data_type = 0xFF
            self.node.object_dictionary.add_object(fake_var)
        self.data = [
            (TX, b'\x40\x00\x21\x00\x00\x00\x00\x00'),
            (RX, b'\x43\x00\x21\x00\xfe\xfd\xfc\xfb')
        ]
        data = self.network[2].sdo.upload(0x2100, 0)
        self.assertEqual(data, b'\xfe\xfd\xfc\xfb')

    def test_unknown_datatype112(self):
        """Test an unknown datatype, but known OD, of 112 bits (14 bytes)."""
        return  # FIXME: Disabled temporarily until datatype conditionals are fixed, see #436
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
        self.assertEqual(data, b'\xb2\x01\x20\x02\x91\x12\x03\x19\x21\x70\xfe\xfd\xfc\xfb')

if __name__ == "__main__":
    unittest.main()
