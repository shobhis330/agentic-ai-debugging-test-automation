
import streamlit as st

from core.test_comparison import compare_versions

st.set_page_config(
    page_title="Original vs Corrected Comparison",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ Original vs Corrected Test Comparison")
st.caption(
    "Run the same pytest test cases against original and corrected Python code."
)

st.warning(
    "Uploaded Python code and tests execute on this computer. "
    "This is not a secure sandbox. Only execute code you trust."
)

st.info(
    "This feature does not call Gemini. You must provide both code versions "
    "and the pytest test file."
)

file_name = st.text_input(
    "Python file name",
    value="target.py",
    help="Use a .py filename, for example calculator.py."
)

st.subheader("1. Original Python Code")
original_code = st.text_area(
    "Paste the original code",
    height=250,
    key="comparison_original"
)

st.subheader("2. Corrected Python Code")
corrected_code = st.text_area(
    "Paste the corrected code",
    height=250,
    key="comparison_corrected"
)

st.subheader("3. Pytest Test Cases")
test_code = st.text_area(
    "Paste the same pytest tests for both versions",
    height=250,
    key="comparison_tests",
    placeholder="Example:\ndef test_add():\n    from target import add\n    assert add(2, 3) == 5"
)

st.caption(
    "The test file should import your Python module using its filename "
    "without the .py extension. For example, calculator.py becomes "
    "'from calculator import add'."
)

st.divider()

authorized = st.checkbox(
    "I have reviewed the original code, corrected code and tests, "
    "and authorize their execution on this computer."
)

if st.button(
    "Compare Test Results",
    type="primary",
    disabled=not authorized
):
    if not original_code.strip():
        st.error("Please provide the original Python code.")
    elif not corrected_code.strip():
        st.error("Please provide the corrected Python code.")
    elif not test_code.strip():
        st.error("Please provide pytest test cases.")
    elif not file_name.strip() or not file_name.endswith(".py"):
        st.error("Please enter a valid Python filename ending in .py.")
    else:
        with st.spinner("Running tests against both code versions..."):
            result = compare_versions(
                original_code,
                corrected_code,
                test_code,
                file_name
            )

        if not result.get("success"):
            st.error(result.get("error", "Comparison could not be completed."))

            with st.expander("Original execution output"):
                st.code(
                    result.get("original", {}).get("output", "")
                    or result.get("original", {}).get("error", "No output"),
                    language="text"
                )

            with st.expander("Corrected execution output"):
                st.code(
                    result.get("corrected", {}).get("output", "")
                    or result.get("corrected", {}).get("error", "No output"),
                    language="text"
                )
        else:
            st.session_state["comparison_result"] = result

if "comparison_result" in st.session_state:
    result = st.session_state["comparison_result"]

    st.divider()
    st.subheader("4. Comparison Results")

    original = result["original"]["counts"]
    corrected = result["corrected"]["counts"]
    comparison = result["comparison"]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Original Code")
        st.metric("Passed", original["passed"])
        st.metric("Failed", original["failed"])
        st.metric("Errors", original["errors"])
        st.metric("Success Rate", f'{original["success_rate"]}%')

    with col2:
        st.markdown("### Corrected Code")
        st.metric("Passed", corrected["passed"])
        st.metric("Failed", corrected["failed"])
        st.metric("Errors", corrected["errors"])
        st.metric("Success Rate", f'{corrected["success_rate"]}%')

    st.divider()
    st.subheader("5. Improvement Summary")

    summary_col1, summary_col2, summary_col3 = st.columns(3)

    summary_col1.metric(
        "Change in Passed Tests",
        comparison["passed_change"],
        delta=comparison["passed_change"]
    )

    summary_col2.metric(
        "Change in Failed Tests",
        comparison["failed_change"],
        delta=comparison["failed_change"],
        delta_color="inverse"
    )

    rate_change = round(
        comparison["corrected_success_rate"]
        - comparison["original_success_rate"],
        2
    )

    summary_col3.metric(
        "Success Rate Change",
        f"{rate_change} percentage points"
    )

    if (
        corrected["failed"] == 0
        and corrected["errors"] == 0
        and corrected["total"] > 0
    ):
        st.success("All collected tests passed on the corrected version.")
    elif comparison["improved"]:
        st.success("The corrected version shows an improvement in test results.")
    else:
        st.warning(
            "The corrected version has not demonstrated an improvement. "
            "Review the test outputs."
        )

    with st.expander("Original Code Test Output"):
        st.code(result["original"]["output"], language="text")

    with st.expander("Corrected Code Test Output"):
        st.code(result["corrected"]["output"], language="text")

    st.download_button(
        "Download Comparison Report",
        data=(
            "ORIGINAL VS CORRECTED TEST COMPARISON\n\n"
            f"Original results: {original}\n\n"
            f"Corrected results: {corrected}\n\n"
            f"Improvement summary: {comparison}\n\n"
            "ORIGINAL OUTPUT\n"
            f'{result["original"]["output"]}\n\n'
            "CORRECTED OUTPUT\n"
            f'{result["corrected"]["output"]}'
        ),
        file_name="test_comparison_report.txt",
        mime="text/plain"
    )
