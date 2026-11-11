
import streamlit as st
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.bug_explainer import explain_bugs
from core.code_quality import analyze_code_quality


st.set_page_config(
    page_title="AI Bug Explanation",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 AI Bug Explanation")

st.write(
    "Use Gemini AI to understand Python bugs, identify their causes, "
    "and learn how to correct them."
)

st.info(
    "Your submitted source code is sent to the Gemini API for analysis. "
    "Do not submit passwords, API keys, personal data, or other secrets."
)

input_method = st.radio(
    "Choose code input method",
    ["Upload Python File", "Paste Python Code"],
    horizontal=True,
    key="bug_explanation_input_method"
)

source_code = ""
file_name = "pasted_code.py"

if input_method == "Upload Python File":

    uploaded_file = st.file_uploader(
        "Upload Python file",
        type=["py"],
        key="bug_explanation_upload"
    )

    if uploaded_file is not None:
        source_code = uploaded_file.getvalue().decode(
            "utf-8",
            errors="replace"
        )
        file_name = uploaded_file.name
        st.success(f"Loaded: {file_name}")

else:
    source_code = st.text_area(
        "Paste your Python code",
        height=350,
        placeholder="Paste your Python code here...",
        key="bug_explanation_source"
    )

    file_name = st.text_input(
        "File name",
        value="pasted_code.py"
    )

if st.button(
    "🤖 Explain Bugs with Gemini",
    type="primary"
):
    if not source_code.strip():
        st.warning("Please upload or paste Python code first.")

    else:
        with st.spinner("Checking code and preparing AI explanation..."):

            static_result = analyze_code_quality(source_code)

            if not static_result["success"]:
                st.error(static_result["error"])
                st.session_state.pop("bug_explanation_result", None)

            else:
                findings = (
                    static_result.get("potential_bugs", [])
                    + static_result.get("issues", [])
                )

                result = explain_bugs(
                    source_code=source_code,
                    file_name=file_name,
                    findings=findings
                )

                st.session_state["bug_explanation_result"] = result
                st.session_state["bug_explanation_file"] = file_name

result = st.session_state.get("bug_explanation_result")

if result:
    st.divider()
    st.subheader("AI Debugging Report")

    if result["success"]:
        st.success("Gemini analysis completed successfully.")

        st.markdown(result["explanation"])

        st.download_button(
            "⬇️ Download AI Bug Explanation",
            data=result["explanation"],
            file_name="ai_bug_explanation.md",
            mime="text/markdown"
        )

    else:
        st.error(result["error"])

st.caption(
    "AI explanations are suggestions. Review corrections and run tests "
    "before applying them to your original project."
)
