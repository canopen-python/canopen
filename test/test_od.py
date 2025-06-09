import unittest

from canopen import objectdictionary as od


class TestDataConversions(unittest.TestCase):

    def test_boolean(self):
        var = od.ODVariable("Test BOOLEAN", 0x1000)
        var.data_type = od.BOOLEAN
        self.assertEqual(var.decode_raw(b"\x01"), True)
        self.assertEqual(var.decode_raw(b"\x00"), False)
        self.assertEqual(var.encode_raw(True), b"\x01")
        self.assertEqual(var.encode_raw(False), b"\x00")

    def test_unsigned8(self):
        var = od.ODVariable("Test UNSIGNED8", 0x1000)
        var.data_type = od.UNSIGNED8
        self.assertEqual(var.decode_raw(b"\xff"), 255)
        self.assertEqual(var.encode_raw(254), b"\xfe")

    def test_unsigned16(self):
        var = od.ODVariable("Test UNSIGNED16", 0x1000)
        var.data_type = od.UNSIGNED16
        self.assertEqual(var.decode_raw(b"\xfe\xff"), 65534)
        self.assertEqual(var.encode_raw(65534), b"\xfe\xff")

    def test_unsigned24(self):
        var = od.ODVariable("Test UNSIGNED24", 0x1000)
        var.data_type = od.UNSIGNED24
        self.assertEqual(var.decode_raw(b"\xfd\xfe\xff"), 16776957)
        self.assertEqual(var.encode_raw(16776957), b"\xfd\xfe\xff")

    def test_unsigned32(self):
        var = od.ODVariable("Test UNSIGNED32", 0x1000)
        var.data_type = od.UNSIGNED32
        self.assertEqual(var.decode_raw(b"\xfc\xfd\xfe\xff"), 4294901244)
        self.assertEqual(var.encode_raw(4294901244), b"\xfc\xfd\xfe\xff")

    def test_unsigned40(self):
        var = od.ODVariable("Test UNSIGNED40", 0x1000)
        var.data_type = od.UNSIGNED40
        self.assertEqual(var.decode_raw(b"\xfb\xfc\xfd\xfe\xff"), 0xfffefdfcfb)
        self.assertEqual(var.encode_raw(0xfffefdfcfb), b"\xfb\xfc\xfd\xfe\xff")

    def test_unsigned48(self):
        var = od.ODVariable("Test UNSIGNED48", 0x1000)
        var.data_type = od.UNSIGNED48
        self.assertEqual(var.decode_raw(b"\xfa\xfb\xfc\xfd\xfe\xff"), 0xfffefdfcfbfa)
        self.assertEqual(var.encode_raw(0xfffefdfcfbfa), b"\xfa\xfb\xfc\xfd\xfe\xff")

    def test_unsigned56(self):
        var = od.ODVariable("Test UNSIGNED56", 0x1000)
        var.data_type = od.UNSIGNED56
        self.assertEqual(var.decode_raw(b"\xf9\xfa\xfb\xfc\xfd\xfe\xff"), 0xfffefdfcfbfaf9)
        self.assertEqual(var.encode_raw(0xfffefdfcfbfaf9), b"\xf9\xfa\xfb\xfc\xfd\xfe\xff")

    def test_unsigned64(self):
        var = od.ODVariable("Test UNSIGNED64", 0x1000)
        var.data_type = od.UNSIGNED64
        self.assertEqual(var.decode_raw(b"\xf8\xf9\xfa\xfb\xfc\xfd\xfe\xff"), 0xfffefdfcfbfaf9f8)
        self.assertEqual(var.encode_raw(0xfffefdfcfbfaf9f8), b"\xf8\xf9\xfa\xfb\xfc\xfd\xfe\xff")

    def test_integer8(self):
        var = od.ODVariable("Test INTEGER8", 0x1000)
        var.data_type = od.INTEGER8
        self.assertEqual(var.decode_raw(b"\xff"), -1)
        self.assertEqual(var.decode_raw(b"\x7f"), 127)
        self.assertEqual(var.encode_raw(-2), b"\xfe")
        self.assertEqual(var.encode_raw(127), b"\x7f")

    def test_integer16(self):
        var = od.ODVariable("Test INTEGER16", 0x1000)
        var.data_type = od.INTEGER16
        self.assertEqual(var.decode_raw(b"\xfe\xff"), -2)
        self.assertEqual(var.decode_raw(b"\x01\x00"), 1)
        self.assertEqual(var.encode_raw(-2), b"\xfe\xff")
        self.assertEqual(var.encode_raw(1), b"\x01\x00")

    def test_integer24(self):
        var = od.ODVariable("Test INTEGER24", 0x1000)
        var.data_type = od.INTEGER24
        self.assertEqual(var.decode_raw(b"\xfe\xff\xff"), -2)
        self.assertEqual(var.decode_raw(b"\x01\x00\x00"), 1)
        self.assertEqual(var.encode_raw(-2), b"\xfe\xff\xff")
        self.assertEqual(var.encode_raw(1), b"\x01\x00\x00")

    def test_integer32(self):
        var = od.ODVariable("Test INTEGER32", 0x1000)
        var.data_type = od.INTEGER32
        self.assertEqual(var.decode_raw(b"\xfe\xff\xff\xff"), -2)
        self.assertEqual(var.decode_raw(b"\x01\x00\x00\x00"), 1)
        self.assertEqual(var.encode_raw(1), b"\x01\x00\x00\x00")
        self.assertEqual(var.encode_raw(-2), b"\xfe\xff\xff\xff")

    def test_integer40(self):
        var = od.ODVariable("Test INTEGER40", 0x1000)
        var.data_type = od.INTEGER40
        self.assertEqual(var.decode_raw(b"\xfe\xff\xff\xff\xff"), -2)
        self.assertEqual(var.decode_raw(b"\x01\x00\x00\x00\x00"), 1)
        self.assertEqual(var.encode_raw(-2), b"\xfe\xff\xff\xff\xff")
        self.assertEqual(var.encode_raw(1), b"\x01\x00\x00\x00\x00")

    def test_integer48(self):
        var = od.ODVariable("Test INTEGER48", 0x1000)
        var.data_type = od.INTEGER48
        self.assertEqual(var.decode_raw(b"\xfe\xff\xff\xff\xff\xff"), -2)
        self.assertEqual(var.decode_raw(b"\x01\x00\x00\x00\x00\x00"), 1)
        self.assertEqual(var.encode_raw(-2), b"\xfe\xff\xff\xff\xff\xff")
        self.assertEqual(var.encode_raw(1), b"\x01\x00\x00\x00\x00\x00")

    def test_integer56(self):
        var = od.ODVariable("Test INTEGER56", 0x1000)
        var.data_type = od.INTEGER56
        self.assertEqual(var.decode_raw(b"\xfe\xff\xff\xff\xff\xff\xff"), -2)
        self.assertEqual(var.decode_raw(b"\x01\x00\x00\x00\x00\x00\x00"), 1)
        self.assertEqual(var.encode_raw(-2), b"\xfe\xff\xff\xff\xff\xff\xff")
        self.assertEqual(var.encode_raw(1), b"\x01\x00\x00\x00\x00\x00\x00")

    def test_integer64(self):
        var = od.ODVariable("Test INTEGER64", 0x1000)
        var.data_type = od.INTEGER64
        self.assertEqual(var.decode_raw(b"\xfe\xff\xff\xff\xff\xff\xff\xff"), -2)
        self.assertEqual(var.decode_raw(b"\x01\x00\x00\x00\x00\x00\x00\x00"), 1)
        self.assertEqual(var.encode_raw(-2), b"\xfe\xff\xff\xff\xff\xff\xff\xff")
        self.assertEqual(var.encode_raw(1), b"\x01\x00\x00\x00\x00\x00\x00\x00")

    def test_real32(self):
        var = od.ODVariable("Test REAL32", 0x1000)
        var.data_type = od.REAL32
        # Select values that are exaclty representable in decimal notation
        self.assertEqual(var.decode_raw(b"\x00\x00\x00\x00"), 0.)
        self.assertEqual(var.decode_raw(b"\x00\x00\x60\x40"), 3.5)
        self.assertEqual(var.decode_raw(b"\x00\x20\x7a\xc4"), -1000.5)

    def test_real64(self):
        var = od.ODVariable("Test REAL64", 0x1000)
        var.data_type = od.REAL64
        # Select values that are exaclty representable in decimal notation
        self.assertEqual(var.decode_raw(b"\x00\x00\x00\x00\x00\x00\x00\x00"), 0.)
        self.assertEqual(var.decode_raw(b"\x00\x00\x00\x00\x00\x4a\x93\x40"), 1234.5)
        self.assertEqual(var.decode_raw(b"\x06\x81\x95\x43\x0b\x42\x8f\xc0"), -1000.2555)

    def test_visible_string(self):
        var = od.ODVariable("Test VISIBLE_STRING", 0x1000)
        var.data_type = od.VISIBLE_STRING
        self.assertEqual(var.decode_raw(b"abcdefg"), "abcdefg")
        self.assertEqual(var.decode_raw(b"zero terminated\x00"), "zero terminated")
        self.assertEqual(var.encode_raw("testing"), b"testing")

    def test_unicode_string(self):
        var = od.ODVariable("Test UNICODE_STRING", 0x1000)
        var.data_type = od.UNICODE_STRING
        self.assertEqual(var.decode_raw(b"\x61\x00\x62\x00\x63\x00"), "abc")
        self.assertEqual(var.decode_raw(b"\x61\x00\x62\x00\x63\x00\x00\x00"), "abc")  # Zero terminated
        self.assertEqual(var.encode_raw("abc"), b"\x61\x00\x62\x00\x63\x00")
        self.assertEqual(var.decode_raw(b"\x60\x3f\x7d\x59"), "\u3f60\u597d")  # Chinese "Nǐ hǎo", hello
        self.assertEqual(var.encode_raw("\u3f60\u597d"), b"\x60\x3f\x7d\x59")  # Chinese "Nǐ hǎo", hello

    def test_octet_string(self):
        var = od.ODVariable("Test OCTET_STRING", 0x1000)
        var.data_type = od.OCTET_STRING
        self.assertEqual(var.decode_raw(b"abcdefg"), b"abcdefg")
        self.assertEqual(var.decode_raw(b"zero terminated\x00"), b"zero terminated\x00")
        self.assertEqual(var.encode_raw(b"testing"), b"testing")

    def test_domain(self):
        var = od.ODVariable("Test DOMAIN", 0x1000)
        var.data_type = od.DOMAIN
        self.assertEqual(var.decode_raw(b"abcdefg"), b"abcdefg")
        self.assertEqual(var.decode_raw(b"zero terminated\x00"), b"zero terminated\x00")
        self.assertEqual(var.encode_raw(b"testing"), b"testing")


