
import ast
import re
import sys
import subprocess

from pathlib import Path


# ==================================================
# CONFIGURATION
# ==================================================

DEFAULT_TIMEOUT = 60
MAX_OUTPUT_LENGTH = 100000

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "site-packages",
}


# ==================================================
# RESULT HELPER
# ==================================================

def create_result(
    success=False,
    return_code=-1,
    passed=0,
    failed=0,
    errors=0,
    skipped=0,
    output="",
    timed_out=False,
    no_tests=False,
    failed_test_files=None,
    traceback_files=None,
    imported_source_files=None,
    candidate_source_files=None,
    failure_details=None,
):
    """Create a consistent test result dictionary."""

    return {
        "success": success,
        "return_code": return_code,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "output": str(output)[:MAX_OUTPUT_LENGTH],
        "timed_out": timed_out,
        "no_tests": no_tests,
        "failed_test_files": failed_test_files or [],
        "traceback_files": traceback_files or [],
        "imported_source_files": imported_source_files or [],
        "candidate_source_files": candidate_source_files or [],
        "failure_details": failure_details or [],
    }


# ==================================================
# SINGLE PYTHON FILE VALIDATION
# ==================================================

def validate_python_code(source_code, file_name="solution.py"):
    """
    Validate Python source code without executing it.

    Checks syntax using AST and Python compilation.
    """

    if not isinstance(source_code, str):
        return {
            "success": False,
            "syntax_valid": False,
            "compilation_valid": False,
            "error_type": "InvalidInput",
            "error": "Source code must be a string.",
            "line": None,
            "column": None,
        }

    if not source_code.strip():
        return {
            "success": False,
            "syntax_valid": False,
            "compilation_valid": False,
            "error_type": "EmptyCode",
            "error": "Python source code is empty.",
            "line": None,
            "column": None,
        }

    try:
        ast.parse(source_code, filename=file_name)

        compile(
            source_code,
            file_name,
            "exec",
        )

        return {
            "success": True,
            "syntax_valid": True,
            "compilation_valid": True,
            "error_type": None,
            "error": None,
            "line": None,
            "column": None,
        }

    except SyntaxError as error:
        return {
            "success": False,
            "syntax_valid": False,
            "compilation_valid": False,
            "error_type": "SyntaxError",
            "error": error.msg,
            "line": error.lineno,
            "column": error.offset,
        }

    except (ValueError, TypeError) as error:
        return {
            "success": False,
            "syntax_valid": False,
            "compilation_valid": False,
            "error_type": type(error).__name__,
            "error": str(error),
            "line": None,
            "column": None,
        }


# ==================================================
# PROJECT ROOT DETECTION
# ==================================================

def has_test_files(directory):
    """Check whether a directory contains likely pytest files."""

    directory = Path(directory)

    if not directory.is_dir():
        return False

    if any(
        (directory / name).is_dir()
        for name in ("tests", "test")
    ):
        return True

    if any(
        (directory / name).is_file()
        for name in (
            "pytest.ini",
            "pyproject.toml",
            "tox.ini",
            "setup.cfg",
        )
    ):
        return True

    return (
        any(directory.glob("test_*.py"))
        or any(directory.glob("*_test.py"))
    )


def find_test_root(project_path):
    """
    Find the actual Python project root.

    Supports ZIP files containing one extra top-level folder.
    """

    root = Path(project_path).resolve()

    if not root.is_dir():
        return None

    if has_test_files(root):
        return root

    children = [
        item
        for item in root.iterdir()
        if item.is_dir()
        and item.name not in IGNORED_DIRECTORIES
    ]

    if len(children) == 1:
        child = children[0]

        if has_test_files(child):
            return child

    return root


# ==================================================
# FILE PATH HELPERS
# ==================================================

def is_test_file(path):
    """Identify files that look like pytest test files."""

    name = Path(path).name.lower()

    return (
        name.startswith("test_")
        or name.endswith("_test.py")
    )


def normalize_project_file(file_path, project_root):
    """
    Convert a file path into a safe project-relative path.

    Rejects files outside the project.
    """

    if not file_path:
        return None

    project_root = Path(project_root).resolve()

    cleaned = str(file_path).strip().strip("'\"")

    # Try to resolve the supplied path.
    candidate = Path(cleaned)

    if candidate.is_absolute():
        possible_path = candidate.resolve()
    else:
        possible_path = (project_root / candidate).resolve()

    try:
        relative_path = possible_path.relative_to(project_root)

    except ValueError:
        # Also try interpreting Windows-style paths.
        cleaned = cleaned.replace("\\", "/").lstrip("/")
        possible_path = (project_root / cleaned).resolve()

        try:
            relative_path = possible_path.relative_to(project_root)
        except ValueError:
            return None

    if not possible_path.is_file():
        return None

    if possible_path.suffix.lower() != ".py":
        return None

    if any(
        part.lower() in IGNORED_DIRECTORIES
        for part in relative_path.parts
    ):
        return None

    return relative_path.as_posix()


# ==================================================
# AST-BASED SOURCE FILE DETECTION
# ==================================================

