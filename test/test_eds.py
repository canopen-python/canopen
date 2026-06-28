import io
import os
import pathlib
import unittest
from configparser import RawConfigParser
from unittest.mock import MagicMock, patch

import canopen
from canopen.objectdictionary.eds import _signed_int_from_hex, build_variable
from canopen.utils import pretty_index

from .util import DATATYPES_EDS, SAMPLE_EDS, tmp_file


class TestEDS(unittest.TestCase):

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
        self.od = canopen.import_od(SAMPLE_EDS, 2)

    def test_load_nonexisting_file(self):
        with self.assertRaises(IOError):
            canopen.import_od('/path/to/wrong_file.eds')
        with self.assertRaises(IOError):
            canopen.import_od(pathlib.Path('/path/to/wrong_file.eds'))

    def test_load_unsupported_format(self):
        with self.assertRaisesRegex(ValueError, "'py'"):
            canopen.import_od(__file__)
        with self.assertRaisesRegex(ValueError, "''"):
            canopen.import_od('')
        with self.assertRaisesRegex(ValueError, "''"):
            canopen.import_od(object())
        with self.assertRaisesRegex(ValueError, "''"):
            filelike_object = io.StringIO()  # no .name attribute
            self.addCleanup(filelike_object.close)
            canopen.import_od(filelike_object)

    def test_load_file_object(self):
        with open(SAMPLE_EDS) as fp:
            od = canopen.import_od(fp)
        self.assertTrue(len(od) > 0)

    def test_load_implicit_nodeid(self):
        # sample.eds has a DeviceComissioning section with NodeID set to 0x10.
        od = canopen.import_od(SAMPLE_EDS)
        self.assertEqual(od.node_id, 16)

    def test_load_implicit_nodeid_fallback(self):
        # First, remove the NodeID option from DeviceComissioning.
        with open(SAMPLE_EDS) as f:
            lines = [L for L in f.readlines() if not L.startswith("NodeID=")]
        with io.StringIO("".join(lines)) as buf:
            buf.name = "mock.eds"
            od = canopen.import_od(buf)
            self.assertIsNone(od.node_id)

        # Next, try an EDS file without a DeviceComissioning section.
        od = canopen.import_od(DATATYPES_EDS)
        self.assertIsNone(od.node_id)

    def test_load_explicit_nodeid(self):
        od = canopen.import_od(SAMPLE_EDS, node_id=3)
        self.assertEqual(od.node_id, 3)

    def test_load_baudrate(self):
        od = canopen.import_od(SAMPLE_EDS)
        self.assertEqual(od.bitrate, 500_000)

    def test_load_baudrate_fallback(self):
        # Remove the Baudrate option.
        with open(SAMPLE_EDS) as f:
            lines = [L for L in f.readlines() if not L.startswith("Baudrate=")]
        with io.StringIO("".join(lines)) as buf:
            buf.name = "mock.eds"
            od = canopen.import_od(buf)
            self.assertIsNone(od.bitrate)

    def test_variable(self):
        var = self.od['Producer heartbeat time']
        self.assertIsInstance(var, canopen.objectdictionary.ODVariable)
        self.assertEqual(var.index, 0x1017)
        self.assertEqual(var.subindex, 0)
        self.assertEqual(var.name, 'Producer heartbeat time')
        self.assertEqual(var.data_type, canopen.objectdictionary.UNSIGNED16)
        self.assertEqual(var.access_type, 'rw')
        self.assertFalse(var.is_domain)
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
        self.assertFalse(var.is_domain)

    def test_record_with_limits(self):
        cases = [
            (0x3020, 0, 127),  # _          INTEGER8   hex limits
            (0x3021, 2, 10),  # _           UNSIGNED8  hex limits
            (0x3022, 100, 1000),  # _       UNSIGNED16 decimal limits
            (0x3023, -100, 100),  # _       INTEGER16  decimal limits
            (0x3030, -2147483648, -1),  # _ INTEGER32  hex limits
            (0x3031, -1, 0),  # _           INTEGER24  hex limits
            (0x3032, -1, 0),  # _           INTEGER40  hex limits
            (0x3033, -1, 0),  # _           INTEGER48  hex limits
            (0x3034, -1, 0),  # _           INTEGER56  hex limits
            (0x3040, -10, +10),  # _        INTEGER64  hex limits
        ]
        for index, expected_min, expected_max in cases:
            with self.subTest(index=f"0x{index:04X}"):
                var = self.od[index]
                self.assertEqual(var.min, expected_min)
                self.assertEqual(var.max, expected_max)

    def test_signed_int_from_hex(self):
        for data_type, test_cases in self.test_data.items():
            for test_case in test_cases:
                with self.subTest(data_type=data_type, test_case=test_case):
                    result = _signed_int_from_hex('0x' + test_case["hex_str"], test_case["bit_length"])
                    self.assertEqual(result, test_case["expected"])

    def test_signed_int_from_hex_accepts_decimal(self):
        # Negative decimal values are valid EDS literals (CiA 306 allows both formats).
        self.assertEqual(_signed_int_from_hex("-1", 8), -1)
        self.assertEqual(_signed_int_from_hex("-128", 8), -128)
        self.assertEqual(_signed_int_from_hex("-2147483648", 32), -2147483648)

    def test_signed_int_from_hex_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            _signed_int_from_hex("0xFFFF", 8)   # 16-bit value into 8-bit field
        with self.assertRaises(ValueError):
            _signed_int_from_hex("-129", 8)     # below minimum for 8-bit signed

    def test_build_variable_range_warnings(self):
        eds = RawConfigParser()
        cases = [
            ("2003", "LowLimit", str(-0xFFFF)),  # INTEGER16 < signed min
            ("2003", "HighLimit", "0x10000"),  # INTEGER16 > unsigned max
            ("2001", "DefaultValue", "SOMETHING"),  # BOOLEAN non-numeric
            ("2003", "DefaultValue", "SOMETHING"),  # INTEGER16 non-numeric
            ("2006", "ParameterValue", ""),  # UNSIGNED16 empty
        ]
        for index, option, value in cases:
            with self.subTest(index=index, option=option, value=value):
                # Fresh version for mutating temporarily
                eds.clear()
                eds.read(DATATYPES_EDS)
                eds[index][option] = value
                with self.assertLogs(level="WARN") as cm:
                    build_variable(eds, index, node_id=42, object_type=7, index=int(index, 16))
                self.assertRegex(cm.output[0], option)

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
        self.assertFalse(var.is_domain)

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
        self.assertFalse(var.is_domain)
        self.assertEqual(len(var), 16)

    def test_dummy_variable_undefined(self):
        with self.assertRaises(KeyError):
            var_undef = self.od['Dummy0001']

    def test_reading_factor(self):
        var = self.od['EDS file extensions']['FactorAndDescription']
        self.assertEqual(var.factor, 0.1)
        self.assertEqual(var.description, "This is the a test description")
        self.assertEqual(var.unit,'mV')
        var2 = self.od['EDS file extensions']['Error Factor and No Description']
        self.assertEqual(var2.description, '')
        self.assertEqual(var2.factor, 1)
        self.assertEqual(var2.unit, '')

    def test_read_domain_object(self):
        var = self.od[0x3063]
        self.assertIsInstance(var, canopen.objectdictionary.ODVariable)
        self.assertEqual(var.index, 0x3063)
        self.assertEqual(var.subindex, 0)
        self.assertEqual(var.name, 'DOMAIN object')
        self.assertEqual(var.data_type, canopen.objectdictionary.UNSIGNED32)
        self.assertEqual(var.access_type, 'rw')
        self.assertTrue(var.is_domain)

    def test_read_domain_subobject(self):
        record = self.od[0x3064]
        var = record[1]
        self.assertIsInstance(var, canopen.objectdictionary.ODVariable)
        self.assertEqual(var.index, 0x3064)
        self.assertEqual(var.subindex, 1)
        self.assertEqual(var.name, 'DOMAIN sub-object')
        self.assertEqual(var.data_type, canopen.objectdictionary.UNSIGNED32)
        self.assertEqual(var.access_type, 'rw')
        self.assertTrue(var.is_domain)

    def test_roundtrip_domain_objects(self):
        # ObjectType==DOMAIN survive an EDS export/import round-trip
        with io.StringIO() as dest:
            canopen.export_od(self.od, dest, 'eds')
            dest.name = 'mock.eds'
            dest.seek(0)
            od2 = canopen.import_od(dest)
        self.assertFalse(od2['Producer heartbeat time'].is_domain)
        self.assertFalse(od2['Identity object']['Vendor-ID'].is_domain)
        self.assertTrue(od2[0x3063].is_domain)
        self.assertTrue(od2[0x3064][1].is_domain)

    def test_export_without_raw_default_values(self):
        od = canopen.import_od(DATATYPES_EDS)
        # Make sure the values are not cached in raw form
        for var in od.values():
            try:
                delattr(var, 'default_raw')
            except AttributeError:
                pass
        with io.StringIO() as dest:
            canopen.export_od(od, dest, 'eds')

    def test_reading_custom_options(self):
        """Custom options (unknown EDS keys) are collected in custom_options dict."""
        var = self.od[0x3061]
        self.assertIsInstance(var, canopen.objectdictionary.ODVariable)
        self.assertEqual(var.custom_options, {'Category': 'Motor', 'Offset': '100'})

    def test_custom_options_standard_keys_excluded(self):
        """Standard CiA 306 keys must NOT appear in custom_options."""
        var = self.od[0x3061]
        for key in ('ParameterName', 'ObjectType', 'DataType', 'AccessType', 'PDOMapping'):
            self.assertNotIn(key, var.custom_options,
                             f"Standard key {key!r} must not be in custom_options")

    def test_custom_options_empty_for_standard_object(self):
        """Objects without extra keys must have an empty custom_options dict."""
        var = self.od['Producer heartbeat time']
        self.assertEqual(var.custom_options, {})

    def test_custom_options_record(self):
        """custom_options is read for ODRecord container objects too."""
        record = self.od[0x3062]
        self.assertIsInstance(record, canopen.objectdictionary.ODRecord)
        self.assertEqual(record.custom_options, {'RecordTag': 'vendor_specific'})
        # sub-entries without extra keys have empty custom_options
        self.assertEqual(record[1].custom_options, {})

    def test_roundtrip_custom_options(self):
        """custom_options survive an EDS export/import round-trip."""
        import io
        with io.StringIO() as dest:
            canopen.export_od(self.od, dest, 'eds')
            dest.name = 'mock.eds'
            dest.seek(0)
            od2 = canopen.import_od(dest)
        self.assertEqual(od2[0x3061].custom_options, {'Category': 'Motor', 'Offset': '100'})
        self.assertEqual(od2[0x3062].custom_options, {'RecordTag': 'vendor_specific'})

    def test_roundtrip_custom_options_not_duplicated_as_standard(self):
        """After round-trip the re-imported object must not contain standard keys."""
        import io
        with io.StringIO() as dest:
            canopen.export_od(self.od, dest, 'eds')
            dest.name = 'mock.eds'
            dest.seek(0)
            od2 = canopen.import_od(dest)
        for key in ('ParameterName', 'ObjectType', 'DataType', 'AccessType', 'PDOMapping'):
            self.assertNotIn(key, od2[0x3061].custom_options)

    def test_comments(self):
        self.assertEqual(self.od.comments,
                         """
|-------------|
| Don't panic |
|-------------|
""".strip())

    def test_export_eds_to_file(self):
        for suffix in ".eds", ".dcf":
            for implicit in True, False:
                with tmp_file(suffix=suffix) as tmp:
                    dest = tmp.name
                    doctype = None if implicit else suffix[1:]
                    with self.subTest(dest=dest, doctype=doctype):
                        canopen.export_od(self.od, dest, doctype)
                        self.verify_od(dest, doctype)

    def test_export_eds_to_file_unknown_extension(self):
        for suffix in ".txt", "":
            with tmp_file(suffix=suffix) as tmp:
                dest = tmp.name
                with self.subTest(dest=dest, doctype=None):
                    canopen.export_od(self.od, dest)

                    # The import_od() API has some shortcomings compared to the
                    # export_od() API, namely that it does not take a doctype
                    # parameter. This means it has to be able to deduce the
                    # doctype from its 'source' parameter. In this case, this
                    # is not possible, since we're using an unknown extension,
                    # so we have to do a couple of tricks in order to make this
                    # work.
                    with open(dest, "r") as source:
                        data = source.read()
                    with io.StringIO() as buf:
                        buf.write(data)
                        buf.seek(io.SEEK_SET)
                        buf.name = "mock.eds"
                        self.verify_od(buf, "eds")

    def test_export_eds_auto_close(self):
        fd = io.StringIO()
        self.addCleanup(fd.close)
        canopen.export_od(self.od, fd)
        # File object already passed in must NOT be closed
        self.assertIs(fd.closed, False)
        for path in ("mock.eds", pathlib.Path("mock.eds")):
            with self.subTest(path=path):
                fd = io.StringIO()
                with patch("canopen.objectdictionary.open", return_value=fd):
                    canopen.export_od(self.od, path)
                # File object opened at path must be closed before return
                self.assertIs(fd.closed, True)

    def test_export_eds_auto_close_exception(self):
        buf = io.StringIO()
        self.addCleanup(buf.close)
        fd = MagicMock(wraps=buf)
        fd.write.side_effect = IOError("Simulated write failure")
        with (
            patch("canopen.objectdictionary.open", return_value=fd),
            self.assertRaises(IOError),
        ):
            canopen.export_od(self.od, "mock.eds")
        # File object opened at path must be closed on inner exception
        self.assertIs(buf.closed, True)

    def test_export_eds_unknown_doctype(self):
        filelike_object = io.StringIO()
        self.addCleanup(filelike_object.close)
        for dest in "filename", None, filelike_object:
            with self.subTest(dest=dest):
                with self.assertRaisesRegex(ValueError, "'unknown'"):
                    canopen.export_od(self.od, dest, doc_type="unknown")
                # Make sure no files are created is a filename is supplied.
                if isinstance(dest, str):
                    with self.assertRaises(FileNotFoundError):
                        os.stat(dest)

    def test_export_eds_to_filelike_object(self):
        for doctype in "eds", "dcf":
            with io.StringIO() as dest:
                with self.subTest(dest=dest, doctype=doctype):
                    canopen.export_od(self.od, dest, doctype)

                    # The import_od() API assumes the file-like object has a
                    # well-behaved 'name' member.
                    dest.name = f"mock.{doctype}"
                    dest.seek(io.SEEK_SET)
                    self.verify_od(dest, doctype)

    def test_export_eds_to_stdout(self):
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()) as f:
            ret = canopen.export_od(self.od, None, "eds")
        self.assertIsNone(ret)

        dump = f.getvalue()
        with io.StringIO(dump) as buf:
            # The import_od() API assumes the TextIO object has a well-behaved
            # 'name' member.
            buf.name = "mock.eds"
            self.verify_od(buf, "eds")

    def verify_od(self, source, doctype):
        exported_od = canopen.import_od(source)

        for index in exported_od:
            self.assertIn(exported_od[index].name, self.od)
            self.assertIn(index, self.od)

        for index in self.od:
            if index < 0x0008:
                # ignore dummies
                continue
            self.assertIn(self.od[index].name, exported_od)
            self.assertIn(index, exported_od)

            actual_object = exported_od[index]
            expected_object = self.od[index]
            self.assertEqual(type(actual_object), type(expected_object))
            self.assertEqual(actual_object.name, expected_object.name)

            if isinstance(actual_object, canopen.objectdictionary.ODVariable):
                expected_vars = [expected_object]
                actual_vars = [actual_object]
            else:
                expected_vars = [expected_object[idx] for idx in expected_object]
                actual_vars = [actual_object[idx] for idx in actual_object]

            for prop in [
                "allowed_baudrates",
                "vendor_name",
                "vendor_number",
                "product_name",
                "product_number",
                "revision_number",
                "order_code",
                "simple_boot_up_master",
                "simple_boot_up_slave",
                "granularity",
                "dynamic_channels_supported",
                "group_messaging",
                "nr_of_RXPDO",
                "nr_of_TXPDO",
                "LSS_supported",
            ]:
                self.assertEqual(getattr(self.od.device_information, prop),
                                 getattr(exported_od.device_information, prop),
                                 f"prop {prop!r} mismatch on DeviceInfo")

            for evar, avar in zip(expected_vars, actual_vars):
                self.assertEqual(getattr(avar, "data_type", None), getattr(evar, "data_type", None),
                                 f" mismatch on {pretty_index(evar.index, evar.subindex)}")
                self.assertEqual(getattr(avar, "default_raw", None), getattr(evar, "default_raw", None),
                                 f" mismatch on {pretty_index(evar.index, evar.subindex)}")
                self.assertEqual(getattr(avar, "min", None), getattr(evar, "min", None),
                                 f" mismatch on {pretty_index(evar.index, evar.subindex)}")
                self.assertEqual(getattr(avar, "max", None), getattr(evar, "max", None),
                                 f" mismatch on {pretty_index(evar.index, evar.subindex)}")
                if doctype == "dcf":
                    self.assertEqual(getattr(avar, "value", None), getattr(evar, "value", None),
                                     f" mismatch on {pretty_index(evar.index, evar.subindex)}")

                self.assertEqual(self.od.comments, exported_od.comments)


if __name__ == "__main__":
    unittest.main()
