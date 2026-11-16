
import ast
import difflib
import json
import os
import re
import shutil
import sys
import tempfile
import time
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
from core.test_comparison import compare_versions
from core.debugging_history import add_history_entry, update_history_entry, get_history


st.set_page_config(
    page_title="DebugEngage AI",
    page_icon="🐞",
    layout="wide",
)

# ==========================================================
# DEBUGENGAGE AI - PROFESSIONAL LIGHT UI THEME
# ==========================================================

st.markdown(
    """
    <style>
    :root {
        --bg: #F1F5F9;
        --surface: #FFFFFF;
        --sidebar: #E2E8F0;
        --primary: #DC2626;
        --primary-hover: #B91C1C;
        --text: #1E293B;
        --muted: #64748B;
        --border: #CBD5E1;
    }

    .stApp { background-color: var(--bg); color: var(--text); }
    :root { accent-color: var(--primary); }
    [data-testid="stHeader"] { background: var(--bg); }
    [data-testid="stMain"] .block-container {
        max-width: 1200px;
        padding-top: 1.7rem;
        padding-bottom: 3rem;
    }
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div:first-child {
        background-color: var(--sidebar);
        border-right: 1px solid var(--border);
    }
    [data-testid="stSidebarNav"] { display: none; }

    h1, h2, h3 {
        color: var(--text) !important;
        font-weight: 700 !important;
        letter-spacing: -0.4px;
    }
    p, label { color: var(--text); }
    [data-testid="stCaptionContainer"] p { color: var(--muted) !important; }

    .stButton > button,
    [data-testid="stDownloadButton"] button {
        background: var(--primary) !important;
        color: #FFFFFF !important;
        border: 1px solid var(--primary) !important;
        border-radius: 9px;
        min-height: 42px;
        font-weight: 600;
        transition: 0.2s ease;
        box-shadow: none !important;
    }
    .stButton > button:hover,
    [data-testid="stDownloadButton"] button:hover {
        background: var(--primary-hover) !important;
        color: #FFFFFF !important;
        border-color: var(--primary-hover) !important;
    }
    .stButton > button:focus,
    [data-testid="stDownloadButton"] button:focus {
        outline: 2px solid rgba(220, 38, 38, 0.25);
        outline-offset: 2px;
    }
    .stTextInput input, .stTextArea textarea {
        background: white;
        color: var(--text);
        border: 1px solid var(--border);
        border-radius: 9px;
    }
    [data-testid="stFileUploader"] {
        background: white;
        border: 1px dashed #94A3B8;
        border-radius: 12px;
        padding: 10px;
    }
    [data-testid="stMetric"] {
        background: white;
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 14px;
    }
    [data-testid="stExpander"] {
        background: white;
        border: 1px solid var(--border);
        border-radius: 10px;
    }
    [data-testid="stAlert"] { border-radius: 10px; }
    [data-testid="stInfo"], [data-testid="stWarning"],
    [data-testid="stSuccess"], [data-testid="stError"] {
        border-radius: 10px;
    }
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        border: 1px solid var(--border);
        border-radius: 10px;
        overflow: hidden;
        background: #FFFFFF;
    }
    [data-testid="stFileUploader"] section {
        background: #FFFFFF;
        border-radius: 9px;
    }
    [data-testid="stSidebar"] .stRadio label {
        padding: 7px 9px;
        border-radius: 8px;
    }
    [data-testid="stSidebar"] .stRadio label:hover {
        background: rgba(220, 38, 38, 0.10);
    }
    hr { border-color: var(--border); }

    @media (max-width: 768px) {
        [data-testid="stMain"] .block-container { padding: 1rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
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
    "single_uploaded_file_name": "",
    "single_uploaded_file_code": "",
    "single_diagnosis": None,
    "single_repair_review": None,
    "single_test_code": "",
    "single_test_explanation": "",
    "single_test_result": None,
    "single_comparison_result": None,
    "single_test_generation_error": "",
    "single_test_generation_attempted": False,
    "central_single_upload_signature": None,
    "central_project_ready": False,
    "central_upload_name": None,
    "central_selected_file": None,
    "central_original_code": None,
    "central_original_sources": {},
    "central_corrected_code": None,
    "central_test_code": None,
    "central_test_explanation": "",
    "central_test_generation_error": "",
    "central_diagnosis": None,
    "central_history_entry_id": None,
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ==========================================================
# GENERAL HELPERS
# ==========================================================

def reset_single_file_results():
    st.session_state.single_diagnosis = None
    st.session_state.single_repair_review = None
    st.session_state.single_test_code = ""
    st.session_state.single_test_explanation = ""
    st.session_state.single_test_result = None
    st.session_state.single_comparison_result = None
    st.session_state.single_test_generation_error = ""
    st.session_state.single_test_generation_attempted = False


def clear_single_code():
    st.session_state.single_source_code = ""
    st.session_state.single_file_name = "solution.py"
    st.session_state.single_file_name_input = "solution.py"
    st.session_state.single_uploaded_file_name = ""
    st.session_state.single_uploaded_file_code = ""
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
        "central_history_entry_id",
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


def sync_single_upload_to_shared_project(source_code, file_name):
    """Publish the uploaded single .py file as the current shared project."""
    current_sig = (file_name, source_code)
    if st.session_state.get("central_single_upload_signature") == current_sig:
        return
    reset_project_state()
    workspace = tempfile.mkdtemp(prefix="debugengage_single_")
    project_path = Path(workspace) / "project"
    project_path.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file_name).name
    if not safe_name.lower().endswith(".py"):
        safe_name += ".py"
    (project_path / safe_name).write_text(source_code, encoding="utf-8")
    analysis = analyze_project(project_path)
    st.session_state.workspace = workspace
    st.session_state.project_path = str(project_path.resolve())
    st.session_state.analysis_results = analysis
    st.session_state.central_upload_name = safe_name
    st.session_state.central_project_ready = True
    st.session_state.central_single_upload_signature = current_sig
    st.session_state.central_selected_file = safe_name
    st.session_state.central_original_code = source_code
    st.session_state.central_original_sources = {safe_name: source_code}
    st.session_state.central_original_path = str((project_path / safe_name).resolve())
    st.session_state.central_corrected_code = None
    st.session_state.central_test_code = None
    st.session_state.central_diagnosis = None
    st.session_state.central_test_generation_error = ""


def sync_single_diagnosis_to_shared_project(source_code, file_name, diagnosis):
    """Make Single Python Code results available to the shared comparison page."""
    sync_single_upload_to_shared_project(source_code, file_name)

    safe_name = Path(file_name).name
    if not safe_name.lower().endswith(".py"):
        safe_name += ".py"

    st.session_state.central_project_ready = True
    st.session_state.central_upload_name = safe_name
    st.session_state.central_selected_file = safe_name
    st.session_state.central_original_code = source_code
    original_sources = dict(st.session_state.get("central_original_sources") or {})
    original_sources[safe_name] = source_code
    st.session_state.central_original_sources = original_sources
    st.session_state.central_original_path = str(
        (Path(st.session_state.project_path) / safe_name).resolve()
    )
    st.session_state.central_corrected_code = (
        diagnosis.get("fixed_code", "")
        if isinstance(diagnosis, dict) else ""
    )
    st.session_state.central_diagnosis = diagnosis
    st.session_state.central_test_code = ""
    st.session_state.central_test_explanation = ""
    st.session_state.central_test_generation_error = ""
    st.session_state.pop("comparison_result", None)


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


def render_debugging_workflow(source_code, diagnosis):
    """Show a state-based view of the current single-file debugging pipeline."""
    if not diagnosis:
        return

    file_name = st.session_state.get("single_file_name", "solution.py")
    repair_valid = validate_repair_code(diagnosis, file_name)
    generated = bool(st.session_state.get("single_test_code", "").strip())
    comparison = st.session_state.get("single_comparison_result")
    validation = validate_python_code(source_code, file_name) if source_code.strip() else {"success": False}

    if validation.get("success"):
        analysis_status, analysis_detail = "Complete", "Original code passed syntax checks"
    else:
        analysis_status, analysis_detail = "Needs attention", "Original code has a syntax issue"

    diagnosis_status = "Complete"
    diagnosis_detail = str(diagnosis.get("bug_type", "AI diagnosis returned"))

    if repair_valid:
        repair_status, repair_detail = "Complete", "Corrected code passed syntax validation"
    elif diagnosis.get("status") == "bug_found":
        repair_status, repair_detail = "Needs attention", "Review the proposed correction"
    else:
        repair_status, repair_detail = "Not required", "No repair was generated for this diagnosis"

    if generated:
        tests_status, tests_detail = "Complete", "Pytest cases generated and ready for review"
    elif st.session_state.get("single_test_generation_error"):
        tests_status, tests_detail = "Needs attention", "Test generation could not complete"
    elif repair_valid:
        tests_status, tests_detail = "In progress", "Preparing tests for the corrected code"
    else:
        tests_status, tests_detail = "Waiting", "Available after a valid correction"

    if comparison:
        corrected = comparison.get("corrected", {})
        total = corrected.get("passed", 0) + corrected.get("failed", 0) + corrected.get("errors", 0)
        if corrected.get("success") and total > 0 and corrected.get("failed", 0) == 0 and corrected.get("errors", 0) == 0:
            final_status = "Passed"
            final_detail = f"All {corrected.get('passed', 0)} corrected-code tests passed"
        else:
            final_status = "Needs attention"
            final_detail = "Some tests failed, errored, timed out, or collected no tests"
    else:
        final_status, final_detail = "Waiting", "Run Automatic Validation to verify the fix"

    review = st.session_state.get("single_repair_review")
    if review:
        review_verdict = review.get("verdict", "REVIEW_REQUIRED")
        review_status = "Complete" if review_verdict == "PASS" else "Needs attention"
        review_detail = str(review.get("summary", review_verdict))
    elif repair_valid:
        review_status, review_detail = "In progress", "Independent review is pending"
    else:
        review_status, review_detail = "Waiting", "Available after a valid correction"

    steps = [
        ("01", "Code Analysis", analysis_status, analysis_detail),
        ("02", "AI Diagnosis", diagnosis_status, diagnosis_detail),
        ("03", "Code Repair", repair_status, repair_detail),
        ("04", "AI Code Review", review_status, review_detail),
        ("05", "Test Generation", tests_status, tests_detail),
        ("06", "Final Validation", final_status, final_detail),
    ]

    st.markdown("### 🔄 Debugging Workflow")
    st.caption("Live status of each stage for the current Python file.")
    columns = st.columns(len(steps))
    for column, (number, title, status, detail) in zip(columns, steps):
        if status in ("Complete", "Passed"):
            color, symbol = "#15803D", "✓"
        elif status == "Needs attention":
            color, symbol = "#B91C1C", "!"
        elif status == "In progress":
            color, symbol = "#B45309", "…"
        else:
            color, symbol = "#64748B", "○"

        safe_title = str(title).replace("<", "&lt;").replace(">", "&gt;")
        safe_detail = str(detail).replace("<", "&lt;").replace(">", "&gt;")
        safe_status = str(status).replace("<", "&lt;").replace(">", "&gt;")
        html = (
            '<div style="background:#FFFFFF;border:1px solid #CBD5E1;'
            f'border-top:4px solid {color};border-radius:10px;padding:12px;min-height:150px;">'
            f'<div style="font-size:12px;color:#64748B;font-weight:700;">STEP {number}</div>'
            f'<div style="font-size:15px;color:#1E293B;font-weight:700;margin:7px 0;">{safe_title}</div>'
            f'<div style="font-size:12px;color:{color};font-weight:700;margin-bottom:7px;">{symbol} {safe_status}</div>'
            f'<div style="font-size:12px;color:#64748B;line-height:1.4;">{safe_detail}</div>'
            '</div>'
        )
        with column:
            st.markdown(html, unsafe_allow_html=True)


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
# INDEPENDENT AI CODE REVIEW AGENT
# ==========================================================

def review_repair_with_ai(original_code, corrected_code, file_name, diagnosis):
    """Independently review a proposed repair; never modify or approve it automatically."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured. Add it to your .env file.")

    client = genai.Client(api_key=api_key)
    prompt = f"""You are an independent senior Python code reviewer.
Review the proposed repair independently. Do not assume the repair agent is correct.
Check whether the diagnosed issue is actually addressed, whether behavior was unintentionally changed,
whether new bugs or security risks were introduced, and whether edge cases are handled.

FILE: {Path(file_name).name}
ORIGINAL CODE:
<original>
{original_code}
</original>
PROPOSED CORRECTED CODE:
<corrected>
{corrected_code}
</corrected>
DIAGNOSIS:
{json.dumps(diagnosis, ensure_ascii=False, default=str)}

Return ONLY valid JSON with this exact structure:
{{
  "verdict": "PASS" or "NEEDS_REVISION" or "REVIEW_REQUIRED",
  "summary": "short overall assessment",
  "findings": [{{"severity": "high|medium|low|info", "title": "finding", "detail": "explanation"}}],
  "checks": {{"diagnosed_issue_addressed": true, "unintended_changes": false, "edge_cases_considered": true}},
  "recommendation": "specific next action"
}}
If uncertain, use REVIEW_REQUIRED. Do not claim tests were executed.
"""
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config={"temperature": 0.1},
    )
    raw = (getattr(response, "text", None) or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The AI reviewer did not return valid JSON.")
    result = json.loads(raw[start:end + 1])
    if result.get("verdict") not in {"PASS", "NEEDS_REVISION", "REVIEW_REQUIRED"}:
        result["verdict"] = "REVIEW_REQUIRED"
    if not isinstance(result.get("findings"), list):
        result["findings"] = []

    # A PASS verdict is only displayed when every required review check is
    # explicitly true. Missing or false checks must remain visible to the user.
    required_checks = (
        "diagnosed_issue_addressed",
        "unintended_changes",
        "edge_cases_considered",
    )
    checks = result.get("checks")
    if not isinstance(checks, dict):
        checks = {}
    result["checks"] = checks
    incomplete_or_failed = any(checks.get(name) is not True for name in required_checks)
    if result.get("verdict") == "PASS" and incomplete_or_failed:
        result["verdict"] = "REVIEW_REQUIRED"
        result["summary"] = (
            str(result.get("summary", ""))
            + " One or more required review checks were not explicitly passed."
        ).strip()
        result["recommendation"] = (
            "Inspect the unchecked review items, compare the original and corrected code, "
            "and run the tests before accepting the repair."
        )
    return result


def display_repair_review(review, key_prefix="repair_review"):
    if not review:
        return
    st.subheader("🧑‍⚖️ Independent AI Code Review")
    verdict = review.get("verdict", "REVIEW_REQUIRED")
    if verdict == "PASS":
        st.success("Reviewer verdict: PASS — no blocking issue was identified.")
    elif verdict == "NEEDS_REVISION":
        st.error("Reviewer verdict: NEEDS REVISION — inspect the findings before using this repair.")
    else:
        st.warning("Reviewer verdict: REVIEW REQUIRED — the result needs human attention.")
    st.write(review.get("summary", "No summary returned."))
    findings = review.get("findings", [])
    if findings:
        for item in findings:
            severity = str(item.get("severity", "info")).upper()
            st.markdown(f"**{severity}: {item.get('title', 'Review finding')}**")
            st.write(item.get("detail", ""))
    else:
        st.caption("No specific findings were returned.")
    checks = review.get("checks", {})
    if checks:
        st.markdown("**Review checks**")
        check_labels = {
            "diagnosed_issue_addressed": "Diagnosed issue addressed",
            "unintended_changes": "No unintended changes",
            "edge_cases_considered": "Edge cases considered",
        }
        ordered_checks = [
            (name, checks.get(name))
            for name in (
                "diagnosed_issue_addressed",
                "unintended_changes",
                "edge_cases_considered",
            )
        ]
        cols = st.columns(3)
        for col, (name, passed) in zip(cols, ordered_checks):
            with col:
                label = check_labels[name]
                if passed is True:
                    st.success(label + " ✓")
                elif passed is False:
                    st.error(label + " — not passed")
                else:
                    st.warning(label + " — not verified")
    st.info("Recommendation: " + str(review.get("recommendation", "Review manually before proceeding.")))
    st.caption("This is an AI review, not proof of correctness. Run the generated tests and inspect the code before accepting it.")


# ==========================================================
# PYTEST GENERATION
# ==========================================================

def _extract_generated_test_content(response_text):
    """
    Extract pytest code from Gemini's response.

    Prefer explicit plain-text delimiters. Also accept a valid JSON
    response for compatibility with older prompts/models.
    """

    if not isinstance(response_text, str) or not response_text.strip():
        raise ValueError(
            "Gemini returned an empty test-generation response."
        )

    text = response_text.strip()

    # Backward compatibility: accept the earlier JSON response format.
    cleaned = re.sub(
        r"^\s*```(?:json)?\s*|\s*```\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            test_code = result.get("test_code", "")
            explanation = result.get("explanation", "")
            if isinstance(test_code, str) and test_code.strip():
                return test_code.strip(), str(explanation or "")
    except json.JSONDecodeError:
        pass

    # Preferred format: plain text with explicit section markers.
    test_match = re.search(
        r"TEST_CODE_START\s*(.*?)\s*TEST_CODE_END",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    explanation_match = re.search(
        r"EXPLANATION_START\s*(.*?)\s*EXPLANATION_END",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if test_match:
        test_code = test_match.group(1).strip()
        explanation = (
            explanation_match.group(1).strip()
            if explanation_match else
            "Automatically generated pytest cases for normal and edge-case behaviour."
        )
        # Remove an accidental outer Python Markdown fence.
        test_code = re.sub(
            r"^\s*```(?:python)?\s*|\s*```\s*$",
            "",
            test_code,
            flags=re.IGNORECASE,
        ).strip()
        if test_code:
            return test_code, explanation

    # Last-resort compatibility: accept one Python code fence if it
    # contains pytest test functions.
    code_blocks = re.findall(
        r"```(?:python|py)?\s*(.*?)```",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in code_blocks:
        candidate = block.strip()
        if re.search(r"(?m)^\s*(async\s+)?def\s+test_", candidate):
            return (
                candidate,
                "Automatically generated pytest cases. Review the tests before execution.",
            )

    raise ValueError(
        "Gemini's test response could not be parsed. "
        "The response did not contain the required test-code markers "
        "or a valid test_code JSON field."
    )


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

Generate a complete pytest test file for the intended correct behaviour
of the Python program. The exact same test file will be run independently
against both the original source and the proposed corrected source.

MODULE NAME: {module_name}

ORIGINAL SOURCE CODE:
<original_source>
{original_code}
</original_source>

PROPOSED CORRECTED SOURCE CODE:
<corrected_source>
{corrected_code}
</corrected_source>

AI DIAGNOSIS:
{json.dumps(diagnosis, ensure_ascii=False, default=str)}

TEST REQUIREMENTS:
- Import the required functions/classes from {module_name}.
- Generate independent pytest functions whose names start with test_.
- Cover normal inputs and meaningful edge cases.
- Include tests that expose the diagnosed defects in the original code.
- Expected results must represent intended behaviour, not copy the buggy implementation.
- Do not write tests that deliberately expect known bugs.
- Do not invent functions or imports that are absent from the source.
- Do not use network access, subprocesses, file deletion, or unrelated system actions.
- Keep tests deterministic and self-contained.
- Do not return JSON.
- Do not add Markdown code fences.
- Follow the output format below exactly.

OUTPUT FORMAT (plain text, not JSON):

TEST_CODE_START
[Write the complete Python pytest test file here, including imports and test functions.]
TEST_CODE_END
EXPLANATION_START
[Briefly describe the functions and edge cases covered.]
EXPLANATION_END

Return nothing before TEST_CODE_START and nothing after EXPLANATION_END.
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config={"temperature": 0.2},
    )

    response_text = getattr(response, "text", None)
    test_code, explanation = _extract_generated_test_content(response_text)

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
        "explanation": explanation,
    }


def generate_pytest_tests_with_retry(
    original_code,
    corrected_code,
    file_name,
    diagnosis,
    attempts=3,
):
    """
    Retry temporary Gemini availability/rate-limit failures.
    Delays are bounded so the Streamlit request cannot loop forever.
    """
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            return generate_pytest_tests(
                original_code=original_code,
                corrected_code=corrected_code,
                file_name=file_name,
                diagnosis=diagnosis,
            )
        except Exception as error:
            last_error = error
            message = str(error).lower()
            retryable_response_failure = any(
                marker in message
                for marker in (
                    "could not be parsed",
                    "invalid json",
                    "empty test-generation response",
                    "syntax error",
                    "did not generate any pytest test functions",
                    "did not generate valid pytest code",
                )
            )

            temporary_service_failure = any(
                marker in message
                for marker in (
                    "503", "unavailable", "high demand",
                    "429", "resource_exhausted",
                    "504", "deadline_exceeded",
                    "timeout", "temporarily",
                )
            )

            if not (
                retryable_response_failure or temporary_service_failure
            ) or attempt >= attempts:
                raise

            time.sleep(attempt * 2)

    raise RuntimeError(
        f"Unable to generate tests after {attempts} attempts: {last_error}"
    )


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
# INLINE FEATURE PAGE RENDERING
# ==========================================================

# ==========================================================
# EMBEDDED FEATURE PAGES
# These modules are embedded so the feature-page .py files are not needed.
# ==========================================================
EMBEDDED_FEATURE_PAGES = {'Code_Quality.py': '\nimport streamlit as st\nimport pandas as pd\nfrom pathlib import Path\nimport sys\n\nPROJECT_ROOT = Path(__file__).resolve().parents[2]\n\nif str(PROJECT_ROOT) not in sys.path:\n    sys.path.insert(0, str(PROJECT_ROOT))\n\nfrom core.code_quality import analyze_code_quality\n\n\nst.set_page_config(\n    page_title="Code Quality Analysis",\n    page_icon="📊",\n    layout="wide"\n)\n\nst.title("📊 Code Quality Analysis")\n\nst.write(\n    "Analyze Python code for quality issues, potential bugs, "\n    "and function complexity."\n)\n\nst.info(\n    "Static analysis examines source code without executing it. "\n    "Potential bug findings are heuristic warnings and should be reviewed."\n)\n\nshared_source = st.session_state.get("central_original_code") or ""\nshared_name = st.session_state.get("central_selected_file") or st.session_state.get("central_upload_name") or "shared_project.py"\nshared_path = st.session_state.get("project_path")\nsource_code = shared_source\nsource_name = shared_name\n# Prefer the current extracted project file so analysis reflects approved repairs.\nif shared_path and shared_name:\n    current_source_path = (Path(shared_path) / shared_name).resolve()\n    try:\n        current_source_path.relative_to(Path(shared_path).resolve())\n        if current_source_path.is_file():\n            source_code = current_source_path.read_text(encoding="utf-8-sig", errors="replace")\n    except (OSError, ValueError):\n        pass\n\n# Main uploaded project is the default. A feature-specific upload is optional.\nif not source_code and shared_path:\n    candidates = sorted(Path(shared_path).rglob("*.py"))\n    ignored = {".venv", "venv", ".git", "node_modules", "__pycache__", ".pytest_cache"}\n    candidates = [p for p in candidates if not any(part.lower() in ignored for part in p.parts)]\n    candidates = [p for p in candidates if not (p.name.lower().startswith("test_") or p.name.lower().endswith("_test.py"))]\n    if candidates:\n        labels = [p.relative_to(shared_path).as_posix() for p in candidates]\n        selected = st.selectbox("Python file from uploaded project", labels, key="quality_shared_file_v3")\n        chosen = candidates[labels.index(selected)]\n        source_code = chosen.read_text(encoding="utf-8-sig", errors="replace")\n        source_name = selected\n\nif source_code.strip():\n    st.success(f"Using previously uploaded project: {source_name}")\nelse:\n    st.info("No main project is uploaded yet. You can upload a file below or use Single Python Code / Complete ZIP Project first.")\n\nwith st.expander("Use a different file for Code Quality Analysis (optional)"):\n    local_file = st.file_uploader("Upload a Python file for this analysis only", type=["py"], key="quality_local_upload_v3")\n    if local_file is not None:\n        source_code = local_file.getvalue().decode("utf-8-sig", errors="replace")\n        source_name = local_file.name\n        st.info(f"Using separate file for this feature only: {source_name}")\n\nif st.session_state.get("quality_last_source") != source_code:\n    st.session_state.pop("quality_analysis_result", None)\n    st.session_state["quality_last_source"] = source_code\n\nif st.button("🔍 Analyze Code", type="primary"):\n    if not source_code.strip():\n        st.warning("Please upload or paste Python code first.")\n        st.session_state.pop("quality_analysis_result", None)\n    else:\n        with st.spinner("Analyzing your code..."):\n            result = analyze_code_quality(source_code)\n\n        st.session_state["quality_analysis_result"] = result\n\nresult = st.session_state.get("quality_analysis_result")\n\nif result:\n    if not result["success"]:\n        st.error(result["error"])\n\n    else:\n        summary = result["summary"]\n\n        st.divider()\n        st.subheader("Analysis Results")\n\n        col1, col2, col3, col4 = st.columns(4)\n\n        col1.metric("Code Quality Score", f\'{result["score"]}/100\')\n        col2.metric("Quality Issues", result["total_issues"])\n        st.caption(\n            "The score reflects detected code-quality issues. Heuristic potential-bug warnings are reported separately and do not reduce this score."\n        )\n        col3.metric("Potential Bugs", summary["potential_bugs"])\n        col4.metric("Functions", summary["functions"])\n\n        st.subheader("Code Quality Issue Severity")\n\n        c1, c2, c3 = st.columns(3)\n        c1.metric("🔴 High", summary["high"])\n        c2.metric("🟠 Medium", summary["medium"])\n        c3.metric("🟢 Low", summary["low"])\n\n        if result["potential_bugs"]:\n            st.warning(\n                f\'{summary["potential_bugs"]} potential programming bug(s) were also identified. Review these warnings even when the quality score is high.\'\n            )\n\n        if result["score"] >= 80 and not result["potential_bugs"]:\n            st.success("Good code quality based on the current static checks.")\n        elif result["score"] >= 80 and result["potential_bugs"]:\n            st.info("Few formal quality issues were detected, but potential bug warnings still require review.")\n        elif result["score"] >= 50:\n            st.warning("Some code quality improvements are recommended.")\n        else:\n            st.error("Several code quality issues need attention.")\n\n        st.divider()\n        st.subheader("🐞 Potential Programming Bugs")\n\n        if result["potential_bugs"]:\n            st.caption(\n                f\'{len(result["potential_bugs"])} potential issue(s) found. \'\n                "Each finding is shown below with its location and recommended action."\n            )\n\n            for index, bug in enumerate(result["potential_bugs"], start=1):\n                severity = str(bug.get("severity", "Review")).upper()\n                st.markdown(f"#### {index}. {bug.get(\'category\', \'Potential bug\')} — {severity}")\n                bug_col1, bug_col2 = st.columns([1, 3])\n                with bug_col1:\n                    st.metric("Source line", bug.get("line", "N/A"))\n                with bug_col2:\n                    st.write("**What was detected**")\n                    st.write(bug.get("message", "No explanation was provided by the analyzer."))\n                st.write("**Recommended action**")\n                st.info(bug.get("suggestion", "Review this code and add a test for the expected behavior."))\n                st.caption(\n                    "Heuristic warning only: confirm the intended behavior and run tests before changing code."\n                )\n                if index < len(result["potential_bugs"]):\n                    st.divider()\n        else:\n            st.success("No potential bugs detected by the current checks.")\n\n        st.divider()\n        st.subheader("🧮 Function Complexity Analysis")\n\n        if result["complexities"]:\n            complexity_df = pd.DataFrame(result["complexities"])\n            preferred_columns = [\n                column for column in ["function", "line", "complexity", "rating"]\n                if column in complexity_df.columns\n            ]\n            if preferred_columns:\n                complexity_df = complexity_df[preferred_columns]\n\n            if "complexity" in complexity_df.columns:\n                complexity_df["complexity"] = pd.to_numeric(\n                    complexity_df["complexity"], errors="coerce"\n                )\n                complexity_df = complexity_df.sort_values(\n                    "function" if "function" in complexity_df.columns else "complexity"\n                )\n\n            st.dataframe(\n                complexity_df,\n                use_container_width=True,\n                hide_index=True\n            )\n\n            complexity_values = (\n                complexity_df["complexity"].dropna().tolist()\n                if "complexity" in complexity_df.columns else []\n            )\n            if complexity_values:\n                average_complexity = sum(complexity_values) / len(complexity_values)\n                low_count = sum(value <= 5 for value in complexity_values)\n                moderate_count = sum(6 <= value <= 10 for value in complexity_values)\n                high_count = sum(11 <= value <= 20 for value in complexity_values)\n                very_high_count = sum(value > 20 for value in complexity_values)\n\n                c1, c2, c3, c4, c5 = st.columns(5)\n                c1.metric("Functions analyzed", len(complexity_values))\n                c2.metric("Low (≤5)", low_count)\n                c3.metric("Moderate (6–10)", moderate_count)\n                c4.metric("High (11–20)", high_count)\n                c5.metric("Very High (>20)", very_high_count)\n                st.metric("Average cyclomatic complexity", f"{average_complexity:.1f}")\n\n            st.caption(\n                "Cyclomatic complexity estimates independent execution paths. "\n                "It is not a runtime-performance measurement; thresholds are guidance."\n            )\n        else:\n            st.info("No functions were found in the submitted code.")\n\n        st.divider()\n        st.subheader("🛠️ Code Quality Recommendations")\n\n        if result["issues"]:\n            quality_df = pd.DataFrame(result["issues"])\n\n            st.dataframe(\n                quality_df,\n                use_container_width=True,\n                hide_index=True\n            )\n\n            st.download_button(\n                "⬇️ Download Quality Report",\n                data=quality_df.to_csv(index=False).encode("utf-8"),\n                file_name="code_quality_report.csv",\n                mime="text/csv"\n            )\n        else:\n            st.success("No quality issues detected.")\n\n        st.caption(\n            f\'Lines analyzed: {summary["lines"]} | \'\n            f\'Classes: {summary["classes"]}\'\n        )\n\n        st.warning(\n            "These checks cannot detect every logical bug. "\n            "Review warnings and run appropriate tests before accepting code."\n        )\n', 'AI_Bug_Explanation.py': '\nimport streamlit as st\nimport sys\nfrom pathlib import Path\n\nPROJECT_ROOT = Path(__file__).resolve().parents[2]\n\nif str(PROJECT_ROOT) not in sys.path:\n    sys.path.insert(0, str(PROJECT_ROOT))\n\nfrom core.bug_explainer import explain_bugs as _explain_bugs_once\nfrom core.code_quality import analyze_code_quality\nimport time\n\n\ndef explain_bugs(source_code, file_name="uploaded_code.py", findings=None):\n    """Retry temporary Gemini service failures without changing shared uploads."""\n    delays = (2, 4, 8)\n    result = None\n    for attempt in range(len(delays) + 1):\n        result = _explain_bugs_once(\n            source_code=source_code, file_name=file_name, findings=findings\n        )\n        if result.get("success"):\n            return result\n        error_text = str(result.get("error", "")).lower()\n        temporary = any(marker in error_text for marker in (\n            "503", "unavailable", "high demand", "429", "resource_exhausted",\n            "504", "deadline_exceeded", "timeout", "temporarily"\n        ))\n        if not temporary or attempt >= len(delays):\n            break\n        time.sleep(delays[attempt])\n    if result and not result.get("success"):\n        result["error"] = (\n            str(result.get("error", "Gemini request failed."))\n            + "\\n\\nGemini was retried automatically, but the service is still unavailable. "\n              "Please try again in a few minutes. Your uploaded project is still selected."\n        )\n    return result\n\n\n\nst.set_page_config(\n    page_title="AI Bug Explanation",\n    page_icon="🤖",\n    layout="wide"\n)\n\nst.title("🤖 AI Bug Explanation")\n\nst.write(\n    "Use Gemini AI to understand Python bugs, identify their causes, "\n    "and learn how to correct them."\n)\n\nst.info(\n    "Your submitted source code is sent to the Gemini API for analysis. "\n    "Do not submit passwords, API keys, personal data, or other secrets."\n)\n\nshared_source = st.session_state.get("central_original_code") or ""\nshared_name = st.session_state.get("central_selected_file") or st.session_state.get("central_upload_name") or "shared_project.py"\nshared_path = st.session_state.get("project_path")\nsource_code = shared_source\nfile_name = shared_name\n\n# Main uploaded project is selected automatically; no second upload is required.\nif not source_code and shared_path:\n    candidates = sorted(Path(shared_path).rglob("*.py"))\n    ignored = {".venv", "venv", ".git", "node_modules", "__pycache__", ".pytest_cache"}\n    candidates = [p for p in candidates if not any(part.lower() in ignored for part in p.parts)]\n    candidates = [p for p in candidates if not (p.name.lower().startswith("test_") or p.name.lower().endswith("_test.py"))]\n    if candidates:\n        labels = [p.relative_to(shared_path).as_posix() for p in candidates]\n        selected = st.selectbox("Python file from uploaded project", labels, key="bug_shared_file_v3")\n        chosen = candidates[labels.index(selected)]\n        source_code = chosen.read_text(encoding="utf-8-sig", errors="replace")\n        file_name = chosen.name\n\nif source_code.strip():\n    st.success(f"Using previously uploaded project: {file_name}")\nelse:\n    st.info("No main project is uploaded yet. You can upload a file below or use Single Python Code / Complete ZIP Project first.")\n\nwith st.expander("Use a different file for AI Bug Explanation (optional)"):\n    local_file = st.file_uploader("Upload a Python file for this explanation only", type=["py"], key="bug_explanation_local_upload_v3")\n    if local_file is not None:\n        source_code = local_file.getvalue().decode("utf-8-sig", errors="replace")\n        file_name = local_file.name\n        st.info(f"Using separate file for this feature only: {file_name}")\n\nif st.button(\n    "🤖 Explain Bugs with Gemini",\n    type="primary"\n):\n    if not source_code.strip():\n        st.warning("Please upload or paste Python code first.")\n\n    else:\n        with st.spinner("Checking code and preparing AI explanation..."):\n\n            static_result = analyze_code_quality(source_code)\n\n            if not static_result["success"]:\n                st.error(static_result["error"])\n                st.session_state.pop("bug_explanation_result", None)\n\n            else:\n                findings = (\n                    static_result.get("potential_bugs", [])\n                    + static_result.get("issues", [])\n                )\n\n                result = explain_bugs(\n                    source_code=source_code,\n                    file_name=file_name,\n                    findings=findings\n                )\n\n                st.session_state["bug_explanation_result"] = result\n                st.session_state["bug_explanation_file"] = file_name\n\nresult = st.session_state.get("bug_explanation_result")\n\nif result:\n    st.divider()\n    st.subheader("AI Debugging Report")\n\n    if result["success"]:\n        st.success("Gemini analysis completed successfully.")\n\n        st.markdown(result["explanation"])\n\n        st.download_button(\n            "⬇️ Download AI Bug Explanation",\n            data=result["explanation"],\n            file_name="ai_bug_explanation.md",\n            mime="text/markdown"\n        )\n\n    else:\n        st.error(result["error"])\n\nst.caption(\n    "AI explanations are suggestions. Review corrections and run tests "\n    "before applying them to your original project."\n)\n', 'Test_Coverage_Report.py': '\nimport json\nimport sys\nfrom pathlib import Path\n\nimport pandas as pd\nimport streamlit as st\n\nPROJECT_ROOT = Path(__file__).resolve().parents[2]\n\nif str(PROJECT_ROOT) not in sys.path:\n    sys.path.insert(0, str(PROJECT_ROOT))\n\nfrom core.test_coverage import (\n    generate_pytest_tests,\n    run_coverage_tests\n)\n\n\nst.set_page_config(\n    page_title="Test Coverage Report",\n    page_icon="🧪",\n    layout="wide"\n)\n\nst.title("🧪 Test Coverage Report")\n\nst.write(\n    "Generate or upload pytest test cases, execute them, "\n    "and measure how much of your Python source code is covered."\n)\n\nst.info(\n    "Line coverage measures which executable source lines were run "\n    "during the tests. It does not prove that the code is correct."\n)\n\nst.warning(\n    "Security notice: Running tests executes Python source and test code "\n    "on the computer running this application. This prototype is not "\n    "a secure sandbox. Only run code and tests that you trust."\n)\n\n\n# ---------------------------------------------------------\n# SESSION STATE\n# ---------------------------------------------------------\n\ndefaults = {\n    "coverage_test_code": "",\n    "coverage_test_explanation": "",\n    "coverage_result": None,\n    "coverage_last_source": "",\n    "coverage_last_file": "",\n    "coverage_last_source_identity": None,\n    "coverage_last_version": "",\n    "coverage_result_version": ""\n}\n\nfor key, value in defaults.items():\n    if key not in st.session_state:\n        st.session_state[key] = value\n\n\n# ---------------------------------------------------------\n# SOURCE CODE INPUT\n# ---------------------------------------------------------\n\nst.subheader("1. Python Source Code")\n\nshared_original_source = st.session_state.get("central_original_code") or ""\nshared_corrected_source = st.session_state.get("central_corrected_code") or ""\nshared_name = (\n    st.session_state.get("central_selected_file")\n    or st.session_state.get("central_upload_name")\n    or "solution.py"\n)\nshared_path = st.session_state.get("project_path")\ncoverage_source_rel_path = st.session_state.get("central_selected_file") or ""\ncoverage_project_root = shared_path if shared_path and shared_original_source else None\ncoverage_test_rel_path = None\ncoverage_uses_shared_project = bool(\n    shared_original_source.strip()\n    and coverage_project_root\n    and coverage_source_rel_path\n)\ncoverage_version_label = "Original Code"\nsource_code = shared_original_source\nfile_name = shared_name\n\nif coverage_uses_shared_project:\n    version_options = ["Original Code"]\n    if shared_corrected_source.strip():\n        version_options.append("Corrected Code")\n\n    selected_version = st.radio(\n        "Choose which code version to test",\n        version_options,\n        horizontal=True,\n        key="coverage_code_version",\n        help="The same pytest test cases are used for either version."\n    )\n    if selected_version == "Corrected Code":\n        source_code = shared_corrected_source\n        coverage_version_label = "Corrected Code"\n    else:\n        source_code = shared_original_source\n        coverage_version_label = "Original Code"\n\n    st.success(f"Using shared debugging session: {file_name}")\n    st.info(\n        f"Selected version: **{coverage_version_label}**. "\n        "The original and corrected versions are tested separately in an isolated temporary copy. "\n        "Your uploaded project files are not overwritten."\n    )\nelse:\n    source_code = ""\n    if shared_path:\n        candidates = sorted(Path(shared_path).rglob("*.py"))\n        ignored = {\n            ".venv", "venv", ".git", "node_modules",\n            "__pycache__", ".pytest_cache"\n        }\n        candidates = [\n            p for p in candidates\n            if not any(part.lower() in ignored for part in p.parts)\n        ]\n        candidates = [\n            p for p in candidates\n            if not (\n                p.name.lower().startswith("test_")\n                or p.name.lower().endswith("_test.py")\n            )\n        ]\n        if candidates:\n            labels = [p.relative_to(shared_path).as_posix() for p in candidates]\n            selected = st.selectbox(\n                "Python file from uploaded project",\n                labels,\n                key="coverage_shared_file_v3"\n            )\n            chosen = candidates[labels.index(selected)]\n            source_code = chosen.read_text(encoding="utf-8-sig", errors="replace")\n            file_name = chosen.name\n            coverage_source_rel_path = selected\n            coverage_project_root = shared_path\n            coverage_uses_shared_project = True\n            coverage_version_label = "Project Source"\n\n    if source_code.strip():\n        st.success(f"Using project source: {file_name}")\n    else:\n        st.info(\n            "No main project is uploaded yet. Upload a ZIP project or use "\n            "Single Python Code first."\n        )\n\nwith st.expander("Use a different file for Test Coverage (optional)"):\n    local_file = st.file_uploader(\n        "Upload a Python file for this coverage report only",\n        type=["py"],\n        key="coverage_local_upload_v3"\n    )\n    if local_file is not None:\n        source_code = local_file.getvalue().decode("utf-8-sig", errors="replace")\n        file_name = local_file.name\n        coverage_project_root = None\n        coverage_source_rel_path = None\n        coverage_test_rel_path = None\n        coverage_uses_shared_project = False\n        coverage_version_label = "Uploaded File"\n        st.info(f"Using separate file for this feature only: {file_name}")\n\n\n# Clear tests only when the selected source file changes.\n# Switching Original/Corrected must preserve the exact same test suite.\nsource_identity = (\n    coverage_source_rel_path or file_name,\n    file_name,\n    shared_original_source if (coverage_uses_shared_project and shared_original_source) else source_code,\n)\nif source_identity != st.session_state.coverage_last_source_identity:\n    st.session_state.coverage_result = None\n    st.session_state.coverage_test_code = ""\n    st.session_state.coverage_test_explanation = ""\n    st.session_state.coverage_last_source_identity = source_identity\n\n# A result belongs to one code version only. Never display an Original\n# result while Corrected Code is selected, or vice versa.\nif coverage_version_label != st.session_state.coverage_last_version:\n    st.session_state.coverage_result = None\n    st.session_state.coverage_last_version = coverage_version_label\n\nst.session_state.coverage_last_source = source_code\nst.session_state.coverage_last_file = file_name\n\n\nst.divider()\n\n\n# ---------------------------------------------------------\n# TEST CASE INPUT\n# ---------------------------------------------------------\n\nst.subheader("2. Provide Pytest Test Cases")\n\ntest_method = st.radio(\n    "Choose how to provide test cases",\n    ["Reuse Tests from Shared Project", "Generate Tests with Gemini", "Upload Test File"],\n    horizontal=True,\n    key="coverage_test_method_v2"\n)\n\nif test_method == "Reuse Tests from Shared Project":\n    shared_test_files = []\n    if shared_path:\n        shared_root = Path(shared_path)\n        shared_test_files = sorted(\n            p for p in shared_root.rglob("*.py")\n            if (p.name.lower().startswith("test_") or p.name.lower().endswith("_test.py"))\n            and not any(part.lower() in {".venv", "venv", ".git", "node_modules", "__pycache__", ".pytest_cache"} for part in p.parts)\n        )\n    if shared_test_files:\n        test_labels = [p.relative_to(shared_path).as_posix() for p in shared_test_files]\n        selected_test = st.selectbox("Select an existing project test file", test_labels, key="coverage_shared_test_file")\n        chosen_test = shared_test_files[test_labels.index(selected_test)]\n        coverage_test_rel_path = selected_test\n        reused_test_code = chosen_test.read_text(encoding="utf-8-sig", errors="replace")\n        if reused_test_code != st.session_state.coverage_test_code:\n            st.session_state.coverage_test_code = reused_test_code\n            st.session_state.coverage_test_explanation = f"Reused from uploaded project: {selected_test}"\n            st.session_state.coverage_result = None\n        st.success(f"Using tests from the shared project: {selected_test}")\n    else:\n        shared_generated_tests = st.session_state.get("central_test_code") or ""\n        same_shared_source = (\n            coverage_uses_shared_project\n            and bool(shared_original_source.strip())\n            and bool(st.session_state.get("central_test_code"))\n        )\n        if same_shared_source and shared_generated_tests.strip():\n            if st.session_state.coverage_test_code != shared_generated_tests:\n                st.session_state.coverage_test_code = shared_generated_tests\n                st.session_state.coverage_test_explanation = (\n                    st.session_state.get("central_test_explanation")\n                    or "Reused AI-generated pytest tests from the shared debugging workflow."\n                )\n                st.session_state.coverage_result = None\n            st.success("Reusing AI-generated pytest tests from Original vs Corrected Comparison.")\n            st.caption("The exact same test cases are retained when you switch between Original Code and Corrected Code.")\n        else:\n            st.info("No pytest files or reusable generated tests were found in the shared project. Choose Generate Tests with Gemini or Upload Test File.")\n\nelif test_method == "Generate Tests with Gemini":\n\n    st.write(\n        "Gemini will inspect your source code and generate "\n        "pytest test cases."\n    )\n\n    if st.button(\n        "✨ Generate Test Cases",\n        type="primary",\n        disabled=not bool(source_code.strip()),\n        key="coverage_generate_tests"\n    ):\n\n        try:\n            with st.spinner("Gemini is generating test cases..."):\n\n                generated = generate_pytest_tests(\n                    source_code,\n                    file_name\n                )\n\n            st.session_state.coverage_test_code = generated["test_code"]\n            st.session_state.coverage_test_explanation = (\n                generated["explanation"]\n            )\n            st.session_state.coverage_result = None\n            # Keep generated tests available to the comparison workflow too.\n            if coverage_uses_shared_project:\n                st.session_state.central_test_code = generated["test_code"]\n                st.session_state.central_test_explanation = generated["explanation"]\n\n            st.success("Test cases generated successfully.")\n\n        except Exception as error:\n            st.error(f"Test generation failed: {error}")\n\nelse:\n\n    uploaded_test_file = st.file_uploader(\n        "Upload a pytest file",\n        type=["py"],\n        key="coverage_test_upload"\n    )\n\n    if uploaded_test_file is not None:\n\n        try:\n            uploaded_test_code = uploaded_test_file.getvalue().decode(\n                "utf-8-sig"\n            )\n\n            if (\n                uploaded_test_code\n                != st.session_state.coverage_test_code\n            ):\n                st.session_state.coverage_test_code = uploaded_test_code\n                st.session_state.coverage_test_explanation = (\n                    "Tests uploaded by the user."\n                )\n                st.session_state.coverage_result = None\n\n        except UnicodeDecodeError:\n            st.error("The test file must use UTF-8 encoding.")\n\n\n# ---------------------------------------------------------\n# REVIEW GENERATED OR UPLOADED TESTS\n# ---------------------------------------------------------\n\nif st.session_state.coverage_test_code:\n\n    st.divider()\n    st.subheader("3. Review Test Cases")\n\n    if st.session_state.coverage_test_explanation:\n        st.info(st.session_state.coverage_test_explanation)\n\n    edited_test_code = st.text_area(\n        "Review or edit your pytest code before execution",\n        value=st.session_state.coverage_test_code,\n        height=300,\n        key="coverage_test_editor"\n    )\n\n    st.session_state.coverage_test_code = edited_test_code\n    if coverage_uses_shared_project:\n        st.session_state.central_test_code = edited_test_code\n\n    st.download_button(\n        "⬇️ Download Test Cases",\n        data=edited_test_code,\n        file_name="test_generated.py",\n        mime="text/x-python",\n        disabled=not bool(edited_test_code.strip()),\n        key="coverage_download_tests"\n    )\n\n    st.divider()\n\n    st.subheader("4. Run Tests and Measure Coverage")\n\n    authorized = st.checkbox(\n        "I understand that Python source code and test code "\n        "will execute on this computer, and I trust both files.",\n        key="coverage_execution_consent"\n    )\n\n    if st.button(\n        "▶ Run Tests and Generate Coverage Report",\n        type="primary",\n        disabled=(\n            not authorized\n            or not source_code.strip()\n            or not edited_test_code.strip()\n        ),\n        key="coverage_run_tests"\n    ):\n\n        try:\n            with st.spinner(\n                "Running pytest and measuring source-code coverage..."\n            ):\n\n                result = run_coverage_tests(\n                    source_code=source_code,\n                    file_name=file_name,\n                    test_code=edited_test_code,\n                    timeout=60,\n                    project_root=coverage_project_root,\n                    source_rel_path=coverage_source_rel_path,\n                    test_rel_path=coverage_test_rel_path,\n                )\n\n            st.session_state.coverage_result = result\n            st.session_state.coverage_result_version = coverage_version_label\n\n        except Exception as error:\n            st.session_state.coverage_result = None\n            st.error(f"Test execution failed: {error}")\n\n\n# ---------------------------------------------------------\n# COVERAGE RESULTS\n# ---------------------------------------------------------\n\nresult = st.session_state.coverage_result\n\nif result:\n\n    st.divider()\n    st.header("📊 Test Coverage Results")\n    result_version = (\n        st.session_state.get("coverage_result_version")\n        or coverage_version_label\n    )\n    st.info(f"Code version tested: **{result_version}**")\n\n    passed = result["passed"]\n    failed = result["failed"]\n    errors = result["errors"]\n    skipped = result["skipped"]\n    total = result["total"]\n\n    col1, col2, col3, col4 = st.columns(4)\n\n    col1.metric("Passed", passed)\n    col2.metric("Failed", failed)\n    col3.metric("Errors", errors)\n    col4.metric("Skipped", skipped)\n\n    st.subheader("Test Execution Summary")\n\n    if total == 0:\n        st.warning(\n            "No tests were collected. The submitted code has not "\n            "been validated by this test run."\n        )\n\n    else:\n\n        st.metric(\n            "Test Pass Percentage",\n            f\'{result["pass_percentage"]:.2f}%\'\n        )\n\n        if result["success"]:\n            st.success("All collected tests passed.")\n\n        else:\n            st.error(\n                "Some tests failed or produced errors. "\n                "Review the execution output below."\n            )\n\n    st.divider()\n    st.subheader("📈 Source Code Line Coverage")\n\n    coverage = result["coverage"]\n\n    if coverage["available"]:\n\n        percentage = coverage["percent"]\n\n        covered_lines = coverage["covered_lines"]\n        total_lines = coverage["total_lines"]\n        missing_lines = coverage["missing_lines"]\n\n        coverage_col1, coverage_col2, coverage_col3 = st.columns(3)\n\n        coverage_col1.metric(\n            "Line Coverage",\n            f"{percentage:.2f}%"\n        )\n\n        coverage_col2.metric(\n            "Covered Lines",\n            covered_lines\n        )\n\n        coverage_col3.metric(\n            "Executable Lines",\n            total_lines\n        )\n\n        st.progress(\n            min(max(percentage / 100, 0.0), 1.0)\n        )\n\n        if percentage == 100:\n            st.success(\n                "All executable source lines were covered in this run."\n            )\n\n        elif percentage >= 80:\n            st.success(\n                "Good line coverage. Some executable lines may remain untested."\n            )\n\n        elif percentage >= 50:\n            st.warning(\n                "Moderate line coverage. Add tests for uncovered lines."\n            )\n\n        else:\n            st.warning(\n                "Low line coverage. More test cases are recommended."\n            )\n\n        st.write("**Uncovered source lines:**")\n\n        if missing_lines:\n            st.code(\n                ", ".join(str(line) for line in missing_lines)\n            )\n        else:\n            st.success("No uncovered executable lines were reported.")\n\n    else:\n\n        st.warning(\n            "Line coverage could not be calculated."\n        )\n\n        if coverage.get("error"):\n            st.caption(coverage["error"])\n\n    st.divider()\n    st.subheader("📋 Detailed Test Execution Output")\n\n    with st.expander("View pytest output", expanded=True):\n        st.code(\n            result.get("output", "No execution output available."),\n            language="text"\n        )\n\n    # Download report\n    report_data = {\n        "file_name": file_name,\n        "code_version": result_version,\n        "passed": passed,\n        "failed": failed,\n        "errors": errors,\n        "skipped": skipped,\n        "total": total,\n        "test_pass_percentage": result["pass_percentage"],\n        "coverage": coverage\n    }\n\n    st.download_button(\n        "⬇️ Download Coverage Report (JSON)",\n        data=json.dumps(report_data, indent=4),\n        file_name="test_coverage_report.json",\n        mime="application/json",\n        key="coverage_download_report"\n    )\n\n    st.caption(\n        "The selected code version is tested using the same pytest test cases. "\n        "Coverage indicates which executable lines were run. "\n        "It does not measure whether assertions are correct or "\n        "whether every possible behaviour is tested."\n    )\n', 'Debugging_History.py': '\nimport json\nimport pandas as pd\nimport streamlit as st\n\nfrom core.debugging_history import (\n    get_history,\n    get_history_summary,\n    get_status_label,\n    delete_history_entry,\n    clear_history\n)\n\nst.set_page_config(\n    page_title="Debugging History",\n    page_icon="📚",\n    layout="wide"\n)\n\nst.title("📚 Debugging History")\nst.caption("View and manage your previous debugging sessions.")\n\nhistory = get_history()\nsummary = get_history_summary()\n\n# A detected bug is not counted as a successfully validated repair.\ncol1, col2, col3, col4 = st.columns(4)\n\ncol1.metric("Total Sessions", summary["total"])\ncol2.metric("Validated Successfully", summary["successful"])\ncol3.metric("Failed Sessions", summary["failed"])\ncol4.metric("Pending / Needs Attention", summary["pending"])\n\nif summary.get("unclassified", 0):\n    st.info(\n        f\'{summary["unclassified"]} session(s) have an unrecognized status. \'\n        "They are included in Total Sessions but not counted as successful or failed."\n    )\n\nst.divider()\n\nif not history:\n    st.info(\n        "No debugging history is available yet. "\n        "Records will appear here when debugging sessions are saved."\n    )\nelse:\n    # Search and filter\n    search_col, filter_col = st.columns(2)\n\n    with search_col:\n        search_text = st.text_input(\n            "Search by file name or issue",\n            placeholder="Enter a file name or keyword"\n        )\n\n    with filter_col:\n        status_options = [\n            "All", "bug_found", "no_bug_found", "success", "fixed",\n            "passed", "failed", "error", "environment_issue",\n            "insufficient_information", "review_required",\n            "review_unavailable", "pending", "in_progress"\n        ]\n        selected_status = st.selectbox("Filter by status", status_options)\n\n    filtered_history = []\n\n    for item in history:\n        file_name = item.get("file_name", "")\n        issue = item.get("issue", "")\n        status = item.get("status", "")\n\n        matches_search = (\n            search_text.lower() in file_name.lower()\n            or search_text.lower() in issue.lower()\n        )\n\n        matches_status = (\n            selected_status == "All"\n            or status.lower() == selected_status.lower()\n        )\n\n        if matches_search and matches_status:\n            filtered_history.append(item)\n\n    st.subheader(f"Sessions ({len(filtered_history)})")\n\n    # Table\n    table_data = []\n\n    for item in filtered_history:\n        table_data.append({\n            "Date": item.get("timestamp", ""),\n            "File": item.get("file_name", ""),\n            "Status": get_status_label(item.get("status", "")),\n            "Issue": item.get("issue", ""),\n            "Tests": item.get("test_summary", "")\n        })\n\n    if table_data:\n        st.dataframe(\n            pd.DataFrame(table_data),\n            use_container_width=True,\n            hide_index=True\n        )\n\n        csv_data = pd.DataFrame(table_data).to_csv(index=False)\n\n        st.download_button(\n            "⬇️ Download History CSV",\n            data=csv_data,\n            file_name="debugging_history.csv",\n            mime="text/csv"\n        )\n\n    st.divider()\n    st.subheader("Session Details")\n\n    for item in filtered_history:\n        title = (\n            f"{item.get(\'file_name\', \'Unknown file\')} | "\n            f"{item.get(\'timestamp\', \'\')} | "\n            f"{get_status_label(item.get(\'status\', \'Unknown\'))}"\n        )\n\n        with st.expander(title):\n            st.write("**Issue:**", item.get("issue") or "Not provided")\n            st.write("**Test Summary:**", item.get("test_summary") or "Not provided")\n            st.write("**Details:**", item.get("details") or "Not provided")\n\n            original_code = item.get("original_code", "")\n            corrected_code = item.get("corrected_code", "")\n\n            if original_code:\n                st.markdown("**Original Code**")\n                st.code(original_code, language="python")\n\n            if corrected_code:\n                st.markdown("**Corrected Code**")\n                st.code(corrected_code, language="python")\n\n            if st.button(\n                "Delete this session",\n                key=f"delete_{item.get(\'id\')}"\n            ):\n                delete_history_entry(item.get("id"))\n                st.success("Session deleted.")\n                st.rerun()\n\n    st.divider()\n\n    if st.button("🗑️ Clear All History", type="secondary"):\n        st.session_state["confirm_clear_history"] = True\n\n    if st.session_state.get("confirm_clear_history", False):\n        st.warning("Are you sure you want to delete all debugging history?")\n\n        confirm_col, cancel_col = st.columns(2)\n\n        with confirm_col:\n            if st.button("Yes, delete all"):\n                clear_history()\n                st.session_state["confirm_clear_history"] = False\n                st.success("All history deleted.")\n                st.rerun()\n\n        with cancel_col:\n            if st.button("Cancel"):\n                st.session_state["confirm_clear_history"] = False\n                st.rerun()\n'}

def render_feature_page(relative_path):
    """Render an embedded feature page inside the main Streamlit app."""
    feature_name = Path(relative_path).name
    source = EMBEDDED_FEATURE_PAGES.get(feature_name)
    if source is None:
        st.error(f"Embedded feature page was not found: {feature_name}")
        return

    # Give the embedded page its expected on-disk location for PROJECT_ROOT
    # calculations, while executing its source directly from this app.py.
    feature_path = PROJECT_ROOT / "frontend" / "pages" / feature_name
    tree = ast.parse(source, filename=str(feature_path))

    class RemovePageConfig(ast.NodeTransformer):
        def visit_Expr(self, node):
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and isinstance(value.func.value, ast.Name)
                and value.func.value.id == "st"
                and value.func.attr == "set_page_config"
            ):
                return None
            return self.generic_visit(node)

    tree = RemovePageConfig().visit(tree)
    ast.fix_missing_locations(tree)

    namespace = {
        "__name__": f"debugengage_embedded_{feature_path.stem}",
        "__file__": str(feature_path),
    }
    exec(compile(tree, str(feature_path), "exec"), namespace)


# ==========================================================
# APPLICATION HEADER AND NAVIGATION
# ==========================================================

st.markdown(
    """
    <div style="background:#FFFFFF; padding:22px 26px; border-radius:16px;
                border:1px solid #CBD5E1; margin-bottom:22px;">
        <h1 style="margin:0; color:#1E293B;">🐞 DebugEngage AI</h1>
        <p style="color:#64748B; margin:8px 0 0 0;">
            Your AI-powered Python debugging assistant. Find bugs,
            understand errors, correct code and validate fixes with tests.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Choose Page",
    [
        "Home",
        "Single Python Code",
        "Complete ZIP Project",
        "Code Quality Analysis",
        "AI Bug Explanation",
        "Test Coverage Report",
        "Debugging History",
        "Original vs Corrected Comparison",
        "About",
    ],
    key="debugengage_selected_page",
)

# Open the selected feature page. These files must be present in
# frontend/pages/ with the exact filenames shown below.
FEATURE_PAGE_PATHS = {
    "Code Quality Analysis": "pages/Code_Quality.py",
    "AI Bug Explanation": "pages/AI_Bug_Explanation.py",
    "Test Coverage Report": "pages/Test_Coverage_Report.py",
    "Debugging History": "pages/Debugging_History.py",
}

if page in FEATURE_PAGE_PATHS:
    render_feature_page(FEATURE_PAGE_PATHS[page])
    st.stop()

st.sidebar.divider()
st.sidebar.caption(
    "Python Debugging and Test Automation"
)


# ==========================================================
# SHARED PROJECT COMPARISON
# ==========================================================

if page == "Original vs Corrected Comparison":
    st.title("⚖️ Original vs Corrected Test Comparison")
    st.caption("Compare the uploaded project's original code with its AI-proposed correction using the same tests.")
    project_path_value = st.session_state.get("project_path")
    diagnosis_value = st.session_state.get("central_diagnosis") or st.session_state.get("repair_result")
    selected_rel_value = st.session_state.get("central_selected_file")
    original_value = st.session_state.get("central_original_code")
    corrected_value = st.session_state.get("central_corrected_code") or (diagnosis_value or {}).get("fixed_code", "")
    comparison_source_mode = st.radio(
        "Comparison source",
        ["Use shared project", "Upload a different Python file"],
        horizontal=True,
        key="comparison_source_mode_inline",
    )
    if comparison_source_mode == "Upload a different Python file":
        local_comparison_file = st.file_uploader(
            "Upload a Python file for this comparison only",
            type=["py"],
            key="comparison_local_original_inline",
        )
        local_original_code = ""
        local_file_name = "target.py"
        if local_comparison_file is not None:
            local_original_code = local_comparison_file.getvalue().decode("utf-8-sig", errors="replace")
            local_file_name = Path(local_comparison_file.name).name
            st.success(f"Using {local_file_name} only for this comparison. The shared project is unchanged.")
        local_corrected_code = st.text_area("Corrected Python Code", height=220, key="comparison_local_corrected_inline")
        local_test_code = st.text_area("Pytest Test Cases", height=220, key="comparison_local_tests_inline")
        local_authorized = st.checkbox("I trust this code and authorize local test execution.", key="comparison_local_authorize_inline")
        if st.button("Compare Uploaded File", type="primary", disabled=not local_authorized):
            if not local_original_code.strip() or not local_corrected_code.strip() or not local_test_code.strip():
                st.warning("Upload the original file and provide its corrected version and pytest cases.")
            else:
                with st.spinner("Comparing the uploaded file versions..."):
                    st.session_state["comparison_result"] = compare_versions(local_original_code, local_corrected_code, local_test_code, local_file_name)
                st.rerun()
        project_path_value = None

    if comparison_source_mode == "Use shared project" and project_path_value and selected_rel_value and original_value and corrected_value:
        st.success(f"Using uploaded project: {st.session_state.get('central_upload_name', 'Python project')}")
        st.write(f"**Selected source file:** `{selected_rel_value}`")
        st.info("Original code, corrected code and diagnosis come from the shared project. You do not need to paste them again.")
        project_root_value = Path(project_path_value)
        existing_test_files = []
        chosen_label = None
        for candidate in project_root_value.rglob("*.py"):
            relative = candidate.relative_to(project_root_value)
            if any(part.lower() in {".venv", "venv", ".git", "node_modules", "__pycache__", ".pytest_cache"} for part in relative.parts):
                continue
            if candidate.name.lower().startswith("test_") or candidate.name.lower().endswith("_test.py"):
                existing_test_files.append(candidate)
        if existing_test_files:
            test_labels = [item.relative_to(project_root_value).as_posix() for item in existing_test_files]
            chosen_label = st.selectbox("Reuse an existing pytest file", test_labels)
            chosen_test_file = existing_test_files[test_labels.index(chosen_label)]
            test_code_value = chosen_test_file.read_text(encoding="utf-8-sig")
            st.caption("Existing project tests are reused automatically from the uploaded project.")
        else:
            test_code_value = st.session_state.get("central_test_code", "")
            if test_code_value:
                st.success("No existing tests were found. AI-generated pytest tests are ready for review.")
                if st.session_state.get("central_test_explanation"):
                    st.caption(st.session_state.central_test_explanation)
                test_code_value = st.text_area("Review generated tests", value=test_code_value, height=260, key="central_test_review_editor")
                st.session_state.central_test_code = test_code_value
            else:
                st.warning("No existing or generated pytest tests are available yet. Return to Single Python Code or Complete ZIP Project, run AI diagnosis, and generate tests for a valid correction.")
                if st.session_state.get("central_test_generation_error"):
                    st.error(st.session_state.central_test_generation_error)
        if test_code_value:
            with st.expander("View test cases"):
                st.code(test_code_value, language="python")
            st.warning("Tests execute on this computer. This prototype is not a secure sandbox. Only proceed if you trust the uploaded code and tests.")
            authorize_comparison = st.checkbox("I trust this project and authorize local test execution.", key="central_authorize_comparison")
            if st.button("Compare Original vs Corrected", type="primary", disabled=not authorize_comparison):
                with st.spinner("Running the same tests against both code versions..."):
                    comparison_result_value = compare_versions(
                        original_value, corrected_value, test_code_value,
                        Path(selected_rel_value).name,
                        project_root=project_root_value,
                        source_rel_path=selected_rel_value,
                        test_rel_path=chosen_label,
                    )
                st.session_state["comparison_result"] = comparison_result_value

                # A corrected version that passes the same test suite validates the repair.
                # Update the original diagnosis record instead of leaving it as bug_found.
                if (
                    comparison_source_mode == "Use shared project"
                    and comparison_result_value.get("success")
                ):
                    corrected_result = comparison_result_value.get("corrected", {})
                    corrected_counts = corrected_result.get("counts", {})
                    corrected_total = corrected_counts.get("total", 0)
                    corrected_passed = corrected_counts.get("passed", 0)
                    corrected_failed = corrected_counts.get("failed", 0)
                    corrected_errors = corrected_counts.get("errors", 0)

                    if (
                        corrected_total > 0
                        and corrected_passed > 0
                        and corrected_failed == 0
                        and corrected_errors == 0
                    ):
                        history_entry_id = st.session_state.get("central_history_entry_id")

                        # Recover the matching record for sessions created before this fix.
                        if not history_entry_id:
                            selected_name = str(selected_rel_value or Path(file_name).name)
                            for history_item in get_history():
                                history_file = str(history_item.get("file_name", ""))
                                same_file = (
                                    history_file == selected_name
                                    or Path(history_file).name == Path(selected_name).name
                                )
                                same_original = (
                                    history_item.get("original_code", "") == original_value
                                )
                                if same_file and same_original:
                                    history_entry_id = history_item.get("id")
                                    break

                        history_changes = {
                            "status": "success",
                            "issue": "Repair validated successfully",
                            "corrected_code": corrected_value,
                            "test_summary": (
                                f"{corrected_passed} passed, "
                                f"{corrected_failed} failed, "
                                f"{corrected_errors} errors"
                            ),
                            "details": (
                                "The corrected code passed the same pytest suite "
                                "used in Original vs Corrected Comparison. "
                                f"Original: {comparison_result_value.get('original', {}).get('counts', {}).get('passed', 0)} passed, "
                                f"{comparison_result_value.get('original', {}).get('counts', {}).get('failed', 0)} failed. "
                                f"Corrected: {corrected_passed} passed, "
                                f"{corrected_failed} failed, {corrected_errors} errors."
                            ),
                        }

                        updated = (
                            update_history_entry(history_entry_id, **history_changes)
                            if history_entry_id else False
                        )

                        if not updated:
                            new_history_entry = add_history_entry(
                                file_name=selected_rel_value or Path(file_name).name,
                                status="success",
                                issue=history_changes["issue"],
                                original_code=original_value,
                                corrected_code=corrected_value,
                                test_summary=history_changes["test_summary"],
                                details=history_changes["details"],
                            )
                            history_entry_id = new_history_entry.get("id")

                        st.session_state["central_history_entry_id"] = history_entry_id

                st.rerun()
    elif comparison_source_mode == "Use shared project":
        st.warning("Upload or paste a Python file in Single Python Code, or upload a ZIP in Complete ZIP Project. Run AI diagnosis and generate pytest cases first. The corrected code and tests will then appear here automatically.")

    comparison_result_value = st.session_state.get("comparison_result")
    if comparison_result_value:
        if not comparison_result_value.get("success"):
            st.error(comparison_result_value.get("error", "Comparison could not be completed."))
            for result_key in ("original", "corrected"):
                with st.expander(f"{result_key.title()} execution output"):
                    st.code(comparison_result_value.get(result_key, {}).get("output", "No output"), language="text")
        else:
            original_counts = comparison_result_value["original"]["counts"]
            corrected_counts = comparison_result_value["corrected"]["counts"]
            comparison_summary = comparison_result_value["comparison"]
            left, right = st.columns(2)
            with left:
                st.subheader("Original Code")
                st.metric("Passed", original_counts["passed"])
                st.metric("Failed", original_counts["failed"])
                st.metric("Errors", original_counts["errors"])
                st.metric("Success Rate", f"{original_counts['success_rate']}%")
            with right:
                st.subheader("Corrected Code")
                st.metric("Passed", corrected_counts["passed"])
                st.metric("Failed", corrected_counts["failed"])
                st.metric("Errors", corrected_counts["errors"])
                st.metric("Success Rate", f"{corrected_counts['success_rate']}%")
            a, b, c = st.columns(3)
            a.metric("Passed-test change", comparison_summary["passed_change"])
            b.metric("Failed-test change", comparison_summary["failed_change"], delta_color="inverse")
            c.metric("Success-rate change", f"{round(comparison_summary['corrected_success_rate'] - comparison_summary['original_success_rate'], 2)} percentage points")
            if corrected_counts["total"] and corrected_counts["failed"] == 0 and corrected_counts["errors"] == 0:
                st.success("All collected tests passed on the corrected code.")
            elif comparison_summary["improved"]:
                st.success("The corrected code improved the test results.")
            else:
                st.warning("The corrected code has not demonstrated an improvement.")
            with st.expander("Original test output"):
                st.code(comparison_result_value["original"]["output"], language="text")
            with st.expander("Corrected test output"):
                st.code(comparison_result_value["corrected"]["output"], language="text")
    st.stop()

# ==========================================================
# HOME PAGE
# ==========================================================

if page == "Home":
    st.title("Welcome to DebugEngage AI")
    st.write(
        "An AI-powered Python debugging and test validation system. "
        "Use the navigation menu to upload a project once and work with its debugging tools."
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

if page == "Single Python Code":

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

            # Track the uploaded file separately from the editable
            # output filename. Otherwise, changing the filename to
            # solution.py makes every Streamlit rerun look like a new
            # upload and clears the diagnosis/test results.
            upload_changed = (
                st.session_state.single_uploaded_file_name != uploaded_file.name
                or st.session_state.single_uploaded_file_code != uploaded_code
            )

            if upload_changed:
                st.session_state.single_uploaded_file_name = uploaded_file.name
                st.session_state.single_uploaded_file_code = uploaded_code
                st.session_state.single_source_code = uploaded_code
                sync_single_upload_to_shared_project(uploaded_code, uploaded_file.name)

                # Use the uploaded name as the initial output name only
                # when the user has not already chosen another filename.
                current_name = st.session_state.get(
                    "single_file_name_input",
                    st.session_state.single_file_name,
                )
                if not current_name or current_name == "solution.py":
                    st.session_state.single_file_name = uploaded_file.name
                    st.session_state.single_file_name_input = uploaded_file.name

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
                st.session_state.single_repair_review = None

                # Publish the same source and diagnosis for the
                # Original vs Corrected Comparison page.
                sync_single_diagnosis_to_shared_project(
                    source_code=source_code,
                    file_name=file_name,
                    diagnosis=diagnosis,
                )

                if is_valid_repair(diagnosis):
                    try:
                        with st.spinner("Independent AI Code Review Agent is checking the proposed repair..."):
                            st.session_state.single_repair_review = review_repair_with_ai(
                                source_code, diagnosis["fixed_code"], file_name, diagnosis
                            )
                    except Exception as review_error:
                        st.session_state.single_repair_review = {
                            "verdict": "REVIEW_REQUIRED",
                            "summary": "The independent review could not be completed.",
                            "findings": [{"severity": "medium", "title": "Reviewer unavailable", "detail": str(review_error)}],
                            "checks": {},
                            "recommendation": "Review the proposed code manually and run tests before using it.",
                        }
                # The text_input widget with key="single_file_name_input"
                # has already been instantiated during this Streamlit run.
                # Updating that widget-owned key here raises StreamlitAPIException.
                # Keep the normalized filename in our separate application key.
                st.session_state.single_file_name = file_name

                # Save this diagnosis once when the user clicks the button.
                history_entry = add_history_entry(
                    file_name=file_name,
                    status=diagnosis.get("status", "insufficient_information"),
                    issue=diagnosis.get("bug_type", "Diagnosis completed"),
                    original_code=source_code,
                    corrected_code=diagnosis.get("fixed_code", ""),
                    test_summary="Tests not run yet",
                    details=(
                        f"Explanation: {diagnosis.get('explanation', '')}\n"
                        f"AI Provider: {diagnosis.get('ai_provider', 'Unknown')}\n"
                        f"Confidence: {diagnosis.get('confidence', 'Not specified')}\n"
                        f"Recommended Action: {diagnosis.get('recommended_action', '')}\n"
                        f"Issues: {json.dumps(diagnosis.get('issues', []), ensure_ascii=False)}"
                    )
                )
                st.session_state["central_history_entry_id"] = history_entry.get("id")

                st.session_state.single_test_code = ""
                st.session_state.single_test_explanation = ""
                st.session_state.single_test_result = None
                st.session_state.single_comparison_result = None
                st.session_state.single_test_generation_error = ""
                st.session_state.single_test_generation_attempted = False
                st.session_state.central_test_code = ""
                st.session_state.central_test_explanation = ""
                st.session_state.central_test_generation_error = ""

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
        display_repair_review(st.session_state.get("single_repair_review"))

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
            "Test cases are generated automatically after a successful "
            "AI correction. Review the generated tests before running them."
        )

        st.warning(
            "Security notice: pytest executes Python code on this "
            "computer. This prototype is not a secure sandbox. "
            "Only run code and tests that you trust."
        )

        # Automatically generate tests once for each successful repair.
        if repair_valid and not st.session_state.single_test_code:
            if not st.session_state.single_test_generation_attempted:
                st.session_state.single_test_generation_attempted = True
                try:
                    with st.spinner(
                        "Generating pytest cases automatically with Gemini..."
                    ):
                        generated = generate_pytest_tests_with_retry(
                            original_code=source_code,
                            corrected_code=diagnosis["fixed_code"],
                            file_name=file_name,
                            diagnosis=diagnosis,
                            attempts=3,
                        )

                    st.session_state.single_test_code = generated["test_code"]
                    st.session_state.single_test_explanation = generated["explanation"]
                    st.session_state.central_test_code = generated["test_code"]
                    st.session_state.central_test_explanation = generated["explanation"]
                    st.session_state.central_test_generation_error = ""
                    st.session_state.single_test_generation_error = ""
                    st.session_state.single_test_result = None
                    st.session_state.single_comparison_result = None
                    st.success(
                        "Pytest cases generated automatically. "
                        "Review them before execution."
                    )

                except Exception as error:
                    st.session_state.single_test_generation_error = str(error)
                    st.session_state.central_test_generation_error = str(error)

        if repair_valid and not st.session_state.single_test_code:
            if st.session_state.single_test_generation_error:
                st.error(
                    "Automatic test generation could not complete. "
                    "Your corrected code is safe and available above; "
                    "the test-generation service may be temporarily unavailable. "
                    f"Details: {st.session_state.single_test_generation_error}"
                )

            if st.button(
                "🔄 Retry Automatic Test Generation",
                use_container_width=True,
                key="retry_automatic_test_generation",
            ):
                st.session_state.single_test_generation_attempted = True
                st.session_state.single_test_generation_error = ""
                try:
                    with st.spinner(
                        "Retrying automatic pytest generation..."
                    ):
                        generated = generate_pytest_tests_with_retry(
                            original_code=source_code,
                            corrected_code=diagnosis["fixed_code"],
                            file_name=file_name,
                            diagnosis=diagnosis,
                            attempts=3,
                        )

                    st.session_state.single_test_code = generated["test_code"]
                    st.session_state.single_test_explanation = generated["explanation"]
                    st.session_state.central_test_code = generated["test_code"]
                    st.session_state.central_test_explanation = generated["explanation"]
                    st.session_state.central_test_generation_error = ""
                    st.session_state.single_test_generation_error = ""
                    st.session_state.single_test_result = None
                    st.session_state.single_comparison_result = None
                    st.success("Tests generated successfully.")
                    st.rerun()

                except Exception as error:
                    st.session_state.single_test_generation_error = str(error)
                    st.session_state.central_test_generation_error = str(error)
                    st.error(
                        "Test generation is still unavailable. "
                        f"Please retry later. Details: {error}"
                    )

        elif repair_valid and st.session_state.single_test_code:
            st.subheader("Review Automatically Generated Pytest Code")

            if st.session_state.single_test_explanation:
                st.info(st.session_state.single_test_explanation)

            edited_test_code = st.text_area(
                "Generated test code (review or edit before execution)",
                value=st.session_state.single_test_code,
                height=300,
                key="single_test_code_editor",
            )

            st.session_state.single_test_code = edited_test_code
            st.session_state.central_test_code = edited_test_code
            st.session_state.central_test_explanation = (
                st.session_state.single_test_explanation
            )

            authorize_single_tests = st.checkbox(
                "I understand that pytest executes the source and "
                "test code on this computer, and I trust both files.",
                key="authorize_single_file_tests",
            )

            st.caption(
                "The same generated test file is run independently "
                "against the original and corrected versions."
            )

            if st.button(
                "▶ Run Automatic Validation",
                type="primary",
                use_container_width=True,
                disabled=not (
                    authorize_single_tests
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
                    st.session_state.single_test_result = None

                except Exception as error:
                    st.session_state.single_comparison_result = None
                    st.error(f"Code comparison failed: {error}")

            if st.session_state.single_comparison_result:
                show_comparison_results(
                    st.session_state.single_comparison_result
                )

    # Reflect the actual state of the current debugging run.
    if st.session_state.single_diagnosis:
        st.divider()
        render_debugging_workflow(
            source_code=st.session_state.single_source_code,
            diagnosis=st.session_state.single_diagnosis,
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

    st.info(
        "Upload your Python file or complete ZIP project here once. "
        "The same extracted project is then used by diagnosis, code quality, "
        "bug explanation, test coverage, history and comparison."
    )

    uploaded_zip = st.file_uploader(
        "Upload Python File or Complete Project ZIP",
        type=["py", "zip"],
        key="zip_project_upload",
    )

    if uploaded_zip is not None:
        if st.button(
            "Upload and Analyze Project",
            type="primary",
            use_container_width=True,
        ):
            reset_project_state()
            workspace = tempfile.mkdtemp(prefix="debugengage_project_")
            try:
                upload_name = Path(uploaded_zip.name).name
                if upload_name.lower().endswith(".py"):
                    project_path = Path(workspace) / "project"
                    project_path.mkdir(parents=True, exist_ok=True)
                    target_file = project_path / upload_name
                    target_file.write_bytes(uploaded_zip.getvalue())
                else:
                    with st.spinner("Extracting project ZIP..."):
                        project_path = extract_project_zip(uploaded_zip, workspace)
                    project_path = Path(project_path).resolve()

                project_path = Path(project_path).resolve()
                if not project_path.exists() or not project_path.is_dir():
                    raise FileNotFoundError("Uploaded project folder was not found.")

                with st.spinner("Analyzing Python files and existing tests..."):
                    analysis_results = analyze_project(project_path)

                st.session_state.workspace = workspace
                st.session_state.project_path = str(project_path)
                st.session_state.analysis_results = analysis_results
                st.session_state.last_test_result = None
                st.session_state.repair_result = None
                st.session_state.repair_file = None
                st.session_state.repair_applied = False
                st.session_state.post_repair_result = None
                st.session_state.central_upload_name = upload_name
                st.session_state.central_single_upload_signature = None
                st.session_state.central_project_ready = True
                st.session_state.central_selected_file = None
                st.session_state.central_original_code = None
                st.session_state.central_original_sources = {
                    path.relative_to(project_path).as_posix(): path.read_text(encoding="utf-8-sig", errors="replace")
                    for path in get_project_files(project_path)
                    if not (path.name.lower().startswith("test_") or path.name.lower().endswith("_test.py"))
                }
                st.session_state.central_corrected_code = None
                st.session_state.central_test_code = None
                st.success("Project uploaded and analyzed. You can now use the other tools without uploading it again.")
                st.rerun()
            except Exception as error:
                shutil.rmtree(workspace, ignore_errors=True)
                st.error(f"Project upload or analysis failed: {error}")

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

                original_sources = dict(st.session_state.get("central_original_sources") or {})
                if selected_file not in original_sources:
                    original_sources[selected_file] = selected_path.read_text(
                        encoding="utf-8-sig", errors="replace"
                    )
                    st.session_state.central_original_sources = original_sources
                original_code = original_sources[selected_file]
                st.session_state.central_selected_file = selected_file
                st.session_state.central_original_code = original_code
                st.session_state.central_original_path = str(selected_path)

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
                        st.session_state.central_selected_file = selected_file
                        st.session_state.central_original_code = original_code
                        st.session_state.central_corrected_code = diagnosis.get("fixed_code", "")
                        st.session_state.central_diagnosis = diagnosis
                        st.session_state.central_test_code = ""
                        st.session_state.central_test_explanation = ""
                        if is_valid_repair(diagnosis):
                            try:
                                with st.spinner("Generating pytest tests for the uploaded project file..."):
                                    generated_tests = generate_pytest_tests_with_retry(
                                        original_code=original_code,
                                        corrected_code=diagnosis["fixed_code"],
                                        file_name=selected_path.name,
                                        diagnosis=diagnosis,
                                        attempts=3,
                                    )
                                st.session_state.central_test_code = generated_tests["test_code"]
                                st.session_state.central_test_explanation = generated_tests["explanation"]
                            except Exception as test_generation_error:
                                st.session_state.central_test_generation_error = str(test_generation_error)

                        # Save this ZIP-project diagnosis to history.
                        history_entry = add_history_entry(
                            file_name=selected_file,
                            status=diagnosis.get("status", "insufficient_information"),
                            issue=diagnosis.get("bug_type", "Diagnosis completed"),
                            original_code=original_code,
                            corrected_code=diagnosis.get("fixed_code", ""),
                            test_summary="Project tests not yet validated after repair",
                            details=(
                                f"Explanation: {diagnosis.get('explanation', '')}\n"
                                f"AI Provider: {diagnosis.get('ai_provider', 'Unknown')}\n"
                                f"Confidence: {diagnosis.get('confidence', 'Not specified')}\n"
                                f"Recommended Action: {diagnosis.get('recommended_action', '')}\n"
                                f"Issues: {json.dumps(diagnosis.get('issues', []), ensure_ascii=False)}"
                            )
                        )
                        st.session_state["central_history_entry_id"] = history_entry.get("id")

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

                    original_sources = st.session_state.get("central_original_sources") or {}
                    original_code = original_sources.get(
                        st.session_state.get("central_selected_file"),
                        st.session_state.get("central_original_code") or ""
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
                                    total_validated = (
                                        validation_result.get("passed", 0)
                                        + validation_result.get("failed", 0)
                                        + validation_result.get("errors", 0)
                                    )
                                    if (
                                        validation_result.get("success")
                                        and total_validated > 0
                                        and validation_result.get("failed", 0) == 0
                                        and validation_result.get("errors", 0) == 0
                                    ):
                                        history_changes = {
                                            "status": "success",
                                            "issue": "Repair validated successfully",
                                            "corrected_code": st.session_state.get("central_corrected_code") or fixed_code,
                                            "test_summary": (
                                                f"{validation_result.get('passed', 0)} passed, "
                                                f"{validation_result.get('failed', 0)} failed, "
                                                f"{validation_result.get('errors', 0)} errors"
                                            ),
                                            "details": "Post-repair project test suite completed successfully."
                                        }
                                        updated = update_history_entry(
                                            st.session_state.get("central_history_entry_id"),
                                            **history_changes
                                        ) if st.session_state.get("central_history_entry_id") else False
                                        if not updated:
                                            add_history_entry(
                                                file_name=st.session_state.get("central_selected_file") or selected_path.name,
                                                status="success",
                                                original_code=st.session_state.get("central_original_code") or "",
                                                **history_changes
                                            )
                                    else:
                                        failed_status = "failed" if validation_result.get("failed", 0) else "error"
                                        failed_summary = (
                                            f"{validation_result.get('passed', 0)} passed, "
                                            f"{validation_result.get('failed', 0)} failed, "
                                            f"{validation_result.get('errors', 0)} errors"
                                        )
                                        if st.session_state.get("central_history_entry_id"):
                                            update_history_entry(
                                                st.session_state.get("central_history_entry_id"),
                                                status=failed_status,
                                                issue="Post-repair validation did not pass",
                                                test_summary=failed_summary,
                                                details="Post-repair project tests did not all pass. Review the test output and remaining failing files.",
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
