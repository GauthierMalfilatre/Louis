##
## EPITECH PROJECT, 2026
## SENSAI
## File description:
## The metrics of the traces, without louis:  cd src && python -m monitor ../louis.traces.jsonl --open
##
import argparse
import sys
from monitor.recorder import traces_path
from monitor.report import report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m monitor", description="Metrics of the calls louis recorded")
    parser.add_argument("traces", nargs="?", default=None, help="the traces file (default: LOUIS_TRACES, or louis.traces.jsonl here)")
    parser.add_argument("-o", "--output", default=None, help="where to write the dashboard (default: next to the traces)")
    parser.add_argument("--open", action="store_true", help="open the dashboard in the browser")
    args: argparse.Namespace = parser.parse_args()

    sys.exit(report(args.traces or traces_path(), args.output, open_browser=args.open))
