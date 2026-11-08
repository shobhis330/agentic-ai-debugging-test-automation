
import shutil
import stat
import zipfile

from pathlib import Path, PurePosixPath, PureWindowsPath


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

MAX_ZIP_SIZE = 50 * 1024 * 1024
MAX_EXTRACTED_SIZE = 200 * 1024 * 1024
MAX_FILES = 2000

EXCLUDED_DIRS = {
    ".venv",
    "venv",
    ".git",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".idea",
    ".vscode",
}

EXCLUDED_FILES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
}

PROJECT_MARKERS = {
    "pytest.ini",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Pipfile",
    "tox.ini",
    "manage.py",
}

STRUCTURAL_DIRS = {
    "src",
    "tests",
    "test",
    "lib",
    "app",
}


# --------------------------------------------------
# EXCLUSION CHECK
# --------------------------------------------------

def _is_excluded(path):
    """Check whether a ZIP path contains excluded files or folders."""

    if any(part.lower() in EXCLUDED_DIRS for part in path.parts):
        return True

    name = path.name.lower()

    if name in EXCLUDED_FILES:
        return True

    if name.startswith(".env."):
        return True

    return False


# --------------------------------------------------
# PATH VALIDATION
# --------------------------------------------------

def _is_safe_path(name):
    """Reject absolute paths, traversal paths and Windows drive paths."""

    if not name or "\x00" in name:
        return False

    normalized = name.replace("\\", "/")

    posix_path = PurePosixPath(normalized)
    windows_path = PureWindowsPath(normalized)

    if posix_path.is_absolute():
        return False

    if windows_path.is_absolute() or windows_path.drive:
        return False

    if ".." in posix_path.parts:
        return False

    # Prevent Windows alternate data streams.
    if any(":" in part for part in posix_path.parts):
        return False

    return True


# --------------------------------------------------
# PROJECT ROOT DETECTION
# --------------------------------------------------

def _looks_like_project_root(directory):
    """Identify common Python project structures."""

    if any(
        (directory / marker).is_file()
        for marker in PROJECT_MARKERS
    ):
        return True

    if any(
        (directory / name).is_dir()
        for name in ("tests", "test", "src")
    ):
        return True

    # Search nested packages for Python files.
    for python_file in directory.rglob("*.py"):
        relative_path = python_file.relative_to(directory)

        if not _is_excluded(relative_path):
            return True

    return False


def find_project_root(project_dir):
    """
    Detect unnecessary enclosing folders.

    Example:

        project.zip
        └── outer_folder/
            └── actual_project/
                ├── main.py
                └── tests/

    Returns the actual project directory.
    """

    current = Path(project_dir).resolve()

    while current.is_dir():

        children = list(current.iterdir())

        files = [
            item for item in children
            if item.is_file()
        ]

        directories = [
            item for item in children
            if item.is_dir()
        ]

        # Stop if the current directory contains files
        # or more than one subdirectory.
        if files or len(directories) != 1:
            return current

        candidate = directories[0]

        # Do not mistake normal project folders for wrappers.
        if candidate.name.lower() in STRUCTURAL_DIRS:
            return current

        if not _looks_like_project_root(candidate):
            return current

        current = candidate

    return current


# --------------------------------------------------
# DUPLICATE PATH VALIDATION
# --------------------------------------------------

def _validate_duplicate_paths(members):
    """
    Detect duplicate and Windows case-insensitive path collisions.

    Windows generally treats filenames with different capitalization
    as the same path.

    Example:
        App.py
        app.py

    These cannot safely coexist on Windows.
    """

    seen_paths = {}

    for member in members:

        name = member.filename

        if not _is_safe_path(name):
            raise ValueError(
                "ZIP contains an unsafe file path."
            )

        path = PurePosixPath(
            name.replace("\\", "/")
        )

        if not path.parts or _is_excluded(path):
            continue

        # Directory entries are allowed to repeat.
        if member.is_dir():
            continue

        normalized_name = str(path)

        # Detect exact duplicate paths.
        if normalized_name in seen_paths:
            raise ValueError(
                f"ZIP contains duplicate file paths: {normalized_name}"
            )

        # Detect Windows case-insensitive collisions.
        casefolded_name = normalized_name.casefold()

        for existing_name in seen_paths:

            if existing_name.casefold() == casefolded_name:
                raise ValueError(
                    "ZIP contains filenames that differ only by "
                    f"capitalization: {existing_name} and {normalized_name}. "
                    "Rename one file before uploading on Windows."
                )

        seen_paths[normalized_name] = "file"


# --------------------------------------------------
# ZIP EXTRACTION
# --------------------------------------------------

