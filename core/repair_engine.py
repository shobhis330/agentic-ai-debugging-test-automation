
import ast
import json
import os
import re
import time
from typing import Any

from google import genai


MODEL = "gemini-3.5-flash-lite"

VALID_STATUSES = {
    "bug_found",
    "no_bug_found",
    "environment_issue",
    "insufficient_information",
}


def get_gemini_client():
    """Create Gemini client using the environment API key."""
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not found. Check your .env file."
        )

    return genai.Client(api_key=api_key)


def _validate_response(result: Any) -> dict:
    """Validate and normalize Gemini's response."""

    if not isinstance(result, dict):
        raise ValueError("Invalid AI response format.")

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
        raise ValueError(f"Invalid status: {status}")

    confidence = result["confidence"]

    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise ValueError("Invalid confidence value.")

    if not isinstance(result["bug_type"], str):
        raise ValueError("Invalid bug type.")

    if not isinstance(result["explanation"], str):
        raise ValueError("Invalid explanation.")

    fixed_code = result["fixed_code"]

    if not isinstance(fixed_code, str):
        raise ValueError("Invalid fixed code.")

    if status == "bug_found":
        if not fixed_code.strip():
            raise ValueError("Corrected code is empty.")

        ast.parse(fixed_code)
        result["syntax_valid"] = True
    else:
        result["fixed_code"] = ""
        result["syntax_valid"] = None

    issues = result.get("issues", [])

    if not isinstance(issues, list):
        issues = []

    result["issues"] = issues
    result["confidence"] = float(confidence)

    result.setdefault("recommended_action", "Review the diagnosis.")
    result["ai_provider"] = "Gemini"

    return result


def local_fallback(test_output):
    """
    Safe local diagnosis when Gemini is unavailable.

    Does not generate or apply replacement code.
    """

    output = str(test_output).lower()

    passed = re.search(r"\b\d+\s+passed\b", output)
    failed = re.search(r"\b\d+\s+failed\b", output)
    errors = re.search(r"\b\d+\s+errors?\b", output)

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
                "Check project imports, dependencies, and test configuration."
            ),
            "ai_provider": "Local fallback",
        }

    return {
        "status": "insufficient_information",
        "bug_type": "Diagnosis temporarily unavailable",
        "explanation": (
            "Gemini is unavailable and the local fallback cannot "
            "reliably determine the cause of the test failure. "
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


def repair_code(source_code, test_output, file_name="solution.py"):
    """
    Diagnose Python code using Gemini with automatic retry
    and a safe local fallback.
    """

    if not isinstance(source_code, str) or not source_code.strip():
        raise ValueError("Source code is empty or invalid.")

    if not isinstance(test_output, str):
        test_output = str(test_output)

    if not test_output.strip():
        raise ValueError("Test output is empty.")

    prompt = f"""
You are an expert Python debugging agent.

Analyze the source code and test output carefully.

FILE:
{file_name}

SOURCE CODE:
<source_code>
{source_code}
</source_code>

TEST OUTPUT:
<test_output>
{test_output}
</test_output>

Rules:
1. Identify only real bugs supported by evidence.
2. Distinguish source-code bugs from environment problems.
3. If tests pass and no defect is identified, use no_bug_found.
4. If imports or test collection fail, use environment_issue
   when supported by the evidence.
5. If a real source-code bug exists, provide complete corrected code.
6. Never modify tests.
7. Never claim corrected code has passed without execution.
8. Do not invent bugs.

Return ONLY valid JSON with these fields:

{{
    "status": "bug_found",
    "bug_type": "Bug category",
    "explanation": "Evidence-based explanation",
    "fixed_code": "Complete corrected source code",
    "confidence": 0.95,
    "issues": [],
    "recommended_action": "Next action"
}}

Allowed statuses:
bug_found
no_bug_found
environment_issue
insufficient_information

For all statuses other than bug_found,
fixed_code must be an empty string.
"""

    # Try Gemini up to three times.
    delays = [2, 4, 6]
    last_error = None

    for attempt in range(3):
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
                raise ValueError("Gemini returned an empty response.")

            result = json.loads(response.text)

            return _validate_response(result)

        except Exception as error:
            last_error = error
            error_text = str(error).lower()

            # Do not retry invalid API keys or configuration errors.
            if (
                "api key" in error_text
                or "permission denied" in error_text
                or "unauthorized" in error_text
            ):
                break

            if attempt < 2:
                time.sleep(delays[attempt])

    # Gemini failed: use local diagnosis instead of crashing.
    fallback = local_fallback(test_output)
    fallback["gemini_error"] = str(last_error)[:500]

    return fallback


if __name__ == "__main__":
    print("Agentic AI Debugging Engine Ready")
    print(f"Configured model: {MODEL}")
