
import ast
import difflib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google import genai

# ==========================================================
# PROJECT CONFIGURATION
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from core.zip_extractor import extract_project_zip
from core.project_analyzer import analyze_project
from core.repair_engine import repair_code
from core.test_runner import run_tests, validate_python_code


st.set_page_config(
    page_title="DebugEngage AI",
    page_icon="🐞",
    layout="wide",
)


# ==========================================================
# SESSION STATE
# ==========================================================

DEFAULT_STATE = {
    "project_path": None,
    "workspace": None,
    "analysis_results": None,
    "last_test_result": None,
    "repair_result": None,
    "repair_file": None,
    "repair_applied": False,
    "post_repair_result": None,

    "single_source_code": "",
    "single_file_name": "solution.py",
    "single_diagnosis": None,
    "single_test_code": "",
    "single_test_explanation": "",
    "single_test_result": None,
    "single_comparison_result": None,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ==========================================================
# GENERAL HELPERS
# ==========================================================

def reset_single_file_results():
    st.session_state.single_diagnosis = None
    st.session_state.single_test_code = ""
    st.session_state.single_test_explanation = ""
    st.session_state.single_test_result = None
    st.session_state.single_comparison_result = None


def clear_single_code():
    st.session_state.single_source_code = ""
    st.session_state.single_file_name = "solution.py"
    st.session_state.single_file_name_input = "solution.py"
    reset_single_file_results()


def reset_project_state():
    old_workspace = st.session_state.get("workspace")

    if old_workspace:
        shutil.rmtree(old_workspace, ignore_errors=True)

    for key in (
        "project_path",
        "workspace",
        "analysis_results",
        "last_test_result",
        "repair_result",
        "repair_file",
        "repair_applied",
        "post_repair_result",
    ):
        st.session_state[key] = DEFAULT_STATE[key]


def get_project_files(project_path):
    project_path = Path(project_path).resolve()

    ignored = {
        ".venv", "venv", ".git", "__pycache__",
        "node_modules", ".pytest_cache", ".mypy_cache",
        ".tox", "site-packages",
    }

    files = []

    for path in project_path.rglob("*.py"):
        relative_parts = path.relative_to(project_path).parts

        if any(part in ignored for part in relative_parts):
            continue

        if path.is_file():
            files.append(path)

    return sorted(files)


def get_relative_path(file_path, project_path):
    return str(
        Path(file_path).resolve().relative_to(
            Path(project_path).resolve()
        )
    )


def resolve_project_file(project_path, relative_file_path):
    root = Path(project_path).resolve()
    candidate = (root / relative_file_path).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "Selected file is outside the project folder."
        ) from error

    if not candidate.is_file() or candidate.suffix.lower() != ".py":
        raise FileNotFoundError(
            "Selected Python file does not exist."
        )

    return candidate


def get_test_output(result):
    if not result:
        return ""
    return str(result.get("output", "No test output available."))


def format_confidence(value):
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return "Not specified"

    if 0 <= confidence <= 1:
        return f"{confidence * 100:.0f}%"

    return "Not specified"


def is_valid_repair(diagnosis):
    if not isinstance(diagnosis, dict):
        return False

    fixed_code = diagnosis.get("fixed_code")

    return (
        diagnosis.get("status") == "bug_found"
        and isinstance(fixed_code, str)
        and bool(fixed_code.strip())
    )


def validate_repair_code(diagnosis, file_name):
    if not is_valid_repair(diagnosis):
        return False

    result = validate_python_code(
        diagnosis["fixed_code"],
        file_name,
    )

    return result.get("success", False)


# ==========================================================
# PYTEST GENERATION
# ==========================================================

def generate_pytest_tests(
    original_code,
    corrected_code,
    file_name,
    diagnosis,
):
    """
    Generate tests intended to distinguish the original
    implementation from the proposed corrected implementation.
    """

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. "
            "Add it to your .env file."
        )

    module_name = Path(file_name).stem

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", module_name):
        module_name = "solution"

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are an expert Python software test engineer.

Create pytest tests for the intended correct behaviour of the
Python program.

The same test file will be run against BOTH:
1. The original source code.
2. The proposed corrected source code.

The purpose is to check whether the proposed correction fixes
the defects identified in the diagnosis.

Module name: {module_name}

ORIGINAL SOURCE:
{original_code}

PROPOSED CORRECTED SOURCE:
{corrected_code}

AI DIAGNOSIS:
{json.dumps(diagnosis, ensure_ascii=False, default=str)}