def extract_project_zip(uploaded_file, workspace):
    """
    Safely extract an uploaded ZIP into a project workspace.

    Features:
    - ZIP size validation
    - Path traversal protection
    - Absolute path protection
    - Symbolic link and special file rejection
    - Sensitive file exclusion
    - Duplicate file detection
    - Windows case-collision detection
    - File count limitation
    - Extracted size limitation
    - Partial extraction cleanup
    - Automatic project root detection

    Returns:
        Path: Actual extracted project root.
    """

    uploaded_size = getattr(uploaded_file, "size", None)

    if uploaded_size is not None and uploaded_size > MAX_ZIP_SIZE:
        raise ValueError(
            "ZIP file exceeds the 50 MB upload limit."
        )

    workspace = Path(workspace).resolve()
    project_dir = workspace / "project"

    # Avoid mixing files from an earlier extraction.
    if project_dir.exists():

        if not project_dir.is_dir():
            raise ValueError(
                "Project workspace path is not a directory."
            )

        if any(project_dir.iterdir()):
            raise ValueError(
                "Project workspace is not empty. "
                "Please provide a fresh workspace."
            )

    else:
        project_dir.mkdir(parents=True, exist_ok=True)

    extracted_size = 0
    file_count = 0

    try:

        with zipfile.ZipFile(uploaded_file) as archive:

            members = archive.infolist()

            # ------------------------------------------
            # FIRST PASS: VALIDATE ARCHIVE ENTRIES
            # ------------------------------------------

            _validate_duplicate_paths(members)

            for member in members:

                name = member.filename

                if not _is_safe_path(name):
                    raise ValueError(
                        "ZIP contains an unsafe file path."
                    )

                path = PurePosixPath(
                    name.replace("\\", "/")
                )

                if not path.parts or _is_excluded(path):
                    continue

                mode = member.external_attr >> 16
                file_type = stat.S_IFMT(mode)

                # Reject symbolic links and special filesystem objects.
                if file_type not in (
                    0,
                    stat.S_IFREG,
                    stat.S_IFDIR,
                ):
                    raise ValueError(
                        "ZIP contains an unsupported special file."
                    )

                if member.file_size < 0:
                    raise ValueError(
                        "ZIP contains an invalid file size."
                    )

                if member.is_dir():
                    continue

                if file_type == stat.S_IFDIR:
                    raise ValueError(
                        "ZIP contains an invalid file entry."
                    )

                file_count += 1
                extracted_size += member.file_size

            # Validate total file count.
            if file_count > MAX_FILES:
                raise ValueError(
                    "ZIP contains too many files."
                )

            # Validate total uncompressed size.
            if extracted_size > MAX_EXTRACTED_SIZE:
                raise ValueError(
                    "Extracted project exceeds the 200 MB limit."
                )

            # ------------------------------------------
            # SECOND PASS: EXTRACT VALIDATED FILES
            # ------------------------------------------

            actual_extracted_size = 0

            for member in members:

                name = member.filename

                if not _is_safe_path(name):
                    continue

                path = PurePosixPath(
                    name.replace("\\", "/")
                )

                if not path.parts or _is_excluded(path):
                    continue

                target = (
                    project_dir / Path(*path.parts)
                ).resolve()

                # Ensure extracted files remain inside project_dir.
                if not target.is_relative_to(project_dir):
                    raise ValueError(
                        "ZIP contains an unsafe extraction path."
                    )

                if member.is_dir():
                    target.mkdir(
                        parents=True,
                        exist_ok=True
                    )
                    continue

                target.parent.mkdir(
                    parents=True,
                    exist_ok=True
                )

                copied = 0

                with (
                    archive.open(member) as source,
                    target.open("xb") as destination
                ):

                    while True:

                        chunk = source.read(1024 * 1024)

                        if not chunk:
                            break

                        copied += len(chunk)
                        actual_extracted_size += len(chunk)

                        if copied > member.file_size:
                            raise ValueError(
                                "Invalid ZIP file size."
                            )

                        if actual_extracted_size > MAX_EXTRACTED_SIZE:
                            raise ValueError(
                                "Actual extracted size exceeds "
                                "the 200 MB limit."
                            )

                        destination.write(chunk)

                if copied != member.file_size:
                    raise ValueError(
                        "ZIP file extraction was incomplete."
                    )

    # ----------------------------------------------
    # ERROR HANDLING AND CLEANUP
    # ----------------------------------------------

    except Exception as error:

        # Remove partially extracted files after any failure.
        if project_dir.exists():
            shutil.rmtree(
                project_dir,
                ignore_errors=True
            )

        if isinstance(error, zipfile.BadZipFile):
            raise ValueError(
                "The uploaded file is not a valid ZIP archive."
            ) from error

        if isinstance(
            error,
            (RuntimeError, NotImplementedError)
        ):
            raise ValueError(
                f"Unable to extract ZIP file: {error}"
            ) from error

        raise

    # ----------------------------------------------
    # DETECT ACTUAL PROJECT ROOT
    # ----------------------------------------------

    actual_project_root = find_project_root(project_dir)

    return actual_project_root


# --------------------------------------------------
# STANDALONE EXECUTION
# --------------------------------------------------

if __name__ == "__main__":

    print("ZIP Extractor Module")
    print("--------------------")
    print(f"Maximum ZIP size: {MAX_ZIP_SIZE // (1024 * 1024)} MB")
    print(
        f"Maximum extracted size: "
        f"{MAX_EXTRACTED_SIZE // (1024 * 1024)} MB"
    )
    print(f"Maximum files: {MAX_FILES}")
    print("Windows filename collision protection: Enabled")
