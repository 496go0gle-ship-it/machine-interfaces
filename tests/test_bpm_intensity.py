"""BPM intensity (tmit) handling when the control system does not report it.

ATF2:monitors leaves the intensity field empty in the extraction line, so every
BPM reads 0. The orbit must still be computed from the recorded positions.
"""
import numpy as np
import pytest

from machine_interfaces.Backend.State import State

NAMES = ["B1", "B2", "B3"]
X = np.array([[0.10, -0.20, 0.30],
              [0.12, -0.22, 0.28],
              [0.11, -0.21, 0.29]])
Y = X * -2.0


def make_state(tmit):
    return State(bpms={"names": NAMES, "x": X.copy(), "y": Y.copy(), "tmit": np.asarray(tmit, dtype=float)})


@pytest.mark.parametrize("tmit", [np.zeros_like(X), np.full_like(X, np.nan)], ids=["zero", "nan"])
def test_orbit_without_recorded_intensity_keeps_every_shot(tmit):
    with pytest.warns(RuntimeWarning, match="not recorded"):
        orbit = make_state(tmit).get_orbit()

    np.testing.assert_allclose(orbit["x"], X.mean(axis=0))
    np.testing.assert_allclose(orbit["y"], Y.mean(axis=0))
    assert not orbit["faulty"].any()


def test_orbit_with_recorded_intensity_still_drops_shots_without_beam():
    tmit = np.ones_like(X)
    tmit[1, :] = 0.0  # no beam on the second shot

    orbit = make_state(tmit).get_orbit()

    np.testing.assert_allclose(orbit["x"], X[[0, 2]].mean(axis=0))
    np.testing.assert_allclose(orbit["y"], Y[[0, 2]].mean(axis=0))


def test_orbit_with_recorded_intensity_flags_bpm_without_beam():
    tmit = np.ones_like(X)
    tmit[:, 2] = 0.0  # beam never reaches B3

    orbit = make_state(tmit).get_orbit()

    assert orbit["faulty"].tolist() == [False, False, True]
    np.testing.assert_allclose(orbit["x"][:2], X[:, :2].mean(axis=0))


atf2_ext = pytest.importorskip("machine_interfaces_atf2.InterfaceATF2_Ext")


class FakeMonitorsPV:
    """Stands in for epics.PV('ATF2:monitors'): 10 values per BPM."""

    def __init__(self, rows):
        self.rows = np.asarray(rows, dtype=float)

    def get(self):
        return self.rows.ravel()


def monitor_rows(intensity, status=(1, 1, 1)):
    rows = np.zeros((3, 10))
    rows[:, 0] = status
    rows[:, 1] = [100.0, -200.0, 300.0]  # um
    rows[:, 2] = [-50.0, 60.0, -70.0]  # um
    rows[:, 3] = intensity
    rows[:, 4] = [1.0, 2.0, 3.0]
    return rows


def make_ext_interface(monkeypatch, rows):
    monkeypatch.setattr(atf2_ext, "PV", lambda name: FakeMonitorsPV(rows))
    interface = atf2_ext.InterfaceATF2_Ext.__new__(atf2_ext.InterfaceATF2_Ext)
    interface.nsamples = 2
    interface.bpm_sample_interval_s = 0.0
    interface.MONITOR_INDEX_TO_NAME = dict(enumerate(NAMES))
    interface.bpm_indexes = np.arange(len(NAMES))
    return interface


def test_ext_records_missing_intensity_as_nan(monkeypatch):
    interface = make_ext_interface(monkeypatch, monitor_rows(intensity=0.0))

    bpms = interface.get_bpms()

    assert bpms["tmit"].shape == (2, 3)
    assert np.isnan(bpms["tmit"]).all()
    np.testing.assert_allclose(bpms["x"][0], [0.1, -0.2, 0.3])

    with pytest.warns(RuntimeWarning, match="not recorded"):
        orbit = State(bpms=bpms).get_orbit()
    np.testing.assert_allclose(orbit["x"], [0.1, -0.2, 0.3])


def test_ext_keeps_reported_intensity_and_status(monkeypatch):
    rows = monitor_rows(intensity=[5.0, 6.0, 7.0], status=(1, 0, 1))
    interface = make_ext_interface(monkeypatch, rows)

    bpms = interface.get_bpms()

    np.testing.assert_allclose(bpms["tmit"][0], [5.0, 0.0, 7.0])