class TestAlternativeRepresentations(unittest.TestCase):

    def test_phys(self):
        var = od.ODVariable("Test INTEGER16", 0x1000)
        var.data_type = od.INTEGER16
        var.factor = 0.1

        self.assertAlmostEqual(var.decode_phys(128), 12.8)
        self.assertEqual(var.encode_phys(-0.1), -1)

    def test_desc(self):
        var = od.ODVariable("Test UNSIGNED8", 0x1000)
        var.data_type = od.UNSIGNED8
        var.add_value_description(0, "Value 0")
        var.add_value_description(1, "Value 1")
        var.add_value_description(3, "Value 3")

        self.assertEqual(var.decode_desc(0), "Value 0")
        self.assertEqual(var.decode_desc(3), "Value 3")
        self.assertEqual(var.encode_desc("Value 1"), 1)

    def test_bits(self):
        var = od.ODVariable("Test UNSIGNED8", 0x1000)
        var.data_type = od.UNSIGNED8
        var.add_bit_definition("BIT 0", [0])
        var.add_bit_definition("BIT 2 and 3", [2, 3])

        self.assertEqual(var.decode_bits(1, "BIT 0"), 1)
        self.assertEqual(var.decode_bits(1, [1]), 0)
        self.assertEqual(var.decode_bits(0xf, [0, 1, 2, 3]), 15)
        self.assertEqual(var.decode_bits(8, "BIT 2 and 3"), 2)
        self.assertEqual(var.encode_bits(0xf, [1], 0), 0xd)
        self.assertEqual(var.encode_bits(0, "BIT 0", 1), 1)


