"""Offline SysID sextupole lifecycle regressions; never construct hardware."""
import unittest
from unittest.mock import Mock

import numpy as np

from machine_interfaces.Interfaces.AbstractMachineInterface import AbstractMachineInterface
from machine_interfaces_atf2.InterfaceATF2_Ext import InterfaceATF2_Ext
from machine_interfaces_atf2.InterfaceATF2_Ext_RFTrack import InterfaceATF2_Ext_RFTrack


class TestSextupoleLifecycle(unittest.TestCase):
    interface_types = (InterfaceATF2_Ext, InterfaceATF2_Ext_RFTrack)

    def make_machine(self, interface_type):
        machine = interface_type.__new__(interface_type)
        machine.sextupoles = ["SF6FF", "SD4FF"]
        machine._saved_sextupoles_state = None
        strengths = np.array([1.25, -2.5])

        def read():
            return {"names": machine.sextupoles.copy(), "bdes": strengths.copy(),
                    "bact": strengths.copy() + 0.01}

        def write(names, values):
            self.assertEqual(list(names), machine.sextupoles)
            strengths[:] = values

        machine.get_sextupoles = Mock(side_effect=read)
        machine.set_sextupoles = Mock(side_effect=write)
        return machine, strengths

    def test_switch_off_and_restore_setpoints_across_modes(self):
        for interface_type in self.interface_types:
            with self.subTest(interface=interface_type.__name__):
                machine, strengths = self.make_machine(interface_type)
                for expected in ([1.25, -2.5], [3.0, -4.0]):
                    strengths[:] = expected
                    machine.switch_off_sextupoles()
                    np.testing.assert_array_equal(strengths, [0.0, 0.0])
                    self.assertTrue(machine.reset_sextupoles())
                    np.testing.assert_array_equal(strengths, expected)
                    self.assertIsNone(machine._saved_sextupoles_state)
                machine.set_sextupoles.reset_mock()
                self.assertFalse(machine.reset_sextupoles())
                machine.set_sextupoles.assert_not_called()

    def test_reset_before_switch_off_does_not_write(self):
        for interface_type in self.interface_types:
            with self.subTest(interface=interface_type.__name__):
                machine, _ = self.make_machine(interface_type)
                self.assertFalse(machine.reset_sextupoles())
                machine.set_sextupoles.assert_not_called()

    def test_failed_restore_keeps_saved_setpoints_for_retry(self):
        for interface_type in self.interface_types:
            with self.subTest(interface=interface_type.__name__):
                machine, strengths = self.make_machine(interface_type)
                machine.switch_off_sextupoles()
                write = machine.set_sextupoles.side_effect
                machine.set_sextupoles.side_effect = RuntimeError("offline write failed")
                with self.assertRaisesRegex(RuntimeError, "offline write failed"):
                    machine.reset_sextupoles()
                self.assertIsNotNone(machine._saved_sextupoles_state)
                machine.set_sextupoles.side_effect = write
                self.assertTrue(machine.reset_sextupoles())
                np.testing.assert_array_equal(strengths, [1.25, -2.5])

    def test_default_hooks_do_not_operate_magnets(self):
        machine = Mock()
        AbstractMachineInterface.switch_off_sextupoles(machine)
        AbstractMachineInterface.reset_sextupoles(machine)
        self.assertEqual(machine.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
