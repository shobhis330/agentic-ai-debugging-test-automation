
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def _module_name(file_name):
    name = Path(file_name).stem
    name = re.sub(r"\W+", "_", name)

    if not name or name[0].isdigit():
        name = f"module_{name}"

    return name


def _parse_results(output):
    patterns = {
        "passed": r"(\d+)\s+passed",
        "failed": r"(\d+)\s+failed",
        "errors": r"(\d+)\s+errors?",
        "skipped": r"(\d+)\s+skipped",
        "warnings": r"(\d+)\s+warnings?"
    }

    counts = {}

    for key, pattern in patterns.items():
        match = re.search(pattern, output, re.IGNORECASE)
        counts[key] = int(match.group(1)) if match else 0

    total = (
        counts["passed"]
        + counts["failed"]
        + counts["errors"]
        + counts["skipped"]
    )

    counts["total"] = total
    counts["success_rate"] = (
        round(counts["passed"] / total * 100, 2)
        if total else 0
    )

    return counts


def run_test_comparison(
    source_code,
    test_code,
    file_name="target.py",
    timeout=60
):
    """
    Execute the same pytest file against one source-code version.
    Uploaded source and tests execute on the host machine.
    """

    if not source_code or not source_code.strip():
        return {
            "success": False,
            "error": "Source code is empty."
        }

    if not test_code or not test_code.strip():
        return {
            "success": False,
            "error": "Test code is empty."
        }

    module_name = _module_name(file_name)

    try:
        with tempfile.TemporaryDirectory(prefix="debug_compare_") as temp:
            workspace = Path(temp)
            tests_dir = workspace / "tests"
            tests_dir.mkdir()

            source_path = workspace / f"{module_name}.py"
            test_path = tests_dir / "test_comparison.py"

            source_path.write_text(source_code, encoding="utf-8")
            test_path.write_text(test_code, encoding="utf-8")

            environment = os.environ.copy()
            old_pythonpath = environment.get("PYTHONPATH", "")

            environment["PYTHONPATH"] = (
                str(workspace)
                + os.pathsep
                + old_pythonpath
            )

            command = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--tb=short",
                str(test_path)
            ]

            try:
                process = subprocess.run(
                    command,
                    cwd=str(workspace),
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "error": f"Tests exceeded the {timeout}-second time limit."
                }

            output = process.stdout + "\n" + process.stderr
            counts = _parse_results(output)

            return {
                "success": process.returncode == 0,
                "return_code": process.returncode,
                "counts": counts,
                "output": output,
                "module_name": module_name
            }

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc)
        }


def compare_versions(
    original_code,
    corrected_code,
    test_code,
    file_name="target.py"
):
    """Run identical tests against original and corrected code."""

    original = run_test_comparison(
        original_code,
        test_code,
        file_name
    )

    corrected = run_test_comparison(
        corrected_code,
        test_code,
        file_name
    )

    if not original.get("counts") or not corrected.get("counts"):
        return {
            "success": False,
            "original": original,
            "corrected": corrected,
            "error": "Could not compare both versions. Check the execution outputs."
        }

    original_counts = original["counts"]
    corrected_counts = corrected["counts"]

    return {
        "success": True,
        "original": original,
        "corrected": corrected,
        "comparison": {
            "passed_change": (
                corrected_counts["passed"] - original_counts["passed"]
            ),
            "failed_change": (
                corrected_counts["failed"] - original_counts["failed"]
            ),
            "original_success_rate": original_counts["success_rate"],
            "corrected_success_rate": corrected_counts["success_rate"],
            "improved": (
                corrected_counts["passed"] > original_counts["passed"]
                or corrected_counts["failed"] < original_counts["failed"]
            )
        }
    }
