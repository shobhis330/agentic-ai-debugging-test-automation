import sys

import ast
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

BASE_DIR = Path(__file__).resolve().parent
CASES_DIR = BASE_DIR / "evaluation_cases"
MODEL = "gemini-3.5-flash-lite"
MAX_RETRIES = 3

load_dotenv(BASE_DIR / ".env")


def get_client():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found in .env")
    return genai.Client(api_key=key)


def run_tests(case_dir):
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "-q", "--tb=short", "test_solution.py"
        ],
        cwd=str(case_dir),
        capture_output=True,
        text=True,
        timeout=30
    )
    return result.returncode, result.stdout + result.stderr


def request_repair(client, code, feedback, function_name):
    prompt = f"""
You are an expert Python debugging agent.

Fix the bug in this function using the pytest failure feedback.

FUNCTION NAME: {function_name}

CURRENT CODE:
{code}

PYTEST FEEDBACK:
{feedback}

Requirements:
1. Fix the actual demonstrated bug.
2. Preserve the function name and its arguments.
3. Handle the tested edge cases.
4. Do not modify or weaken the tests.
5. Return complete Python source code.

Return JSON with exactly these fields:
bug_type, explanation, fixed_code, confidence.
confidence must be a number between 0 and 1.
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )

    data = json.loads(response.text)

    required = {
        "bug_type", "explanation", "fixed_code", "confidence"
    }
    if not isinstance(data, dict) or not required.issubset(data):
        raise ValueError("Gemini returned an invalid repair response.")

    if not isinstance(data["fixed_code"], str):
        raise ValueError("Invalid fixed_code.")

    tree = ast.parse(data["fixed_code"])
    functions = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    if function_name not in functions:
        raise ValueError("Required function missing from repair.")

    compile(data["fixed_code"], "candidate.py", "exec")
    return data


def repair_case(case_id):
    case_dir = CASES_DIR / case_id
    solution = case_dir / "solution.py"

    if not solution.is_file():
        raise FileNotFoundError(f"Missing case: {case_id}")

    original_code = solution.read_text(encoding="utf-8")
    client = get_client()

    print("\n" + "=" * 55)
    print(f"AGENTIC AI DEBUGGING: {case_id}")
    print("=" * 55)

    try:
        for attempt in range(MAX_RETRIES + 1):
            exit_code, feedback = run_tests(case_dir)

            print(f"\nTest run {attempt + 1}")
            print(feedback)

            if exit_code == 0:
                print(f"SUCCESS: {case_id} PASSED")
                return {
                    "case": case_id,
                    "status": "PASS",
                    "repair_attempts": attempt,
                    "details": "All tests passed."
                }

            if attempt == MAX_RETRIES:
                break

            tree = ast.parse(solution.read_text(encoding="utf-8"))
            functions = [
                node.name for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]

            if not functions:
                raise ValueError("No function found in solution.")

            print(f"Gemini repair attempt {attempt + 1}/{MAX_RETRIES}")

            repair = request_repair(
                client,
                solution.read_text(encoding="utf-8"),
                feedback,
                functions[0]
            )

            candidate = repair["fixed_code"]
            solution.write_text(candidate, encoding="utf-8")

            print("Bug:", repair["bug_type"])
            print("Explanation:", repair["explanation"])
            print("Confidence:", repair["confidence"])

        print(f"FAILED: {case_id} did not pass.")
        return {
            "case": case_id,
            "status": "FAIL",
            "repair_attempts": MAX_RETRIES,
            "details": "Repair limit reached."
        }

    except Exception as error:
        print("ERROR:", error)
        return {
            "case": case_id,
            "status": "ERROR",
            "repair_attempts": 0,
            "details": str(error)
        }

    finally:
        # Keep the original buggy example reproducible for future runs.
        solution.write_text(original_code, encoding="utf-8")


def run_all():
    results = []

    for case_id in ["TC01", "TC02", "TC03"]:
        results.append(repair_case(case_id))

    csv_path = BASE_DIR / "week2_evaluation_results.csv"

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["case", "status", "repair_attempts", "details"]
        )
        writer.writeheader()
        writer.writerows(results)

    passed = sum(r["status"] == "PASS" for r in results)

    print("\n" + "=" * 55)
    print("FINAL EVALUATION SUMMARY")
    print("=" * 55)
    print(f"Total cases: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed or errors: {len(results) - passed}")
    print(f"Results saved: {csv_path}")

    return passed == len(results)