Requirements:
- Generate independent pytest functions named test_*.
- Test normal cases and meaningful edge cases.
- Tests should express the intended correct behaviour.
- Do not write tests that deliberately expect known bugs.
- Do not simply copy the implementation's behaviour as the expected result.
- Use the diagnosis to understand what behaviour should be corrected.
- Import from {module_name}.
- Do not use network access, subprocesses, file deletion,
  or unrelated system actions.
- Do not include markdown fences.
- Return only valid JSON with:
  "test_code": complete pytest test file as a string
  "explanation": short test coverage description
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    response_text = getattr(response, "text", None)

    if not response_text:
        raise ValueError(
            "Gemini returned an empty test-generation response."
        )

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini returned invalid JSON while generating tests."
        ) from error

    test_code = result.get("test_code", "")

    if not isinstance(test_code, str) or not test_code.strip():
        raise ValueError(
            "Gemini did not generate valid pytest code."
        )

    try:
        tree = ast.parse(test_code)
    except SyntaxError as error:
        raise ValueError(
            f"Generated tests have a syntax error: {error}"
        ) from error

    test_functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]

    if not test_functions:
        raise ValueError(
            "Gemini did not generate any pytest test functions."
        )

    return {
        "test_code": test_code,
        "explanation": str(result.get("explanation", "")),
    }


# ==========================================================
# SINGLE-FILE TEST EXECUTION
# ==========================================================

def run_single_file_tests(source_code, file_name, test_code):
    """
    Run pytest against a temporary copy of a Python file.
    The original local file is not modified.
    """

    if not source_code.strip():
        raise ValueError("The Python source code is empty.")

    if not test_code.strip():
        raise ValueError("The pytest test code is empty.")

    if len(source_code) > 100000:
        raise ValueError(
            "The source file exceeds 100,000 characters."
        )

    if len(test_code) > 100000:
        raise ValueError(
            "The test file exceeds 100,000 characters."
        )

    source_validation = validate_python_code(
        source_code,
        file_name,
    )

    if not source_validation.get("success", False):
        raise ValueError(
            "The source file has a syntax error."
        )

    try:
        ast.parse(test_code)
    except SyntaxError as error:
        raise ValueError(
            f"The test file has a syntax error: {error}"
        ) from error

    safe_name = Path(file_name).name

    if not safe_name.lower().endswith(".py"):
        safe_name += ".py"

    module_stem = Path(safe_name).stem

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", module_stem):
        safe_name = "solution.py"

    with tempfile.TemporaryDirectory(
        prefix="debugengage_single_test_"
    ) as temp_dir:

        temp_root = Path(temp_dir)
        tests_dir = temp_root / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)

        (temp_root / safe_name).write_text(
            source_code,
            encoding="utf-8",
        )

        (tests_dir / "test_user_cases.py").write_text(
            test_code,
            encoding="utf-8",
        )

        return run_tests(temp_root, timeout=60)


def compare_original_and_corrected(
    original_code,
    corrected_code,
    file_name,
    test_code,
):
    """
    Run exactly the same test file against two independent
    temporary project copies.
    """

    original_result = run_single_file_tests(
        original_code,
        file_name,
        test_code,
    )

    corrected_result = run_single_file_tests(
        corrected_code,
        file_name,
        test_code,
    )

    return {
        "original": original_result,
        "corrected": corrected_result,
    }


# ==========================================================
# DIAGNOSIS DISPLAY
# ==========================================================

def show_diagnosis_summary(diagnosis):
    st.write(
        "**Diagnosis Status:**",
        diagnosis.get("status", "Not specified"),
    )

    st.write(
        "**Bug Type:**",
        diagnosis.get("bug_type", "Not specified"),
    )

    st.write(
        "**Explanation:**",
        diagnosis.get("explanation", "No explanation available."),
    )

    st.write(
        "**Confidence:**",
        format_confidence(diagnosis.get("confidence")),
    )

    if diagnosis.get("ai_provider"):
        st.caption(
            f"AI Provider: {diagnosis['ai_provider']}"
        )

    if diagnosis.get("recommended_action"):
        st.info(diagnosis["recommended_action"])


def show_issue_details(diagnosis):
    issues = diagnosis.get("issues", [])

    if not issues:
        st.info(
            "No separate issue snippets were returned. "
            "Review the complete corrected code."
        )
        return

    st.subheader("Detected Problems and Corrections")

    for index, issue in enumerate(issues, start=1):
        if isinstance(issue, str):
            issue = {"problem": issue}

        title = issue.get("problem", f"Issue {index}")

        if issue.get("line"):
            title += f" - Line {issue['line']}"

        with st.expander(title):
            st.write(
                issue.get(
                    "explanation",
                    "No additional explanation.",
                )
            )

            original = issue.get("original_snippet", "")
            corrected = issue.get("corrected_snippet", "")

            if original:
                st.markdown("**Original Code Section**")
                st.code(original, language="python")

            if corrected:
                st.markdown("**Corrected Code Section**")
                st.code(corrected, language="python")

            if issue.get("severity"):
                st.caption(
                    f"Severity: {issue['severity']}"
                )


