"""ATF2 Ext quadrupole read-back: batched PV reads and the tracking-model update."""
import numpy as np
import pytest

ext_module = pytest.importorskip("machine_interfaces_atf2.InterfaceATF2_Ext")

MOVER = ["MAG:DES:X", "MAG:DES:Y", "MAG:DES:R", "ENC:X", "ENC:Y", "ENC:R"]
VALUES = {
    # final-focus quadrupole with a mover
    "QM15FF:currentWrite": 10.0, "QM15FF:current": 9.9,
    **{f"QM15FF:{suffix}": float(i + 1) for i, suffix in enumerate(MOVER)},
    # extraction-line quadrupole: no mover, and only the currentRead read-back
    "QF1X:currentWrite": 20.0, "QF1X:currentRead": 19.5,
}


class FakePV:
    waits = {}

    def __init__(self, name, auto_monitor=None):
        self.pvname = self.chid = name
        self.connected = name in VALUES

    def wait_for_connection(self, timeout=None):
        FakePV.waits[self.pvname] = FakePV.waits.get(self.pvname, 0) + 1
        return self.connected

    def get(self, timeout=None):
        return VALUES.get(self.pvname)


class FakeCA:
    @staticmethod
    def get(chid, wait=True):
        return None if not wait else VALUES.get(chid)

    @staticmethod
    def get_complete(chid, timeout=None):
        return VALUES.get(chid)


class FakeModel:
    def __init__(self, fail=False):
        self.k1l = {"QM15FF": 0.0, "QF1X": 0.0}
        self.pushed = []
        self.fail = fail

    def get_quadrupoles(self, names=None):
        return {"names": list(self.k1l), "bdes": np.array(list(self.k1l.values()))}

    def set_quadrupoles(self, names, values):
        if self.fail:
            raise RuntimeError("model update failed")
        self.pushed.append(list(names))
        self.k1l.update(zip(names, values))


@pytest.fixture
def ext(monkeypatch):
    FakePV.waits = {}
    monkeypatch.setattr(ext_module, "PV", FakePV)
    monkeypatch.setattr(ext_module, "ca", FakeCA)
    interface = ext_module.InterfaceATF2_Ext.__new__(ext_module.InterfaceATF2_Ext)
    interface.quadrupoles = ["QM15FF", "QF1X"]
    interface.qmag_pv = {}
    interface.qmag_alias_to_canonical = {}
    interface.tracking_interface = FakeModel()
    interface.current_to_k1l = lambda name, current: 0.01 * current
    return interface


def test_read_values(ext):
    q = ext.get_quadrupoles()

    assert q["names"] == ["QM15FF", "QF1X"]
    np.testing.assert_allclose(q["ides"], [10.0, 20.0])
    np.testing.assert_allclose(q["iact"], [9.9, 19.5])  # QF1X falls back to currentRead
    np.testing.assert_allclose([q[k][0] for k in ("xdes", "ydes", "rolldes", "xact", "yact", "rollact")], [1, 2, 3, 4, 5, 6])
    assert all(np.isnan(q[k][1]) for k in ("xdes", "ydes", "rolldes", "xact", "yact", "rollact"))
    np.testing.assert_allclose(q["bdes"], [0.1, 0.2])
    np.testing.assert_allclose(q["bact"], [0.099, 0.195])


def test_batch_matches_one_by_one_reads(ext):
    names = [f"QM15FF:{s}" for s in MOVER] + ["QF1X:current", "QF1X:currentRead", "QF1X:MAG:DES:X"]
    batch = ext._pv_get_many(names)
    for name in names:
        expected = ext._pv_get(name)
        assert (np.isnan(batch[name]) and np.isnan(expected)) or batch[name] == expected


def test_missing_pvs_are_waited_for_only_once(ext):
    ext.get_quadrupoles()
    missing = [name for name in FakePV.waits if name not in VALUES]
    assert missing and all(FakePV.waits[name] == 1 for name in missing)

    ext.get_quadrupoles()
    assert all(FakePV.waits[name] == 1 for name in missing)


def test_model_gets_only_changed_strengths(ext):
    ext.get_quadrupoles()
    assert ext.tracking_interface.pushed == [["QM15FF", "QF1X"]]

    ext.get_quadrupoles()
    assert ext.tracking_interface.pushed == [["QM15FF", "QF1X"]]


def test_failed_model_update_keeps_the_strengths(ext):
    ext.tracking_interface = FakeModel(fail=True)

    q = ext.get_quadrupoles()

    np.testing.assert_allclose(q["bact"], [0.099, 0.195])


def test_interface_has_a_log_method(capsys):
    interface = ext_module.InterfaceATF2_Ext.__new__(ext_module.InterfaceATF2_Ext)
    interface.log("hello")
    assert "hello" in capsys.readouterr().out
