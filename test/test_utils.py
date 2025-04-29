import unittest

from canopen.utils import pretty_index


class TestUtils(unittest.TestCase):

    def test_pretty_index(self):
        self.assertEqual(pretty_index(0x12AB), "0x12AB")
        self.assertEqual(pretty_index(0x12AB, 0xCD), "0x12AB:CD")
        self.assertEqual(pretty_index(0x12AB, ""), "0x12AB")
        self.assertEqual(pretty_index("test"), "'test'")
        self.assertEqual(pretty_index("test", 0xCD), "'test':CD")
        self.assertEqual(pretty_index(None), "")
        self.assertEqual(pretty_index(""), "")
        self.assertEqual(pretty_index("", ""), "")
        self.assertEqual(pretty_index(None, 0xAB), "0xAB")


if __name__ == "__main__":
    unittest.main()