def display_repair(
    diagnosis,
    original_code,
    file_name,
    key_prefix,
):
    show_diagnosis_summary(diagnosis)

    if diagnosis.get("status") != "bug_found":
        if diagnosis.get("status") == "no_bug_found":
            st.success("No source-code bug was identified.")
        elif diagnosis.get("status") == "environment_issue":
            st.warning(
                "The issue appears related to the environment, "
                "dependencies or configuration."
            )
        else:
            st.warning(
                "No valid corrected code was generated."
            )
        return False

    fixed_code = diagnosis.get("fixed_code", "")

    if not isinstance(fixed_code, str) or not fixed_code.strip():
        st.error("Gemini did not return complete corrected code.")
        return False

    validation = validate_python_code(
        fixed_code,
        file_name,
    )

    if not validation.get("success", False):
        st.error("Generated code failed Python syntax validation.")
        st.code(
            validation.get("error", "Unknown syntax error.")
        )
        return False

    show_issue_details(diagnosis)

    st.success(
        "Corrected code passed Python syntax validation."
    )

    st.subheader("Complete Corrected Python Code")
    st.code(fixed_code, language="python")

    st.download_button(
        label="Download Corrected Python File",
        data=fixed_code,
        file_name=f"fixed_{Path(file_name).name}",
        mime="text/x-python",
        key=f"{key_prefix}_download",
    )

    st.subheader("Before and After Comparison")

    diff = difflib.unified_diff(
        original_code.splitlines(),
        fixed_code.splitlines(),
        fromfile="Original Code",
        tofile="Corrected Code",
        lineterm="",
    )

    diff_text = "\n".join(diff)

    if diff_text:
        st.code(diff_text, language="diff")
    else:
        st.info("No differences were detected.")

    return True


# ==========================================================
# TEST RESULTS DISPLAY
# ==========================================================

def show_test_results(result, heading="Test Results"):
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

    total = passed + failed + errors

    if result.get("timed_out"):
        st.error("Test execution timed out.")

    elif result.get("no_tests") or total == 0:
        st.warning("No tests were collected.")

    elif (
        result.get("success")
        and failed == 0
        and errors == 0
    ):
        st.success("All collected tests passed.")

    else:
        st.error("Some tests failed or produced errors.")

    with st.expander("View Test Execution Output"):
        st.code(
            result.get("output", "No output available.")
        )


def show_comparison_results(comparison):
    st.header("📊 Original vs Corrected Code Comparison")

    original = comparison["original"]
    corrected = comparison["corrected"]

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Original Code")
        show_test_results(
            original,
            "Original Code Test Results",
        )

    with col2:
        st.subheader("Corrected Code")
        show_test_results(
            corrected,
            "Corrected Code Test Results",
        )

    original_passed = original.get("passed", 0)
    corrected_passed = corrected.get("passed", 0)

    original_total = (
        original.get("passed", 0)
        + original.get("failed", 0)
        + original.get("errors", 0)
    )

    corrected_total = (
        corrected.get("passed", 0)
        + corrected.get("failed", 0)
        + corrected.get("errors", 0)
    )

    st.divider()
    st.subheader("Comparison Summary")

    metric1, metric2, metric3 = st.columns(3)

    metric1.metric(
        "Original Tests Passed",
        original_passed,
    )

    metric2.metric(
        "Corrected Tests Passed",
        corrected_passed,
    )

    metric3.metric(
        "Additional Tests Passed",
        corrected_passed - original_passed,
    )

    if original_total == 0 or corrected_total == 0:
        st.warning(
            "Comparison is inconclusive because one or both "
            "test runs collected no tests."
        )

    elif (
        corrected.get("timed_out")
        or original.get("timed_out")
    ):
        st.warning(
            "Comparison is inconclusive because a test run timed out."
        )

    elif (
        corrected.get("success")
        and corrected.get("failed", 0) == 0
        and corrected.get("errors", 0) == 0
    ):
        if (
            original.get("failed", 0) > 0
            or original.get("errors", 0) > 0
        ):
            st.success(
                "The corrected version passed all collected tests, "
                "while the original version had failures."
            )
        else:
            st.success(
                "Both versions passed all collected tests. "
                "The generated tests did not demonstrate a failure "
                "in the original version."
            )

    else:
        st.warning(
            "The corrected version still has failing tests or errors. "
            "Review the test output before accepting the repair."
        )

    st.caption(
        "The same test file was executed independently against "
        "both code versions. Test results depend on the quality "
        "and coverage of the generated or uploaded tests."
    )


