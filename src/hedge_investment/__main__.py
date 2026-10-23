"""Run a portfolio comparison from JSON."""

import argparse
import json
from pathlib import Path

from .io import load_comparison


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    example_input = project_root / "examples" / "portfolio_comparison.json"

    parser = argparse.ArgumentParser(
        description="Compare defensive and aggressive portfolio scenarios from JSON."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=str(example_input),
        help="input JSON file (defaults to the fictional example in examples/)",
    )
    args = parser.parse_args()

    try:
        result = load_comparison(args.input)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
