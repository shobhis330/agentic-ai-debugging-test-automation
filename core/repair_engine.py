import ast
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai


# --------------------------------------------------
# ENVIRONMENT CONFIGURATION
# --------------------------------------------------

# Project root is one directory above core/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env independently of the terminal's current directory.
load_dotenv(
    dotenv_path=PROJECT_ROOT / ".env",
    override=False
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

MODEL = "gemini-3.5-flash-lite"

MAX_RETRIES = 3

RETRY_DELAYS = [2, 4, 6]

MAX_TEST_OUTPUT_CHARS = 20000

VALID_STATUSES = {
    "bug_found",
    "no_bug_found",
    "environment_issue",
    "insufficient_information",
}


# --------------------------------------------------
# GEMINI CLIENT
# --------------------------------------------------

def get_gemini_client():
    """Create Gemini client using the environment API key."""

    # Ensure .env is loaded even when this function is
    # called directly outside Streamlit.
    load_dotenv(
        dotenv_path=PROJECT_ROOT / ".env",
        override=False
    )

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not found. Check your .env file."
        )

    return genai.Client(api_key=api_key)


# --------------------------------------------------
# RESPONSE HELPERS
# --------------------------------------------------

def extract_json(response_text):
    """Extract JSON from Gemini response."""

    if not isinstance(response_text, str):
        raise ValueError("Gemini returned an invalid response.")

    response_text = response_text.strip()

    # Handle accidental Markdown code fences.
    if response_text.startswith("```"):

        response_text = re.sub(
            r"^```(?:json)?\s*",
            "",
            response_text,
            flags=re.IGNORECASE,
        )

        response_text = re.sub(
            r"\s*```$",
            "",
            response_text,
        )

    try:
        return json.loads(response_text)

    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini returned invalid JSON."
        ) from error


def normalize_issues(issues):
    """
    Normalize issue descriptions.

    Supports both string-based and structured issue descriptions.
    """

    if not isinstance(issues, list):
        return []

    normalized = []

    for issue in issues:

        if isinstance(issue, str):

            normalized.append({
                "problem": issue,
                "line": None,
                "severity": "Not specified",
                "explanation": issue,
                "original_snippet": "",
                "corrected_snippet": "",
            })

        elif isinstance(issue, dict):

            normalized.append({
                "problem": str(
                    issue.get("problem", issue.get("title", "Code issue"))
                ),
                "line": issue.get("line"),
                "severity": str(
                    issue.get("severity", "Not specified")
                ),
                "explanation": str(
                    issue.get("explanation", "")
                ),
                "original_snippet": str(
                    issue.get("original_snippet", "")
                ),
                "corrected_snippet": str(
                    issue.get("corrected_snippet", "")
                ),
            })

    return normalized


# --------------------------------------------------
# RESPONSE VALIDATION
# --------------------------------------------------

def _validate_response(result: Any) -> dict:
    """Validate and normalize Gemini's response."""

    if not isinstance(result, dict):
        raise ValueError(
            "Invalid AI response format."
        )

    required_fields = {
        "status",
        "bug_type",
        "explanation",
        "fixed_code",
        "confidence",
    }

    missing = required_fields - result.keys()

    if missing:
        raise ValueError(
            f"Missing response fields: {sorted(missing)}"
        )

    status = result["status"]

    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status: {status}"
        )

    confidence = result["confidence"]

    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise ValueError(
            "Invalid confidence value."
        )

    if not isinstance(result["bug_type"], str):
        raise ValueError(
            "Invalid bug type."
        )

    if not isinstance(result["explanation"], str):
        raise ValueError(
            "Invalid explanation."
        )

    fixed_code = result["fixed_code"]

    if not isinstance(fixed_code, str):
        raise ValueError(
            "Invalid corrected code."
        )

    # Validate the complete corrected Python file.
    if status == "bug_found":

        if not fixed_code.strip():
            raise ValueError(
                "Gemini returned empty corrected code."
            )

        try:
            ast.parse(fixed_code)

        except SyntaxError as error:
            raise ValueError(
                "Gemini's corrected code contains syntax errors: "
                f"{error}"
            ) from error

        result["syntax_valid"] = True

    else:

        result["fixed_code"] = ""
        result["syntax_valid"] = None

    result["issues"] = normalize_issues(
        result.get("issues", [])
    )

    result["confidence"] = float(confidence)

    result.setdefault(
        "recommended_action",
        "Review the diagnosis."
    )

    result["ai_provider"] = "Gemini"

    return result


# --------------------------------------------------
# LOCAL FALLBACK
# --------------------------------------------------