# ==========================================================
# APPLICATION HEADER AND NAVIGATION
# ==========================================================

st.title("🐞 DebugEngage AI")
st.write(
    "Agentic AI Python debugging, code correction "
    "and automated test validation."
)

st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Choose Page",
    [
        "Single Python Code",
        "Complete ZIP Project",
        "Code Quality Analysis",
        "AI Bug Explanation",
        "Test Coverage Report",
        "Debugging History",
        "Original vs Corrected Comparison",
        "About",
    ],
)

# These feature pages must exist inside frontend/pages/.
PAGE_PATHS = {
    "Code Quality Analysis": "pages/Code_Quality.py",
    "AI Bug Explanation": "pages/AI_Bug_Explanation.py",
    "Test Coverage Report": "pages/Test_Coverage_Report.py",
    "Debugging History": "pages/Debugging_History.py",
    "Original vs Corrected Comparison": "pages/Original_vs_Corrected_Comparison.py",
}

if page in PAGE_PATHS:
    st.switch_page(PAGE_PATHS[page])

st.sidebar.divider()
st.sidebar.caption(
    "Python Debugging and Test Automation"
)


# ==========================================================
# ABOUT PAGE
# ==========================================================

if page == "About":
    st.title("About DebugEngage AI")

    st.write(
        """
        DebugEngage AI helps developers identify and correct
        Python programming errors using AI-assisted debugging
        and automated test validation.

        It supports individual Python files and complete
        Python projects.
        """
    )

    st.subheader("Main Features")

    features = [
        "Upload or paste individual Python files",
        "Upload complete ZIP projects",
        "Python syntax validation",
        "AI-based bug diagnosis",
        "Complete corrected source code",
        "Before-and-after code comparison",
        "Gemini-generated pytest tests",
        "Original vs corrected test comparison",
        "Human approval before ZIP repair",
        "Post-repair project validation",
    ]

    for feature in features:
        st.write(f"✓ {feature}")

    st.subheader("Technology Stack")
    st.write(
        """
        - Python
        - Streamlit
        - Google Gemini API
        - pytest
        - AST
        """
    )

    st.warning(
        "Security: This prototype does not provide a secure sandbox. "
        "Uploaded project tests execute on the computer running "
        "the application. Only run projects and tests you trust."
    )


# ==========================================================
# SINGLE PYTHON CODE MODE
# ==========================================================

