
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from google import genai


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = "gemini-3.5-flash-lite"


def get_safe_module_name(file_name):
    """Return a valid Python module name."""
    module_name = Path(file_name).stem

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", module_name):
        return "solution"

    return module_name


def generate_pytest_tests(source_code, file_name):
    """Generate pytest tests using Gemini."""

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check your project .env file."
        )

    if not source_code.strip():
        raise ValueError("Python source code is empty.")

    if len(source_code) > 100000:
        raise ValueError("Source code exceeds 100,000 characters.")

    module_name = get_safe_module_name(file_name)

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are an expert Python software test engineer.

Generate a complete pytest test file for this Python module.

MODULE NAME:
{module_name}

SOURCE CODE:
{source_code}

REQUIREMENTS:

1. Import functions and classes from {module_name}.
2. Generate independent pytest functions beginning with test_.
3. Cover normal inputs, edge cases and invalid inputs where appropriate.
4. Test intended behaviour, not merely reproduce the current implementation.
5. Do not weaken tests to make incorrect code pass.
6. Do not invent requirements that cannot reasonably be inferred.
7. If behaviour is ambiguous, mention the assumption in the explanation.
8. Do not use network access, subprocesses, file deletion or unrelated
   system actions in generated tests.
9. Do not modify the original source code.
10. Do not include Markdown code fences.

Return a JSON object with exactly these fields:

{{
    "test_code": "complete pytest source code",
    "explanation": "short explanation of test cases and assumptions"
}}

Return only valid JSON.
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )

    response_text = getattr(response, "text", None)

    if not response_text:
        raise ValueError("Gemini returned an empty test-generation response.")

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini returned invalid JSON while generating tests."
        ) from error

    test_code = result.get("test_code", "")

    if not isinstance(test_code, str) or not test_code.strip():
        raise ValueError("Gemini did not generate valid pytest code.")

    try:
        tree = ast.parse(test_code)
    except SyntaxError as error:
        raise ValueError(
            f"Generated test code has a syntax error: {error}"
        ) from error

    test_functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]

    if not test_functions:
        raise ValueError("No pytest test functions were generated.")

    return {
        "test_code": test_code,
        "explanation": str(result.get("explanation", ""))
    }


def parse_pytest_counts(output):
    """Extract test result counts from pytest output."""

    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "total": 0
    }

    patterns = {
        "passed": r"(\d+)\s+passed",
        "failed": r"(\d+)\s+failed",
        "errors": r"(\d+)\s+errors?",
        "skipped": r"(\d+)\s+skipped"
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, output, re.IGNORECASE)

        if match:
            counts[key] = int(match.group(1))

    counts["total"] = (
        counts["passed"]
        + counts["failed"]
        + counts["errors"]
        + counts["skipped"]
    )

    return counts


def run_coverage_tests(source_code, file_name, test_code, timeout=60):
    """
    Run pytest with coverage measurement against a temporary copy.

    The original source file is never modified.
    This is not a secure sandbox: Python source and tests execute
    on the computer running this application.
    """

    if not source_code.strip():
        raise ValueError("Python source code is empty.")

    if not test_code.strip():
        raise ValueError("Pytest test code is empty.")

    if len(source_code) > 100000 or len(test_code) > 100000:
        raise ValueError("Source or test code exceeds 100,000 characters.")

    try:
        ast.parse(source_code)
    except SyntaxError as error:
        raise ValueError(
            f"Source code has a syntax error: {error}"
        ) from error

    try:
        test_tree = ast.parse(test_code)
    except SyntaxError as error:
        raise ValueError(
            f"Test code has a syntax error: {error}"
        ) from error

    test_functions = [
        node for node in ast.walk(test_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]

    if not test_functions:
        raise ValueError("The test file contains no test_ functions.")

    module_name = get_safe_module_name(file_name)
    safe_file_name = f"{module_name}.py"

    with tempfile.TemporaryDirectory(
        prefix="debugengage_coverage_"
    ) as temp_dir:

        root = Path(temp_dir)
        tests_dir = root / "tests"
        tests_dir.mkdir()

        source_path = root / safe_file_name
        test_path = tests_dir / "test_generated.py"

        source_path.write_text(source_code, encoding="utf-8")
        test_path.write_text(test_code, encoding="utf-8")

        coverage_data = root / ".coverage"
        coverage_json = root / "coverage.json"

        env = os.environ.copy()
        env["COVERAGE_FILE"] = str(coverage_data)

        existing_pythonpath = env.get("PYTHONPATH", "")

        env["PYTHONPATH"] = (
            str(root)
            + os.pathsep
            + existing_pythonpath
        )

        command = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            f"--source={module_name}",
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            "tests/test_generated.py"
        ]

        try:
            execution = subprocess.run(
                command,
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Test execution exceeded the {timeout}-second timeout."
            )

        except FileNotFoundError:
            raise RuntimeError(
                "Python could not start the coverage command."
            )

        output = (
            (execution.stdout or "")
            + "\n"
            + (execution.stderr or "")
        )

        counts = parse_pytest_counts(output)

        # Generate a machine-readable coverage report.
        coverage_command = [
            sys.executable,
            "-m",
            "coverage",
            "json",
            "-o",
            str(coverage_json)
        ]

        coverage_process = subprocess.run(
            coverage_command,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=30
        )

        coverage_result = {
            "available": False,
            "percent": 0.0,
            "covered_lines": 0,
            "total_lines": 0,
            "missing_lines": [],
            "error": None
        }

        if coverage_process.returncode == 0 and coverage_json.exists():

            try:
                report = json.loads(
                    coverage_json.read_text(encoding="utf-8")
                )

                files = report.get("files", {})

                file_data = None

                for path, data in files.items():
                    if Path(path).name == safe_file_name:
                        file_data = data
                        break

                if file_data is not None:
                    summary = file_data.get("summary", {})

                    total_lines = summary.get("num_statements", 0)
                    covered_lines = summary.get("covered_lines", 0)

                    percent = (
                        summary.get("percent_covered", 0.0)
                        if total_lines
                        else 0.0
                    )

                    coverage_result = {
                        "available": True,
                        "percent": round(float(percent), 2),
                        "covered_lines": covered_lines,
                        "total_lines": total_lines,
                        "missing_lines": file_data.get(
                            "missing_lines", []
                        ),
                        "error": None
                    }

                else:
                    coverage_result["error"] = (
                        "Coverage data for the submitted source file "
                        "was not found."
                    )

            except (ValueError, OSError, TypeError) as error:
                coverage_result["error"] = str(error)

        else:
            coverage_result["error"] = (
                coverage_process.stderr
                or "Coverage report could not be generated."
            )

        passed = counts["passed"]
        failed = counts["failed"]
        errors = counts["errors"]
        skipped = counts["skipped"]

        executed_tests = passed + failed + errors

        pass_percentage = (
            round((passed / executed_tests) * 100, 2)
            if executed_tests
            else 0.0
        )

        return {
            "success": (
                execution.returncode == 0
                and executed_tests > 0
                and failed == 0
                and errors == 0
            ),
            "exit_code": execution.returncode,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "total": counts["total"],
            "pass_percentage": pass_percentage,
            "coverage": coverage_result,
            "output": output
        }
