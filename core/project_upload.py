
"""
Project Upload Module

Responsibilities:
- Validate uploaded project files.
- Accept ZIP project uploads.
- Validate the uploaded filename and file object.
- Pass valid ZIP files to the secure ZIP extractor.
- Return the actual extracted project root.

ZIP security and extraction are handled by core.zip_extractor.
"""

from pathlib import Path

from core.zip_extractor import extract_project_zip as _extract_project_zip


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

ALLOWED_EXTENSIONS = {".zip"}

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB


# --------------------------------------------------
# UPLOAD VALIDATION
# --------------------------------------------------

def validate_project_upload(uploaded_file):
    """
    Validate an uploaded project ZIP file.

    Args:
        uploaded_file: Streamlit UploadedFile or compatible
                       file-like object.

    Raises:
        ValueError: If the upload is invalid.

    Returns:
        bool: True when validation succeeds.
    """

    if uploaded_file is None:
        raise ValueError("Please upload a ZIP project file.")

    # Check filename when available.
    filename = getattr(uploaded_file, "name", None)

    if filename:
        extension = Path(filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError(
                "Invalid file format. Please upload a .zip file."
            )

    # Check uploaded file size when available.
    uploaded_size = getattr(uploaded_file, "size", None)

    if uploaded_size is not None:

        if uploaded_size <= 0:
            raise ValueError("The uploaded ZIP file is empty.")

        if uploaded_size > MAX_UPLOAD_SIZE:
            raise ValueError(
                "ZIP file exceeds the maximum upload limit of 50 MB."
            )

    # Check whether the object supports file operations.
    if not hasattr(uploaded_file, "read"):
        raise ValueError(
            "Invalid upload. The uploaded object is not readable."
        )

    return True


# --------------------------------------------------
# PROJECT UPLOAD AND EXTRACTION
# --------------------------------------------------

def extract_project_zip(uploaded_file, workspace):
    """
    Validate and extract an uploaded ZIP project.

    Args:
        uploaded_file:
            Uploaded ZIP file.

        workspace:
            Directory where the extracted project will be stored.

    Returns:
        Path: Actual extracted project root.

    Raises:
        ValueError: If upload validation or extraction fails.
    """

    # Step 1: Validate uploaded file.
    validate_project_upload(uploaded_file)

    # Step 2: Validate workspace.
    if workspace is None:
        raise ValueError("A project workspace must be provided.")

    workspace_path = Path(workspace).resolve()

    # Step 3: Reset file position before extraction.
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    # Step 4: Perform secure ZIP extraction.
    project_root = _extract_project_zip(
        uploaded_file,
        workspace_path
    )

    # Step 5: Verify extracted project directory.
    project_root = Path(project_root).resolve()

    if not project_root.exists() or not project_root.is_dir():
        raise ValueError(
            "Project extraction failed. "
            "The extracted project directory was not found."
        )

    # Step 6: Return the actual project root.
    return project_root


# --------------------------------------------------
# STANDALONE TEST
# --------------------------------------------------

if __name__ == "__main__":

    print("Project Upload Module")
    print("---------------------")
    print("Supported format: ZIP")
    print("Maximum upload size: 50 MB")
    print("Secure extraction: Enabled")
    print("Module loaded successfully.")