elif page == "Single Python Code":

    st.header("📝 Single Python Code Debugging")

    st.write(
        "Paste Python code or upload an individual .py file."
    )

    uploaded_file = st.file_uploader(
        "Upload Python File",
        type=["py"],
        key="single_python_upload",
    )

    if uploaded_file is not None:
        try:
            uploaded_code = uploaded_file.getvalue().decode(
                "utf-8-sig"
            )

            if (
                st.session_state.single_file_name != uploaded_file.name
                or st.session_state.single_source_code != uploaded_code
            ):
                st.session_state.single_source_code = uploaded_code
                st.session_state.single_file_name = uploaded_file.name
                reset_single_file_results()

        except UnicodeDecodeError:
            st.error(
                "Unable to read the uploaded file. "
                "Please use UTF-8 encoding."
            )

    file_name = st.text_input(
        "Python File Name",
        value=st.session_state.single_file_name,
        key="single_file_name_input",
    )

    if not file_name.strip():
        file_name = "solution.py"

    if not file_name.lower().endswith(".py"):
        file_name += ".py"

    source_code = st.text_area(
        "Paste Your Python Code",
        key="single_source_code",
        height=350,
        placeholder="Paste your complete Python code here...",
    )

    st.subheader("Error Information")

    error_output = st.text_area(
        "Error Message or Test Output (Optional)",
        height=120,
        placeholder="Paste the traceback or error message here...",
    )

    col1, col2 = st.columns(2)

    with col1:
        diagnose_clicked = st.button(
            "Diagnose and Correct My Code",
            type="primary",
            use_container_width=True,
        )

    with col2:
        st.button(
            "Clear Code",
            use_container_width=True,
            on_click=clear_single_code,
        )

    if source_code.strip():
        validation = validate_python_code(
            source_code,
            file_name,
        )

        st.subheader("Local Syntax Validation")

        if validation.get("success", False):
            st.success(
                "Python syntax and compilation validation passed."
            )
        else:
            st.error(
                validation.get(
                    "error",
                    "Syntax validation failed.",
                )
            )

    if diagnose_clicked:
        if not source_code.strip():
            st.error("Please paste code or upload a Python file.")

        elif len(source_code) > 100000:
            st.error(
                "The file exceeds the 100,000-character limit."
            )

        else:
            try:
                with st.spinner(
                    "Gemini is analyzing your Python code..."
                ):
                    diagnosis = repair_code(
                        source_code,
                        error_output,
                        file_name=file_name,
                    )

                st.session_state.single_diagnosis = diagnosis
                st.session_state.single_file_name = file_name

                st.session_state.single_test_code = ""
                st.session_state.single_test_explanation = ""
                st.session_state.single_test_result = None
                st.session_state.single_comparison_result = None

            except Exception as error:
                st.error(f"Diagnosis failed: {error}")

    diagnosis = st.session_state.single_diagnosis

    if diagnosis:
        st.divider()
        st.header("🤖 AI Diagnosis and Correction")

        repair_valid = display_repair(
            diagnosis=diagnosis,
            original_code=st.session_state.single_source_code,
            file_name=st.session_state.single_file_name,
            key_prefix="single_python",
        )

        st.info(
            "Single-file mode does not modify your original local file. "
            "Review and download the corrected code before using it."
        )

        # --------------------------------------------------
        # SINGLE-FILE AUTOMATED TESTING AND COMPARISON
        # --------------------------------------------------

        st.divider()
        st.header("🧪 Single-File Automated Testing")

        st.write(
            "Upload pytest tests or generate tests with Gemini. "
            "Then compare the original and corrected versions."
        )

        st.warning(
            "Security notice: pytest executes Python code on this "
            "computer. This prototype is not a secure sandbox. "
            "Only run code and tests that you trust."
        )

        test_mode = st.radio(
            "Choose how to provide tests",
            [
                "Upload pytest file",
                "Generate tests with Gemini",
            ],
            horizontal=True,
            key="single_test_mode",
        )

        if test_mode == "Upload pytest file":
            uploaded_test_file = st.file_uploader(
                "Upload your pytest test file (.py)",
                type=["py"],
                key="single_pytest_upload",
            )

            if uploaded_test_file is not None:
                try:
                    uploaded_test_code = (
                        uploaded_test_file.getvalue().decode(
                            "utf-8-sig"
                        )
                    )

                    if (
                        st.session_state.single_test_code
                        != uploaded_test_code
                    ):
                        st.session_state.single_test_code = uploaded_test_code
                        st.session_state.single_test_explanation = (
                            "Tests uploaded by the user."
                        )
                        st.session_state.single_test_result = None
                        st.session_state.single_comparison_result = None

                except UnicodeDecodeError:
                    st.error(
                        "The test file must use UTF-8 encoding."
                    )

        else:
            st.caption(
                "Gemini will inspect the original code, proposed "
                "corrected code and diagnosis to create tests for "
                "the intended behaviour."
            )

            if st.button(
                "✨ Generate Comparison Tests with Gemini",
                use_container_width=True,
                disabled=not (
                    source_code.strip()
                    and repair_valid
                ),
                key="generate_comparison_tests",
            ):
                try:
                    with st.spinner(
                        "Gemini is generating comparison tests..."
                    ):
                        generated = generate_pytest_tests(
                            original_code=source_code,
                            corrected_code=diagnosis["fixed_code"],
                            file_name=file_name,
                            diagnosis=diagnosis,
                        )

                    st.session_state.single_test_code = (
                        generated["test_code"]
                    )

                    st.session_state.single_test_explanation = (
                        generated["explanation"]
                    )

                    st.session_state.single_test_result = None
                    st.session_state.single_comparison_result = None

                    st.success(
                        "Comparison tests generated. "
                        "Review them before execution."
                    )

                except Exception as error:
                    st.error(
                        f"Test generation failed: {error}"
                    )

        if st.session_state.single_test_code:
            st.subheader("Review Pytest Test Code")

            if st.session_state.single_test_explanation:
                st.info(
                    st.session_state.single_test_explanation
                )

            edited_test_code = st.text_area(
                "Test code (review or edit before execution)",
                value=st.session_state.single_test_code,
                height=300,
                key="single_test_code_editor",
            )

            st.session_state.single_test_code = edited_test_code

            authorize_single_tests = st.checkbox(
                "I understand that pytest executes the source and "
                "test code on this computer, and I trust both files.",
                key="authorize_single_file_tests",
            )

            st.caption(
                "Both versions are run in separate temporary folders. "
                "The same test file is used for both runs."
            )

            if st.button(
                "▶ Compare Original vs Corrected Code",
                type="primary",
                use_container_width=True,
                disabled=not (
                    authorize_single_tests
                    and repair_valid
                    and bool(edited_test_code.strip())
                ),
                key="compare_single_file_versions",
            ):
                try:
                    with st.spinner(
                        "Running the same pytest tests against both versions..."
                    ):
                        comparison = compare_original_and_corrected(
                            original_code=source_code,
                            corrected_code=diagnosis["fixed_code"],
                            file_name=file_name,
                            test_code=edited_test_code,
                        )

                    st.session_state.single_comparison_result = comparison

                except Exception as error:
                    st.session_state.single_comparison_result = None
                    st.error(
                        f"Code comparison failed: {error}"
                    )

            if st.session_state.single_comparison_result:
                show_comparison_results(
                    st.session_state.single_comparison_result
                )

            if st.button(
                "▶ Run Tests Against Original Code Only",
                disabled=not authorize_single_tests,
                key="run_original_only",
            ):
                try:
                    with st.spinner(
                        "Running tests against original code..."
                    ):
                        result = run_single_file_tests(
                            source_code,
                            file_name,
                            edited_test_code,
                        )

                    st.session_state.single_test_result = result

                except Exception as error:
                    st.error(
                        f"Test execution failed: {error}"
                    )

            if st.session_state.single_test_result:
                show_test_results(
                    st.session_state.single_test_result,
                    "Original Code Test Results",
                )


