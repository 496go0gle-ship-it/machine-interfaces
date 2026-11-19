"""ATF2 Ext beamline sequence and the repair tool for data recorded without BPM names."""
import gzip
import os
import pickle

import pytest

ext = pytest.importorskip("machine_interfaces_atf2.InterfaceATF2_Ext")
repair = pytest.importorskip("machine_interfaces_atf2.repair_ext_sequence")

OLD_SEQUENCE = ["MB2X", "ZV1X", "ZV2X", "ZH1X", "MSF1FF"]


def test_sequence_places_bpms_between_correctors():
    sequence, raw = ext.build_ext_sequence()

    assert sequence[0] == "MB1X"
    assert sequence.index("ZV1X") < sequence.index("MQF1X") < sequence.index("ZV2X")
    assert sequence.index("ZH1X") < sequence.index("MQF4X")
    assert sequence.index("MFB2FF") < sequence.index("MFB1FF") < sequence.index("MQM11FF")
    assert len(sequence) == len(set(sequence))
    assert "FB1FF" in raw and "QF1X" in raw


def test_sequence_contains_every_bpm_of_the_old_sequence():
    sequence, _ = ext.build_ext_sequence()
    assert set(OLD_SEQUENCE) <= set(sequence)


def write_state(path, interface_id, sequence=OLD_SEQUENCE, compressed=True):
    data = {"interface_id": interface_id, "sequence": list(sequence), "bpms": {"names": ["MB2X"]}}
    opener = gzip.open if compressed else open
    with opener(path, "wb") as file:
        pickle.dump(data, file)


def read_state(path):
    with open(path, "rb") as file:
        compressed = file.read(2) == b"\x1f\x8b"
    with (gzip.open if compressed else open)(path, "rb") as file:
        return pickle.load(file)


def test_repair_writes_a_fixed_copy_and_leaves_the_original(tmp_path):
    source = tmp_path / "ATF2_Ext_20261119_112700_Orbit"
    source.mkdir()
    write_state(source / "DATA_ZH1X_p0000.pkl", repair.EXT_INTERFACE_ID)
    write_state(source / "plain.pkl", repair.EXT_INTERFACE_ID, compressed=False)
    write_state(source / "other.pkl", "machine_interfaces_clear.InterfaceCLEAR.InterfaceCLEAR")
    (source / "bpms.txt").write_text("MB2X\n")
    destination = tmp_path / "fixed"

    changed, unchanged = repair.repair_folder(str(source), str(destination))

    expected, _ = ext.build_ext_sequence()
    assert sorted(changed) == ["DATA_ZH1X_p0000.pkl", "plain.pkl"]
    assert unchanged == ["other.pkl"]
    assert read_state(destination / "DATA_ZH1X_p0000.pkl")["sequence"] == expected
    assert read_state(destination / "plain.pkl")["sequence"] == expected
    assert read_state(destination / "other.pkl")["sequence"] == OLD_SEQUENCE
    assert read_state(destination / "DATA_ZH1X_p0000.pkl")["bpms"] == {"names": ["MB2X"]}
    assert (destination / "bpms.txt").read_text() == "MB2X\n"
    assert read_state(source / "DATA_ZH1X_p0000.pkl")["sequence"] == OLD_SEQUENCE


def test_repair_refuses_an_existing_destination(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    destination = tmp_path / "fixed"
    destination.mkdir()

    with pytest.raises(FileExistsError):
        repair.repair_folder(str(source), str(destination))
