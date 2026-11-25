"""Shared constants. Run scripts from the repo root, e.g. `python -m part_a.train`."""
from pathlib import Path

SEED = 42
ROOT = Path(__file__).parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"
