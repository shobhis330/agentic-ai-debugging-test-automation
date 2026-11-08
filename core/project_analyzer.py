
import ast
import sys
from pathlib import Path

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

EXCLUDED_DIRS = {
    ".venv",
    "venv",
    "env",
    ".git",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "site-packages",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

MAX_FILE_SIZE = 500_000

DEPENDENCY_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "pipfile",
    "pipfile.lock",
    "poetry.lock",
    "uv.lock",
    "pdm.lock",
    "environment.yml",
    "environment.yaml",
    "conda.yaml",
}

ENTRY_POINT_NAMES = {
    "main.py",
    "app.py",
    "run.py",
    "server.py",
    "manage.py",
}

TEST_DIRECTORY_NAMES = {
    "test",
    "tests",
}

STANDARD_LIBRARY = getattr(
    sys,
    "stdlib_module_names",
    set()
)


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def is_excluded(path):
    """Check whether a file belongs to an excluded directory."""

    return any(
        part.lower() in EXCLUDED_DIRS
        for part in path.parts
    )


def is_test_file(file_path, relative_path):
    """Identify common Python test file patterns."""

    name = file_path.name.lower()

    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or any(
            part.lower() in TEST_DIRECTORY_NAMES
            for part in relative_path.parts
        )
    )


def detect_project_type(root, python_files, dependency_files):
    """Identify the likely type of Python project."""

    all_names = {
        path.name.lower()
        for path in root.iterdir()
    }

    directory_names = {
        path.name.lower()
        for path in root.iterdir()
        if path.is_dir()
    }

    if "manage.py" in all_names:
        return "Django Web Application"

    if "app.py" in all_names and "streamlit" in str(
        dependency_files
    ).lower():
        return "Streamlit Application"

    if "fastapi" in str(dependency_files).lower():
        return "FastAPI Application"

    if "flask" in str(dependency_files).lower():
        return "Flask Application"

    if "notebooks" in directory_names:
        return "Data Science / Machine Learning Project"

    if "models" in directory_names and (
        "data" in directory_names
        or "datasets" in directory_names
    ):
        return "Machine Learning Project"

    if "tests" in directory_names or "test" in directory_names:
        return "Python Application with Tests"

    if python_files:
        return "General Python Project"

    return "Unknown Project Type"


def classify_imports(imports, local_modules):
    """Classify imports into standard, local and third-party."""

    categories = {
        "standard_library": [],
        "third_party": [],
        "local": [],
    }

    for module in sorted(imports):

        if module in STANDARD_LIBRARY:
            categories["standard_library"].append(module)

        elif module in local_modules:
            categories["local"].append(module)

        else:
            categories["third_party"].append(module)

    return categories


# --------------------------------------------------
# MAIN PROJECT ANALYZER
# --------------------------------------------------

