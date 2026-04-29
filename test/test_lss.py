import re
import struct
import unittest
from unittest.mock import MagicMock

from canopen.lss import (
    LssMaster,
    LssError,
    CS_INQUIRE_VENDOR_ID,
    CS_INQUIRE_PRODUCT_CODE,
    CS_INQUIRE_REVISION_NUMBER,
    CS_INQUIRE_SERIAL_NUMBER,
    ListMessageNeedResponse,
)


class TestLssMaster(unittest.TestCase):
    """Tests for LssMaster message encoding, decoding, and error handling.

    Follows the same pattern as test_sdo.py: replace network.send_message
    with a custom method that records sent data and injects responses
    synchronously.
    """

    def setUp(self):
        self.lss = LssMaster()
        self.lss.RESPONSE_TIMEOUT = 0.1
        self.network = MagicMock()
        self.lss.network = self.network
        self.sent_messages = []

    def _send_and_respond(self, response):
        """Return a send_message side_effect that always injects the given response."""

        def side_effect(cob_id, data):
            self.sent_messages.append((cob_id, bytes(data)))
            if data[0] in ListMessageNeedResponse:
                self.lss.on_message_received(LssMaster.LSS_RX_COBID, response, 0.0)

        return side_effect

    def _send_no_response(self, cob_id, data):
        """Record but do not send a response."""
        self.sent_messages.append((cob_id, bytes(data)))

    # ---- switch state global ----

    def test_send_switch_state_global_configuration(self):
        self.network.send_message.side_effect = self._send_no_response
        self.lss.send_switch_state_global(LssMaster.CONFIGURATION_STATE)
        self.assertEqual(len(self.sent_messages), 1)
        cob_id, data = self.sent_messages[0]
        self.assertEqual(cob_id, LssMaster.LSS_TX_COBID)
        self.assertEqual(len(data), 8)
        self.assertEqual(data[:2], b'\x04\x01')

    def test_send_switch_state_global_waiting(self):
        self.network.send_message.side_effect = self._send_no_response
        self.lss.send_switch_state_global(LssMaster.WAITING_STATE)
        _, data = self.sent_messages[0]
        self.assertEqual(data[:2], b'\x04\x00')

    def test_send_switch_state_global_no_response_expected(self):
        self.network.send_message.side_effect = self._send_no_response
        self.lss.send_switch_state_global(LssMaster.CONFIGURATION_STATE)

    # ---- configure node ID ----

    def test_configure_node_id_success(self):
        response = b'\x11\x00\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        self.lss.configure_node_id(5)
        _, data = self.sent_messages[0]
        self.assertEqual(data[:2], b'\x11\x05')

    def test_configure_node_id_error(self):
        response = b'\x11\x01\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        with self.assertRaisesRegex(LssError, re.compile('error.*1', re.I)):
            self.lss.configure_node_id(200)

    def test_configure_node_id_wrong_cs(self):
        response = b'\xFF\x00\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        with self.assertRaisesRegex(LssError, re.compile('not for.*request', re.I)):
            self.lss.configure_node_id(5)

    # ---- configure bit timing ----

    def test_configure_bit_timing_success(self):
        response = b'\x13\x00\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)

        self.lss.configure_bit_timing(4)
        _, data = self.sent_messages[0]
        self.assertEqual(data[:3], b'\x13\x00\x04')

    # ---- activate bit timing ----

    def test_activate_bit_timing(self):
        self.network.send_message.side_effect = self._send_no_response
        self.lss.activate_bit_timing(500)
        _, data = self.sent_messages[0]
        self.assertEqual(data[:3], b'\x15\xF4\x01')

    # ---- store configuration ----

    def test_store_configuration_success(self):
        response = b'\x17\x00\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        self.lss.store_configuration()

    def test_store_configuration_error(self):
        response = b'\x17\x01\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        with self.assertRaisesRegex(LssError, re.compile('error.*1', re.I)):
            self.lss.store_configuration()

    # ---- inquire node ID ----

    def test_inquire_node_id(self):
        response = b'\x5E\x2A\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        node_id = self.lss.inquire_node_id()
        self.assertEqual(node_id, 42)

    def test_inquire_node_id_wrong_cs(self):
        response = b'\xFF\x2A\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        with self.assertRaisesRegex(LssError, re.compile('not for.*request', re.I)):
            self.lss.inquire_node_id()

    # ---- inquire LSS address ----

    def test_inquire_vendor_id(self):
        response = b'\x5A\x78\x56\x34\x12\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        result = self.lss.inquire_lss_address(CS_INQUIRE_VENDOR_ID)
        self.assertEqual(result, 0x12345678)

    def test_inquire_product_code(self):
        response = b'\x5B\xCD\xAB\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        result = self.lss.inquire_lss_address(CS_INQUIRE_PRODUCT_CODE)
        self.assertEqual(result, 0xABCD)

    def test_inquire_revision_number(self):
        response = b'\x5C\x63\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        result = self.lss.inquire_lss_address(CS_INQUIRE_REVISION_NUMBER)
        self.assertEqual(result, 99)

    def test_inquire_serial_number(self):
        response = b'\x5D\xE9\x03\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        result = self.lss.inquire_lss_address(CS_INQUIRE_SERIAL_NUMBER)
        self.assertEqual(result, 1001)

    def test_inquire_lss_address_wrong_cs(self):
        response = b'\xFF\x00\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        with self.assertRaisesRegex(LssError, re.compile('not for.*request', re.I)):
            self.lss.inquire_lss_address(CS_INQUIRE_VENDOR_ID)

    # ---- switch state selective ----

    def test_send_switch_state_selective_success(self):
        response = b'\x44\x00\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        result = self.lss.send_switch_state_selective(0x1110, 0x2220, 0x3330, 0x4440)
        self.assertTrue(result)

        self.assertEqual(len(self.sent_messages), 4)
        self.assertEqual(self.sent_messages[0][1][:5], b'\x40\x10\x11\x00\x00')
        self.assertEqual(self.sent_messages[1][1][:5], b'\x41\x20\x22\x00\x00')
        self.assertEqual(self.sent_messages[2][1][:5], b'\x42\x30\x33\x00\x00')
        self.assertEqual(self.sent_messages[3][1][:5], b'\x43\x40\x44\x00\x00')

    def test_send_switch_state_selective_no_match(self):
        response = bytearray(8)
        self.network.send_message.side_effect = self._send_and_respond(response)
        result = self.lss.send_switch_state_selective(0x1110, 0x2220, 0x3330, 0x4440)
        self.assertFalse(result)

    # ---- timeout / error handling ----

    def test_no_response_timeout(self):
        self.network.send_message.side_effect = self._send_no_response
        with self.assertRaisesRegex(LssError, re.compile('no LSS response', re.I)):
            self.lss.inquire_node_id()

    def test_unexpected_messages_cleared(self):
        """Stale messages in queue should be cleared before sending."""
        self.lss.responses.put(bytearray(8))
        response = b'\x5E\x0A\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)

        with self.assertLogs(level='INFO') as logs:
            node_id = self.lss.inquire_node_id()
        self.assertEqual(node_id, 10)
        self.assertTrue(any("unexpected" in msg for msg in logs.output))

    # ---- on_message_received ----

    def test_on_message_received(self):
        data = b'\xAA\x00\x00\x00\x00\x00\x00\x00'
        self.lss.on_message_received(LssMaster.LSS_RX_COBID, data, 1.0)
        result = self.lss.responses.get(block=False)
        self.assertEqual(result[0], 0xAA)

    # ---- fast scan ----

    def test_fast_scan_no_slave(self):
        """No slave responds → returns (False, None)."""
        self.network.send_message.side_effect = self._send_no_response
        result, lss_id = self.lss.fast_scan()
        self.assertFalse(result)
        self.assertIsNone(lss_id)

    def test_fast_scan_finds_slave(self):
        """Simulate a slave that always responds to fast scan."""
        response = b'\x4F\x00\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)
        result, lss_id = self.lss.fast_scan()
        self.assertTrue(result)
        self.assertEqual(lss_id, [0, 0, 0, 0])

    # ---- LSS address encoding ----

    def test_lss_address_encoding(self):
        """Verify the 4-byte address is packed correctly in messages."""
        response = b'\x44\x00\x00\x00\x00\x00\x00\x00'
        self.network.send_message.side_effect = self._send_and_respond(response)

        self.lss.send_switch_state_selective(0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0x9ABCDEF0)

        data = self.sent_messages[0][1]
        packed = struct.unpack_from('<I', data, 1)[0]
        self.assertEqual(packed, 0xDEADBEEF)

        data = self.sent_messages[1][1]
        packed = struct.unpack_from('<I', data, 1)[0]
        self.assertEqual(packed, 0xCAFEBABE)

    # ---- obsolete aliases ----

    def test_send_switch_mode_global_alias(self):
        """The obsolete send_switch_mode_global should delegate."""
        self.network.send_message.side_effect = self._send_no_response
        self.lss.send_switch_mode_global(LssMaster.CONFIGURATION_STATE)
        _, data = self.sent_messages[0]
        self.assertEqual(data[:2], b'\x04\x01')


class TestLssError(unittest.TestCase):

    def test_lss_error_is_exception(self):
        self.assertIsInstance(LssError("test"), Exception)

    def test_lss_error_message(self):
        err = LssError("something went wrong")
        self.assertEqual(str(err), "something went wrong")


if __name__ == '__main__':
    unittest.main()
