
import os
import zipfile

# Your project folder
PROJECT_PATH = r"C:\Users\shobh\Documents\agentic-ai-debugging-test-automation"

# ZIP file will be created in Documents
ZIP_PATH = r"C:\Users\shobh\Documents\DebugEngage_AI.zip"

# Folders and files to exclude
EXCLUDE_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache"
}

EXCLUDE_FILES = {
    ".env",
    ".env.local",
    ".env.production"
}

def create_project_zip():
    with zipfile.ZipFile(
        ZIP_PATH, "w", zipfile.ZIP_DEFLATED
    ) as zip_file:

        for root, dirs, files in os.walk(PROJECT_PATH):

            # Skip unnecessary directories
            dirs[:] = [
                d for d in dirs
                if d not in EXCLUDE_DIRS
            ]

            for file in files:

                # Skip sensitive files
                if file in EXCLUDE_FILES:
                    continue

                full_path = os.path.join(root, file)

                relative_path = os.path.relpath(
                    full_path, PROJECT_PATH
                )

                zip_file.write(
                    full_path,
                    arcname=os.path.join(
                        "DebugEngage_AI", relative_path
                    )
                )

    print("ZIP created successfully!")
    print("Location:", ZIP_PATH)
    print("Size:", round(os.path.getsize(ZIP_PATH) / (1024 * 1024), 2), "MB")

if __name__ == "__main__":
    create_project_zip()
