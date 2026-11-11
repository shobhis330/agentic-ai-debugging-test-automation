from core.project_analyzer import analyze_project

result = analyze_project(".")

print("\n--- SYNTAX ERRORS ---")

for error in result["syntax_errors"]:
    print("File:", error["file"])
    print("Line:", error["line"])
    print("Message:", error["message"])
    print("--------------------")

print("Total syntax errors:", result["total_syntax_errors"])