def local_fallback(test_output):
    """
    Safe local diagnosis when Gemini is unavailable.

    Does not generate replacement code.
    """

    output = str(test_output).lower()

    passed = re.search(
        r"\b\d+\s+passed\b",
        output
    )

    failed = re.search(
        r"\b\d+\s+failed\b",
        output
    )

    errors = re.search(
        r"\b\d+\s+errors?\b",
        output
    )

    if passed and not failed and not errors:

        return {
            "status": "no_bug_found",
            "bug_type": "No failing tests detected",

            "explanation": (
                "Gemini is temporarily unavailable. "
                "The local fallback checked the test output. "
                "All collected tests passed, so no repair "
                "is recommended based on the available evidence."
            ),

            "fixed_code": "",
            "confidence": 0.85,
            "syntax_valid": None,
            "issues": [],

            "recommended_action": (
                "No repair required. All collected tests passed. "
                "Retry Gemini diagnosis later for AI code analysis."
            ),

            "ai_provider": "Local fallback",
        }

    environment_terms = [
        "modulenotfounderror",
        "no module named",
        "importerror",
        "error collecting",
        "no tests ran",
        "no tests collected",
        "filenotfounderror",
        "permissionerror",
    ]

    if any(term in output for term in environment_terms):

        return {
            "status": "environment_issue",
            "bug_type": "Test environment or configuration issue",

            "explanation": (
                "The test output contains an import, collection, "
                "or environment-related error. Gemini is unavailable, "
                "so the exact cause could not be confirmed."
            ),

            "fixed_code": "",
            "confidence": 0.70,
            "syntax_valid": None,
            "issues": [],

            "recommended_action": (
                "Check project imports, dependencies, "
                "and test configuration."
            ),

            "ai_provider": "Local fallback",
        }

    return {
        "status": "insufficient_information",
        "bug_type": "Diagnosis temporarily unavailable",

        "explanation": (
            "Gemini is unavailable and the local fallback cannot "
            "reliably determine the cause of the problem. "
            "No replacement code has been generated."
        ),

        "fixed_code": "",
        "confidence": 0.30,
        "syntax_valid": None,
        "issues": [],

        "recommended_action": (
            "Retry diagnosis when the Gemini service is available."
        ),

        "ai_provider": "Local fallback",
    }


# --------------------------------------------------
# GEMINI DEBUGGING PROMPT
# --------------------------------------------------

def build_debugging_prompt(
    source_code,
    test_output,
    file_name,
):
    """Create a detailed debugging prompt for Gemini."""

    if test_output.strip():

        test_information = test_output

    else:

        test_information = (
            "No test output was provided. "
            "Perform static code analysis and identify "
            "only defects supported by the source code. "
            "Do not claim that runtime tests were executed."
        )

    return f"""
You are an advanced Agentic AI Python Debugging Agent.

Your responsibility is to analyze Python code, identify real bugs,
generate corrected code, and explain every correction.

The user may provide:

1. A small Python program.
2. A large Python source file.
3. Python code containing many functions and classes.
4. Code with syntax errors.
5. Code with logical errors.
6. Code with runtime errors.
7. Code with missing or incorrect imports.

You must carefully analyze the entire provided source code.

--------------------------------------------------
FILE INFORMATION
--------------------------------------------------

File name: {file_name}

--------------------------------------------------
COMPLETE SOURCE CODE
--------------------------------------------------

<source_code>
{source_code}
</source_code>

--------------------------------------------------
TEST OUTPUT OR ERROR MESSAGE
--------------------------------------------------

<test_output>
{test_information}
</test_output>

--------------------------------------------------
ANALYSIS REQUIREMENTS
--------------------------------------------------

1. Examine the complete source code.

2. Identify syntax errors, logical errors, runtime risks,
   incorrect conditions, incorrect calculations, and
   incorrect function implementations.

3. Examine imports, variables, functions, classes and
   their relationships.

4. Check whether functions call other functions correctly.

5. Check whether variables are initialized before use.

6. Identify incorrect return statements and conditions.

7. Use the provided test output as evidence when available.

8. If no test output is provided, perform static code analysis.

9. Do not invent bugs.

10. Do not modify code that is already correct unnecessarily.

--------------------------------------------------
CORRECTION REQUIREMENTS
--------------------------------------------------

When a genuine bug is found:

1. Provide the COMPLETE corrected Python source file.

2. Preserve all existing working functions and classes.

3. Preserve imports unless a correction requires a change.

4. Preserve the original program structure wherever possible.

5. Do not remove unrelated code.

6. Do not replace a large program with a short example.

7. Do not provide only pseudocode.

8. Do not provide only the changed function.

9. Correct all identified bugs in the complete file.

10. Ensure the complete corrected code has valid Python syntax.

11. Explain the important corrections individually.

12. Include the original and corrected snippets for each
    issue whenever possible.

13. Never claim that tests passed unless test execution
    evidence was actually provided.

--------------------------------------------------
LARGE CODE REQUIREMENTS
--------------------------------------------------

The source code may contain many lines.

For large source files:

1. Consider the entire source before generating corrections.

2. Preserve relationships between functions and classes.

3. Do not silently omit code from the corrected result.

4. Preserve unrelated functions and imports.

5. Return the complete corrected file, not just a partial section.

6. If the complete corrected file cannot be generated reliably,
   use insufficient_information instead of returning incomplete code.

--------------------------------------------------
RESPONSE STATUS
--------------------------------------------------

Use one of these statuses:

bug_found
no_bug_found
environment_issue
insufficient_information

Use:

bug_found:
When genuine source-code defects are identified and corrected.

no_bug_found:
When no genuine source-code defect is identified.

environment_issue:
When the evidence indicates a dependency, import, configuration,
or test-environment problem rather than a confirmed source-code bug.

insufficient_information:
When the available evidence is not enough for a reliable diagnosis.

--------------------------------------------------
OUTPUT FORMAT
--------------------------------------------------

Return ONLY valid JSON.

Use this exact structure:

{{
    "status": "bug_found",

    "bug_type": "Logical error",

    "explanation": "Explain the identified problems.",

    "fixed_code": "Complete corrected Python source code.",

    "confidence": 0.95,

    "issues": [
        {{
            "problem": "Incorrect calculation",
            "line": 10,
            "severity": "High",
            "explanation": "Explain the problem.",
            "original_snippet": "Original code",
            "corrected_snippet": "Corrected code"
        }}
    ],

    "recommended_action": "Review and validate the corrected code."
}}

For statuses other than bug_found:

- fixed_code must be an empty string.
- Do not invent corrected code.
- Explain why a repair is not available.

Remember:
The corrected code must contain the complete program.
Do not omit unrelated working code.
"""


