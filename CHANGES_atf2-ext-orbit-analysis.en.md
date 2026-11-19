# Changes on branch `atf2-ext-orbit-analysis` (machine-interfaces)

Base: `flight-simulator-framework/machine-interfaces` `master` at `02957e2`.
Japanese version: [CHANGES_atf2-ext-orbit-analysis.ja.md](CHANGES_atf2-ext-orbit-analysis.ja.md)

| Commit | Summary |
|---|---|
| `f2c8890` | Map ATF2 Ext sequence magnets to their BPM names |
| `9f8fbb3` | Keep the orbit when BPM intensity is not recorded |
| `126f4db` | Add a tool to rebuild the sequence of older ATF2 Ext data |
| `ed6386d` | Read quadrupole PVs in one batch in ATF2 Ext |
| `8c62217` | Keep quadrupole strengths when the tracking model is updated |

Files changed: `backends/atf2/machine_interfaces_atf2/InterfaceATF2_Ext.py`, `backends/atf2/machine_interfaces_atf2/repair_ext_sequence.py` (new), `machine_interfaces/Backend/State.py`, `tests/test_bpm_intensity.py` (new), `tests/test_repair_ext_sequence.py` (new), `tests/test_quadrupole_reads.py` (new).

---

## 1. Map ATF2 Ext sequence magnets to their BPM names (`f2c8890`)

**File:** `backends/atf2/machine_interfaces_atf2/InterfaceATF2_Ext.py` (`__init__`)

**Problem.** The beamline sequence lists magnets (`QF1X`, `FB2FF`, `IPB`), while `ATF2:monitors` names the BPM at each of those locations `M<magnet>` (`MQF1X`, `MFB2FF`, `MIPB`). The old code kept only sequence entries whose name was already a BPM name, so almost every BPM was dropped from the recorded sequence. Applications that order devices with `sequence.index()` (response matrix, BBA, orbit bumps) could then not place the BPMs.

**Change.**
- Translate each sequence entry to its BPM name (`X` or `MX`, whichever exists in `MONITOR_INDEX_TO_NAME`); correctors (`Z*`) are kept as they are.
- Prepend `MB1X` and insert `FB1FF` before `QM11FF`, following `atf2_full_twiss.tfs`.
- Remove duplicates and print the BPMs that still have no beamline position.

---

## 2. Keep the orbit when BPM intensity is not recorded (`9f8fbb3`)

### Problem
- In the extraction line, `ATF2:monitors` leaves the BPM intensity field empty, so it reads 0 for every BPM (confirmed on the PV; the DR monitors do report intensity).
- `InterfaceATF2_Ext.get_bpms()` computed `tmit = status * intensity`, so every snapshot was saved with `tmit = 0`.
- Since `d985519` (2026-10-19), `State.get_orbit()` keeps only shots with a positive `tmit`. With `tmit = 0` everywhere, every shot was discarded and all 67 BPMs came out as NaN / faulty.

### Impact before the fix
- Saved ATF2 Ext data (e.g. the 2026-11-19 `ATF2_Ext_*_Orbit` folders) gave no orbit in SysID, BBA, orbit bumps or the response matrix.
- **Live risk in SysID:** with an all-NaN orbit the observed response is 0, so `update_amplitude()` raises the kick by about 1.4x every iteration up to the maximum current, and the plots stay empty.
- The existing tests did not catch this because their fake BPM data used `tmit = 1`.

### Changes

