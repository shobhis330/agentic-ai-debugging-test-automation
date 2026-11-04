
import sys
import shutil
import tempfile
import difflib
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# --------------------------------------------------
# PROJECT CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from core.zip_extractor import extract_project_zip
from core.project_analyzer import analyze_project
from core.repair_engine import repair_code
from core.test_runner import run_tests


st.set_page_config(
    page_title="Agentic AI Python Debugging System",
    page_icon="🐞",
    layout="wide"
)

# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

DEFAULT_STATE = {
    "project_path": None,
    "workspace": None,
    "analysis_results": None,
    "last_test_result": None,
    "repair_result": None,
    "repair_file": None,
    "repair_applied": False,
    "post_repair_result": None,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def reset_project_state():
    """Clear project-related session state."""

    old_workspace = st.session_state.get("workspace")

    if old_workspace:
        shutil.rmtree(old_workspace, ignore_errors=True)

    st.session_state.project_path = None
    st.session_state.workspace = None
    st.session_state.analysis_results = None
    st.session_state.last_test_result = None
    st.session_state.repair_result = None
    st.session_state.repair_file = None
    st.session_state.repair_applied = False
    st.session_state.post_repair_result = None


def get_project_files(project_path):
    """Return Python source files, excluding common generated folders."""

    ignored = {
        ".venv", "venv", ".git", "__pycache__",
        "node_modules", ".pytest_cache", ".mypy_cache"
    }

    files = []

    for path in Path(project_path).rglob("*.py"):
        if any(part in ignored for part in path.parts):
            continue
        files.append(path)

    return sorted(files)


def get_relative_path(file_path, project_path):
    return str(Path(file_path).relative_to(Path(project_path)))


def get_test_output(result):
    """Extract test output safely."""

    if not result:
        return "No test execution has been performed yet."

    return str(result.get("output", "No test output available."))


def is_valid_repair(diagnosis):
    """
    A repair is allowed only when Gemini provides
    non-empty, syntactically valid corrected Python code.
    """

    if not isinstance(diagnosis, dict):
        return False

    fixed_code = diagnosis.get("fixed_code")

    if not isinstance(fixed_code, str) or not fixed_code.strip():
        return False

    bug_type = str(diagnosis.get("bug_type", "")).strip().lower()

    no_bug_labels = {
        "none",
        "no bug",
        "no bugs found",
        "no defect",
        "no issues",
        "no issue found",
        "not required"
    }

    if bug_type in no_bug_labels:
        return False

    return bool(diagnosis.get("syntax_valid", True))


def show_test_results(result, heading="Test Results"):
    """Display pytest counts and output."""

    st.subheader(heading)

    if not result:
        st.info("No test results available.")
        return

    passed = result.get("passed", 0)
    failed = result.get("failed", 0)
    errors = result.get("errors", 0)
    skipped = result.get("skipped", 0)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Passed", passed)
    col2.metric("Failed", failed)
    col3.metric("Errors", errors)
    col4.metric("Skipped", skipped)

    if result.get("timed_out"):
        st.error("Test execution timed out.")
    elif result.get("success") and (passed + failed + errors) > 0:
        st.success("All tests passed.")
    elif passed + failed + errors == 0:
        st.warning(
            "No tests were collected. This is not a successful validation."
        )
    else:
        st.error("Some tests failed or test execution encountered errors.")

    with st.expander("View Test Output"):
        st.code(result.get("output", "No output available."))


# --------------------------------------------------
# APPLICATION HEADER
# --------------------------------------------------

st.title("🐞 Agentic AI Python Debugging System")

st.write(
    "Upload, analyze, diagnose, repair and validate Python projects."
)

st.divider()


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Choose Page",
    ["Project Analysis", "About"]
)


# --------------------------------------------------
# ABOUT PAGE
# --------------------------------------------------

if page == "About":

    st.title("About the Project")

    st.write("""
    The Agentic AI Python Debugging System helps developers
    identify and correct errors in Python projects.

    **Main features:**

    1. Python project ZIP upload.
    2. Project structure analysis.
    3. Syntax error detection.
    4. Automated pytest execution.
    5. Gemini AI-based bug diagnosis.
    6. Corrected code generation.
    7. Human-approved repair.
    8. Post-repair test validation.

    The application uses Python, Streamlit, pytest and Gemini AI.
    """)

    st.info(
        "This is a prototype. Uploaded Python tests execute locally "
        "and are not isolated in a security sandbox."
    )


# --------------------------------------------------
# PROJECT ANALYSIS PAGE
# --------------------------------------------------

