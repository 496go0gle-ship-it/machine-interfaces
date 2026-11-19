"""Rebuild the beamline sequence of ATF2 Ext data recorded before the BPM-name mapping.

Data recorded with InterfaceATF2_Ext before the sequence listed BPM names (MQF1X, ...)
contains only the BPMs whose names happened to match (MB2X, MSF1FF). Applications that
order devices along the beamline (response matrix, BBA, orbit bumps) then ignore almost
every BPM. This tool writes a copy of a data folder in which the `sequence` of every ATF2
Ext state is replaced by the current one. The original files are not modified.

Usage:
    python -m machine_interfaces_atf2.repair_ext_sequence SOURCE [--out DESTINATION]

SOURCE can be one measurement folder (e.g. ATF2_Ext_20261119_112700_Orbit) or a folder
containing several of them. DESTINATION defaults to SOURCE + "_sequence_fixed".
"""
import argparse
import gzip
import os
import pickle
import shutil
import sys

from machine_interfaces_atf2.InterfaceATF2_Ext import build_ext_sequence

EXT_INTERFACE_ID = "machine_interfaces_atf2.InterfaceATF2_Ext.InterfaceATF2_Ext"


def _read_state(path):
    with open(path, "rb") as file:
        compressed = file.read(2) == b"\x1f\x8b"
    opener = gzip.open if compressed else open
    with opener(path, "rb") as file:
        return pickle.load(file), compressed


def _write_state(path, data, compressed):
    if compressed:
        with gzip.open(path, "wb", compresslevel=6) as file:
            pickle.dump(data, file)
    else:
        with open(path, "wb") as file:
            pickle.dump(data, file)


def repair_state_file(path, sequence):
    """Replace the sequence of one ATF2 Ext state file in place. Return True if it changed."""
    data, compressed = _read_state(path)
    if not isinstance(data, dict) or data.get("interface_id") != EXT_INTERFACE_ID:
        return False
    if list(data.get("sequence", [])) == list(sequence):
        return False
    data["sequence"] = list(sequence)
    _write_state(path, data, compressed)
    return True


def repair_folder(source, destination):
    """Copy `source` to `destination` and rebuild the sequence of every ATF2 Ext state in the copy."""
    source = os.path.abspath(os.path.expanduser(source))
    destination = os.path.abspath(os.path.expanduser(destination))
    if not os.path.isdir(source):
        raise NotADirectoryError(source)
    if os.path.exists(destination):
        raise FileExistsError(f"{destination} already exists; choose another --out")

    shutil.copytree(source, destination)
    sequence, _ = build_ext_sequence()
    changed, unchanged = [], []
    for root, _, files in os.walk(destination):
        for name in sorted(files):
            if not name.endswith(".pkl"):
                continue
            path = os.path.join(root, name)
            (changed if repair_state_file(path, sequence) else unchanged).append(os.path.relpath(path, destination))
    return changed, unchanged


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", help="measurement folder, or a folder of measurement folders")
    parser.add_argument("--out", help="destination folder (default: SOURCE_sequence_fixed)")
    args = parser.parse_args(argv)

    destination = args.out or os.path.abspath(os.path.expanduser(args.source)).rstrip(os.sep) + "_sequence_fixed"
    changed, unchanged = repair_folder(args.source, destination)
    print(f"Wrote {destination}")
    print(f"  sequence rebuilt in {len(changed)} file(s); {len(unchanged)} file(s) left as they were")
    for name in changed:
        print(f"    {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
