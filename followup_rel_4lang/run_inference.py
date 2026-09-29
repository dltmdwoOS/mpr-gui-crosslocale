"""REL O/R/C/F entry point, reusing the repository model adapters."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01_code/src"))

from mpr_crosslocale.inference.run_rel_followup import main

if __name__ == "__main__":
    main()
