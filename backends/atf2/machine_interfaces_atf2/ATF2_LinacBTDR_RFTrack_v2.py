"""Explicit SAD-v2 development profile; historical frozen models stay separate."""
import hashlib
import json
from pathlib import Path

from .ATF2_LinacBTDR_RFTrack import ATF2LinacBTDRRFTrack
from .SAD_RFTrack_coordinates import RigidHandoff
from .tests.linac_bt_dr_model_config import MODEL_ENERGY_MATCHED_CAVITY_VOLTAGE_MV


def build_sad_v2_upstream():
    root=Path(__file__).with_name('LinacBT_ATF2')/'sad_v2'
    profile=json.loads((root/'model.json').read_text())
    tfs=root/profile['tfs']
    if hashlib.sha256(tfs.read_bytes()).hexdigest()!=profile['tfs_sha256']:
        raise ValueError('SAD-v2 TFS differs from the declared model version')
    machine=ATF2LinacBTDRRFTrack(
        cavity_voltage_mv=MODEL_ENERGY_MATCHED_CAVITY_VOLTAGE_MV,
        linac_bt_tfs_path=tfs,sad_coordinate_records=profile['coordinates'],
        dr_entry=profile['dr_entry'],dr_rf_mode='equilibrium',handoff_mode='reference_anchored')
    machine.handoff=RigidHandoff(profile['source_nominal_mm_mrad'],machine.dr_closed_orbit,profile['dr_entry'])
    machine.handoff_mode='sad_v2_rigid_nominal'
    machine.handoff_time_reference_mm_c=machine.reference_exit_time_mm_c
    machine.linac_bt_metadata['model_profile']=profile
    return machine