elif page == "Project Analysis":

    st.header("📁 Upload Python Project")

    uploaded_file = st.file_uploader(
        "Upload your Python project as a ZIP file",
        type=["zip"]
    )

    if uploaded_file is not None:

        if st.button("Analyze Project", type="primary"):

            reset_project_state()

            workspace = tempfile.mkdtemp(
                prefix="agentic_debugging_"
            )

            try:
                with st.spinner("Extracting project..."):

                    extract_project_zip(
                        uploaded_file,
                        workspace
                    )

                project_path = Path(workspace) / "project"

                if not project_path.exists():
                    raise FileNotFoundError(
                        "Extracted project folder was not found."
                    )

                with st.spinner("Analyzing Python project..."):

                    results = analyze_project(project_path)

                st.session_state.workspace = workspace
                st.session_state.project_path = str(project_path)
                st.session_state.analysis_results = results

                st.success("Project uploaded and analyzed successfully!")

            except Exception as error:

                shutil.rmtree(workspace, ignore_errors=True)

                st.error(f"Project analysis failed: {error}")


    # --------------------------------------------------
    # DISPLAY ANALYSIS RESULTS
    # --------------------------------------------------

    if st.session_state.project_path:

        project_path = Path(st.session_state.project_path)
        results = st.session_state.analysis_results or {}

        st.divider()
        st.header("📊 Project Analysis Results")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Python Files",
            results.get("total_python_files", 0)
        )

        col2.metric(
            "Test Files",
            results.get("total_test_files", 0)
        )

        col3.metric(
            "Syntax Errors",
            results.get("total_syntax_errors", 0)
        )

        col4.metric(
            "Unreadable Files",
            len(results.get("unreadable_files", []))
        )

        # Python files

        with st.expander("View Python Files"):

            for file in results.get("python_files", []):
                st.write(file)

        # Test files

        with st.expander("View Test Files"):

            for file in results.get("test_files", []):
                st.write(file)

        # Dependencies

        with st.expander("View Dependencies"):

            st.write(
                results.get("dependency_files", [])
            )

        # Imported modules

        with st.expander("View Imported Modules"):

            st.write(
                results.get("imports", [])
            )

        # Syntax errors

        st.subheader("🔍 Syntax Error Detection")

        syntax_errors = results.get("syntax_errors", [])

        if syntax_errors:
            st.error("Syntax errors detected!")

            for error in syntax_errors:
                st.write(error)
        else:
            st.success("No syntax errors detected!")

        # --------------------------------------------------
        # AUTOMATED TEST EXECUTION
        # --------------------------------------------------

        st.divider()
        st.header("🧪 Automated Test Execution")

        st.warning(
            "Running pytest executes Python code from the uploaded "
            "project. Only run tests for projects you trust. "
            "This prototype does not provide a security sandbox."
        )

        authorize_tests = st.checkbox(
            "I understand the risk and authorize test execution "
            "for this uploaded project."
        )

        if st.button(
            "Run Automated Tests",
            disabled=not authorize_tests
        ):

            with st.spinner("Running pytest..."):

                test_result = run_tests(project_path)

                st.session_state.last_test_result = test_result

                # A new test run invalidates an older diagnosis.
                st.session_state.repair_result = None
                st.session_state.repair_file = None
                st.session_state.repair_applied = False
                st.session_state.post_repair_result = None

        if st.session_state.last_test_result:

            show_test_results(
                st.session_state.last_test_result,
                "Most Recent Test Execution"
            )

        # --------------------------------------------------
        # GEMINI AI DIAGNOSIS
        # --------------------------------------------------

        st.divider()
        st.header("🤖 Gemini AI Diagnosis")

        st.write(
            "Select a Python source file to identify bugs "
            "and generate corrected code."
        )

        all_python_files = get_project_files(project_path)

        # Prefer source files over test files.
        source_files = [
            path for path in all_python_files
            if "test" not in path.name.lower()
            and "tests" not in path.parts
        ]

        if not source_files:
            source_files = all_python_files

        if source_files:

            relative_files = [
                get_relative_path(path, project_path)
                for path in source_files
            ]

            selected_file_name = st.selectbox(
                "Select Python file",
                relative_files
            )

            selected_file = project_path / selected_file_name

            if st.button("Diagnose with Gemini", type="primary"):

                try:

                    source_code = selected_file.read_text(
                        encoding="utf-8-sig"
                    )

                    if len(source_code) > 30000:
                        st.error(
                            "Selected file is too large for diagnosis. "
                            "Please select a smaller Python file."
                        )
                    else:

                        test_output = get_test_output(
                            st.session_state.last_test_result
                        )

                        with st.spinner(
                            "Gemini is analyzing the selected file..."
                        ):

                            diagnosis = repair_code(
                                source_code,
                                test_output,
                                file_name=selected_file.name
                            )

                        st.session_state.repair_result = diagnosis
                        st.session_state.repair_file = str(selected_file)
                        st.session_state.repair_applied = False
                        st.session_state.post_repair_result = None

                except Exception as error:

                    st.error(f"Gemini diagnosis failed: {error}")

        else:
            st.warning("No Python files found in this project.")

        # --------------------------------------------------
        # DISPLAY DIAGNOSIS
        # --------------------------------------------------

        diagnosis = st.session_state.repair_result

        if diagnosis:

            st.divider()
            st.subheader("🧠 Diagnosis Results")

            st.write(
                "**Bug Type:**",
                diagnosis.get("bug_type", "Not specified")
            )

            st.write(
                "**Explanation:**",
                diagnosis.get("explanation", "No explanation available.")
            )

            st.write(
                "**Confidence:**",
                f"{diagnosis.get('confidence', 'Not specified')}%"
            )

            # --------------------------------------------------
            # NO REPAIR REQUIRED
            # --------------------------------------------------

            if not is_valid_repair(diagnosis):

                st.success(
                    "No repair required. Gemini did not provide "
                    "valid corrected code. The selected file will "
                    "not be modified."
                )

                st.info(
                    "If the automated tests passed, the project "
                    "has already passed its current test validation."
                )

                if diagnosis.get("fixed_code"):
                    st.warning(
                        "Gemini returned code without a valid repair "
                        "status. It will not be applied automatically."
                    )

            # --------------------------------------------------
            # VALID REPAIR AVAILABLE
            # --------------------------------------------------

            else:

                fixed_code = diagnosis["fixed_code"]

                st.subheader("💡 Suggested Corrected Code")

                st.code(
                    fixed_code,
                    language="python"
                )

                original_path = Path(
                    st.session_state.repair_file
                )

                original_code = original_path.read_text(
                    encoding="utf-8-sig"
                )

                diff = difflib.unified_diff(
                    original_code.splitlines(),
                    fixed_code.splitlines(),
                    fromfile="Before Repair",
                    tofile="After Repair",
                    lineterm=""
                )

                with st.expander("View Before-and-After Diff"):

                    st.code(
                        "\n".join(diff),
                        language="diff"
                    )

                st.info(
                    "The extracted project will only be modified "
                    "after you approve the suggested repair."
                )

                # --------------------------------------------------
                # HUMAN APPROVAL
                # --------------------------------------------------

                if not st.session_state.repair_applied:

                    if st.button(
                        "Approve and Apply Repair",
                        type="primary"
                    ):

                        try:

                            # Final safety check before writing.
                            if not fixed_code.strip():
                                raise ValueError(
                                    "Corrected code is empty."
                                )

                            original_path.write_text(
                                fixed_code,
                                encoding="utf-8"
                            )

                            st.session_state.repair_applied = True
                            st.session_state.post_repair_result = None

                            st.success(
                                "Repair applied to the extracted project copy!"
                            )

                            st.info(
                                "Your original ZIP and local source "
                                "project remain unchanged."
                            )

                        except Exception as error:

                            st.error(
                                f"Could not apply repair: {error}"
                            )

                else:

                    st.success(
                        "Repair has already been applied."
                    )

                # --------------------------------------------------
                # POST-REPAIR VALIDATION
                # --------------------------------------------------

                if st.session_state.repair_applied:

                    st.divider()
                    st.header("🔄 Post-Repair Test Validation")

                    if st.button("Run Post-Repair Validation"):

                        with st.spinner(
                            "Validating repaired project..."
                        ):

                            validation_result = run_tests(
                                project_path
                            )

                            st.session_state.post_repair_result = (
                                validation_result
                            )

                    if st.session_state.post_repair_result:

                        validation = (
                            st.session_state.post_repair_result
                        )

                        show_test_results(
                            validation,
                            "Post-Repair Validation Results"
                        )

                        total_tests = (
                            validation.get("passed", 0)
                            + validation.get("failed", 0)
                            + validation.get("errors", 0)
                        )

                        if (
                            validation.get("success")
                            and total_tests > 0
                            and validation.get("failed", 0) == 0
                            and validation.get("errors", 0) == 0
                        ):

                            st.success(
                                "Repair successfully validated! "
                                "All collected tests passed."
                            )

                        else:

                            st.error(
                                "Some tests failed or no tests were "
                                "collected. The repair is not fully validated."
                            )

