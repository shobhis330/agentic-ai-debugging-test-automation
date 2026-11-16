import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
MODEL_NAME = "gemini-3.5-flash-lite"


def get_safe_module_name(file_name):
    """Derive the importable module name from the selected source filename."""
    stem = Path(str(file_name)).stem
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", stem):
        return "solution"
    return stem


def generate_pytest_tests(source_code, file_name):
    """Generate pytest tests using Gemini."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing. Check your project .env file.")
    if not isinstance(source_code, str) or not source_code.strip():
        raise ValueError("Python source code is empty.")
    if len(source_code) > 100000:
        raise ValueError("Source code exceeds 100,000 characters.")

    module_name = get_safe_module_name(file_name)

    try:
        from google import genai
    except ImportError as error:
        raise RuntimeError(
            "The Gemini SDK is not installed. Run: pip install google-genai"
        ) from error

    client = genai.Client(api_key=api_key)

    prompt = f"""You are an expert Python software test engineer.
Generate a complete pytest test file for this Python module.
MODULE NAME: {module_name}
SOURCE CODE:
{source_code}
Requirements:
- Import functions/classes from {module_name}.
- Use independent functions named test_*.
- Cover normal, edge and invalid inputs where reasonable.
- Test intended behaviour, not the current buggy implementation.
- Do not weaken tests to make incorrect code pass.
- Do not use network, subprocesses, deletion, or unrelated system actions.
- Do not modify source code.
Return only a JSON object with exactly test_code and explanation. test_code must be complete Python source without Markdown fences."""

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

    if not any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name.startswith("test_")
        for n in ast.walk(tree)
    ):
        raise ValueError("No pytest test functions were generated.")

    return {
        "test_code": test_code,
        "explanation": str(result.get("explanation", ""))
    }


def parse_pytest_counts(output):
    """Parse pytest's final numeric summary, ignoring later stderr messages."""
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "total": 0,
    }

    summary_pattern = re.compile(
        r"(?im)^\s*(?P<body>(?:\d+\s+(?:passed|failed|errors?|skipped)"
        r"(?:,\s*)?\s*)+)(?:in\s+[0-9.]+s)?\s*$"
    )
    matches = list(summary_pattern.finditer(str(output)))
    summary = matches[-1].group("body") if matches else ""

    for key, pattern in {
        "passed": r"(\d+)\s+passed\b",
        "failed": r"(\d+)\s+failed\b",
        "errors": r"(\d+)\s+errors?\b",
        "skipped": r"(\d+)\s+skipped\b",
    }.items():
        match = re.search(pattern, summary, re.I)
        if match:
            counts[key] = int(match.group(1))

    counts["total"] = sum(
        counts[key] for key in ("passed", "failed", "errors", "skipped")
    )
    return counts


