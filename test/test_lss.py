import struct
import unittest
from unittest.mock import MagicMock

from canopen.lss import (
    LssMaster,
    LssError,
    CS_SWITCH_STATE_GLOBAL,
    CS_CONFIGURE_NODE_ID,
    CS_CONFIGURE_BIT_TIMING,
    CS_STORE_CONFIGURATION,
    CS_SWITCH_STATE_SELECTIVE_VENDOR_ID,
    CS_SWITCH_STATE_SELECTIVE_PRODUCT_CODE,
    CS_SWITCH_STATE_SELECTIVE_REVISION_NUMBER,
    CS_SWITCH_STATE_SELECTIVE_SERIAL_NUMBER,
    CS_SWITCH_STATE_SELECTIVE_RESPONSE,
    CS_INQUIRE_NODE_ID,
    CS_INQUIRE_VENDOR_ID,
    CS_INQUIRE_PRODUCT_CODE,
    CS_INQUIRE_REVISION_NUMBER,
    CS_INQUIRE_SERIAL_NUMBER,
    CS_IDENTIFY_SLAVE,
    CS_FAST_SCAN,
    CS_ACTIVATE_BIT_TIMING,
    ERROR_NONE,
    ERROR_INADMISSIBLE,
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
        """A send_message side_effect that records but sends no response."""
        self.sent_messages.append((cob_id, bytes(data)))

    # ---- switch state global ----

    def test_send_switch_state_global_configuration(self):
        self.network.send_message.side_effect = self._send_no_response
        self.lss.send_switch_state_global(LssMaster.CONFIGURATION_STATE)
        self.assertEqual(len(self.sent_messages), 1)
        cob_id, data = self.sent_messages[0]
        self.assertEqual(cob_id, LssMaster.LSS_TX_COBID)
        self.assertEqual(len(data), 8)
        self.assertEqual(data[0], CS_SWITCH_STATE_GLOBAL)
        self.assertEqual(data[1], LssMaster.CONFIGURATION_STATE)

    def test_send_switch_state_global_waiting(self):
        self.network.send_message.side_effect = self._send_no_response
        self.lss.send_switch_state_global(LssMaster.WAITING_STATE)
        _, data = self.sent_messages[0]
        self.assertEqual(data[0], CS_SWITCH_STATE_GLOBAL)
        self.assertEqual(data[1], LssMaster.WAITING_STATE)

    def test_send_switch_state_global_no_response_expected(self):
        self.network.send_message.side_effect = self._send_no_response
        self.lss.send_switch_state_global(LssMaster.CONFIGURATION_STATE)

    # ---- configure node ID ----

    def test_configure_node_id_success(self):
        response = bytearray(8)
        response[0] = CS_CONFIGURE_NODE_ID
        response[1] = ERROR_NONE
        self.network.send_message.side_effect = self._send_and_respond(response)

        self.lss.configure_node_id(5)
        _, data = self.sent_messages[0]
        self.assertEqual(data[0], CS_CONFIGURE_NODE_ID)
        self.assertEqual(data[1], 5)

    def test_configure_node_id_error(self):
        response = bytearray(8)
        response[0] = CS_CONFIGURE_NODE_ID
        response[1] = ERROR_INADMISSIBLE
        self.network.send_message.side_effect = self._send_and_respond(response)

        with self.assertRaises(LssError):
            self.lss.configure_node_id(200)

    def test_configure_node_id_wrong_cs(self):
        response = bytearray(8)
        response[0] = 0xFF
        response[1] = ERROR_NONE
        self.network.send_message.side_effect = self._send_and_respond(response)

        with self.assertRaises(LssError):
            self.lss.configure_node_id(5)

    # ---- configure bit timing ----

    def test_configure_bit_timing_success(self):
        response = bytearray(8)
        response[0] = CS_CONFIGURE_BIT_TIMING
        response[1] = ERROR_NONE
        self.network.send_message.side_effect = self._send_and_respond(response)

        self.lss.configure_bit_timing(4)
        _, data = self.sent_messages[0]
        self.assertEqual(data[0], CS_CONFIGURE_BIT_TIMING)
        self.assertEqual(data[1], 0)
        self.assertEqual(data[2], 4)

    # ---- activate bit timing ----

    def test_activate_bit_timing(self):
        self.network.send_message.side_effect = self._send_no_response
        self.lss.activate_bit_timing(500)
        _, data = self.sent_messages[0]
        self.assertEqual(data[0], CS_ACTIVATE_BIT_TIMING)
        delay = struct.unpack_from('<H', data, 1)[0]
        self.assertEqual(delay, 500)

    # ---- store configuration ----

    def test_store_configuration_success(self):
        response = bytearray(8)
        response[0] = CS_STORE_CONFIGURATION
        response[1] = ERROR_NONE
        self.network.send_message.side_effect = self._send_and_respond(response)
        self.lss.store_configuration()

    def test_store_configuration_error(self):
        response = bytearray(8)
        response[0] = CS_STORE_CONFIGURATION
        response[1] = 1
        self.network.send_message.side_effect = self._send_and_respond(response)

        with self.assertRaises(LssError):
            self.lss.store_configuration()

    # ---- inquire node ID ----

    def test_inquire_node_id(self):
        response = bytearray(8)
        response[0] = CS_INQUIRE_NODE_ID
        response[1] = 42
        self.network.send_message.side_effect = self._send_and_respond(response)

        node_id = self.lss.inquire_node_id()
        self.assertEqual(node_id, 42)

    def test_inquire_node_id_wrong_cs(self):
        response = bytearray(8)
        response[0] = 0xFF
        response[1] = 42
        self.network.send_message.side_effect = self._send_and_respond(response)

        with self.assertRaises(LssError):
            self.lss.inquire_node_id()

    # ---- inquire LSS address ----

    def test_inquire_vendor_id(self):
        response = bytearray(8)
        response[0] = CS_INQUIRE_VENDOR_ID
        struct.pack_into('<I', response, 1, 0x12345678)
        self.network.send_message.side_effect = self._send_and_respond(response)

        result = self.lss.inquire_lss_address(CS_INQUIRE_VENDOR_ID)
        self.assertEqual(result, 0x12345678)

    def test_inquire_product_code(self):
        response = bytearray(8)
        response[0] = CS_INQUIRE_PRODUCT_CODE
        struct.pack_into('<I', response, 1, 0xABCD)
        self.network.send_message.side_effect = self._send_and_respond(response)

        result = self.lss.inquire_lss_address(CS_INQUIRE_PRODUCT_CODE)
        self.assertEqual(result, 0xABCD)

    def test_inquire_revision_number(self):
        response = bytearray(8)
        response[0] = CS_INQUIRE_REVISION_NUMBER
        struct.pack_into('<I', response, 1, 99)
        self.network.send_message.side_effect = self._send_and_respond(response)

        result = self.lss.inquire_lss_address(CS_INQUIRE_REVISION_NUMBER)
        self.assertEqual(result, 99)

    def test_inquire_serial_number(self):
        response = bytearray(8)
        response[0] = CS_INQUIRE_SERIAL_NUMBER
        struct.pack_into('<I', response, 1, 1001)
        self.network.send_message.side_effect = self._send_and_respond(response)

        result = self.lss.inquire_lss_address(CS_INQUIRE_SERIAL_NUMBER)
        self.assertEqual(result, 1001)

    def test_inquire_lss_address_wrong_cs(self):
        response = bytearray(8)
        response[0] = 0xFF
        self.network.send_message.side_effect = self._send_and_respond(response)

        with self.assertRaises(LssError):
            self.lss.inquire_lss_address(CS_INQUIRE_VENDOR_ID)

    # ---- switch state selective ----

    def test_send_switch_state_selective_success(self):
        response = bytearray(8)
        response[0] = CS_SWITCH_STATE_SELECTIVE_RESPONSE
        self.network.send_message.side_effect = self._send_and_respond(response)

        result = self.lss.send_switch_state_selective(
            0x1111, 0x2222, 0x3333, 0x4444)
        self.assertTrue(result)

        self.assertEqual(len(self.sent_messages), 4)
        self.assertEqual(self.sent_messages[0][1][0], CS_SWITCH_STATE_SELECTIVE_VENDOR_ID)
        self.assertEqual(self.sent_messages[1][1][0], CS_SWITCH_STATE_SELECTIVE_PRODUCT_CODE)
        self.assertEqual(self.sent_messages[2][1][0], CS_SWITCH_STATE_SELECTIVE_REVISION_NUMBER)
        self.assertEqual(self.sent_messages[3][1][0], CS_SWITCH_STATE_SELECTIVE_SERIAL_NUMBER)

    def test_send_switch_state_selective_no_match(self):
        response = bytearray(8)
        response[0] = 0x00
        self.network.send_message.side_effect = self._send_and_respond(response)

        result = self.lss.send_switch_state_selective(
            0x1111, 0x2222, 0x3333, 0x4444)
        self.assertFalse(result)

    # ---- timeout / error handling ----

    def test_no_response_timeout(self):
        self.network.send_message.side_effect = self._send_no_response
        with self.assertRaises(LssError) as ctx:
            self.lss.inquire_node_id()
        self.assertIn("No LSS response", str(ctx.exception))

    def test_unexpected_messages_cleared(self):
        """Stale messages in queue should be cleared before sending."""
        self.lss.responses.put(b'\x00' * 8)

        response = bytearray(8)
        response[0] = CS_INQUIRE_NODE_ID
        response[1] = 10
        self.network.send_message.side_effect = self._send_and_respond(response)

        with self.assertLogs(level='INFO') as logs:
            node_id = self.lss.inquire_node_id()
        self.assertEqual(node_id, 10)
        self.assertTrue(any("unexpected" in msg for msg in logs.output))

    # ---- on_message_received ----

    def test_on_message_received(self):
        data = bytearray(8)
        data[0] = 0xAA
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
        response = bytearray(8)
        response[0] = CS_IDENTIFY_SLAVE
        self.network.send_message.side_effect = self._send_and_respond(response)

        result, lss_id = self.lss.fast_scan()
        self.assertTrue(result)
        self.assertEqual(lss_id, [0, 0, 0, 0])

    # ---- LSS address encoding ----

    def test_lss_address_encoding(self):
        """Verify the 4-byte address is packed correctly in messages."""
        response = bytearray(8)
        response[0] = CS_SWITCH_STATE_SELECTIVE_RESPONSE
        self.network.send_message.side_effect = self._send_and_respond(response)

        self.lss.send_switch_state_selective(
            0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0x9ABCDEF0)

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
        self.assertEqual(data[0], CS_SWITCH_STATE_GLOBAL)
        self.assertEqual(data[1], LssMaster.CONFIGURATION_STATE)


class TestLssError(unittest.TestCase):

    def test_lss_error_is_exception(self):
        self.assertIsInstance(LssError("test"), Exception)

    def test_lss_error_message(self):
        err = LssError("something went wrong")
        self.assertEqual(str(err), "something went wrong")


if __name__ == '__main__':
    unittest.main()
