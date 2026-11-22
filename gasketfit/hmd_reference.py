"""OEM HMD and coupled headband preview; never exported as print geometry."""
from functools import lru_cache
from pathlib import Path
import numpy as np
from .meshio import Mesh


@lru_cache(maxsize=1)
def hmd_reference():
    with np.load(Path(__file__).with_name('pfd_hmd_reference.npz'), allow_pickle=False) as data:
        return Mesh(data['vertices'].copy(), data['faces'].copy(), 'PFDMR HMD reference')


@lru_cache(maxsize=1)
def hmd_reference_samples():
    with np.load(Path(__file__).with_name('pfd_hmd_reference.npz'),allow_pickle=False) as data:
        return data['front_samples'].copy() if 'front_samples' in data else None
