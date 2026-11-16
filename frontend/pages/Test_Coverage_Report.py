
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
    "coverage_last_file": "",
    "coverage_last_source_identity": None,
    "coverage_last_version": "",
    "coverage_result_version": ""
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------------------------------------------------
# SOURCE CODE INPUT
# ---------------------------------------------------------

st.subheader("1. Python Source Code")

shared_original_source = st.session_state.get("central_original_code") or ""
shared_corrected_source = st.session_state.get("central_corrected_code") or ""
shared_name = (
    st.session_state.get("central_selected_file")
    or st.session_state.get("central_upload_name")
    or "solution.py"
)
shared_path = st.session_state.get("project_path")
coverage_source_rel_path = st.session_state.get("central_selected_file") or ""
coverage_project_root = shared_path if shared_path and shared_original_source else None
coverage_test_rel_path = None
coverage_uses_shared_project = bool(
    shared_original_source.strip()
    and coverage_project_root
    and coverage_source_rel_path
)
coverage_version_label = "Original Code"
source_code = shared_original_source
file_name = shared_name

if coverage_uses_shared_project:
    version_options = ["Original Code"]
    if shared_corrected_source.strip():
        version_options.append("Corrected Code")

    selected_version = st.radio(
        "Choose which code version to test",
        version_options,
        horizontal=True,
        key="coverage_code_version",
        help="The same pytest test cases are used for either version."
    )
    if selected_version == "Corrected Code":
        source_code = shared_corrected_source
        coverage_version_label = "Corrected Code"
    else:
        source_code = shared_original_source
        coverage_version_label = "Original Code"

    st.success(f"Using shared debugging session: {file_name}")
    st.info(
        f"Selected version: **{coverage_version_label}**. "
        "The original and corrected versions are tested separately in an isolated temporary copy. "
        "Your uploaded project files are not overwritten."
    )
else:
    source_code = ""
    if shared_path:
        candidates = sorted(Path(shared_path).rglob("*.py"))
        ignored = {
            ".venv", "venv", ".git", "node_modules",
            "__pycache__", ".pytest_cache"
        }
        candidates = [
            p for p in candidates
            if not any(part.lower() in ignored for part in p.parts)
        ]
        candidates = [
            p for p in candidates
            if not (
                p.name.lower().startswith("test_")
                or p.name.lower().endswith("_test.py")
            )
        ]
        if candidates:
            labels = [p.relative_to(shared_path).as_posix() for p in candidates]
            selected = st.selectbox(
                "Python file from uploaded project",
                labels,
                key="coverage_shared_file_v3"
            )
            chosen = candidates[labels.index(selected)]
            source_code = chosen.read_text(encoding="utf-8-sig", errors="replace")
            file_name = chosen.name
            coverage_source_rel_path = selected
            coverage_project_root = shared_path
            coverage_uses_shared_project = True
            coverage_version_label = "Project Source"

    if source_code.strip():
        st.success(f"Using project source: {file_name}")
    else:
        st.info(
            "No main project is uploaded yet. Upload a ZIP project or use "
            "Single Python Code first."
        )

with st.expander("Use a different file for Test Coverage (optional)"):
    local_file = st.file_uploader(
        "Upload a Python file for this coverage report only",
        type=["py"],
        key="coverage_local_upload_v3"
    )
    if local_file is not None:
        source_code = local_file.getvalue().decode("utf-8-sig", errors="replace")
        file_name = local_file.name
        coverage_project_root = None
        coverage_source_rel_path = None
        coverage_test_rel_path = None
        coverage_uses_shared_project = False
        coverage_version_label = "Uploaded File"
        st.info(f"Using separate file for this feature only: {file_name}")


# Clear tests only when the selected source file changes.
# Switching Original/Corrected must preserve the exact same test suite.
source_identity = (
    coverage_source_rel_path or file_name,
    file_name,
    shared_original_source if (coverage_uses_shared_project and shared_original_source) else source_code,
)
if source_identity != st.session_state.coverage_last_source_identity:
    st.session_state.coverage_result = None
    st.session_state.coverage_test_code = ""
    st.session_state.coverage_test_explanation = ""
    st.session_state.coverage_last_source_identity = source_identity