def run_coverage_tests(
    source_code,
    file_name,
    test_code,
    timeout=60,
    project_root=None,
    source_rel_path=None,
    test_rel_path=None,
):
    """Run pytest with the selected source and its sibling project modules.

    When project_root is supplied, all safe Python files are staged into an
    isolated temporary workspace so imports such as ``from pricing import ...``
    continue to work. Only the selected source and selected test file are
    replaced; the user's project is never modified.
    """
    import shutil

    if not isinstance(source_code, str) or not source_code.strip():
        raise ValueError("Python source code is empty.")
    if not isinstance(test_code, str) or not test_code.strip():
        raise ValueError("Pytest test code is empty.")
    if len(source_code) > 100000 or len(test_code) > 100000:
        raise ValueError("Source or test code exceeds 100,000 characters.")

    try:
        ast.parse(source_code, filename=str(file_name))
        test_tree = ast.parse(test_code, filename="test_generated.py")
    except SyntaxError as error:
        raise ValueError(f"Python syntax error: {error}") from error

    if not any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name.startswith("test_")
        for n in ast.walk(test_tree)
    ):
        raise ValueError("The test file contains no test_ functions.")

    module_name = get_safe_module_name(file_name)

    def safe_relative(value, fallback):
        candidate = Path(value).as_posix() if value else fallback
        pure = Path(candidate)
        if pure.is_absolute() or ".." in pure.parts:
            raise ValueError("Project file path must stay inside the project folder.")
        if pure.suffix.lower() != ".py":
            raise ValueError("Project source and test paths must end in .py.")
        return pure

    source_relative = safe_relative(source_rel_path, f"{module_name}.py")
    test_relative = safe_relative(test_rel_path, "tests/test_generated.py")

    with tempfile.TemporaryDirectory(prefix="debugengage_coverage_") as temp_dir:
        root = Path(temp_dir)

        if project_root:
            project = Path(project_root).resolve()
            if not project.is_dir():
                raise ValueError("The shared project folder no longer exists.")
            excluded = {
                ".git", ".venv", "venv", "env", "node_modules",
                "__pycache__", ".pytest_cache", ".mypy_cache",
                ".ruff_cache", "dist", "build", "htmlcov",
            }
            for candidate in project.rglob("*.py"):
                relative = candidate.relative_to(project)
                if any(part.lower() in excluded for part in relative.parts):
                    continue
                if candidate.is_symlink():
                    continue
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(candidate, destination)

        source_path = root / source_relative
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(source_code, encoding="utf-8")

        test_path = root / test_relative
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(test_code, encoding="utf-8")

        coverage_data = root / ".coverage"
        coverage_json = root / "coverage.json"
        env = os.environ.copy()
        env["COVERAGE_FILE"] = str(coverage_data)
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) + (os.pathsep + old_pythonpath if old_pythonpath else "")

        command = [
            sys.executable, "-m", "coverage", "run", "--branch",
            f"--source={module_name}", "-m", "pytest", "-q",
            "--tb=short", "--color=no", str(test_relative),
        ]
        try:
            execution = subprocess.run(
                command, cwd=str(root), env=env, capture_output=True,
                text=True, timeout=timeout, errors="replace",
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"Test execution exceeded the {timeout}-second timeout."
            ) from error
        except FileNotFoundError as error:
            raise RuntimeError(
                "Python could not start pytest/coverage. Install pytest and coverage."
            ) from error

        output = (execution.stdout or "") + "\n" + (execution.stderr or "")
        counts = parse_pytest_counts(output)

        coverage_result = {
            "available": False, "percent": 0.0, "covered_lines": 0,
            "total_lines": 0, "missing_lines": [], "error": None,
        }
        coverage_process = subprocess.run(
            [sys.executable, "-m", "coverage", "json", "-o", str(coverage_json)],
            cwd=str(root), env=env, capture_output=True, text=True,
            timeout=30, errors="replace",
        )
        if coverage_process.returncode == 0 and coverage_json.exists():
            try:
                report = json.loads(coverage_json.read_text(encoding="utf-8"))
                file_data = next(
                    (data for path, data in report.get("files", {}).items()
                     if str(path).replace("\\\\", "/").endswith(source_relative.as_posix())),
                    None,
                )
                if file_data is not None:
                    summary = file_data.get("summary", {})
                    coverage_result = {
                        "available": True,
                        "percent": round(float(summary.get("percent_covered", 0.0)), 2),
                        "covered_lines": int(summary.get("covered_lines", 0)),
                        "total_lines": int(summary.get("num_statements", 0)),
                        "missing_lines": file_data.get("missing_lines", []),
                        "error": None,
                    }
                else:
                    coverage_result["error"] = (
                        f"Coverage data for {source_path.as_posix()} was not found. "
                        "Confirm that the tests import the selected source module."
                    )
            except (ValueError, OSError, TypeError) as error:
                coverage_result["error"] = str(error)
        else:
            coverage_result["error"] = (
                coverage_process.stderr or coverage_process.stdout
                or "Coverage report could not be generated."
            )

        total = counts["total"]
        return {
            "success": (
                execution.returncode == 0 and total > 0
                and counts["failed"] == 0 and counts["errors"] == 0
            ),
            "return_code": execution.returncode,
            "passed": counts["passed"], "failed": counts["failed"],
            "errors": counts["errors"], "skipped": counts["skipped"],
            "total": total,
            "pass_percentage": round(counts["passed"] / total * 100, 2) if total else 0.0,
            "output": output, "coverage": coverage_result,
            "module_name": module_name,
        }
