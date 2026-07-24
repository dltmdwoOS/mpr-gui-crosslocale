#!/usr/bin/env python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mpr_crosslocale.data.build_pilot import main


if __name__ == "__main__":
    main()
