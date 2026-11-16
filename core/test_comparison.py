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
    """Parse pytest's terminal summary rather than incidental traceback text."""
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "warnings": 0
    }

    lines = [
        line.strip()
        for line in str(output).splitlines()
        if re.search(
            r"\b(in|passed|failed|error|errors|skipped|warnings?)\b",
            line,
            re.I
        )
    ]

    summary = lines[-1] if lines else ""

    for key, pattern in {
        "passed": r"(\d+)\s+passed\b",
        "failed": r"(\d+)\s+failed\b",
        "errors": r"(\d+)\s+errors?\b",
        "skipped": r"(\d+)\s+skipped\b",
        "warnings": r"(\d+)\s+warnings?\b",
    }.items():

        match = re.search(pattern, summary, re.I)

        if match:
            counts[key] = int(match.group(1))

    counts["total"] = sum(
        counts[k]
        for k in ("passed", "failed", "errors", "skipped")
    )

    counts["success_rate"] = (
        round(
            counts["passed"] / counts["total"] * 100,
            2
        )
        if counts["total"]
        else 0.0
    )

    return counts


def run_test_comparison(
    source_code,
    test_code,
    file_name="target.py",
    timeout=60,
    project_root=None,
    source_rel_path=None,
    test_rel_path=None,
):
    """Execute one code version with its sibling modules and the same tests."""
    import shutil

    if not isinstance(source_code, str) or not source_code.strip():
        return {"success": False, "error": "Source code is empty."}
    if not isinstance(test_code, str) or not test_code.strip():
        return {"success": False, "error": "Test code is empty."}

    module_name = _module_name(file_name)

    def safe_relative(value, fallback):
        candidate = Path(value) if value else Path(fallback)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("Project file path must stay inside the project folder.")
        if candidate.suffix.lower() != ".py":
            raise ValueError("Project source and test paths must end in .py.")
        return candidate

    try:
        source_relative = safe_relative(source_rel_path, f"{module_name}.py")
        test_relative = safe_relative(test_rel_path, "tests/test_comparison.py")

        with tempfile.TemporaryDirectory(prefix="debug_compare_") as temp:
            workspace = Path(temp)

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
                    destination = workspace / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate, destination)

            source_path = workspace / source_relative
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(source_code, encoding="utf-8")

            test_path = workspace / test_relative
            test_path.parent.mkdir(parents=True, exist_ok=True)
            test_path.write_text(test_code, encoding="utf-8")

            environment = os.environ.copy()
            old_pythonpath = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = (
                str(workspace) + (os.pathsep + old_pythonpath if old_pythonpath else "")
            )
            command = [
                sys.executable, "-m", "pytest", "-q", "--tb=short", "--color=no",
                str(test_relative),
            ]
            process = subprocess.run(
                command, cwd=str(workspace), env=environment,
                capture_output=True, text=True, timeout=timeout,
                errors="replace",
            )
            output = (process.stdout or "") + "\n" + (process.stderr or "")
            counts = _parse_results(output)
            return {
                "success": process.returncode == 0,
                "return_code": process.returncode,
                "counts": counts,
                "output": output,
                "module_name": module_name,
            }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Tests exceeded the {timeout}-second time limit."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def compare_versions(
    original_code,
    corrected_code,
    test_code,
    file_name="target.py",
    project_root=None,
    source_rel_path=None,
    test_rel_path=None,
):
    """Run identical tests against original and corrected project versions."""
    common = {
        "file_name": file_name,
        "project_root": project_root,
        "source_rel_path": source_rel_path,
        "test_rel_path": test_rel_path,
    }
    original = run_test_comparison(original_code, test_code, **common)
    corrected = run_test_comparison(corrected_code, test_code, **common)

    if not original.get("counts") or not corrected.get("counts"):
        return {
            "success": False, "original": original, "corrected": corrected,
            "error": "Could not compare both versions. Check the execution outputs.",
        }

    original_counts = original["counts"]
    corrected_counts = corrected["counts"]
    return {
        "success": True,
        "original": original,
        "corrected": corrected,
        "comparison": {
            "passed_change": corrected_counts["passed"] - original_counts["passed"],
            "failed_change": corrected_counts["failed"] - original_counts["failed"],
            "original_success_rate": original_counts["success_rate"],
            "corrected_success_rate": corrected_counts["success_rate"],
            "improved": (
                corrected_counts["passed"] > original_counts["passed"]
                or corrected_counts["failed"] < original_counts["failed"]
            ),
        },
    }
