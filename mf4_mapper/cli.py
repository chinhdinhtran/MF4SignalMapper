from __future__ import annotations

import argparse
import logging
import sys

from .pipeline import ConversionPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Map DBC signals into a raw CAN MF4 without removing raw data."
    )
    parser.add_argument("--mf4", required=True, help="Input raw MF4")
    parser.add_argument("--dbc", required=True, help="One common CAN DBC")
    parser.add_argument("--output", required=True, help="Output mapped MF4")
    parser.add_argument(
        "--config",
        required=True,
        help="JSON channel marker mapping configuration",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    try:
        pipeline = ConversionPipeline(args.config)
        report = pipeline.convert(args.mf4, args.dbc, args.output)

        print("\n=== Conversion summary ===")
        for assignment in report.channels:
            markers = ", ".join(f"0x{x:X}" for x in assignment.matched_ids) or "-"
            print(
                f"CAN{assignment.channel}: "
                f"{assignment.status}, "
                f"network={assignment.logical_name or 'CAN' + str(assignment.channel)}, "
                f"markers={markers}"
            )
        print(f"Decoded groups : {report.decoded_groups}")
        print(f"Decoded signals: {report.decoded_signals}")
        print(f"Output         : {report.output_file}")
        return 0
    except Exception as exc:
        logging.exception("Conversion failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