class TestObjectDictionary(unittest.TestCase):

    def test_add_variable(self):
        test_od = od.ObjectDictionary()
        var = od.ODVariable("Test Variable", 0x1000)
        test_od.add_object(var)
        self.assertEqual(test_od["Test Variable"], var)
        self.assertEqual(test_od[0x1000], var)

    def test_add_record(self):
        test_od = od.ObjectDictionary()
        record = od.ODRecord("Test Record", 0x1001)
        var = od.ODVariable("Test Subindex", 0x1001, 1)
        record.add_member(var)
        test_od.add_object(record)
        self.assertEqual(test_od["Test Record"], record)
        self.assertEqual(test_od[0x1001], record)
        self.assertEqual(test_od["Test Record"]["Test Subindex"], var)

    def test_add_array(self):
        test_od = od.ObjectDictionary()
        array = od.ODArray("Test Array", 0x1002)
        array.add_member(od.ODVariable("Last subindex", 0x1002, 0))
        test_od.add_object(array)
        self.assertEqual(test_od["Test Array"], array)
        self.assertEqual(test_od[0x1002], array)

    def test_get_item_dot(self):
        test_od = od.ObjectDictionary()
        array = od.ODArray("Test Array", 0x1000)
        last_subindex = od.ODVariable("Last subindex", 0x1000, 0)
        last_subindex.data_type = od.UNSIGNED8
        member1 = od.ODVariable("Test Variable", 0x1000, 1)
        member2 = od.ODVariable("Test Variable 2", 0x1000, 2)
        array.add_member(last_subindex)
        array.add_member(member1)
        array.add_member(member2)
        test_od.add_object(array)
        self.assertEqual(test_od["Test Array.Last subindex"], last_subindex)
        self.assertEqual(test_od["Test Array.Test Variable"], member1)
        self.assertEqual(test_od["Test Array.Test Variable 2"], member2)

class TestArray(unittest.TestCase):

    def test_subindexes(self):
        array = od.ODArray("Test Array", 0x1000)
        last_subindex = od.ODVariable("Last subindex", 0x1000, 0)
        last_subindex.data_type = od.UNSIGNED8
        array.add_member(last_subindex)
        array.add_member(od.ODVariable("Test Variable", 0x1000, 1))
        array.add_member(od.ODVariable("Test Variable 2", 0x1000, 2))
        self.assertEqual(array[0].name, "Last subindex")
        self.assertEqual(array[1].name, "Test Variable")
        self.assertEqual(array[2].name, "Test Variable 2")
        self.assertEqual(array[3].name, "Test Variable_3")


if __name__ == "__main__":
    unittest.main()
