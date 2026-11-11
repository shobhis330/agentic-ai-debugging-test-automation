
import argparse
from debugging_agent import repair_case, run_all

parser = argparse.ArgumentParser(
    description="Agentic AI Python Debugging and Test Automation"
)
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--case", choices=["TC01", "TC02", "TC03"])
group.add_argument("--all", action="store_true")

args = parser.parse_args()

if args.all:
    success = run_all()
else:
    result = repair_case(args.case)
    success = result["status"] == "PASS"

raise SystemExit(0 if success else 1)
