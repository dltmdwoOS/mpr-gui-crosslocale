"""Clear entry point for the final RQ4 contextual intervention.

The underlying runner remains backward-compatible with archived NLLB inputs so that
the failed engineering pilot is reproducible, while this module is the documented v4
entry point.
"""

from mpr_crosslocale.inference.run_rel_nllb_intervention import main

if __name__ == "__main__":
    main()
