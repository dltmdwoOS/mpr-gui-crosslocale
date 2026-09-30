"""Standalone batch-size experiment; does not launch full inference."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_code/src"))

from mpr_crosslocale.inference.benchmark_rel_batch import main

if __name__ == "__main__":
    main()
