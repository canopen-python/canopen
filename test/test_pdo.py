import unittest

import canopen

from .util import SAMPLE_EDS, tmp_file


class TestPDO(unittest.TestCase):
    def setUp(self):
        node = canopen.LocalNode(1, SAMPLE_EDS)
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
        by_mapping_record = node.pdo[0x1A00]
        self.assertIsInstance(by_mapping_record, canopen.pdo.PdoMap)
        self.assertEqual(by_mapping_record['INTEGER16 value'].raw, -3)
        self.assertIs(node.tpdo[0x1A00], by_mapping_record)
        self.assertIs(node.tpdo[0x1800], by_mapping_record)
        self.assertIs(node.pdo[0x1800], by_mapping_record)
        by_object_name = node.pdo['INTEGER16 value']
        self.assertIsInstance(by_object_name, canopen.pdo.PdoVariable)
        self.assertIs(by_object_name.od, node.object_dictionary['INTEGER16 value'])
        self.assertEqual(by_object_name.raw, -3)
        by_pdo_index = node.pdo.tx[1]
        self.assertIs(by_pdo_index, by_mapping_record)
        by_object_index = node.pdo[0x2001]
        self.assertIsInstance(by_object_index, canopen.pdo.PdoVariable)
        self.assertIs(by_object_index, by_object_name)
        by_object_index_tpdo = node.tpdo[0x2001]
        self.assertIs(by_object_index_tpdo, by_object_name)
        by_object_index = node.pdo[0x2002]
        self.assertEqual(by_object_index.raw, 0xf)
        self.assertIs(node.pdo['0x2002'], by_object_index)
        self.assertIs(node.tpdo[0x2002], by_object_index)
        self.assertIs(node.pdo[0x1A00][0x2002], by_object_index)

        self.assertRaises(KeyError, lambda: node.pdo[0])
        self.assertRaises(KeyError, lambda: node.tpdo[0])
        self.assertRaises(KeyError, lambda: node.pdo['DOES NOT EXIST'])
        self.assertRaises(KeyError, lambda: node.pdo[0x1BFF])
        self.assertRaises(KeyError, lambda: node.tpdo[0x1BFF])

    def test_pdo_maps_iterate(self):
        node = self.node
        self.assertEqual(len(node.pdo), sum(1 for _ in node.pdo))
        self.assertEqual(len(node.tpdo), sum(1 for _ in node.tpdo))
        self.assertEqual(len(node.rpdo), sum(1 for _ in node.rpdo))
        self.assertEqual(len(node.rpdo) + len(node.tpdo), len(node.pdo))

        pdo = node.tpdo[1]
        self.assertEqual(len(pdo), sum(1 for _ in pdo))

    def test_pdo_save(self):
        self.node.tpdo.save()
        self.node.rpdo.save()

    def test_pdo_save_skip_readonly(self):
        """Expect no exception when a record entry is not writable."""
        # Saving only happens with a defined COB ID and for specified parameters
        self.node.tpdo[1].cob_id = self.node.tpdo[1].predefined_cob_id
        self.node.tpdo[1].trans_type = 1
        self.node.tpdo[1].map_array[1].od.access_type = "r"
        self.node.tpdo[1].save()

        self.node.tpdo[2].cob_id = self.node.tpdo[2].predefined_cob_id
        self.node.tpdo[2].trans_type = 1
        self.node.tpdo[2].com_record[2].od.access_type = "r"
        self.node.tpdo[2].save()

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
