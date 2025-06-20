import time
import unittest
import asyncio

import canopen
from canopen.async_guard import AllowBlocking

from .util import SAMPLE_EDS


class TestSDO(unittest.IsolatedAsyncioTestCase):
    """
    Test SDO client and server against each other.
    """

    __test__ = False  # This is a base class, tests should not be run directly.
    use_async: bool

    def setUp(self):
        loop = None
        if self.use_async:
            loop = asyncio.get_event_loop()

        self.network1 = canopen.Network(loop=loop)
        self.network1.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.network1.connect("test", interface="virtual")
        with AllowBlocking():
            self.remote_node = self.network1.add_node(2, SAMPLE_EDS)

        self.network2 = canopen.Network(loop=loop)
        self.network2.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.network2.connect("test", interface="virtual")
        self.local_node = self.network2.create_node(2, SAMPLE_EDS)
        with AllowBlocking():
            self.remote_node2 = self.network1.add_node(3, SAMPLE_EDS)
        self.local_node2 = self.network2.create_node(3, SAMPLE_EDS)

    def tearDown(self):
        self.network1.disconnect()
        self.network2.disconnect()

    async def test_expedited_upload(self):
        if self.use_async:
            await self.local_node.sdo[0x1400][1].aset_raw(0x99)
            vendor_id = await self.remote_node.sdo[0x1400][1].aget_raw()
        else:
            self.local_node.sdo[0x1400][1].raw = 0x99
            vendor_id = self.remote_node.sdo[0x1400][1].raw
        self.assertEqual(vendor_id, 0x99)

    async def test_block_upload_switch_to_expedite_upload(self):
        if self.use_async:
            self.skipTest("Block upload not supported in async mode")
        with self.assertRaises(canopen.SdoCommunicationError) as context:
            with self.remote_node.sdo[0x1008].open('r', block_transfer=True) as fp:
                pass
        # We get this since the sdo client don't support the switch
        # from block upload to expedite upload
        self.assertEqual("Unexpected response 0x41", str(context.exception))

    async def test_block_download_not_supported(self):
        if self.use_async:
            self.skipTest("Block download not supported in async mode")
        data = b"TEST DEVICE"
        with self.assertRaises(canopen.SdoAbortedError) as context:
            with self.remote_node.sdo[0x1008].open('wb',
                                                   size=len(data),
                                                   block_transfer=True) as fp:
                pass
        self.assertEqual(context.exception.code, 0x05040001)

    async def test_expedited_upload_default_value_visible_string(self):
        if self.use_async:
            device_name = await self.remote_node.sdo["Manufacturer device name"].aget_raw()
        else:
            device_name = self.remote_node.sdo["Manufacturer device name"].raw
        self.assertEqual(device_name, "TEST DEVICE")

    async def test_expedited_upload_default_value_real(self):
        if self.use_async:
            sampling_rate = await self.remote_node.sdo["Sensor Sampling Rate (Hz)"].aget_raw()
        else:
            sampling_rate = self.remote_node.sdo["Sensor Sampling Rate (Hz)"].raw
        self.assertAlmostEqual(sampling_rate, 5.2, places=2)

    async def test_upload_zero_length(self):
        if self.use_async:
            await self.local_node.sdo["Manufacturer device name"].aset_raw(b"")
            with self.assertRaises(canopen.SdoAbortedError) as error:
                await self.remote_node.sdo["Manufacturer device name"].aget_data()
        else:
            self.local_node.sdo["Manufacturer device name"].raw = b""
            with self.assertRaises(canopen.SdoAbortedError) as error:
                self.remote_node.sdo["Manufacturer device name"].data
        # Should be No data available
        self.assertEqual(error.exception.code, 0x0800_0024)

    async def test_segmented_upload(self):
        if self.use_async:
            await self.local_node.sdo["Manufacturer device name"].aset_raw("Some cool device")
            device_name = await self.remote_node.sdo["Manufacturer device name"].aget_data()
        else:
            self.local_node.sdo["Manufacturer device name"].raw = "Some cool device"
            device_name = self.remote_node.sdo["Manufacturer device name"].data
        self.assertEqual(device_name, b"Some cool device")

    async def test_expedited_download(self):
        if self.use_async:
            await self.remote_node.sdo[0x2004].aset_raw(0xfeff)
            value = await self.local_node.sdo[0x2004].aget_raw()
        else:
            self.remote_node.sdo[0x2004].raw = 0xfeff
            value = self.local_node.sdo[0x2004].raw
        self.assertEqual(value, 0xfeff)

    async def test_expedited_download_wrong_datatype(self):
        # Try to write 32 bit in integer16 type
        if self.use_async:
            with self.assertRaises(canopen.SdoAbortedError) as error:
                await self.remote_node.sdo.adownload(0x2001, 0x0, bytes([10, 10, 10, 10]))
        else:
            with self.assertRaises(canopen.SdoAbortedError) as error:
                self.remote_node.sdo.download(0x2001, 0x0, bytes([10, 10, 10, 10]))
        self.assertEqual(error.exception.code, 0x06070010)
        # Try to write normal 16 bit word, should be ok
        if self.use_async:
            await self.remote_node.sdo.adownload(0x2001, 0x0, bytes([10, 10]))
            value = await self.remote_node.sdo.aupload(0x2001, 0x0)
        else:
            self.remote_node.sdo.download(0x2001, 0x0, bytes([10, 10]))
            value = self.remote_node.sdo.upload(0x2001, 0x0)
        self.assertEqual(value, bytes([10, 10]))

    async def test_segmented_download(self):
        if self.use_async:
            await self.remote_node.sdo[0x2000].aset_raw("Another cool device")
            value = await self.local_node.sdo[0x2000].aget_data()
        else:
            self.remote_node.sdo[0x2000].raw = "Another cool device"
            value = self.local_node.sdo[0x2000].data
        self.assertEqual(value, b"Another cool device")

    async def test_slave_send_heartbeat(self):
        # Setting the heartbeat time should trigger heartbeating
        # to start
        if self.use_async:
            await self.remote_node.sdo["Producer heartbeat time"].aset_raw(100)
            state = await self.remote_node.nmt.await_for_heartbeat()
        else:
            self.remote_node.sdo["Producer heartbeat time"].raw = 100
            state = self.remote_node.nmt.wait_for_heartbeat()
        self.local_node.nmt.stop_heartbeat()
        # The NMT master will change the state INITIALISING (0)
        # to PRE-OPERATIONAL (127)
        self.assertEqual(state, 'PRE-OPERATIONAL')

    async def test_nmt_state_initializing_to_preoper(self):
        # Initialize the heartbeat timer
        if self.use_async:
            await self.local_node.sdo["Producer heartbeat time"].aset_raw(100)
        else:
            self.local_node.sdo["Producer heartbeat time"].raw = 100
        self.local_node.nmt.stop_heartbeat()
        # This transition shall start the heartbeating
        self.local_node.nmt.state = 'INITIALISING'
        self.local_node.nmt.state = 'PRE-OPERATIONAL'
        if self.use_async:
            state = await self.remote_node.nmt.await_for_heartbeat()
        else:
            state = self.remote_node.nmt.wait_for_heartbeat()
        self.local_node.nmt.stop_heartbeat()
        self.assertEqual(state, 'PRE-OPERATIONAL')

    async def test_receive_abort_request(self):
        if self.use_async:
            await self.remote_node.sdo.aabort(0x05040003)
        else:
            self.remote_node.sdo.abort(0x05040003)
        # Line below is just so that we are sure the client have received the abort
        # before we do the check
        if self.use_async:
            await asyncio.sleep(0.1)
        else:
            time.sleep(0.1)
        self.assertEqual(self.local_node.sdo.last_received_error, 0x05040003)

    async def test_start_remote_node(self):
        self.remote_node.nmt.state = 'OPERATIONAL'
        # Line below is just so that we are sure the client have received the command
        # before we do the check
        if self.use_async:
            await asyncio.sleep(0.1)
        else:
            time.sleep(0.1)
        slave_state = self.local_node.nmt.state
        self.assertEqual(slave_state, 'OPERATIONAL')

    async def test_two_nodes_on_the_bus(self):
        if self.use_async:
            await self.local_node.sdo["Manufacturer device name"].aset_raw("Some cool device")
            device_name = await self.remote_node.sdo["Manufacturer device name"].aget_data()
        else:
            self.local_node.sdo["Manufacturer device name"].raw = "Some cool device"
            device_name = self.remote_node.sdo["Manufacturer device name"].data
        self.assertEqual(device_name, b"Some cool device")

        if self.use_async:
            await self.local_node2.sdo["Manufacturer device name"].aset_raw("Some cool device2")
            device_name = await self.remote_node2.sdo["Manufacturer device name"].aget_data()
        else:
            self.local_node2.sdo["Manufacturer device name"].raw = "Some cool device2"
            device_name = self.remote_node2.sdo["Manufacturer device name"].data
        self.assertEqual(device_name, b"Some cool device2")

    async def test_abort(self):
        if self.use_async:
            with self.assertRaises(canopen.SdoAbortedError) as cm:
                _ = await self.remote_node.sdo.aupload(0x1234, 0)
        else:
            with self.assertRaises(canopen.SdoAbortedError) as cm:
                _ = self.remote_node.sdo.upload(0x1234, 0)
        # Should be Object does not exist
        self.assertEqual(cm.exception.code, 0x06020000)

        if self.use_async:
            with self.assertRaises(canopen.SdoAbortedError) as cm:
                _ = await self.remote_node.sdo.aupload(0x1018, 100)
        else:
            with self.assertRaises(canopen.SdoAbortedError) as cm:
                _ = self.remote_node.sdo.upload(0x1018, 100)
        # Should be Subindex does not exist
        self.assertEqual(cm.exception.code, 0x06090011)

        if self.use_async:
            with self.assertRaises(canopen.SdoAbortedError) as cm:
                _ = await self.remote_node.sdo[0x1001].aget_data()
        else:
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

    async def test_callbacks(self):
        self.local_node.add_read_callback(self._some_read_callback)
        self.local_node.add_write_callback(self._some_write_callback)

        if self.use_async:
            data = await self.remote_node.sdo.aupload(0x1003, 5)
        else:
            data = self.remote_node.sdo.upload(0x1003, 5)
        self.assertEqual(data, b"\x01\x02\x00\x00")
        self.assertEqual(self._kwargs["index"], 0x1003)
        self.assertEqual(self._kwargs["subindex"], 5)

        if self.use_async:
            await self.remote_node.sdo.adownload(0x1017, 0, b"\x03\x04")
        else:
            self.remote_node.sdo.download(0x1017, 0, b"\x03\x04")
        self.assertEqual(self._kwargs["index"], 0x1017)
        self.assertEqual(self._kwargs["subindex"], 0)
        self.assertEqual(self._kwargs["data"], b"\x03\x04")