# A result belongs to one code version only. Never display an Original
# result while Corrected Code is selected, or vice versa.
if coverage_version_label != st.session_state.coverage_last_version:
    st.session_state.coverage_result = None
    st.session_state.coverage_last_version = coverage_version_label

st.session_state.coverage_last_source = source_code
st.session_state.coverage_last_file = file_name


st.divider()


# ---------------------------------------------------------
# TEST CASE INPUT
# ---------------------------------------------------------

st.subheader("2. Provide Pytest Test Cases")

test_method = st.radio(
    "Choose how to provide test cases",
    ["Reuse Tests from Shared Project", "Generate Tests with Gemini", "Upload Test File"],
    horizontal=True,
    key="coverage_test_method_v2"
)

if test_method == "Reuse Tests from Shared Project":
    shared_test_files = []
    if shared_path:
        shared_root = Path(shared_path)
        shared_test_files = sorted(
            p for p in shared_root.rglob("*.py")
            if (p.name.lower().startswith("test_") or p.name.lower().endswith("_test.py"))
            and not any(part.lower() in {".venv", "venv", ".git", "node_modules", "__pycache__", ".pytest_cache"} for part in p.parts)
        )
    if shared_test_files:
        test_labels = [p.relative_to(shared_path).as_posix() for p in shared_test_files]
        selected_test = st.selectbox("Select an existing project test file", test_labels, key="coverage_shared_test_file")
        chosen_test = shared_test_files[test_labels.index(selected_test)]
        coverage_test_rel_path = selected_test
        reused_test_code = chosen_test.read_text(encoding="utf-8-sig", errors="replace")
        if reused_test_code != st.session_state.coverage_test_code:
            st.session_state.coverage_test_code = reused_test_code
            st.session_state.coverage_test_explanation = f"Reused from uploaded project: {selected_test}"
            st.session_state.coverage_result = None
        st.success(f"Using tests from the shared project: {selected_test}")
    else:
        shared_generated_tests = st.session_state.get("central_test_code") or ""
        same_shared_source = (
            coverage_uses_shared_project
            and bool(shared_original_source.strip())
            and bool(st.session_state.get("central_test_code"))
        )
        if same_shared_source and shared_generated_tests.strip():
            if st.session_state.coverage_test_code != shared_generated_tests:
                st.session_state.coverage_test_code = shared_generated_tests
                st.session_state.coverage_test_explanation = (
                    st.session_state.get("central_test_explanation")
                    or "Reused AI-generated pytest tests from the shared debugging workflow."
                )
                st.session_state.coverage_result = None
            st.success("Reusing AI-generated pytest tests from Original vs Corrected Comparison.")
            st.caption("The exact same test cases are retained when you switch between Original Code and Corrected Code.")
        else:
            st.info("No pytest files or reusable generated tests were found in the shared project. Choose Generate Tests with Gemini or Upload Test File.")

elif test_method == "Generate Tests with Gemini":

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
            # Keep generated tests available to the comparison workflow too.
            if coverage_uses_shared_project:
                st.session_state.central_test_code = generated["test_code"]
                st.session_state.central_test_explanation = generated["explanation"]

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
    if coverage_uses_shared_project:
        st.session_state.central_test_code = edited_test_code

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
                    timeout=60,
                    project_root=coverage_project_root,
                    source_rel_path=coverage_source_rel_path,
                    test_rel_path=coverage_test_rel_path,
                )

            st.session_state.coverage_result = result
            st.session_state.coverage_result_version = coverage_version_label

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
    result_version = (
        st.session_state.get("coverage_result_version")
        or coverage_version_label
    )
    st.info(f"Code version tested: **{result_version}**")

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
        "code_version": result_version,
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
        "The selected code version is tested using the same pytest test cases. "
        "Coverage indicates which executable lines were run. "
        "It does not measure whether assertions are correct or "
        "whether every possible behaviour is tested."
    )