def analyze_project(project_path):
    """
    Analyze a Python project.

    Detects:
    - Python source files
    - Test files
    - Imports
    - Import categories
    - Dependency files
    - Syntax errors
    - Unreadable files
    - Large files skipped during analysis
    - Project type
    - Common entry points
    - Project structure
    """

    root = Path(project_path).resolve()

    if not root.exists() or not root.is_dir():
        raise ValueError(
            f"Invalid project directory: {root}"
        )

    python_files = []
    test_files = []
    imports = set()
    dependencies = []
    syntax_errors = []
    unreadable_files = []
    large_files = []
    entry_points = []
    analysis_warnings = []

    # ------------------------------------------------
    # DISCOVER PROJECT FILES
    # ------------------------------------------------

    for file_path in root.rglob("*"):

        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(root)

        if is_excluded(relative_path):
            continue

        # --------------------------------------------
        # DEPENDENCY FILE DETECTION
        # --------------------------------------------

        if file_path.name.lower() in DEPENDENCY_FILES:
            relative_name = str(relative_path)

            if relative_name not in dependencies:
                dependencies.append(relative_name)

        # --------------------------------------------
        # PYTHON FILE DETECTION
        # --------------------------------------------

        if file_path.suffix.lower() != ".py":
            continue

        try:
            file_size = file_path.stat().st_size

        except OSError as error:
            unreadable_files.append({
                "file": str(relative_path),
                "error": str(error),
            })
            continue

        if file_size > MAX_FILE_SIZE:
            large_files.append({
                "file": str(relative_path),
                "size_bytes": file_size,
                "message": "File skipped because it exceeds 500 KB.",
            })
            continue

        try:
            source = file_path.read_text(
                encoding="utf-8-sig"
            )

        except (UnicodeDecodeError, OSError) as error:
            unreadable_files.append({
                "file": str(relative_path),
                "error": str(error),
            })
            continue

        relative_name = str(relative_path)

        python_files.append(relative_name)

        # --------------------------------------------
        # TEST FILE DETECTION
        # --------------------------------------------

        if is_test_file(file_path, relative_path):
            test_files.append(relative_name)

        # --------------------------------------------
        # ENTRY POINT DETECTION
        # --------------------------------------------

        if file_path.name.lower() in ENTRY_POINT_NAMES:
            entry_points.append(relative_name)

        # --------------------------------------------
        # SYNTAX AND IMPORT ANALYSIS
        # --------------------------------------------

        try:
            tree = ast.parse(
                source,
                filename=relative_name
            )

            for node in ast.walk(tree):

                if isinstance(node, ast.Import):

                    for alias in node.names:
                        module = alias.name.split(".")[0]

                        if module:
                            imports.add(module)

                elif isinstance(node, ast.ImportFrom):

                    if node.module:
                        module = node.module.split(".")[0]

                        if module:
                            imports.add(module)

                    elif node.level:
                        # Relative imports are handled separately.
                        imports.add(
                            f"relative_import_level_{node.level}"
                        )

        except SyntaxError as error:

            syntax_errors.append({
                "file": relative_name,
                "line": error.lineno,
                "column": error.offset,
                "message": error.msg,
            })

    # ------------------------------------------------
    # LOCAL MODULE DETECTION
    # ------------------------------------------------

    local_modules = set()

    for item in root.iterdir():

        if item.is_file() and item.suffix == ".py":
            local_modules.add(item.stem)

        elif item.is_dir() and not is_excluded(
            Path(item.name)
        ):
            local_modules.add(item.name)

    # Remove relative import placeholders from ordinary imports.
    regular_imports = {
        module for module in imports
        if not module.startswith("relative_import_level_")
    }

    import_categories = classify_imports(
        regular_imports,
        local_modules
    )

    # ------------------------------------------------
    # PROJECT TYPE DETECTION
    # ------------------------------------------------

    project_type = detect_project_type(
        root,
        python_files,
        dependencies
    )

    # ------------------------------------------------
    # PROJECT STRUCTURE
    # ------------------------------------------------

    structure = []

    for item in sorted(root.iterdir()):

        if is_excluded(Path(item.name)):
            continue

        if item.is_dir():
            structure.append({
                "name": item.name,
                "type": "directory",
            })

        else:
            structure.append({
                "name": item.name,
                "type": "file",
            })

    # ------------------------------------------------
    # ANALYSIS WARNINGS
    # ------------------------------------------------

    if not python_files and large_files:
        analysis_warnings.append(
            "Python files were found but skipped because "
            "they exceed the analysis size limit."
        )

    if not python_files and not large_files:
        analysis_warnings.append(
            "No readable Python source files were found."
        )

    if not test_files:
        analysis_warnings.append(
            "No Python test files were detected."
        )

    if not dependencies:
        analysis_warnings.append(
            "No supported dependency configuration file was detected."
        )

    if large_files:
        analysis_warnings.append(
            f"{len(large_files)} large Python file(s) were skipped."
        )

    if unreadable_files:
        analysis_warnings.append(
            f"{len(unreadable_files)} file(s) could not be read."
        )

    if syntax_errors:
        analysis_warnings.append(
            f"{len(syntax_errors)} Python syntax error(s) detected."
        )

    # ------------------------------------------------
    # FINAL RESULT
    # ------------------------------------------------

    return {
        # Existing fields: preserved for compatibility.
        "project_path": str(root),
        "total_python_files": len(python_files),
        "python_files": sorted(python_files),
        "total_test_files": len(test_files),
        "test_files": sorted(test_files),
        "imports": sorted(regular_imports),
        "dependency_files": sorted(dependencies),
        "total_syntax_errors": len(syntax_errors),
        "syntax_errors": syntax_errors,
        "unreadable_files": unreadable_files,

        # Additional project intelligence.
        "project_type": project_type,
        "entry_points": sorted(entry_points),
        "import_categories": import_categories,
        "total_imports": len(regular_imports),
        "project_structure": structure,
        "large_files": large_files,
        "analysis_warnings": analysis_warnings,
    }


# --------------------------------------------------
# STANDALONE EXECUTION
# --------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    target = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "."
    )

    result = analyze_project(target)

    print(
        json.dumps(
            result,
            indent=4
        )
    )
