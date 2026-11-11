
import os
import json
from pathlib import Path

from dotenv import load_dotenv
from google import genai

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = "gemini-3.5-flash-lite"


def explain_bugs(source_code, file_name="uploaded_code.py", findings=None):
    """
    Use Gemini to explain possible bugs in Python source code.
    Returns a dictionary containing success, explanation, and error.
    """

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return {
            "success": False,
            "explanation": "",
            "error": (
                "GEMINI_API_KEY was not found. "
                "Check that your .env file exists in the project root."
            )
        }

    if not source_code or not source_code.strip():
        return {
            "success": False,
            "explanation": "",
            "error": "No Python source code was provided."
        }

    # Limit input size to keep requests manageable.
    source_for_review = source_code[:25000]

    findings_text = json.dumps(
        findings or [],
        indent=2,
        ensure_ascii=False
    )

    prompt = f"""
You are an experienced Python debugging assistant.

Review the submitted Python program and explain its possible bugs.

FILE NAME:
{file_name}

STATIC ANALYSIS FINDINGS:
{findings_text}

PYTHON SOURCE CODE:
```python
{source_for_review}
```

Prepare a clear debugging report using these sections:

## 1. Overall Review
Briefly explain the general condition of the submitted code.

## 2. Detected Bugs
For each confirmed or likely bug:
- Bug title
- Relevant function and approximate line number
- Original problematic code
- Why the problem occurs
- What can happen when the program runs
- Corrected code
- Explanation of the correction

## 3. Additional Observations
Mention other possible issues that static analysis may have missed.

## 4. Testing Recommendations
Suggest test cases, including normal inputs, edge cases, and invalid inputs.

IMPORTANT:
- Do not invent bugs.
- Distinguish confirmed defects from possible risks.
- If the code appears correct, say so.
- Treat static analysis findings as clues, not guaranteed bugs.
- Preserve the original program's intended behaviour where it can be inferred.
- Do not claim that you executed or tested the code.
- Use beginner-friendly explanations.
- Do not reproduce the entire source file unnecessarily.
"""

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )

        explanation = getattr(response, "text", None)

        if not explanation:
            return {
                "success": False,
                "explanation": "",
                "error": "Gemini returned an empty explanation."
            }

        return {
            "success": True,
            "explanation": explanation,
            "error": None
        }

    except Exception as error:
        return {
            "success": False,
            "explanation": "",
            "error": f"Gemini request failed: {error}"
        }
