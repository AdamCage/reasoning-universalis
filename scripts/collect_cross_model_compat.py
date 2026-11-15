"""Collect only the never-attempted cells of the frozen transport addendum."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cross_model_compat import Collector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    if args.collect:
        print({"study_cells": len(Collector(ROOT).collect())})
    if args.export:
        print({"exported_cells": len(Collector(ROOT).export()), "paid_requests": 0})
    if not args.collect and not args.export:
        parser.print_help()


if __name__ == "__main__":
    main()