# --------------------------------------------------
# MAIN REPAIR FUNCTION
# --------------------------------------------------

def repair_code(
    source_code,
    test_output="",
    file_name="solution.py",
):
    """
    Diagnose Python code using Gemini.

    Supports:
    - Small Python code.
    - Large Python source files.
    - Code pasted into the application.
    - Uploaded .py files.
    - Python files extracted from ZIP projects.

    Returns:
    - Bug diagnosis.
    - Individual issue details.
    - Complete corrected Python code.
    - Syntax validation status.
    """

    if not isinstance(source_code, str):
        raise ValueError(
            "Source code must be a string."
        )

    if not source_code.strip():
        raise ValueError(
            "Source code is empty."
        )

    if not isinstance(test_output, str):
        test_output = str(test_output)

    # Test output is optional for pasted code.
    if len(test_output) > MAX_TEST_OUTPUT_CHARS:

        test_output = (
            test_output[:MAX_TEST_OUTPUT_CHARS]
            + "\n\n[Test output truncated.]"
        )

    prompt = build_debugging_prompt(
        source_code=source_code,
        test_output=test_output,
        file_name=file_name,
    )

    last_error = None

    for attempt in range(MAX_RETRIES):

        try:

            client = get_gemini_client()

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json"
                },
            )

            if not response.text:

                raise ValueError(
                    "Gemini returned an empty response."
                )

            result = extract_json(
                response.text
            )

            validated_result = _validate_response(
                result
            )

            # Additional information for the frontend.
            validated_result["file_name"] = file_name

            validated_result["source_characters"] = len(
                source_code
            )

            validated_result["analysis_scope"] = "Complete source file"

            return validated_result

        except Exception as error:

            last_error = error

            error_text = str(error).lower()

            # Do not retry invalid API credentials.
            if (
                "api key" in error_text
                or "permission denied" in error_text
                or "unauthorized" in error_text
            ):
                break

            if attempt < MAX_RETRIES - 1:

                time.sleep(
                    RETRY_DELAYS[attempt]
                )

    # Gemini unavailable: safe fallback.
    fallback = local_fallback(
        test_output
    )

    fallback["gemini_error"] = str(
        last_error
    )[:500]

    fallback["file_name"] = file_name

    fallback["source_characters"] = len(
        source_code
    )

    fallback["analysis_scope"] = "Local fallback"

    return fallback


# --------------------------------------------------
# LOCAL TEST
# --------------------------------------------------

if __name__ == "__main__":

    print("Agentic AI Debugging Engine Ready")

    print(f"Configured model: {MODEL}")

    print("Supports complete Python source files.")

    print("Supports optional test output.")

    print("Returns issue details and complete corrected code.")