
import ast
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai


# --------------------------------------------------
# PROJECT CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
CASES_DIR = BASE_DIR / "evaluation_cases"

RESULTS_FILE = BASE_DIR / "week2_evaluation_results.csv"

MODEL_NAME = "gemini-3.5-flash-lite"
MAX_RETRIES = 3

load_dotenv(BASE_DIR / ".env")


# --------------------------------------------------
# GEMINI CLIENT
# --------------------------------------------------

def get_client():
    """
    Create Gemini API client using the API key
    stored in the .env file.
    """

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not found. "
            "Please check your .env file."
        )

    return genai.Client(api_key=api_key)


# --------------------------------------------------
# RUN PYTEST
# --------------------------------------------------

def run_tests(case_dir):
    """
    Execute pytest for a particular evaluation case.
    """

    test_file = case_dir / "test_solution.py"

    if not test_file.exists():
        return {
            "passed": False,
            "output": "test_solution.py not found."
        }

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                str(test_file)
            ],
            cwd=str(case_dir),
            capture_output=True,
            text=True,
            timeout=60
        )

        output = (
            result.stdout or ""
        ) + (
            result.stderr or ""
        )

        return {
            "passed": result.returncode == 0,
            "output": output
        }

    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "output": "Test execution timed out."
        }

    except Exception as error:
        return {
            "passed": False,
            "output": f"Test execution error: {error}"
        }


# --------------------------------------------------
# READ SOURCE CODE
# --------------------------------------------------

def read_source_file(file_path):
    """
    Read Python source code from a file.
    """

    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as error:
        raise RuntimeError(
            f"Unable to read {file_path}: {error}"
        )


# --------------------------------------------------
# EXTRACT REQUIRED FUNCTION NAMES
# --------------------------------------------------

def get_function_names(source_code):
    """
    Identify function names in the original Python code.
    """

    try:
        tree = ast.parse(source_code)

        return {
            node.name
            for node in ast.walk(tree)
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef)
            )
        }

    except SyntaxError:
        return set()


# --------------------------------------------------
# EXTRACT JSON RESPONSE
# --------------------------------------------------

def extract_json(response_text):
    """
    Extract JSON from Gemini response.
    Handles responses containing Markdown code fences.
    """

    response_text = response_text.strip()

    response_text = re.sub(
        r"^```(?:json)?\s*",
        "",
        response_text,
        flags=re.IGNORECASE
    )

    response_text = re.sub(
        r"\s*```$",
        "",
        response_text
    )

    try:
        return json.loads(response_text)

    except json.JSONDecodeError:
        match = re.search(
            r"\{.*\}",
            response_text,
            flags=re.DOTALL
        )

        if not match:
            raise ValueError(
                "Gemini did not return valid JSON."
            )

        return json.loads(match.group(0))


# --------------------------------------------------
# REQUEST REPAIR FROM GEMINI
# --------------------------------------------------

def request_repair(source_code, test_feedback):
    """
    Ask Gemini to diagnose the bug and generate
    corrected Python code.
    """

    client = get_client()

    prompt = f"""
You are an expert Python debugging agent.

Your task is to identify and fix the bug in the
provided Python program.

ORIGINAL PYTHON CODE:
---------------------
{source_code}

PYTEST FAILURE DETAILS:
-----------------------
{test_feedback}

INSTRUCTIONS:
1. Identify the actual bug.
2. Explain why the bug occurs.
3. Correct the source code.
4. Preserve the original function names.
5. Preserve the expected function parameters.
6. Do not remove required functionality.
7. Do not add unnecessary code.
8. Return complete corrected Python source code.
9. Do not include explanations inside fixed_code.

Return ONLY valid JSON using this structure:

{{
    "bug_type": "Type of bug",
    "explanation": "Explanation of the bug",
    "fixed_code": "Complete corrected Python source code",
    "confidence": 0.95
}}

The confidence value must be between 0 and 1.
"""

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            print(
                f"Gemini repair attempt "
                f"{attempt}/{MAX_RETRIES}"
            )

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )

            if not response.text:
                raise ValueError(
                    "Gemini returned an empty response."
                )

            repair_data = extract_json(response.text)

            required_fields = [
                "bug_type",
                "explanation",
                "fixed_code",
                "confidence"
            ]

            for field in required_fields:
                if field not in repair_data:
                    raise ValueError(
                        f"Missing response field: {field}"
                    )

            if not isinstance(
                repair_data["fixed_code"],
                str
            ):
                raise ValueError(
                    "fixed_code must be a string."
                )

            return repair_data

        except Exception as error:
            last_error = error

            print(
                f"Gemini attempt {attempt} failed: {error}"
            )

            if attempt < MAX_RETRIES:
                time.sleep(2 * attempt)

    raise RuntimeError(
        f"Gemini repair failed after "
        f"{MAX_RETRIES} attempts: {last_error}"
    )


# --------------------------------------------------
# VALIDATE GENERATED CODE
# --------------------------------------------------

def validate_repair(original_code, fixed_code):
    """
    Check whether the generated code is valid
    and preserves the original function names.
    """

    if not fixed_code.strip():
        return False, "Generated code is empty."

    try:
        ast.parse(fixed_code)

        compile(
            fixed_code,
            "<repaired_code>",
            "exec"
        )

    except SyntaxError as error:
        return False, f"Syntax error: {error}"

    except Exception as error:
        return False, f"Code validation error: {error}"

    original_functions = get_function_names(
        original_code
    )

    repaired_functions = get_function_names(
        fixed_code
    )

    missing_functions = (
        original_functions - repaired_functions
    )

    if missing_functions:
        return (
            False,
            "Required functions missing: "
            + ", ".join(sorted(missing_functions))
        )

    return True, "Generated code passed validation."


