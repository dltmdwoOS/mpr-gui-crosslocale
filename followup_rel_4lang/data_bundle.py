"""CLI wrapper; run from any directory without installing the project first."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_code/src"))

from mpr_crosslocale.data.rel_followup import main

if __name__ == "__main__":
    main()
