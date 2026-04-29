import unittest
from unittest.mock import MagicMock

from canopen.objectdictionary import ODVariable, ObjectDictionary
from canopen.objectdictionary.datatypes import INTEGER8, UNSIGNED16, UNSIGNED32
from canopen.profiles.p402 import BaseNode402, Homing, OperationMode, State402


def _make_od():
    """Create a minimal OD with DS402 objects for testing."""
    od = ObjectDictionary()
    # Controlword
    var = ODVariable("Controlword", 0x6040)
    var.data_type = UNSIGNED16
    var.access_type = "rw"
    od.add_object(var)
    # Statusword
    var = ODVariable("Statusword", 0x6041)
    var.data_type = UNSIGNED16
    var.access_type = "ro"
    od.add_object(var)
    # Modes of operation
    var = ODVariable("Modes of operation", 0x6060)
    var.data_type = INTEGER8
    var.access_type = "rw"
    od.add_object(var)
    # Modes of operation display
    var = ODVariable("Modes of operation display", 0x6061)
    var.data_type = INTEGER8
    var.access_type = "ro"
    od.add_object(var)
    # Supported drive modes
    var = ODVariable("Supported drive modes", 0x6502)
    var.data_type = UNSIGNED32
    var.access_type = "ro"
    od.add_object(var)
    return od


class TestState402(unittest.TestCase):
    """Tests for the State402 static helper and its lookup tables."""

    def test_sw_mask_all_states_defined(self):
        expected = {
            'NOT READY TO SWITCH ON',
            'SWITCH ON DISABLED',
            'READY TO SWITCH ON',
            'SWITCHED ON',
            'OPERATION ENABLED',
            'FAULT',
            'FAULT REACTION ACTIVE',
            'QUICK STOP ACTIVE',
        }
        self.assertEqual(set(State402.SW_MASK.keys()), expected)

    def test_sw_mask_values_are_unique(self):
        """Each state must produce a unique (mask, value) pair."""
        pairs = list(State402.SW_MASK.values())
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_cw_code_commands_round_trip(self):
        """CW_CODE_COMMANDS and CW_COMMANDS_CODE should be inverses."""
        for code, name in State402.CW_CODE_COMMANDS.items():
            self.assertEqual(State402.CW_COMMANDS_CODE[name], code)
        for name, code in State402.CW_COMMANDS_CODE.items():
            self.assertEqual(State402.CW_CODE_COMMANDS[code], name)

    def test_next_state_indirect_from_all_known_states(self):
        """Every known state should have an indirect next state."""
        for state in State402.SW_MASK:
            result = State402.next_state_indirect(state)
            # All states except OPERATION ENABLED should have a path
            if state != 'OPERATION ENABLED':
                self.assertIsNotNone(result, f"No indirect path from {state}")
                self.assertIn(result, State402.SW_MASK,
                              f"Indirect state {result} is not a known state")

    def test_next_state_indirect_specific_paths(self):
        self.assertEqual(
            State402.next_state_indirect('SWITCH ON DISABLED'),
            'READY TO SWITCH ON')
        self.assertEqual(
            State402.next_state_indirect('READY TO SWITCH ON'),
            'SWITCHED ON')
        self.assertEqual(
            State402.next_state_indirect('SWITCHED ON'),
            'OPERATION ENABLED')
        self.assertEqual(
            State402.next_state_indirect('FAULT'),
            'SWITCH ON DISABLED')
        self.assertEqual(
            State402.next_state_indirect('FAULT REACTION ACTIVE'),
            'FAULT')
        self.assertEqual(
            State402.next_state_indirect('QUICK STOP ACTIVE'),
            'SWITCH ON DISABLED')

    def test_next_state_indirect_unknown_state(self):
        self.assertIsNone(State402.next_state_indirect('NONEXISTENT'))

    def test_transition_table_keys_are_valid_states(self):
        known = set(State402.SW_MASK.keys()) | {'START', 'DISABLE VOLTAGE'}
        for from_state, to_state in State402.TRANSITIONTABLE:
            self.assertIn(from_state, known,
                          f"Unknown from-state: {from_state}")
            self.assertIn(to_state, known,
                          f"Unknown to-state: {to_state}")


class TestBaseNode402State(unittest.TestCase):
    """Test state property reading from simulated statusword."""

    def setUp(self):
        self.node = BaseNode402(1, _make_od())

    def test_state_from_statusword(self):
        """Verify all state decoding from statusword bits."""
        test_cases = [
            (0x0000, 'NOT READY TO SWITCH ON'),
            (0x0040, 'SWITCH ON DISABLED'),
            (0x0021, 'READY TO SWITCH ON'),
            (0x0023, 'SWITCHED ON'),
            (0x0027, 'OPERATION ENABLED'),
            (0x0008, 'FAULT'),
            (0x000F, 'FAULT REACTION ACTIVE'),
            (0x0007, 'QUICK STOP ACTIVE'),
        ]
        for sw, expected_state in test_cases:
            with self.subTest(statusword=hex(sw)):
                self.node.tpdo_values[0x6041] = sw
                self.assertEqual(self.node.state, expected_state)

    def test_state_unknown_statusword(self):
        # A statusword that doesn't match any known mask
        self.node.tpdo_values[0x6041] = 0xFFFF
        self.assertEqual(self.node.state, 'UNKNOWN')

    def test_is_faulted_true(self):
        self.node.tpdo_values[0x6041] = 0x0008  # FAULT
        self.assertTrue(self.node.is_faulted())

    def test_is_faulted_false(self):
        self.node.tpdo_values[0x6041] = 0x0040  # SWITCH ON DISABLED
        self.assertFalse(self.node.is_faulted())

    def test_controlword_read_raises(self):
        with self.assertRaises(RuntimeError):
            _ = self.node.controlword


