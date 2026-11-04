
import re
import sys
import subprocess
from pathlib import Path


def find_test_root(project_path):
    """
    Find the actual Python project root.
    Supports ZIP files containing one extra top-level folder.
    """

    root = Path(project_path).resolve()

    if not root.is_dir():
        return None

    # If tests exist directly in the extracted folder,
    # use that folder.
    if (
        (root / "tests").is_dir()
        or (root / "pytest.ini").exists()
        or (root / "pyproject.toml").exists()
        or list(root.glob("test_*.py"))
    ):
        return root

    # Otherwise check for a single nested project folder.
    children = [
        item for item in root.iterdir()
        if item.is_dir()
        and item.name not in {
            ".git", ".venv", "venv",
            "__pycache__", "node_modules"
        }
    ]

    if len(children) == 1:
        child = children[0]

        if (
            (child / "tests").is_dir()
            or (child / "pytest.ini").exists()
            or (child / "pyproject.toml").exists()
            or list(child.glob("test_*.py"))
        ):
            return child

    return root


def run_tests(project_path, timeout=60):

    root = find_test_root(project_path)

    if root is None:
        return {
            "success": False,
            "return_code": -1,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
            "output": "Project directory not found.",
            "timed_out": False
        }

    try:

        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--tb=short"
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace"
        )

        output = process.stdout + "\n" + process.stderr

        passed = 0
        failed = 0
        errors = 0
        skipped = 0

        patterns = {
            "passed": r"(\d+)\s+passed",
            "failed": r"(\d+)\s+failed",
            "errors": r"(\d+)\s+errors?",
            "skipped": r"(\d+)\s+skipped"
        }

        for key, pattern in patterns.items():

            match = re.search(pattern, output)

            if match:
                if key == "passed":
                    passed = int(match.group(1))
                elif key == "failed":
                    failed = int(match.group(1))
                elif key == "errors":
                    errors = int(match.group(1))
                elif key == "skipped":
                    skipped = int(match.group(1))

        # Detect pytest collection errors and zero-test runs.
        no_tests = (
            "no tests ran" in output.lower()
            or "no tests collected" in output.lower()
        )

        has_results = (
            passed + failed + errors + skipped > 0
        )

        if not has_results:
            errors += 1

        success = (
            process.returncode == 0
            and passed + failed + errors > 0
            and failed == 0
            and errors == 0
            and not no_tests
        )

        return {
            "success": success,
            "return_code": process.returncode,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "output": output,
            "timed_out": False
        }

    except subprocess.TimeoutExpired as error:

        return {
            "success": False,
            "return_code": -1,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
            "output": str(error),
            "timed_out": True
        }

    except OSError as error:

        return {
            "success": False,
            "return_code": -1,
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
            "output": str(error),
            "timed_out": False
        }