# ==========================================================
# COMPLETE ZIP PROJECT MODE
# ==========================================================

elif page == "Complete ZIP Project":

    st.header("📦 Complete ZIP Project Debugging")

    st.write(
        "Upload a complete Python project in ZIP format."
    )

    st.warning(
        "Security notice: Uploaded project tests execute code "
        "on the computer running this application. This prototype "
        "does not provide a secure sandbox. Only upload and test "
        "projects you trust."
    )

    uploaded_zip = st.file_uploader(
        "Upload Complete Python Project",
        type=["zip"],
        key="zip_project_upload",
    )

    if uploaded_zip is not None:
        if st.button(
            "Extract and Analyze Project",
            type="primary",
            use_container_width=True,
        ):
            reset_project_state()

            workspace = tempfile.mkdtemp(
                prefix="agentic_debugging_"
            )

            try:
                with st.spinner("Extracting project..."):
                    project_path = extract_project_zip(
                        uploaded_zip,
                        workspace,
                    )

                project_path = Path(project_path).resolve()

                if (
                    not project_path.exists()
                    or not project_path.is_dir()
                ):
                    raise FileNotFoundError(
                        "Extracted project folder was not found."
                    )

                with st.spinner("Analyzing project..."):
                    analysis_results = analyze_project(
                        project_path
                    )

                st.session_state.workspace = workspace
                st.session_state.project_path = str(project_path)
                st.session_state.analysis_results = analysis_results

                st.session_state.last_test_result = None
                st.session_state.repair_result = None
                st.session_state.repair_file = None
                st.session_state.repair_applied = False
                st.session_state.post_repair_result = None

                st.success(
                    "Project extracted and analyzed successfully!"
                )

            except Exception as error:
                shutil.rmtree(workspace, ignore_errors=True)
                st.error(
                    f"Project extraction or analysis failed: {error}"
                )

    # ------------------------------------------------------
    # PROJECT ANALYSIS
    # ------------------------------------------------------

    if st.session_state.project_path:

        project_path = Path(
            st.session_state.project_path
        )

        results = (
            st.session_state.analysis_results or {}
        )

        st.divider()
        st.header("📊 Project Analysis Results")

        python_files = get_project_files(project_path)

        test_files = [
            path for path in python_files
            if path.name.startswith("test_")
            or path.name.endswith("_test.py")
        ]

        col1, col2, col3 = st.columns(3)

        col1.metric("Python Files", len(python_files))
        col2.metric("Test Files", len(test_files))
        col3.metric(
            "Syntax Errors",
            len(results.get("syntax_errors", [])),
        )

        with st.expander("View Python Files"):
            for path in python_files:
                st.write(
                    get_relative_path(path, project_path)
                )

        with st.expander("View Project Analysis Details"):
            st.json(results)

        # --------------------------------------------------
        # INITIAL TEST EXECUTION
        # --------------------------------------------------

        st.divider()
        st.header("🧪 Automated Project Testing")

        allow_tests = st.checkbox(
            "I understand that pytest executes uploaded project "
            "code and I trust this project.",
            key="allow_initial_tests",
        )

        if st.button(
            "Run Project Tests",
            disabled=not allow_tests,
            use_container_width=True,
        ):
            try:
                with st.spinner("Running pytest..."):
                    test_result = run_tests(
                        project_path,
                        timeout=60,
                    )

                st.session_state.last_test_result = test_result

                st.session_state.pop(
                    "zip_selected_python_file",
                    None,
                )

                st.session_state.repair_result = None
                st.session_state.repair_file = None
                st.session_state.repair_applied = False
                st.session_state.post_repair_result = None

            except Exception as error:
                st.error(
                    f"Test execution failed: {error}"
                )

        if st.session_state.last_test_result:
            show_test_results(
                st.session_state.last_test_result,
                "Initial Project Test Results",
            )

        # --------------------------------------------------
        # AUTOMATIC FAILURE ANALYSIS
        # --------------------------------------------------

        st.divider()
        st.header("🤖 AI Project File Diagnosis")

        test_result = (
            st.session_state.last_test_result or {}
        )

        source_files = [
            path for path in python_files
            if not path.name.startswith("test_")
            and not path.name.endswith("_test.py")
        ]

        if not source_files:
            source_files = python_files

        if not source_files:
            st.warning("No Python source files were found.")

        else:
            relative_files = [
                get_relative_path(path, project_path)
                for path in source_files
            ]

            failed_test_files = test_result.get(
                "failed_test_files", []
            )

            imported_source_files = test_result.get(
                "imported_source_files", []
            )

            candidate_source_files = test_result.get(
                "candidate_source_files", []
            )

            failure_details = test_result.get(
                "failure_details", []
            )

            def normalize_path(value):
                return (
                    str(value)
                    .replace("\\", "/")
                    .lstrip("./")
                )

            normalized_candidates = {
                normalize_path(item)
                for item in candidate_source_files
            }

            matching_candidates = [
                relative_file
                for relative_file in relative_files
                if normalize_path(relative_file)
                in normalized_candidates
            ]

            st.subheader("Automatic Failure Analysis")

            if st.session_state.last_test_result:
                if failed_test_files:
                    st.error("Failed Test Files")
                    for item in failed_test_files:
                        st.write(f"• `{item}`")
                else:
                    st.info(
                        "No failed test files were identified."
                    )

                if imported_source_files:
                    st.write("**Imported Source Files**")
                    for item in imported_source_files:
                        st.write(f"• `{item}`")

                if matching_candidates:
                    st.success(
                        "Likely source files identified using "
                        "test failure and import analysis."
                    )
                    for item in matching_candidates:
                        st.write(f"• `{item}`")
                else:
                    st.info(
                        "No matching candidate source file was "
                        "identified. You can select a file manually."
                    )
            else:
                st.info(
                    "Run project tests first to identify failed "
                    "tests and likely source files."
                )

            default_index = 0

            if matching_candidates:
                default_index = relative_files.index(
                    matching_candidates[0]
                )

            selected_file = st.selectbox(
                "Select Python File to Diagnose",
                relative_files,
                index=default_index,
                key="zip_selected_python_file",
            )

            try:
                selected_path = resolve_project_file(
                    project_path,
                    selected_file,
                )

                original_code = selected_path.read_text(
                    encoding="utf-8-sig"
                )

                st.caption(
                    f"Selected file size: "
                    f"{len(original_code):,} characters"
                )

                with st.expander("View Original Source Code"):
                    st.code(original_code, language="python")

            except Exception as error:
                st.error(
                    f"Unable to read selected file: {error}"
                )
                original_code = ""
                selected_path = None

            # ----------------------------------------------
            # GEMINI DIAGNOSIS
            # ----------------------------------------------

            if st.button(
                "Diagnose Selected File with Gemini",
                type="primary",
                use_container_width=True,
            ):
                if not original_code.strip():
                    st.error(
                        "The selected Python file is empty or unreadable."
                    )

                elif len(original_code) > 100000:
                    st.error(
                        "This file exceeds the 100,000-character "
                        "application limit."
                    )

                else:
                    try:
                        test_output = get_test_output(
                            st.session_state.last_test_result
                        )

                        diagnosis_context = (
                            "PROJECT PYTEST OUTPUT:\n"
                            + test_output
                            + "\n\nFAILED TEST FILES:\n"
                            + str(failed_test_files)
                            + "\n\nIMPORTED SOURCE FILES:\n"
                            + str(imported_source_files)
                            + "\n\nLIKELY CANDIDATE SOURCE FILES:\n"
                            + str(candidate_source_files)
                            + "\n\nFAILURE DETAILS:\n"
                            + str(failure_details)
                        )

                        with st.spinner(
                            "Gemini is analyzing the selected file..."
                        ):
                            diagnosis = repair_code(
                                original_code,
                                diagnosis_context,
                                file_name=selected_path.name,
                            )

                        st.session_state.repair_result = diagnosis
                        st.session_state.repair_file = str(
                            selected_path.resolve()
                        )

                        st.session_state.repair_applied = False
                        st.session_state.post_repair_result = None

                    except Exception as error:
                        st.error(
                            f"Gemini diagnosis failed: {error}"
                        )

            # ----------------------------------------------
            # PROJECT DIAGNOSIS DISPLAY
            # ----------------------------------------------

            diagnosis = st.session_state.repair_result

            if (
                diagnosis
                and selected_path is not None
                and st.session_state.repair_file
                == str(selected_path.resolve())
            ):

                st.divider()
                st.header("🧠 Project Diagnosis Results")

                try:
                    selected_path = Path(
                        st.session_state.repair_file
                    ).resolve()

                    selected_path.relative_to(
                        project_path.resolve()
                    )

                    original_code = selected_path.read_text(
                        encoding="utf-8-sig"
                    )

                    repair_is_valid = display_repair(
                        diagnosis=diagnosis,
                        original_code=original_code,
                        file_name=selected_path.name,
                        key_prefix="zip_repair",
                    )

                    if repair_is_valid:
                        fixed_code = diagnosis["fixed_code"]

                        st.divider()
                        st.subheader(
                            "Approve and Apply Correction"
                        )

                        st.warning(
                            "The correction will be written only "
                            "to the temporary extracted project copy. "
                            "Your original ZIP file will not be modified."
                        )

                        if not st.session_state.repair_applied:
                            if st.button(
                                "Approve and Apply Repair",
                                type="primary",
                                key="approve_zip_repair",
                            ):
                                try:
                                    current_target = Path(
                                        st.session_state.repair_file
                                    ).resolve()

                                    current_target.relative_to(
                                        project_path.resolve()
                                    )

                                    validation = validate_python_code(
                                        fixed_code,
                                        current_target.name,
                                    )

                                    if not validation.get(
                                        "success", False
                                    ):
                                        raise ValueError(
                                            "Corrected code failed "
                                            "syntax validation."
                                        )

                                    current_target.write_text(
                                        fixed_code,
                                        encoding="utf-8",
                                    )

                                    st.session_state.repair_applied = True
                                    st.session_state.post_repair_result = None

                                    st.success(
                                        "Repair applied to the extracted project!"
                                    )

                                    st.info(
                                        "Your original ZIP and local "
                                        "source files remain unchanged."
                                    )

                                except Exception as error:
                                    st.error(
                                        f"Could not apply repair: {error}"
                                    )

                        else:
                            st.success(
                                "Approved repair has been applied."
                            )

                        # ----------------------------------
                        # POST-REPAIR TEST VALIDATION
                        # ----------------------------------

                        if st.session_state.repair_applied:
                            st.divider()
                            st.header(
                                "🔄 Post-Repair Test Validation"
                            )

                            st.warning(
                                "This runs pytest against the extracted "
                                "project. Only continue if you trust it."
                            )

                            authorize_post_tests = st.checkbox(
                                "I authorize post-repair pytest execution.",
                                key="authorize_post_repair_tests",
                            )

                            if st.button(
                                "Run Post-Repair Validation",
                                disabled=not authorize_post_tests,
                                key="run_post_repair_tests",
                            ):
                                try:
                                    with st.spinner(
                                        "Validating repaired project..."
                                    ):
                                        validation_result = run_tests(
                                            project_path,
                                            timeout=60,
                                        )

                                    st.session_state.post_repair_result = (
                                        validation_result
                                    )

                                except Exception as error:
                                    st.error(
                                        "Post-repair test execution failed: "
                                        f"{error}"
                                    )

                            if st.session_state.post_repair_result:
                                validation_result = (
                                    st.session_state.post_repair_result
                                )

                                show_test_results(
                                    validation_result,
                                    "Post-Repair Validation Results",
                                )

                                total_tests = (
                                    validation_result.get("passed", 0)
                                    + validation_result.get("failed", 0)
                                    + validation_result.get("errors", 0)
                                )

                                if (
                                    validation_result.get("success")
                                    and total_tests > 0
                                    and validation_result.get("failed", 0) == 0
                                    and validation_result.get("errors", 0) == 0
                                ):
                                    st.success(
                                        "Repair successfully validated. "
                                        "All collected tests passed."
                                    )
                                else:
                                    st.warning(
                                        "The repair is not fully validated. "
                                        "Review the test output."
                                    )

                except Exception as error:
                    st.error(
                        f"Could not display project diagnosis: {error}"
                    )
