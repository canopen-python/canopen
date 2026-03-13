import unittest

import canopen
from canopen.objectdictionary.eds import signed_int_from_hex
from canopen.utils import pretty_index

from .util import SAMPLE_XDD


class TestXDD(unittest.TestCase):

    test_data = {
        "int8": [
            {"hex_str": "7F", "bit_length": 8, "expected": 127},
            {"hex_str": "80", "bit_length": 8, "expected": -128},
            {"hex_str": "FF", "bit_length": 8, "expected": -1},
            {"hex_str": "00", "bit_length": 8, "expected": 0},
            {"hex_str": "01", "bit_length": 8, "expected": 1}
        ],
        "int16": [
            {"hex_str": "7FFF", "bit_length": 16, "expected": 32767},
            {"hex_str": "8000", "bit_length": 16, "expected": -32768},
            {"hex_str": "FFFF", "bit_length": 16, "expected": -1},
            {"hex_str": "0000", "bit_length": 16, "expected": 0},
            {"hex_str": "0001", "bit_length": 16, "expected": 1}
        ],
        "int24": [
            {"hex_str": "7FFFFF", "bit_length": 24, "expected": 8388607},
            {"hex_str": "800000", "bit_length": 24, "expected": -8388608},
            {"hex_str": "FFFFFF", "bit_length": 24, "expected": -1},
            {"hex_str": "000000", "bit_length": 24, "expected": 0},
            {"hex_str": "000001", "bit_length": 24, "expected": 1}
        ],
        "int32": [
            {"hex_str": "7FFFFFFF", "bit_length": 32, "expected": 2147483647},
            {"hex_str": "80000000", "bit_length": 32, "expected": -2147483648},
            {"hex_str": "FFFFFFFF", "bit_length": 32, "expected": -1},
            {"hex_str": "00000000", "bit_length": 32, "expected": 0},
            {"hex_str": "00000001", "bit_length": 32, "expected": 1}
        ],
        "int64": [
            {"hex_str": "7FFFFFFFFFFFFFFF", "bit_length": 64, "expected": 9223372036854775807},
            {"hex_str": "8000000000000000", "bit_length": 64, "expected": -9223372036854775808},
            {"hex_str": "FFFFFFFFFFFFFFFF", "bit_length": 64, "expected": -1},
            {"hex_str": "0000000000000000", "bit_length": 64, "expected": 0},
            {"hex_str": "0000000000000001", "bit_length": 64, "expected": 1}
        ]
    }

    def setUp(self):
        self.od = canopen.import_od(SAMPLE_XDD, 2)

    def test_load_nonexisting_file(self):
        with self.assertRaises(IOError):
            canopen.import_od('/path/to/wrong_file.xdd')

    def test_load_unsupported_format(self):
        with self.assertRaisesRegex(ValueError, "'py'"):
            canopen.import_od(__file__)

    def test_load_file_object(self):
        with open(SAMPLE_XDD) as fp:
            od = canopen.import_od(fp)
        self.assertTrue(len(od) > 0)

    def test_load_explicit_nodeid(self):
        od = canopen.import_od(SAMPLE_XDD, node_id=3)
        self.assertEqual(od.node_id, 3)

    def test_variable(self):
        var = self.od['Producer heartbeat time']
        self.assertIsInstance(var, canopen.objectdictionary.ODVariable)
        self.assertEqual(var.index, 0x1017)
        self.assertEqual(var.subindex, 0)
        self.assertEqual(var.name, 'Producer heartbeat time')
        self.assertEqual(var.data_type, canopen.objectdictionary.UNSIGNED16)
        self.assertEqual(var.access_type, 'rw')
        self.assertEqual(var.default, 0)
        self.assertFalse(var.relative)

    def test_relative_variable(self):
        var = self.od['Receive PDO 0 Communication Parameter']['COB-ID use by RPDO 1']
        self.assertTrue(var.relative)
        self.assertEqual(var.default, 512 + self.od.node_id)

    def test_record(self):
        record = self.od['Identity object']
        self.assertIsInstance(record, canopen.objectdictionary.ODRecord)
        self.assertEqual(len(record), 4)
        self.assertEqual(record.index, 0x1018)
        self.assertEqual(record.name, 'Identity object')
        var = record['Vendor-ID']
        self.assertIsInstance(var, canopen.objectdictionary.ODVariable)
        self.assertEqual(var.name, 'Vendor-ID')
        self.assertEqual(var.index, 0x1018)
        self.assertEqual(var.subindex, 1)
        self.assertEqual(var.data_type, canopen.objectdictionary.UNSIGNED32)
        self.assertEqual(var.access_type, 'ro')

    def test_record_with_limits(self):
        int8 = self.od[0x3020]
        self.assertEqual(int8.min, 0)
        self.assertEqual(int8.max, 127)
        uint8 = self.od[0x3021]
        self.assertEqual(uint8.min, 2)
        self.assertEqual(uint8.max, 10)
        int32 = self.od[0x3030]
        self.assertEqual(int32.min, -2147483648)
        self.assertEqual(int32.max, -1)
        int64 = self.od[0x3040]
        self.assertEqual(int64.min, -10)
        self.assertEqual(int64.max, +10)

    def test_array_compact_subobj(self):
        array = self.od[0x1003]
        self.assertIsInstance(array, canopen.objectdictionary.ODArray)
        self.assertEqual(array.index, 0x1003)
        self.assertEqual(array.name, 'Pre-defined error field')
        var = array[5]
        self.assertIsInstance(var, canopen.objectdictionary.ODVariable)
        self.assertEqual(var.name, 'Pre-defined error field_5')
        self.assertEqual(var.index, 0x1003)
        self.assertEqual(var.subindex, 5)
        self.assertEqual(var.data_type, canopen.objectdictionary.UNSIGNED32)
        self.assertEqual(var.access_type, 'ro')

    def test_explicit_name_subobj(self):
        name = self.od[0x3004].name
        self.assertEqual(name, 'Sensor Status')
        name = self.od[0x3004][1].name
        self.assertEqual(name, 'Sensor Status 1')
        name = self.od[0x3004][3].name
        self.assertEqual(name, 'Sensor Status 3')
        value = self.od[0x3004][3].default
        self.assertEqual(value, 3)

    def test_parameter_name_with_percent(self):
        name = self.od[0x3003].name
        self.assertEqual(name, 'Valve % open')

    def test_compact_subobj_parameter_name_with_percent(self):
        name = self.od[0x3006].name
        self.assertEqual(name, 'Valve 1 % Open')

    def test_sub_index_w_capital_s(self):
        name = self.od[0x3010][0].name
        self.assertEqual(name, 'Temperature')

    def test_dummy_variable(self):
        var = self.od['Dummy0003']
        self.assertIsInstance(var, canopen.objectdictionary.ODVariable)
        self.assertEqual(var.index, 0x0003)
        self.assertEqual(var.subindex, 0)
        self.assertEqual(var.name, 'Dummy0003')
        self.assertEqual(var.data_type, canopen.objectdictionary.INTEGER16)
        self.assertEqual(var.access_type, 'const')
        self.assertEqual(len(var), 16)

    def test_dummy_variable_undefined(self):
        with self.assertRaises(KeyError):
            var_undef = self.od['Dummy0001']

    def test_signed_int_from_hex(self):
        for data_type, test_cases in self.test_data.items():
            for test_case in test_cases:
                with self.subTest(data_type=data_type, test_case=test_case):
                    result = signed_int_from_hex('0x' + test_case["hex_str"], test_case["bit_length"])
                    self.assertEqual(result, test_case["expected"])

if __name__ == "__main__":
    unittest.main()
