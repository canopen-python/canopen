import unittest
from unittest.mock import MagicMock

from canopen.objectdictionary import ODVariable, ObjectDictionary
from canopen.objectdictionary.datatypes import INTEGER8, UNSIGNED16, UNSIGNED32
from canopen.profiles.p402 import BaseNode402, OperationMode, State402


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


def _inject_tpdo(node, index, value):
    """Simulate TPDO reception for a single OD object."""
    fake_obj = MagicMock(index=index, raw=value)
    fake_map = MagicMock()
    fake_map.__iter__ = lambda s: iter([fake_obj])
    node.on_TPDOs_update_callback(fake_map)


class _FakeRpdoVar:
    """Fake RPDO variable that calls a callback when raw is written."""

    def __init__(self, on_write):
        self._raw = 0
        self._on_write = on_write
        self.pdo_parent = MagicMock(is_periodic=False)

    @property
    def raw(self):
        return self._raw

    @raw.setter
    def raw(self, value):
        self._raw = value
        self._on_write(value)


class TestState402(unittest.TestCase):
    """Tests for the State402 static helper and its lookup tables."""

    def test_sw_mask_all_states_defined(self):
        expected = {
            "NOT READY TO SWITCH ON",
            "SWITCH ON DISABLED",
            "READY TO SWITCH ON",
            "SWITCHED ON",
            "OPERATION ENABLED",
            "FAULT",
            "FAULT REACTION ACTIVE",
            "QUICK STOP ACTIVE",
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
            if state != "OPERATION ENABLED":
                self.assertIsNotNone(result, f"No indirect path from {state}")
                self.assertIn(
                    result,
                    State402.SW_MASK,
                    f"Indirect state {result} is not a known state",
                )

    def test_next_state_indirect_specific_paths(self):
        self.assertEqual(
            State402.next_state_indirect("SWITCH ON DISABLED"), "READY TO SWITCH ON"
        )
        self.assertEqual(
            State402.next_state_indirect("READY TO SWITCH ON"), "SWITCHED ON"
        )
        self.assertEqual(
            State402.next_state_indirect("SWITCHED ON"), "OPERATION ENABLED"
        )
        self.assertEqual(State402.next_state_indirect("FAULT"), "SWITCH ON DISABLED")
        self.assertEqual(State402.next_state_indirect("FAULT REACTION ACTIVE"), "FAULT")
        self.assertEqual(
            State402.next_state_indirect("QUICK STOP ACTIVE"), "SWITCH ON DISABLED"
        )

    def test_next_state_indirect_unknown_state(self):
        self.assertIsNone(State402.next_state_indirect("NONEXISTENT"))

    def test_transition_table_keys_are_valid_states(self):
        known = set(State402.SW_MASK.keys()) | {"START", "DISABLE VOLTAGE"}
        for from_state, to_state in State402.TRANSITIONTABLE:
            self.assertIn(from_state, known, f"Unknown from-state: {from_state}")
            self.assertIn(to_state, known, f"Unknown to-state: {to_state}")


class TestBaseNode402State(unittest.TestCase):
    """Test state property reading from simulated TPDO reception."""

    def setUp(self):
        self.node = BaseNode402(1, _make_od())

    def _inject_statusword(self, sw):
        """Simulate TPDO reception with the given statusword."""
        _inject_tpdo(self.node, 0x6041, sw)

    def test_state_from_statusword(self):
        """Verify all state decoding from TPDO-received statusword."""
        test_cases = [
            (0x0000, "NOT READY TO SWITCH ON"),
            (0x0040, "SWITCH ON DISABLED"),
            (0x0021, "READY TO SWITCH ON"),
            (0x0023, "SWITCHED ON"),
            (0x0027, "OPERATION ENABLED"),
            (0x0008, "FAULT"),
            (0x000F, "FAULT REACTION ACTIVE"),
            (0x0007, "QUICK STOP ACTIVE"),
        ]
        for sw, expected_state in test_cases:
            with self.subTest(statusword=hex(sw)):
                self._inject_statusword(sw)
                self.assertEqual(self.node.state, expected_state)

    def test_state_unknown_statusword(self):
        self._inject_statusword(0xFFFF)
        self.assertEqual(self.node.state, "UNKNOWN")

    def test_is_faulted_true(self):
        self._inject_statusword(0x0008)  # FAULT
        self.assertTrue(self.node.is_faulted())

    def test_is_faulted_false(self):
        self._inject_statusword(0x0040)  # SWITCH ON DISABLED
        self.assertFalse(self.node.is_faulted())

    def test_controlword_read_raises(self):
        with self.assertRaises(RuntimeError):
            _ = self.node.controlword

    def test_state_transition_sequence(self):
        """Walk through the state machine by injecting TPDO statusword updates."""
        expected_sequence = [
            (0x0040, "SWITCH ON DISABLED"),
            (0x0021, "READY TO SWITCH ON"),
            (0x0023, "SWITCHED ON"),
            (0x0027, "OPERATION ENABLED"),
        ]
        for sw, expected_state in expected_sequence:
            self._inject_statusword(sw)
            self.assertEqual(self.node.state, expected_state)

    def test_state_fault_recovery_sequence(self):
        """Simulate a fault recovery path via TPDO updates."""
        self._inject_statusword(0x000F)  # FAULT REACTION ACTIVE
        self.assertEqual(self.node.state, "FAULT REACTION ACTIVE")
        self._inject_statusword(0x0008)  # FAULT
        self.assertEqual(self.node.state, "FAULT")
        self._inject_statusword(0x0040)  # SWITCH ON DISABLED
        self.assertEqual(self.node.state, "SWITCH ON DISABLED")

    def test_statusword_sdo_fallback(self):
        """When no TPDO value is cached, statusword falls back to SDO."""
        node = BaseNode402(1, _make_od())
        node.sdo = MagicMock()
        node.sdo.__getitem__ = MagicMock(return_value=MagicMock(raw=0x0040))
        self.assertEqual(node.statusword, 0x0040)

    def test_check_statusword_no_tpdo_pointers(self):
        """check_statusword returns cached statusword when no TPDO pointers."""
        self._inject_statusword(0x0027)
        result = self.node.check_statusword()
        self.assertEqual(result, 0x0027)

    def test_check_statusword_periodic_tpdo(self):
        """check_statusword waits for periodic TPDO reception."""
        self._inject_statusword(0x0040)
        tpdo_ptr = MagicMock()
        tpdo_ptr.pdo_parent.is_periodic = True
        tpdo_ptr.pdo_parent.wait_for_reception.return_value = 1234.0
        self.node.tpdo_pointers[0x6041] = tpdo_ptr  # type: ignore[assignment]
        result = self.node.check_statusword()
        tpdo_ptr.pdo_parent.wait_for_reception.assert_called_once()
        self.assertEqual(result, 0x0040)

    def test_check_statusword_periodic_tpdo_timeout(self):
        """check_statusword raises on TPDO reception timeout."""
        tpdo_ptr = MagicMock()
        tpdo_ptr.pdo_parent.is_periodic = True
        tpdo_ptr.pdo_parent.wait_for_reception.return_value = None
        self.node.tpdo_pointers[0x6041] = tpdo_ptr  # type: ignore[assignment]
        with self.assertRaises(RuntimeError):
            self.node.check_statusword()

    def test_check_statusword_non_periodic_tpdo(self):
        """check_statusword reads SDO for non-periodic TPDO."""
        tpdo_ptr = MagicMock()
        tpdo_ptr.pdo_parent.is_periodic = False
        self.node.tpdo_pointers[0x6041] = tpdo_ptr  # type: ignore[assignment]
        self.node.sdo = MagicMock()
        self.node.sdo.__getitem__ = MagicMock(return_value=MagicMock(raw=0x0023))
        result = self.node.check_statusword()
        self.assertEqual(result, 0x0023)


class TestBaseNode402StateTransition(unittest.TestCase):
    """Test state machine transitions with simulated TPDO/RPDO."""

    def setUp(self):
        self.node = BaseNode402(1, _make_od())
        self.cw_log = []

        def _on_cw_write(value):
            self.cw_log.append(value)
            # Simulate drive response: look up the transition and inject statusword
            current = self.node.state
            for (from_s, to_s), cw in State402.TRANSITIONTABLE.items():
                if cw == value and from_s == current:
                    if to_s in State402.SW_MASK:
                        _, bits = State402.SW_MASK[to_s]
                        self.node.tpdo_values[0x6041] = bits
                    return

        self.node.rpdo_pointers[0x6040] = _FakeRpdoVar(_on_cw_write)  # type: ignore[assignment]

    def test_transition_to_operation_enabled(self):
        """Walk from SWITCH ON DISABLED to OPERATION ENABLED via state setter."""
        _inject_tpdo(self.node, 0x6041, 0x0040)
        self.node.state = "OPERATION ENABLED"
        self.assertEqual(self.node.state, "OPERATION ENABLED")
        self.assertEqual(
            self.cw_log,
            [
                State402.CW_SHUTDOWN,
                State402.CW_SWITCH_ON,
                State402.CW_OPERATION_ENABLED,
            ],
        )

    def test_transition_from_fault(self):
        """Walk from FAULT to SWITCH ON DISABLED via state setter."""
        _inject_tpdo(self.node, 0x6041, 0x0008)
        self.node.state = "SWITCH ON DISABLED"
        self.assertEqual(self.node.state, "SWITCH ON DISABLED")
        self.assertEqual(self.cw_log, [State402.CW_SWITCH_ON_DISABLED])

    def test_transition_quick_stop(self):
        """Transition from OPERATION ENABLED to QUICK STOP ACTIVE."""
        _inject_tpdo(self.node, 0x6041, 0x0027)
        self.node.state = "QUICK STOP ACTIVE"
        self.assertEqual(self.node.state, "QUICK STOP ACTIVE")
        self.assertEqual(self.cw_log, [State402.CW_QUICK_STOP])

    def test_transition_fault_to_operation_enabled(self):
        """Full path from FAULT through to OPERATION ENABLED."""
        _inject_tpdo(self.node, 0x6041, 0x0008)
        self.node.state = "OPERATION ENABLED"
        self.assertEqual(self.node.state, "OPERATION ENABLED")
        self.assertEqual(
            self.cw_log,
            [
                State402.CW_SWITCH_ON_DISABLED,
                State402.CW_SHUTDOWN,
                State402.CW_SWITCH_ON,
                State402.CW_OPERATION_ENABLED,
            ],
        )

    def test_illegal_target_fault_raises(self):
        _inject_tpdo(self.node, 0x6041, 0x0040)
        with self.assertRaises(ValueError):
            self.node.state = "FAULT"

    def test_illegal_target_not_ready_raises(self):
        _inject_tpdo(self.node, 0x6041, 0x0040)
        with self.assertRaises(ValueError):
            self.node.state = "NOT READY TO SWITCH ON"

    def test_illegal_target_fault_reaction_raises(self):
        _inject_tpdo(self.node, 0x6041, 0x0040)
        with self.assertRaises(ValueError):
            self.node.state = "FAULT REACTION ACTIVE"

    def test_controlword_sdo_fallback(self):
        """Controlword write falls back to SDO without RPDO configured."""
        node = BaseNode402(1, _make_od())
        node.sdo = MagicMock()
        node.controlword = 0x0006
        self.assertEqual(node.sdo[0x6040].raw, 0x0006)


class TestBaseNode402Homing(unittest.TestCase):
    """Test homing status via simulated TPDO reception."""

    def setUp(self):
        self.node = BaseNode402(1, _make_od())

    def test_homing_status(self):
        """Verify _homing_status from TPDO-injected statusword."""
        test_cases = [
            (0x0000, "IN PROGRESS"),
            (0x0400, "INTERRUPTED"),
            (0x1000, "ATTAINED"),
            (0x1400, "TARGET REACHED"),
            (0x2000, "ERROR VELOCITY IS NOT ZERO"),
            (0x2400, "ERROR VELOCITY IS ZERO"),
        ]
        for sw, expected in test_cases:
            with self.subTest(statusword=hex(sw)):
                _inject_tpdo(self.node, 0x6041, sw)
                result = self.node._homing_status()
                self.assertEqual(result, expected)


class TestBaseNode402OpMode(unittest.TestCase):
    """Test operation mode reading via simulated TPDO."""

    def setUp(self):
        self.node = BaseNode402(1, _make_od())
        tpdo_ptr = MagicMock()
        tpdo_ptr.pdo_parent.is_periodic = False
        self.node.tpdo_pointers[0x6061] = tpdo_ptr  # type: ignore[assignment]

    def test_op_mode_read_all(self):
        """Read each operation mode from TPDO-cached value."""
        for code, name in OperationMode.CODE2NAME.items():
            with self.subTest(code=code):
                _inject_tpdo(self.node, 0x6061, code)
                self.assertEqual(self.node.op_mode, name)

    def test_op_mode_sdo_fallback(self):
        """op_mode reads from SDO when TPDO pointer is missing."""
        node = BaseNode402(1, _make_od())
        node.sdo = MagicMock()
        node.sdo.__getitem__ = MagicMock(
            return_value=MagicMock(raw=OperationMode.PROFILED_POSITION)
        )
        self.assertEqual(node.op_mode, "PROFILED POSITION")

    def test_op_mode_periodic_tpdo(self):
        """op_mode waits for periodic TPDO then reads cached value."""
        tpdo_ptr = MagicMock()
        tpdo_ptr.pdo_parent.is_periodic = True
        tpdo_ptr.pdo_parent.wait_for_reception.return_value = 1234.0
        self.node.tpdo_pointers[0x6061] = tpdo_ptr  # type: ignore[assignment]
        _inject_tpdo(self.node, 0x6061, OperationMode.HOMING)
        self.assertEqual(self.node.op_mode, "HOMING")

    def test_op_mode_periodic_tpdo_timeout(self):
        """op_mode raises RuntimeError on TPDO reception timeout."""
        tpdo_ptr = MagicMock()
        tpdo_ptr.pdo_parent.is_periodic = True
        tpdo_ptr.pdo_parent.wait_for_reception.return_value = None
        self.node.tpdo_pointers[0x6061] = tpdo_ptr  # type: ignore[assignment]
        with self.assertRaises(RuntimeError):
            _ = self.node.op_mode


class TestOperationMode(unittest.TestCase):
    """Test OperationMode lookup tables."""

    def test_code2name_name2code_round_trip(self):
        for code, name in OperationMode.CODE2NAME.items():
            self.assertEqual(OperationMode.NAME2CODE[name], code)

    def test_all_named_modes_have_support_bit(self):
        for name in OperationMode.NAME2CODE:
            self.assertIn(name, OperationMode.SUPPORTED)


if __name__ == "__main__":
    unittest.main()
