import unittest

import canopen

from .util import SAMPLE_EDS, tmp_file


class TestPDO(unittest.TestCase):
    def setUp(self):
        node = canopen.Node(1, SAMPLE_EDS)
        pdo = node.pdo.tx[1]
        pdo.add_variable('INTEGER16 value')  # 0x2001
        pdo.add_variable('UNSIGNED8 value', length=4)  # 0x2002
        pdo.add_variable('INTEGER8 value', length=4)  # 0x2003
        pdo.add_variable('INTEGER32 value')  # 0x2004
        pdo.add_variable('BOOLEAN value', length=1)  # 0x2005
        pdo.add_variable('BOOLEAN value 2', length=1)  # 0x2006

        # Write some values
        pdo['INTEGER16 value'].raw = -3
        pdo['UNSIGNED8 value'].raw = 0xf
        pdo['INTEGER8 value'].raw = -2
        pdo['INTEGER32 value'].raw = 0x01020304
        pdo['BOOLEAN value'].raw = False
        pdo['BOOLEAN value 2'].raw = True

        self.pdo = pdo
        self.node = node

    def test_pdo_map_bit_mapping(self):
        self.assertEqual(self.pdo.data, b'\xfd\xff\xef\x04\x03\x02\x01\x02')

    def test_pdo_map_getitem(self):
        pdo = self.pdo
        self.assertEqual(pdo['INTEGER16 value'].raw, -3)
        self.assertEqual(pdo['UNSIGNED8 value'].raw, 0xf)
        self.assertEqual(pdo['INTEGER8 value'].raw, -2)
        self.assertEqual(pdo['INTEGER32 value'].raw, 0x01020304)
        self.assertEqual(pdo['BOOLEAN value'].raw, False)
        self.assertEqual(pdo['BOOLEAN value 2'].raw, True)

    def test_pdo_getitem(self):
        node = self.node
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

    def test_pdo_save(self):
        self.node.tpdo.save()
        self.node.rpdo.save()

    def test_pdo_export(self):
        try:
            import canmatrix
        except ImportError:
            raise unittest.SkipTest("The PDO export API requires canmatrix")

        for pdo in "tpdo", "rpdo":
            with tmp_file(suffix=".csv") as tmp:
                fn = tmp.name
                with self.subTest(filename=fn, pdo=pdo):
                    getattr(self.node, pdo).export(fn)
                    with open(fn) as csv:
                        header = csv.readline()
                        self.assertIn("ID", header)
                        self.assertIn("Frame Name", header)


if __name__ == "__main__":
    unittest.main()