def build_module_map(project_root):
    """
    Build a mapping between Python module names and project files.

    Example:
        calculator.py -> calculator
        helpers/math_utils.py -> helpers.math_utils
    """

    project_root = Path(project_root).resolve()

    module_map = {}

    for file_path in project_root.rglob("*.py"):

        try:
            relative_path = file_path.resolve().relative_to(project_root)
        except ValueError:
            continue

        if any(
            part.lower() in IGNORED_DIRECTORIES
            for part in relative_path.parts
        ):
            continue

        if is_test_file(relative_path):
            continue

        parts = list(relative_path.with_suffix("").parts)

        # Handle Python package __init__.py files.
        if parts[-1] == "__init__":
            parts = parts[:-1]

        if not parts:
            continue

        module_name = ".".join(parts)

        module_map[module_name] = relative_path.as_posix()

    return module_map


def find_imported_source_files(failed_test_files, project_root):
    """
    Identify local Python source files imported by failed test files.

    Supports:
        import calculator
        from calculator import add
        import package.module
        from package import module
        Relative imports within packages.

    Only files found inside the uploaded project are considered.
    """

    project_root = Path(project_root).resolve()

    module_map = build_module_map(project_root)

    imported_files = set()

    for test_file in failed_test_files:

        test_path = Path(test_file)

        absolute_test_path = (
            project_root / test_path
        ).resolve()

        try:
            absolute_test_path.relative_to(project_root)
        except ValueError:
            continue

        if not absolute_test_path.is_file():
            continue

        try:
            source = absolute_test_path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            tree = ast.parse(source)

        except (OSError, SyntaxError):
            continue

        # Determine the package of the test file.
        package_parts = list(test_path.parent.parts)

        for node in ast.walk(tree):

            candidates = []

            # Example: import calculator
            if isinstance(node, ast.Import):

                for alias in node.names:
                    candidates.append(alias.name)

            # Example: from calculator import add
            elif isinstance(node, ast.ImportFrom):

                if node.level > 0:
                    base_parts = package_parts[:]

                    for _ in range(node.level - 1):
                        if base_parts:
                            base_parts.pop()

                    if node.module:
                        base_parts.extend(node.module.split("."))

                    base_module = ".".join(base_parts)

                else:
                    base_module = node.module or ""

                if base_module:
                    candidates.append(base_module)

                # Example: from package import module
                for alias in node.names:

                    if alias.name == "*":
                        continue

                    combined_module = ".".join(
                        part
                        for part in (
                            base_module,
                            alias.name,
                        )
                        if part
                    )

                    if combined_module:
                        candidates.append(combined_module)

            # Match imports against actual project files.
            for candidate in candidates:

                if candidate in module_map:
                    imported_files.add(module_map[candidate])

    return sorted(imported_files)


# ==================================================
# PYTEST FAILURE ANALYSIS
# ==================================================

def parse_failure_details(output, project_root):
    """
    Identify:
    1. Failed test files.
    2. Files mentioned in tracebacks.
    3. Source files imported by failed tests.
    4. Possible source files for Gemini diagnosis.
    """

    output = str(output)

    project_root = Path(project_root).resolve()

    failed_test_files = set()
    traceback_files = set()
    failure_details = []

    # Match pytest summary lines:
    # FAILED tests/test_calculator.py::test_add - AssertionError
    # ERROR tests/test_example.py::test_something - Exception

    failure_pattern = re.compile(
        r"^\s*(FAILED|ERROR)\s+(.+?)(?:\s+-\s+(.+))?$",
        re.IGNORECASE,
    )

    for line in output.splitlines():

        match = failure_pattern.match(line)

        if not match:
            continue

        status = match.group(1).upper()

        test_identifier = match.group(2).strip()

        error_message = (
            match.group(3).strip()
            if match.group(3)
            else ""
        )

        test_file = test_identifier.split("::")[0]

        normalized_test_file = normalize_project_file(
            test_file,
            project_root,
        )

        if normalized_test_file:
            failed_test_files.add(normalized_test_file)

        failure_details.append({
            "status": status,
            "test": test_identifier,
            "test_file": normalized_test_file,
            "message": error_message,
        })

    # Find Python file paths in traceback output.
    path_patterns = [
        re.compile(r'File "([^"]+\.py)"'),

        re.compile(
            r'((?:[A-Za-z]:)?[\\/][^\s:()]+\.py)(?::\d+)?'
        ),

        re.compile(
            r'([A-Za-z0-9_.-]+(?:[\\/][A-Za-z0-9_.-]+)*\.py)'
            r'(?::\d+)?'
        ),
    ]

    for line in output.splitlines():

        for pattern in path_patterns:

            for match in pattern.finditer(line):

                normalized_path = normalize_project_file(
                    match.group(1),
                    project_root,
                )

                if normalized_path:
                    traceback_files.add(normalized_path)

    # Identify source files imported by failed test files.
    imported_source_files = find_imported_source_files(
        sorted(failed_test_files),
        project_root,
    )

    # Combine traceback files and AST-based imported files.
    candidate_source_files = sorted(
        file_path
        for file_path in (
            traceback_files.union(imported_source_files)
        )
        if not is_test_file(file_path)
    )

    return {
        "failed_test_files": sorted(failed_test_files),
        "traceback_files": sorted(traceback_files),
        "imported_source_files": imported_source_files,
        "candidate_source_files": candidate_source_files,
        "failure_details": failure_details,
    }