**`machine_interfaces/Backend/State.py` — `State.get_orbit()`**
- If at least one BPM reports a positive intensity: unchanged. Shots with no or low intensity (below half of the BPM's median) are discarded.
- If no BPM reports a positive intensity: issue a `RuntimeWarning` ("BPM intensity (tmit) is not recorded …") and average every shot instead of discarding them.
- The `nanmedian` of all-NaN columns no longer prints a `RuntimeWarning`.

**`backends/atf2/machine_interfaces_atf2/InterfaceATF2_Ext.py` — `get_bpms()`**
- For each sample, if no BPM reports a positive intensity, `tmit` is recorded as NaN ("not measured") instead of 0 ("no beam"). A single message is printed after reading.
- The check is per sample, over all BPMs, so a single BPM that genuinely sees no beam still records 0 when the others report an intensity.
- Positions (`x`, `y`) are unchanged; they are still recorded regardless of `status`.

**`tests/test_bpm_intensity.py` (new, pytest)**

| Test | Checks |
|---|---|
| `test_orbit_without_recorded_intensity_keeps_every_shot[zero]` / `[nan]` | all-zero or all-NaN `tmit` → orbit is the mean of every shot, with a warning |
| `test_orbit_with_recorded_intensity_still_drops_shots_without_beam` | a shot with `tmit = 0` is still dropped when intensity is recorded |
| `test_orbit_with_recorded_intensity_flags_bpm_without_beam` | a BPM that never sees beam is still flagged faulty |
| `test_ext_records_missing_intensity_as_nan` | `InterfaceATF2_Ext.get_bpms()` with a fake `ATF2:monitors` and empty intensity → `tmit` is NaN and the orbit is computed |
| `test_ext_keeps_reported_intensity_and_status` | reported intensity is kept as `status * intensity` |

Run with:

```bash
python -m pip install pytest
python -m pytest tests -q
```

### Verification
- With the fix: 6 passed. Without the fix (`State.py` and `InterfaceATF2_Ext.py` reverted): the 3 tests for the bug fail and the 3 tests for the unchanged behaviour pass.
- 2026-11-19 ATF2 Ext data, `State.get_orbit()`:

  | | BPMs with an orbit | Faulty |
  |---|---|---|
  | Before | 0 / 67 | 67 |
  | After | 43 / 67 | 24 (they read exactly x = y = 0) |

---

## 3. Add a tool to rebuild the sequence of older ATF2 Ext data (`126f4db`)

### Problem
Data recorded before change 1 stores a sequence of 25 entries with only two BPMs (`MB2X`, `MSF1FF`). With the 2026-11-19 data, the response matrix keeps only the BPMs after the first selected corrector, which leaves `MSF1FF`. That BPM reads x = y = 0, so every DATA pair was skipped and the GUI showed "No complete corrector readbacks available for response-matrix."

### Changes
**`backends/atf2/machine_interfaces_atf2/InterfaceATF2_Ext.py`**
- The extraction-line magnet list (`EXT_SEQUENCE`) and the `ATF2:monitors` index map (`MONITOR_INDEX_TO_NAME`) are module-level constants.
- `build_ext_sequence()` builds the sequence from them, without EPICS. `InterfaceATF2_Ext.__init__()` calls it and gets exactly the same sequence as before (78 entries; 12 BPMs such as `MDUMP` and `IPBPM1` still have no position).

**`backends/atf2/machine_interfaces_atf2/repair_ext_sequence.py` (new)**
- Copies a data folder to `SOURCE_sequence_fixed` (or `--out`) and replaces the `sequence` of every ATF2 Ext state in the copy. Everything else in the files is kept; other files are copied as they are.
- The original folder is not modified, and an existing destination is refused.

```bash
python -m machine_interfaces_atf2.repair_ext_sequence ~/CERN-Flight_Simulator-Data
```

Then select the folders inside `CERN-Flight_Simulator-Data_sequence_fixed` in the GUI.

**`tests/test_repair_ext_sequence.py` (new)** — 4 tests: BPM order between correctors, the old BPMs are kept, the repaired copy (gzip and plain pickles, other interfaces untouched, original untouched), and refusing an existing destination.

### Verification
- All 10 tests in `tests/` pass.
- 2026-11-19 data: 12 files repaired (sequence 25 → 78 entries). The response matrix of `ATF2_Ext_20261119_112700_Orbit` is then computed for `ZH1X` and `ZV1X` with 50 BPMs. The largest responses are at `MQD18X` (`ZH1X`, horizontal) and `MQD4BFF` (`ZV1X`, vertical), matching the raw +/- orbit differences.

---

## 4. Read quadrupole PVs in one batch (`ed6386d`)

**Problem.** Every machine state (`get_state()`, e.g. each SysID excitation) calls `get_quadrupoles()`, which read up to 9 PVs per quadrupole one after another, each waiting up to 0.7 s. The 21 extraction-line quadrupoles have no mover, so their 6 mover PVs never connect and cost the full wait on every read (about 21 x 6 x 0.7 s, roughly 90 s).

**Changes** (`InterfaceATF2_Ext.py`)
- `get_quadrupoles()` reads all PVs of all requested quadrupoles with `_pv_get_many()`: connections share one 0.7 s deadline and the reads run in parallel. A PV that did not connect is not waited for again; CA keeps searching, and it is read as soon as it connects.
- `_cached_pv()` keeps one `PV` object per name (`auto_monitor=False`, so `get()` is still a fresh read) instead of creating a new one for every read.
- `update_tracking_model_with_clibmagnet()` pushes to the RF-Track model only the quadrupoles whose finite machine value differs from the model, instead of re-tracking the bunch on every read.
- The per-quadrupole message `'Getting quadrupoles' PVs ...` is no longer printed.

The values read are the same as before (checked in the tests of change 5). The time on the machine has not been measured.

---

## 5. Keep quadrupole strengths when the tracking model is updated (`8c62217`)

**Problem.** `InterfaceATF2_Ext` had no `log()` method (the simulation and Linac interfaces set `self.log = print`). Updating the tracking model from `get_quadrupoles()` called `self.log(...)` and raised `AttributeError`, which was caught as a failed current-to-K1 conversion: `bdes`/`bact` were recorded as NaN for every quadrupole, and the model was never updated. This matches the 2026-11-19 data (currents read, strengths all NaN). Change 4 alone does not fix it: the error still occurs whenever a strength differs from the model.

**Changes**
- `InterfaceATF2_Ext.log()` prints the message; a GUI can still replace it by assigning `interface.log`.
- The model update runs after the conversion and has its own `try`: a failure prints a warning and keeps the strengths.
- `tests/test_quadrupole_reads.py` (new, 6 tests, fake PVs): values of the batched read, same result as reading one by one, missing PVs waited for only once, only changed strengths pushed to the model, strengths kept when the model update fails, `log()` exists.

**Verification.** All 16 tests in `tests/` pass. Without this change, 4 of the 6 new tests fail with the message seen on the machine: `'InterfaceATF2_Ext' object has no attribute 'log'`.

---

## Known issues not addressed here
- **Data recorded before change 1** must be repaired with the tool above before the response matrix, BBA or orbit bumps can use it.
- **BPMs with a fixed value** (`MFB2FF`, `MIPA`, `MIPB` at about 10 mm, `MDUMP` y at -7.202 mm) are still averaged into the orbit, because positions are not masked by `status`. Exclude them through `bpms.txt` for now; masking by `status` should be a separate change once the Ext `status` field has been checked.
- **`InterfaceATF2_Linac.get_bpms()`** computes `tmit` the same way (`status * column 3`). Whether `LINAC:monitors` reports intensity has not been checked.