# --------------------------------------------------
# REPAIR ONE EVALUATION CASE
# --------------------------------------------------

def repair_case(case_dir):
    """
    Diagnose and repair one evaluation case.

    The original source file is restored after testing,
    so evaluation does not permanently modify the
    original test-case program.
    """

    solution_file = case_dir / "solution.py"

    if not solution_file.exists():
        return {
            "case": case_dir.name,
            "status": "SKIPPED",
            "bug_type": "",
            "explanation": "",
            "confidence": 0,
            "attempts": 0,
            "details": "solution.py not found."
        }

    original_code = read_source_file(solution_file)

    initial_test = run_tests(case_dir)

    if initial_test["passed"]:
        return {
            "case": case_dir.name,
            "status": "ALREADY_PASSED",
            "bug_type": "",
            "explanation": "All tests passed initially.",
            "confidence": 1,
            "attempts": 0,
            "details": initial_test["output"]
        }

    final_result = {
        "case": case_dir.name,
        "status": "FAILED",
        "bug_type": "",
        "explanation": "",
        "confidence": 0,
        "attempts": 0,
        "details": initial_test["output"]
    }

    try:

        for attempt in range(1, MAX_RETRIES + 1):

            final_result["attempts"] = attempt

            print(
                f"\nRepairing {case_dir.name} "
                f"(attempt {attempt})"
            )

            try:
                repair_data = request_repair(
                    original_code,
                    initial_test["output"]
                )

                fixed_code = repair_data["fixed_code"]

                valid, validation_message = validate_repair(
                    original_code,
                    fixed_code
                )

                if not valid:
                    final_result["details"] = (
                        validation_message
                    )

                    continue

                # Temporarily apply generated repair.
                solution_file.write_text(
                    fixed_code,
                    encoding="utf-8"
                )

                # Execute tests again.
                retest = run_tests(case_dir)

                final_result.update({
                    "bug_type": repair_data["bug_type"],
                    "explanation": repair_data["explanation"],
                    "confidence": repair_data["confidence"],
                    "details": retest["output"]
                })

                if retest["passed"]:
                    final_result["status"] = "REPAIRED"

                    print(
                        f"{case_dir.name}: Repair successful."
                    )

                    return final_result

                # Restore original code before another attempt.
                solution_file.write_text(
                    original_code,
                    encoding="utf-8"
                )

                # Use the latest test failure as feedback.
                initial_test = retest

            except Exception as error:

                final_result["details"] = str(error)

                print(
                    f"Repair attempt failed: {error}"
                )

                solution_file.write_text(
                    original_code,
                    encoding="utf-8"
                )

        return final_result

    finally:
        # Always restore original evaluation source.
        solution_file.write_text(
            original_code,
            encoding="utf-8"
        )


# --------------------------------------------------
# SAVE EVALUATION RESULTS
# --------------------------------------------------

def save_results(results):
    """
    Save evaluation results in CSV format.
    """

    fieldnames = [
        "case",
        "status",
        "bug_type",
        "explanation",
        "confidence",
        "attempts",
        "details"
    ]

    try:
        with RESULTS_FILE.open(
            "w",
            newline="",
            encoding="utf-8"
        ) as csv_file:

            writer = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames
            )

            writer.writeheader()
            writer.writerows(results)

        print(
            f"\nResults saved to: {RESULTS_FILE}"
        )

    except Exception as error:
        print(f"Unable to save results: {error}")


# --------------------------------------------------
# RUN ALL EVALUATION CASES
# --------------------------------------------------

def run_all():
    """
    Execute all available TC01 to TC15 evaluation cases.
    """

    if not CASES_DIR.exists():
        print(
            f"Evaluation folder not found: {CASES_DIR}"
        )
        return []

    case_directories = sorted(
        [
            path
            for path in CASES_DIR.iterdir()
            if path.is_dir()
            and path.name.startswith("TC")
        ],
        key=lambda path: path.name
    )

    if not case_directories:
        print("No evaluation cases found.")
        return []

    print("\n====================================")
    print(" AGENTIC AI DEBUGGING EVALUATION")
    print("====================================")

    print(
        f"Total evaluation cases: "
        f"{len(case_directories)}"
    )

    results = []

    for case_dir in case_directories:

        print(
            f"\nProcessing {case_dir.name}..."
        )

        result = repair_case(case_dir)

        results.append(result)

        print(
            f"Status: {result['status']}"
        )

    save_results(results)

    # Display summary.
    repaired = sum(
        1 for result in results
        if result["status"] == "REPAIRED"
    )

    already_passed = sum(
        1 for result in results
        if result["status"] == "ALREADY_PASSED"
    )

    failed = sum(
        1 for result in results
        if result["status"] == "FAILED"
    )

    skipped = sum(
        1 for result in results
        if result["status"] == "SKIPPED"
    )

    print("\n====================================")
    print(" EVALUATION SUMMARY")
    print("====================================")

    print(f"Total cases       : {len(results)}")
    print(f"Successfully fixed: {repaired}")
    print(f"Already passed    : {already_passed}")
    print(f"Failed            : {failed}")
    print(f"Skipped           : {skipped}")

    print("====================================")

    return results


# --------------------------------------------------
# MAIN
# --------------------------------------------------

if __name__ == "__main__":
    run_all()