# ==================================================
# PYTEST RESULT PARSING
# ==================================================

def parse_pytest_output(output):
    """Extract pytest result counts from terminal output."""

    output = str(output)

    patterns = {
        "passed": r"\b(\d+)\s+passed\b",
        "failed": r"\b(\d+)\s+failed\b",
        "errors": r"\b(\d+)\s+errors?\b",
        "skipped": r"\b(\d+)\s+skipped\b",
    }

    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
    }

    for key, pattern in patterns.items():

        matches = re.findall(
            pattern,
            output,
            flags=re.IGNORECASE,
        )

        if matches:
            counts[key] = int(matches[-1])

    no_tests = (
        "no tests ran" in output.lower()
        or "no tests collected" in output.lower()
    )

    return counts, no_tests


# ==================================================
# PROJECT TEST EXECUTION
# ==================================================

def run_tests(project_path, timeout=DEFAULT_TIMEOUT):
    """
    Run pytest for an uploaded Python project.

    Supports:
    - Standard Python projects.
    - Projects with tests/ or test/ directories.
    - Projects with one nested top-level folder.
    - Individual Python test files.

    WARNING:
    Pytest executes Python code. This is not a security sandbox.
    Only run trusted projects.
    """

    project_path = Path(project_path).resolve()

    if not project_path.exists():
        return create_result(
            output="Project path does not exist.",
            errors=1,
        )

    if project_path.is_file():

        if project_path.suffix.lower() != ".py":
            return create_result(
                output="Only Python files can be tested.",
                errors=1,
            )

        test_target = project_path
        root = project_path.parent

    elif project_path.is_dir():

        root = find_test_root(project_path)

        if root is None:
            return create_result(
                output="Project directory not found.",
                errors=1,
            )

        test_target = None

    else:
        return create_result(
            output="Invalid project path.",
            errors=1,
        )

    if timeout <= 0:
        return create_result(
            output="Timeout must be greater than zero.",
            errors=1,
        )

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--tb=short",
        "--color=no",
    ]

    if test_target is not None:
        command.append(str(test_target))

    try:

        process = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
            shell=False,
        )

        output = (
            process.stdout
            + "\n"
            + process.stderr
        )

        counts, no_tests = parse_pytest_output(output)

        passed = counts["passed"]
        failed = counts["failed"]
        errors = counts["errors"]
        skipped = counts["skipped"]

        has_results = (
            passed + failed + errors + skipped > 0
        )

        success = (
            process.returncode == 0
            and has_results
            and not no_tests
            and failed == 0
            and errors == 0
        )

        if no_tests:

            output += (
                "\n\nNo tests were collected. "
                "The project was not considered successfully validated."
            )

        elif not has_results:

            output += (
                "\n\nPytest did not report any collected test results."
            )

            no_tests = True

        # Perform automatic failure analysis.
        failure_analysis = parse_failure_details(
            output,
            root,
        )

        return create_result(
            success=success,
            return_code=process.returncode,
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            output=output,
            timed_out=False,
            no_tests=no_tests,
            failed_test_files=failure_analysis[
                "failed_test_files"
            ],
            traceback_files=failure_analysis[
                "traceback_files"
            ],
            imported_source_files=failure_analysis[
                "imported_source_files"
            ],
            candidate_source_files=failure_analysis[
                "candidate_source_files"
            ],
            failure_details=failure_analysis[
                "failure_details"
            ],
        )

    except subprocess.TimeoutExpired as error:

        stdout = error.stdout or ""
        stderr = error.stderr or ""

        if isinstance(stdout, bytes):
            stdout = stdout.decode(
                "utf-8",
                errors="replace",
            )

        if isinstance(stderr, bytes):
            stderr = stderr.decode(
                "utf-8",
                errors="replace",
            )

        output = (
            str(stdout)
            + "\n"
            + str(stderr)
            + f"\n\nTest execution exceeded {timeout} seconds."
        )

        return create_result(
            output=output,
            errors=1,
            timed_out=True,
        )

    except OSError as error:

        return create_result(
            output=f"Could not execute pytest: {error}",
            errors=1,
        )

    except Exception as error:

        return create_result(
            output=f"Unexpected test execution error: {error}",
            errors=1,
        )


# ==================================================
# MODULE TEST
# ==================================================

if __name__ == "__main__":

    print("Agentic AI Test Runner Ready")
    print("Supports Python syntax validation.")
    print("Supports Python compilation validation.")
    print("Supports pytest project execution.")
    print("Supports automatic failed test identification.")
    print("Supports traceback file detection.")
    print("Supports AST-based import analysis.")
    print("Supports candidate source file identification.")
    print("Default timeout:", DEFAULT_TIMEOUT, "seconds")
