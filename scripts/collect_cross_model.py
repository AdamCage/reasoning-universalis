"""Explicit separate approval required; no action defaults to a paid request."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--quote", action="store_true")
    parser.add_argument("--export", action="store_true", help="Keyless fixed-roster raw export; never dispatches")
    args = parser.parse_args()
    if args.prepare:
        from cross_model.prepare import prepare
        result = prepare(ROOT)
        print({"prepared": len(result["items"]), "paid_requests": 0})
    if args.quote:
        from cross_model.runner import quote
        result = quote(ROOT)
        print({k: result[k] for k in ("maximum_new_calls", "worst_case_reservation_rub", "authorization")})
    if args.collect:
        from cross_model.runner import Collector
        result = Collector(ROOT).collect()
        print({"planned_cells": len(result)})
    if args.export:
        from cross_model.runner import Collector
        result = Collector(ROOT).export()
        print({"exported_cells": len(result), "paid_requests": 0})
    if not any((args.collect, args.prepare, args.quote, args.export)):
        parser.print_help()


if __name__ == "__main__":
    main()