class TestSDOSync(TestSDO):
    """ Run the test in non-async mode. """
    __test__ = True
    use_async = False


class TestSDOAsync(TestSDO):
    """ Run the test in async mode. """
    __test__ = True
    use_async = True


class TestPDO(unittest.IsolatedAsyncioTestCase):
    """
    Test PDO slave.
    """

    __test__ = False  # This is a base class, tests should not be run directly.
    use_async: bool

    def setUp(self):
        loop = None
        if self.use_async:
            loop = asyncio.get_event_loop()

        self.network1 = canopen.Network(loop=loop)
        self.network1.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.network1.connect("test", interface="virtual")
        with AllowBlocking():
            self.remote_node = self.network1.add_node(2, SAMPLE_EDS)

        self.network2 = canopen.Network(loop=loop)
        self.network2.NOTIFIER_SHUTDOWN_TIMEOUT = 0.0
        self.network2.connect("test", interface="virtual")
        self.local_node = self.network2.create_node(2, SAMPLE_EDS)

    def tearDown(self):
        self.network1.disconnect()
        self.network2.disconnect()

    async def test_read(self):
        # TODO: Do some more checks here. Currently it only tests that they
        # can be called without raising an error.
        if self.use_async:
            await self.remote_node.pdo.aread()
            await self.local_node.pdo.aread()
        else:
            self.remote_node.pdo.read()
            self.local_node.pdo.read()

    async def test_save(self):
        # TODO: Do some more checks here. Currently it only tests that they
        # can be called without raising an error.
        if self.use_async:
            await self.remote_node.pdo.asave()
            await self.local_node.pdo.asave()
        else:
            self.remote_node.pdo.save()
            self.local_node.pdo.save()


class TestPDOSync(TestPDO):
    """ Run the test in non-async mode. """
    __test__ = True
    use_async = False


class TestPDOAsync(TestPDO):
    """ Run the test in async mode. """
    __test__ = True
    use_async = True


if __name__ == "__main__":
    unittest.main()
