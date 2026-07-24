#!/usr/bin/env python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mpr_crosslocale.inference.run_cross_locale import main


if __name__ == "__main__":
    main()
