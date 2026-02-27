"""Prototype hybrid clinical coder against surface-form JSONL.

Delegates to prototype_clinical_coder_v2 (the active implementation).
Iterations 1-3 that were previously inlined here have been removed.
"""

if __name__ == "__main__":
    from prototype_clinical_coder_v2 import main as _main

    _main()
    raise SystemExit(0)
