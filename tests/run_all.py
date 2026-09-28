"""Run every check: saved puzzles, explanation trail, UI smoke test, and the
hard puzzle set (every 5th puzzle unless --full).

    python tests/run_all.py [--full]
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    full = "--full" in sys.argv
    runs = [["check_saved.py"], ["check_trail.py"], ["ui_smoke.py"],
            ["check_hard.py"] + ([] if full else ["--every", "5"])]
    failed = []
    for args in runs:
        print(f"\n=== {' '.join(args)} ===", flush=True)
        t = time.time()
        code = subprocess.call([sys.executable, os.path.join(HERE, args[0]), *args[1:]], cwd=HERE)
        print(f"--- {args[0]}: {'ok' if code == 0 else 'FAILED'} ({time.time() - t:.0f}s)", flush=True)
        if code:
            failed.append(args[0])
    print("\nALL OK" if not failed else f"\nFAILED: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
