import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import diagnose_audio


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", help="Output device name substring.")
    parser.add_argument("--seconds", type=float, default=6.0, help="Test duration.")
    parser.add_argument("--rate", type=int, default=44100, help="Sample rate.")
    parser.add_argument("--channels", type=int, default=2, help="Channels.")
    args = parser.parse_args()

    sys.argv = [
        sys.argv[0],
        "--loopback",
        "--seconds",
        str(args.seconds),
        "--rate",
        str(args.rate),
        "--channels",
        str(args.channels),
    ]
    if args.device:
        sys.argv.extend(["--device", args.device])
    return diagnose_audio.main()


if __name__ == "__main__":
    raise SystemExit(main())
