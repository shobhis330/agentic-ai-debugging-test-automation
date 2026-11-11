
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.test_coverage import (
    generate_pytest_tests,
    run_coverage_tests
)


st.set_page_config(
    page_title="Test Coverage Report",
    page_icon="🧪",
    layout="wide"
)

st.title("🧪 Test Coverage Report")

st.write(
    "Generate or upload pytest test cases, execute them, "
    "and measure how much of your Python source code is covered."
)

st.info(
    "Line coverage measures which executable source lines were run "
    "during the tests. It does not prove that the code is correct."
)

st.warning(
    "Security notice: Running tests executes Python source and test code "
    "on the computer running this application. This prototype is not "
    "a secure sandbox. Only run code and tests that you trust."
)


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

defaults = {
    "coverage_test_code": "",
    "coverage_test_explanation": "",
    "coverage_result": None,
    "coverage_last_source": "",
    "coverage_last_file": ""
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------------------------------------------------
# SOURCE CODE INPUT
# ---------------------------------------------------------

st.subheader("1. Python Source Code")

input_method = st.radio(
    "Choose code input method",
    ["Upload Python File", "Paste Python Code"],
    horizontal=True,
    key="coverage_input_method"
)

source_code = ""
file_name = "solution.py"

if input_method == "Upload Python File":

    uploaded_file = st.file_uploader(
        "Upload your Python source file",
        type=["py"],
        key="coverage_source_upload"
    )

    if uploaded_file is not None:
        source_code = uploaded_file.getvalue().decode(
            "utf-8-sig",
            errors="replace"
        )
        file_name = uploaded_file.name

        st.success(f"Loaded: {file_name}")

else:

    file_name = st.text_input(
        "Python file name",
        value="solution.py",
        key="coverage_source_filename"
    )

    if not file_name.strip():
        file_name = "solution.py"

    if not file_name.lower().endswith(".py"):
        file_name += ".py"

    source_code = st.text_area(
        "Paste your Python source code",
        height=300,
        placeholder="Paste your Python code here...",
        key="coverage_source_code"
    )


# Clear old results when the source changes.
if (
    source_code != st.session_state.coverage_last_source
    or file_name != st.session_state.coverage_last_file
):
    st.session_state.coverage_result = None
    st.session_state.coverage_test_code = ""
    st.session_state.coverage_test_explanation = ""

    st.session_state.coverage_last_source = source_code
    st.session_state.coverage_last_file = file_name


st.divider()


# ---------------------------------------------------------
# TEST CASE INPUT
# ---------------------------------------------------------

st.subheader("2. Provide Pytest Test Cases")

test_method = st.radio(
    "Choose how to provide test cases",
    ["Generate Tests with Gemini", "Upload Test File"],
    horizontal=True,
    key="coverage_test_method"
)


if test_method == "Generate Tests with Gemini":

    st.write(
        "Gemini will inspect your source code and generate "
        "pytest test cases."
    )

    if st.button(
        "✨ Generate Test Cases",
        type="primary",
        disabled=not bool(source_code.strip()),
        key="coverage_generate_tests"
    ):

        try:
            with st.spinner("Gemini is generating test cases..."):

                generated = generate_pytest_tests(
                    source_code,
                    file_name
                )

            st.session_state.coverage_test_code = generated["test_code"]
            st.session_state.coverage_test_explanation = (
                generated["explanation"]
            )
            st.session_state.coverage_result = None

            st.success("Test cases generated successfully.")

        except Exception as error:
            st.error(f"Test generation failed: {error}")

else:

    uploaded_test_file = st.file_uploader(
        "Upload a pytest file",
        type=["py"],
        key="coverage_test_upload"
    )

    if uploaded_test_file is not None:

        try:
            uploaded_test_code = uploaded_test_file.getvalue().decode(
                "utf-8-sig"
            )

            if (
                uploaded_test_code
                != st.session_state.coverage_test_code
            ):
                st.session_state.coverage_test_code = uploaded_test_code
                st.session_state.coverage_test_explanation = (
                    "Tests uploaded by the user."
                )
                st.session_state.coverage_result = None

        except UnicodeDecodeError:
            st.error("The test file must use UTF-8 encoding.")


# ---------------------------------------------------------
# REVIEW GENERATED OR UPLOADED TESTS
# ---------------------------------------------------------

if st.session_state.coverage_test_code:

    st.divider()
    st.subheader("3. Review Test Cases")

    if st.session_state.coverage_test_explanation:
        st.info(st.session_state.coverage_test_explanation)

    edited_test_code = st.text_area(
        "Review or edit your pytest code before execution",
        value=st.session_state.coverage_test_code,
        height=300,
        key="coverage_test_editor"
    )

    st.session_state.coverage_test_code = edited_test_code

    st.download_button(
        "⬇️ Download Test Cases",
        data=edited_test_code,
        file_name="test_generated.py",
        mime="text/x-python",
        disabled=not bool(edited_test_code.strip()),
        key="coverage_download_tests"
    )

    st.divider()

    st.subheader("4. Run Tests and Measure Coverage")

    authorized = st.checkbox(
        "I understand that Python source code and test code "
        "will execute on this computer, and I trust both files.",
        key="coverage_execution_consent"
    )

    if st.button(
        "▶ Run Tests and Generate Coverage Report",
        type="primary",
        disabled=(
            not authorized
            or not source_code.strip()
            or not edited_test_code.strip()
        ),
        key="coverage_run_tests"
    ):

        try:
            with st.spinner(
                "Running pytest and measuring source-code coverage..."
            ):

                result = run_coverage_tests(
                    source_code=source_code,
                    file_name=file_name,
                    test_code=edited_test_code,
                    timeout=60
                )

            st.session_state.coverage_result = result

        except Exception as error:
            st.session_state.coverage_result = None
            st.error(f"Test execution failed: {error}")


# ---------------------------------------------------------
# COVERAGE RESULTS
# ---------------------------------------------------------

result = st.session_state.coverage_result

if result:

    st.divider()
    st.header("📊 Test Coverage Results")

    passed = result["passed"]
    failed = result["failed"]
    errors = result["errors"]
    skipped = result["skipped"]
    total = result["total"]

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Passed", passed)
    col2.metric("Failed", failed)
    col3.metric("Errors", errors)
    col4.metric("Skipped", skipped)

    st.subheader("Test Execution Summary")

    if total == 0:
        st.warning(
            "No tests were collected. The submitted code has not "
            "been validated by this test run."
        )

    else:

        st.metric(
            "Test Pass Percentage",
            f'{result["pass_percentage"]:.2f}%'
        )

        if result["success"]:
            st.success("All collected tests passed.")

        else:
            st.error(
                "Some tests failed or produced errors. "
                "Review the execution output below."
            )

    st.divider()
    st.subheader("📈 Source Code Line Coverage")

    coverage = result["coverage"]

    if coverage["available"]:

        percentage = coverage["percent"]

        covered_lines = coverage["covered_lines"]
        total_lines = coverage["total_lines"]
        missing_lines = coverage["missing_lines"]

        coverage_col1, coverage_col2, coverage_col3 = st.columns(3)

        coverage_col1.metric(
            "Line Coverage",
            f"{percentage:.2f}%"
        )

        coverage_col2.metric(
            "Covered Lines",
            covered_lines
        )

        coverage_col3.metric(
            "Executable Lines",
            total_lines
        )

        st.progress(
            min(max(percentage / 100, 0.0), 1.0)
        )

        if percentage == 100:
            st.success(
                "All executable source lines were covered in this run."
            )

        elif percentage >= 80:
            st.success(
                "Good line coverage. Some executable lines may remain untested."
            )

        elif percentage >= 50:
            st.warning(
                "Moderate line coverage. Add tests for uncovered lines."
            )

        else:
            st.warning(
                "Low line coverage. More test cases are recommended."
            )

        st.write("**Uncovered source lines:**")

        if missing_lines:
            st.code(
                ", ".join(str(line) for line in missing_lines)
            )
        else:
            st.success("No uncovered executable lines were reported.")

    else:

        st.warning(
            "Line coverage could not be calculated."
        )

        if coverage.get("error"):
            st.caption(coverage["error"])

    st.divider()
    st.subheader("📋 Detailed Test Execution Output")

    with st.expander("View pytest output", expanded=True):
        st.code(
            result.get("output", "No execution output available."),
            language="text"
        )

    # Download report
    report_data = {
        "file_name": file_name,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "total": total,
        "test_pass_percentage": result["pass_percentage"],
        "coverage": coverage
    }

    st.download_button(
        "⬇️ Download Coverage Report (JSON)",
        data=json.dumps(report_data, indent=4),
        file_name="test_coverage_report.json",
        mime="application/json",
        key="coverage_download_report"
    )

    st.caption(
        "Coverage indicates which executable lines were run. "
        "It does not measure whether assertions are correct or "
        "whether every possible behaviour is tested."
    )
