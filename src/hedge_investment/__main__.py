"""Run a portfolio comparison from JSON."""

import argparse
import json
from pathlib import Path

from .ai_explainer import AIConfigurationError, explain_comparison
from .io import load_analysis_input
from .sec_edgar import SecDataError, fetch_company_facts


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
    parser.add_argument(
        "--explain",
        action="store_true",
        help="append a grounded explanation from the hackathon Azure OpenAI endpoint",
    )
    parser.add_argument(
        "--sec-data",
        action="store_true",
        help="fetch the latest public SEC company facts for holdings before explaining",
    )
    args = parser.parse_args()

    try:
        result, client_profile, cik_by_ticker = load_analysis_input(args.input)
        public_facts = None
        if args.sec_data:
            if not args.explain:
                parser.error("--sec-data requires --explain so the retrieved facts can be analysed.")
            tickers = list(dict.fromkeys(
                holding["ticker"]
                for portfolio in result["portfolios"]
                for holding in portfolio["holdings"]
            ))
            public_facts = fetch_company_facts(tickers, cik_by_ticker)
    except (OSError, ValueError, SecDataError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    if args.explain:
        try:
            explanation = explain_comparison(result, client_profile, public_facts)
        except AIConfigurationError as exc:
            parser.error(str(exc))
        print("\nAI research explanation\n-----------------------\n")
        print(explanation)


if __name__ == "__main__":
    main()
