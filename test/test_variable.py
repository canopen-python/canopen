import unittest

from canopen import objectdictionary as od
from canopen.variable import Variable


class _StubVariable(Variable):
    """Minimal concrete Variable for testing read/write/bits."""

    def __init__(self, od_var):
        super().__init__(od_var)
        self._data = od_var.encode_raw(od_var.default)

    def get_data(self):
        return self._data

    def set_data(self, data):
        self._data = data


class TestVariable(unittest.TestCase):

    def test_read_invalid_format(self):
        var = od.ODVariable("Test UNSIGNED8", 0x1000)
        var.data_type = od.UNSIGNED8
        var.default = 0
        v = _StubVariable(var)
        with self.assertRaises(ValueError):
            v.read(fmt="invalid")

    def test_write_desc(self):
        var = od.ODVariable("Test UNSIGNED8", 0x1000)
        var.data_type = od.UNSIGNED8
        var.default = 0
        var.add_value_description(0, "Off")
        var.add_value_description(1, "On")
        v = _StubVariable(var)
        v.write("On", fmt="desc")
        self.assertEqual(v.raw, 1)
        self.assertEqual(v.desc, 1)
        with self.assertRaises(TypeError):
            v.write(b"", fmt="desc")

    def test_raw_with_string_value(self):
        var = od.ODVariable("Test VISIBLE_STRING", 0x1000)
        var.data_type = od.VISIBLE_STRING
        var.default = "hello"
        var.add_value_description(0, "Off")
        v = _StubVariable(var)
        self.assertEqual(v.raw, "hello")
        # String value must not be looked up in value_descriptions
        with self.assertRaises(TypeError):
            _ = v.desc

    def test_bits(self):
        var = od.ODVariable("Test UNSIGNED8", 0x1000)
        var.data_type = od.UNSIGNED8
        var.default = 0
        var.add_bit_definition("BIT 0", [0])
        var.add_bit_definition("BIT 2 and 3", [2, 3])
        v = _StubVariable(var)
        v.raw = 5
        bits = v.bits
        self.assertEqual(bits[0], 1)
        bits[0] = 0
        self.assertEqual(v.raw, 4)


if __name__ == "__main__":
    unittest.main()
