"""Data-driven fixed forehead outlines. Add future named templates here."""
from .localization import tr
from functools import lru_cache
from pathlib import Path
import json
import numpy as np

PRESETS={'custom':{'name':'Benutzerdefiniert'},'vr_panda':{'name':'VR Panda','file':'vr_panda_198x48.json'}}

@lru_cache(maxsize=None)
def preset(key):
    if key not in PRESETS:raise ValueError(tr('Unbekannte Polstervorlage.'))
    entry=PRESETS[key]
    if 'file' not in entry:return entry.copy()
    data=json.loads(Path(__file__).with_name(entry['file']).read_text(encoding='utf-8'))
    outline=np.asarray(data['outline_mm'],dtype=float)
    if outline.ndim!=2 or outline.shape[1]!=2 or not np.isfinite(outline).all():raise ValueError(tr('Ungültige Polsterkontur.'))
    return {**data,'outline':outline}
