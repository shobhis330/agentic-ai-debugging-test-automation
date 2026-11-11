
import streamlit as st
import pandas as pd
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.code_quality import analyze_code_quality


st.set_page_config(
    page_title="Code Quality Analysis",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Code Quality Analysis")

st.write(
    "Analyze Python code for quality issues, potential bugs, "
    "and function complexity."
)

st.info(
    "Static analysis examines source code without executing it. "
    "Potential bug findings are heuristic warnings and should be reviewed."
)

input_method = st.radio(
    "Choose code input method",
    ["Upload Python File", "Paste Python Code"],
    horizontal=True
)

source_code = ""

if input_method == "Upload Python File":
    uploaded_file = st.file_uploader(
        "Upload a Python file",
        type=["py"],
        key="quality_file_upload"
    )

    if uploaded_file is not None:
        source_code = uploaded_file.getvalue().decode(
            "utf-8", errors="replace"
        )
        st.success(f"Loaded: {uploaded_file.name}")

else:
    source_code = st.text_area(
        "Paste your Python code",
        height=300,
        placeholder="Paste your Python code here...",
        key="quality_code_input"
    )

if st.button("🔍 Analyze Code", type="primary"):
    if not source_code.strip():
        st.warning("Please upload or paste Python code first.")
        st.session_state.pop("quality_analysis_result", None)
    else:
        with st.spinner("Analyzing your code..."):
            result = analyze_code_quality(source_code)

        st.session_state["quality_analysis_result"] = result

result = st.session_state.get("quality_analysis_result")

if result:
    if not result["success"]:
        st.error(result["error"])

    else:
        summary = result["summary"]

        st.divider()
        st.subheader("Analysis Results")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Code Quality Score", f'{result["score"]}/100')
        col2.metric("Quality Issues", result["total_issues"])
        col3.metric("Potential Bugs", summary["potential_bugs"])
        col4.metric("Functions", summary["functions"])

        st.subheader("Code Quality Issue Severity")

        c1, c2, c3 = st.columns(3)
        c1.metric("🔴 High", summary["high"])
        c2.metric("🟠 Medium", summary["medium"])
        c3.metric("🟢 Low", summary["low"])

        if result["score"] >= 80:
            st.success("Good code quality based on the current static checks.")
        elif result["score"] >= 50:
            st.warning("Some code quality improvements are recommended.")
        else:
            st.error("Several code quality issues need attention.")

        st.divider()
        st.subheader("🐞 Potential Programming Bugs")

        if result["potential_bugs"]:
            bug_df = pd.DataFrame(result["potential_bugs"])

            st.dataframe(
                bug_df,
                use_container_width=True,
                hide_index=True
            )

            for index, bug in enumerate(
                result["potential_bugs"], start=1
            ):
                with st.expander(
                    f'{index}. {bug["category"]} - {bug["severity"]}'
                ):
                    st.write(f'**Line:** {bug["line"]}')
                    st.write(f'**Finding:** {bug["message"]}')
                    st.write(f'**Suggestion:** {bug["suggestion"]}')
        else:
            st.success("No potential bugs detected by the current checks.")

        st.divider()
        st.subheader("🧮 Function Complexity Analysis")

        if result["complexities"]:
            complexity_df = pd.DataFrame(result["complexities"])

            st.dataframe(
                complexity_df,
                use_container_width=True,
                hide_index=True
            )

            st.caption(
                "Complexity is estimated using decision points in each "
                "function. It is a basic cyclomatic complexity estimate."
            )
        else:
            st.info("No functions were found in the submitted code.")

        st.divider()
        st.subheader("🛠️ Code Quality Recommendations")

        if result["issues"]:
            quality_df = pd.DataFrame(result["issues"])

            st.dataframe(
                quality_df,
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "⬇️ Download Quality Report",
                data=quality_df.to_csv(index=False).encode("utf-8"),
                file_name="code_quality_report.csv",
                mime="text/csv"
            )
        else:
            st.success("No quality issues detected.")

        st.caption(
            f'Lines analyzed: {summary["lines"]} | '
            f'Classes: {summary["classes"]}'
        )

        st.warning(
            "These checks cannot detect every logical bug. "
            "Review warnings and run appropriate tests before accepting code."
        )
