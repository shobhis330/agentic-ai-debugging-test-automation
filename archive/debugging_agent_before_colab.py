import json
from pathlib import Path

from core.project_analyzer import analyze_project
from core.test_runner import run_tests
from core.repair_engine import repair_code


MAX_REPAIR_ATTEMPTS = 3


def run_debugging_agent(project_path):
    """
    Main agentic debugging workflow.

    Original project files are never automatically overwritten.
    """

    root = Path(project_path).resolve()

    print("\n===================================")
    print(" AGENTIC AI DEBUGGING SYSTEM")
    print("===================================\n")

    # STEP 1: Analyze project
    print("[1/4] Analyzing project...")

    analysis = analyze_project(root)

    print(f"Python files found: {analysis['total_python_files']}")
    print(f"Test files found: {analysis['total_test_files']}")

    # STEP 2: Run initial tests
    print("\n[2/4] Running project tests...")

    test_result = run_tests(root)

    print(test_result["output"])

    if test_result["success"]:
        print("\nAll tests passed. No repair required.")

        return {
            "status": "passed",
            "analysis": analysis,
            "test_result": test_result,
            "repairs": [],
        }

    if test_result["timed_out"]:
        print("\nTest execution timed out. Repair stopped.")

        return {
            "status": "timeout",
            "analysis": analysis,
            "test_result": test_result,
            "repairs": [],
        }

    # STEP 3: Ask Gemini for repair suggestions
    print("\n[3/4] Starting Gemini AI repair...")

    repair_directory = root / "ai_repair_suggestions"
    repair_directory.mkdir(exist_ok=True)

    repairs = []

    for file_name in analysis["python_files"]:

        if file_name in analysis["test_files"]:
            continue

        if len(repairs) >= MAX_REPAIR_ATTEMPTS:
            break

        source_path = root / file_name

        try:
            source_code = source_path.read_text(encoding="utf-8")

            print(f"\nAnalyzing: {file_name}")

            suggestion = repair_code(
                source_code=source_code,
                test_output=test_result["output"],
                file_name=file_name,
            )

            # Preserve directory structure in suggestion folder.
            suggestion_path = repair_directory / file_name
            suggestion_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            suggestion_path.write_text(
                suggestion["fixed_code"],
                encoding="utf-8",
            )

            repairs.append({
                "file": file_name,
                "bug_type": suggestion["bug_type"],
                "explanation": suggestion["explanation"],
                "confidence": suggestion["confidence"],
                "syntax_valid": suggestion["syntax_valid"],
                "suggestion_file": str(suggestion_path),
            })

            print("Repair suggestion generated successfully.")

        except Exception as error:
            print(f"Could not repair {file_name}: {error}")

    # STEP 4: Save report
    print("\n[4/4] Saving debugging report...")

    report = {
        "project": str(root),
        "analysis": analysis,
        "initial_test_result": {
            "success": test_result["success"],
            "return_code": test_result["return_code"],
            "timed_out": test_result["timed_out"],
        },
        "repair_attempt_limit": MAX_REPAIR_ATTEMPTS,
        "repairs": repairs,
    }

    report_directory = root / "reports"
    report_directory.mkdir(exist_ok=True)

    report_path = report_directory / "debugging_report.json"

    report_path.write_text(
        json.dumps(report, indent=4),
        encoding="utf-8",
    )

    print(f"\nReport saved at: {report_path}")
    print(f"Repair suggestions generated: {len(repairs)}")
    print("\nOriginal source files were not modified.")
    print("\nAgent execution completed.")

    return {
        "status": "completed",
        "analysis": analysis,
        "test_result": test_result,
        "repairs": repairs,
        "report_path": str(report_path),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Agentic AI Python Debugging System"
    )

    parser.add_argument(
        "project_path",
        nargs="?",
        default="sample_projects",
        help="Path of the Python project to analyze",
    )

    args = parser.parse_args()

    result = run_debugging_agent(args.project_path)

    print("\nFinal Status:", result["status"])