class TestBaseNode402NextState(unittest.TestCase):
    """Test _next_state logic for state transitions."""

    def setUp(self):
        self.node = BaseNode402(1, _make_od())

    def _set_state(self, state_name):
        _, bits = State402.SW_MASK[state_name]
        self.node.tpdo_values[0x6041] = bits

    def test_direct_transition(self):
        """When a direct transition exists, _next_state returns the target."""
        self._set_state('SWITCH ON DISABLED')
        self.assertEqual(
            self.node._next_state('READY TO SWITCH ON'),
            'READY TO SWITCH ON')

    def test_indirect_transition(self):
        """When no direct path, _next_state returns the indirect next step."""
        self._set_state('SWITCH ON DISABLED')
        # No direct path to OPERATION ENABLED
        result = self.node._next_state('OPERATION ENABLED')
        self.assertEqual(result, 'READY TO SWITCH ON')

    def test_illegal_target_fault(self):
        self._set_state('SWITCH ON DISABLED')
        with self.assertRaises(ValueError):
            self.node._next_state('FAULT')

    def test_illegal_target_not_ready(self):
        self._set_state('SWITCH ON DISABLED')
        with self.assertRaises(ValueError):
            self.node._next_state('NOT READY TO SWITCH ON')

    def test_illegal_target_fault_reaction(self):
        self._set_state('SWITCH ON DISABLED')
        with self.assertRaises(ValueError):
            self.node._next_state('FAULT REACTION ACTIVE')

    def test_full_path_to_operation_enabled(self):
        """Walk the state machine from SWITCH ON DISABLED to OPERATION ENABLED."""
        path = []
        self._set_state('SWITCH ON DISABLED')
        target = 'OPERATION ENABLED'
        current = self.node.state
        while current != target:
            next_s = self.node._next_state(target)
            path.append(next_s)
            self._set_state(next_s)
            current = self.node.state
        self.assertEqual(path, [
            'READY TO SWITCH ON',
            'SWITCHED ON',
            'OPERATION ENABLED',
        ])

    def test_path_from_fault_to_operation_enabled(self):
        """Walk from FAULT to OPERATION ENABLED."""
        path = []
        self._set_state('FAULT')
        target = 'OPERATION ENABLED'
        current = self.node.state
        while current != target:
            next_s = self.node._next_state(target)
            path.append(next_s)
            self._set_state(next_s)
            current = self.node.state
        self.assertEqual(path, [
            'SWITCH ON DISABLED',
            'READY TO SWITCH ON',
            'SWITCHED ON',
            'OPERATION ENABLED',
        ])


class TestBaseNode402HomingStatus(unittest.TestCase):
    """Test homing status word interpretation."""

    def setUp(self):
        self.node = BaseNode402(1, _make_od())

    def test_homing_states(self):
        test_cases = [
            (0x0000, 'IN PROGRESS'),
            (0x0400, 'INTERRUPTED'),
            (0x1000, 'ATTAINED'),
            (0x1400, 'TARGET REACHED'),
            (0x2000, 'ERROR VELOCITY IS NOT ZERO'),
            (0x2400, 'ERROR VELOCITY IS ZERO'),
        ]
        for sw, expected in test_cases:
            with self.subTest(statusword=hex(sw)):
                self.node.tpdo_values[0x6041] = sw
                # Test the bitmask logic directly without calling _homing_status,
                # which would require a fully configured TPDO setup
                status = None
                for key, value in Homing.STATES.items():
                    bitmask, bits = value
                    if sw & bitmask == bits:
                        status = key
                self.assertEqual(status, expected)


class TestOperationMode(unittest.TestCase):
    """Test OperationMode lookup tables."""

    def test_code2name_name2code_round_trip(self):
        for code, name in OperationMode.CODE2NAME.items():
            self.assertEqual(OperationMode.NAME2CODE[name], code)

    def test_supported_bitmask_unique(self):
        values = list(OperationMode.SUPPORTED.values())
        # All bitmasks should be unique (each is a single bit)
        self.assertEqual(len(values), len(set(values)))

    def test_all_named_modes_have_support_bit(self):
        for name in OperationMode.NAME2CODE:
            self.assertIn(name, OperationMode.SUPPORTED)


class TestBaseNode402TPDOCallback(unittest.TestCase):
    """Test the TPDO update callback."""

    def setUp(self):
        self.node = BaseNode402(1, _make_od())

    def test_on_tpdos_update_callback(self):
        fake_obj = MagicMock(index=0x6041, raw=0x0027)
        fake_map = MagicMock()
        fake_map.__iter__ = lambda s: iter([fake_obj])
        self.node.on_TPDOs_update_callback(fake_map)
        self.assertEqual(self.node.tpdo_values[0x6041], 0x0027)


if __name__ == '__main__':
    unittest.main()
