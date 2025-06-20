import unittest

import canopen

from .util import SAMPLE_EDS, tmp_file


class TestPDO(unittest.IsolatedAsyncioTestCase):

    __test__ = False  # This is a base class, tests should not be run directly.
    use_async: bool

    def setUp(self):
        node = canopen.Node(1, SAMPLE_EDS)
        pdo = node.pdo.tx[1]
        pdo.add_variable('INTEGER16 value')  # 0x2001
        pdo.add_variable('UNSIGNED8 value', length=4)  # 0x2002
        pdo.add_variable('INTEGER8 value', length=4)  # 0x2003
        pdo.add_variable('INTEGER32 value')  # 0x2004
        pdo.add_variable('BOOLEAN value', length=1)  # 0x2005
        pdo.add_variable('BOOLEAN value 2', length=1)  # 0x2006

        self.pdo = pdo
        self.node = node

    async def set_values(self):
        """Initialize the PDO with some valuues.

        Do this in a separate method in order to be abel to use the
        async and sync versions of the tests.
        """
        node = self.node
        pdo = node.pdo.tx[1]
        if self.use_async:
            # Write some values (different from the synchronous values)
            await pdo['INTEGER16 value'].aset_raw(12)
            await pdo['UNSIGNED8 value'].aset_raw(0xe)
            await pdo['INTEGER8 value'].aset_raw(-4)
            await pdo['INTEGER32 value'].aset_raw(0x56789abc)
            await pdo['BOOLEAN value'].aset_raw(True)
            await pdo['BOOLEAN value 2'].aset_raw(False)
        else:
            # Write some values
            pdo['INTEGER16 value'].raw = -3
            pdo['UNSIGNED8 value'].raw = 0xf
            pdo['INTEGER8 value'].raw = -2
            pdo['INTEGER32 value'].raw = 0x01020304
            pdo['BOOLEAN value'].raw = False
            pdo['BOOLEAN value 2'].raw = True

    async def test_pdo_map_bit_mapping(self):
        await self.set_values()
        if self.use_async:
            self.assertEqual(self.pdo.data, b'\x0c\x00\xce\xbc\x9a\x78\x56\x01')
        else:
            self.assertEqual(self.pdo.data, b'\xfd\xff\xef\x04\x03\x02\x01\x02')

    async def test_pdo_map_getitem(self):
        await self.set_values()
        pdo = self.pdo
        if self.use_async:
            self.assertEqual(await pdo['INTEGER16 value'].aget_raw(), 12)
            self.assertEqual(await pdo['UNSIGNED8 value'].aget_raw(), 0xe)
            self.assertEqual(await pdo['INTEGER8 value'].aget_raw(), -4)
            self.assertEqual(await pdo['INTEGER32 value'].aget_raw(), 0x56789abc)
            self.assertEqual(await pdo['BOOLEAN value'].aget_raw(), True)
            self.assertEqual(await pdo['BOOLEAN value 2'].aget_raw(), False)
        else:
            self.assertEqual(pdo['INTEGER16 value'].raw, -3)
            self.assertEqual(pdo['UNSIGNED8 value'].raw, 0xf)
            self.assertEqual(pdo['INTEGER8 value'].raw, -2)
            self.assertEqual(pdo['INTEGER32 value'].raw, 0x01020304)
            self.assertEqual(pdo['BOOLEAN value'].raw, False)
            self.assertEqual(pdo['BOOLEAN value 2'].raw, True)

    async def test_pdo_getitem(self):
        await self.set_values()
        node = self.node
        if self.use_async:
            self.assertEqual(await node.tpdo[1]['INTEGER16 value'].aget_raw(), 12)
            self.assertEqual(await node.tpdo[1]['UNSIGNED8 value'].aget_raw(), 0xe)
            self.assertEqual(await node.tpdo[1]['INTEGER8 value'].aget_raw(), -4)
            self.assertEqual(await node.tpdo[1]['INTEGER32 value'].aget_raw(), 0x56789abc)
            self.assertEqual(await node.tpdo['INTEGER32 value'].aget_raw(), 0x56789abc)
            self.assertEqual(await node.tpdo[1]['BOOLEAN value'].aget_raw(), True)
            self.assertEqual(await node.tpdo[1]['BOOLEAN value 2'].aget_raw(), False)

            # Test different types of access
            self.assertEqual(await node.pdo[0x1600]['INTEGER16 value'].aget_raw(), 12)
            self.assertEqual(await node.pdo['INTEGER16 value'].aget_raw(), 12)
            self.assertEqual(await node.pdo.tx[1]['INTEGER16 value'].aget_raw(), 12)
            self.assertEqual(await node.pdo[0x2001].aget_raw(), 12)
            self.assertEqual(await node.tpdo[0x2001].aget_raw(), 12)
            self.assertEqual(await node.pdo[0x2002].aget_raw(), 0xe)
            self.assertEqual(await node.pdo['0x2002'].aget_raw(), 0xe)
            self.assertEqual(await node.tpdo[0x2002].aget_raw(), 0xe)
            self.assertEqual(await node.pdo[0x1600][0x2002].aget_raw(), 0xe)
        else:
            self.assertEqual(node.tpdo[1]['INTEGER16 value'].raw, -3)
            self.assertEqual(node.tpdo[1]['UNSIGNED8 value'].raw, 0xf)
            self.assertEqual(node.tpdo[1]['INTEGER8 value'].raw, -2)
            self.assertEqual(node.tpdo[1]['INTEGER32 value'].raw, 0x01020304)
            self.assertEqual(node.tpdo['INTEGER32 value'].raw, 0x01020304)
            self.assertEqual(node.tpdo[1]['BOOLEAN value'].raw, False)
            self.assertEqual(node.tpdo[1]['BOOLEAN value 2'].raw, True)

            # Test different types of access
            self.assertEqual(node.pdo[0x1600]['INTEGER16 value'].raw, -3)
            self.assertEqual(node.pdo['INTEGER16 value'].raw, -3)
            self.assertEqual(node.pdo.tx[1]['INTEGER16 value'].raw, -3)
            self.assertEqual(node.pdo[0x2001].raw, -3)
            self.assertEqual(node.tpdo[0x2001].raw, -3)
            self.assertEqual(node.pdo[0x2002].raw, 0xf)
            self.assertEqual(node.pdo['0x2002'].raw, 0xf)
            self.assertEqual(node.tpdo[0x2002].raw, 0xf)
            self.assertEqual(node.pdo[0x1600][0x2002].raw, 0xf)

    async def test_pdo_save(self):
        await self.set_values()
        if self.use_async:
            await self.node.tpdo.asave()
            await self.node.rpdo.asave()
        else:
            self.node.tpdo.save()
            self.node.rpdo.save()

    async def test_pdo_export(self):
        try:
            import canmatrix
        except ImportError:
            self.skipTest("The PDO export API requires canmatrix")

        for pdo in "tpdo", "rpdo":
            with tmp_file(suffix=".csv") as tmp:
                fn = tmp.name
                with self.subTest(filename=fn, pdo=pdo):
                    getattr(self.node, pdo).export(fn)
                    with open(fn) as csv:
                        header = csv.readline()
                        self.assertIn("ID", header)
                        self.assertIn("Frame Name", header)


class TestPDOSync(TestPDO):
    """ Test the functions in synchronous mode. """
    __test__ = True
    use_async = False


class TestPDOAsync(TestPDO):
    """ Test the functions in asynchronous mode. """
    __test__ = True
    use_async = True


if __name__ == "__main__":
    unittest.main()
