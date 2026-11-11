
import ast
import re
from collections import Counter


def analyze_code_quality(source_code):
    """Perform static code-quality and heuristic bug analysis."""

    issues = []
    potential_bugs = []
    complexities = []

    def add_issue(category, severity, line, message, suggestion):
        issues.append({
            "category": category,
            "severity": severity,
            "line": line or 1,
            "message": message,
            "suggestion": suggestion
        })

    def add_bug(category, severity, line, message, suggestion):
        potential_bugs.append({
            "category": category,
            "severity": severity,
            "line": line or 1,
            "message": message,
            "suggestion": suggestion
        })

    try:
        tree = ast.parse(source_code)
    except SyntaxError as error:
        return {
            "success": False,
            "error": f"Syntax error at line {error.lineno}: {error.msg}",
            "score": 0,
            "total_issues": 0,
            "issues": [],
            "potential_bugs": [],
            "complexities": [],
            "summary": {}
        }

    functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    classes = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    ]

    loaded_names = {
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }

    # 1. Unused imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                if name not in loaded_names:
                    add_issue(
                        "Unused Import", "Low", node.lineno,
                        f"Import '{name}' is not used.",
                        "Remove the unused import."
                    )

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname or alias.name
                if name not in loaded_names:
                    add_issue(
                        "Unused Import", "Low", node.lineno,
                        f"Imported name '{name}' is not used.",
                        "Remove the unused import if unnecessary."
                    )

    # 2. Function quality and complexity
    for function in functions:
        end_line = getattr(function, "end_lineno", function.lineno)
        function_length = end_line - function.lineno + 1

        if function_length > 50:
            add_issue(
                "Long Function", "Medium", function.lineno,
                f"Function '{function.name}' has {function_length} lines.",
                "Split the function into smaller functions."
            )

        argument_count = len(function.args.args)

        if argument_count > 5:
            add_issue(
                "Too Many Arguments", "Medium", function.lineno,
                f"Function '{function.name}' has {argument_count} arguments.",
                "Group related arguments where appropriate."
            )

        # Cyclomatic complexity estimate:
        # 1 base path + decision points.
        decisions = sum(
            isinstance(node, (
                ast.If, ast.For, ast.AsyncFor, ast.While,
                ast.IfExp, ast.ExceptHandler, ast.Assert
            ))
            for node in ast.walk(function)
        )

        decisions += sum(
            isinstance(node, ast.BoolOp)
            and isinstance(node.op, (ast.And, ast.Or))
            for node in ast.walk(function)
        )

        complexity = 1 + decisions

        complexities.append({
            "function": function.name,
            "line": function.lineno,
            "complexity": complexity,
            "rating": (
                "Low" if complexity <= 5
                else "Moderate" if complexity <= 10
                else "High"
            )
        })

        if complexity > 10:
            add_issue(
                "High Complexity", "Medium", function.lineno,
                f"Function '{function.name}' has estimated complexity {complexity}.",
                "Break decision-heavy logic into smaller functions."
            )

        # Mutable default arguments
        for default in function.args.defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                add_issue(
                    "Mutable Default Argument", "High", function.lineno,
                    f"Function '{function.name}' uses a mutable default argument.",
                    "Use None as the default and create the object inside the function."
                )

        # 3. Heuristic bug checks within each function
        function_nodes = list(ast.walk(function))

        # Potential division by zero when dividing by len(collection)
        has_length_division = any(
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and isinstance(node.right, ast.Call)
            and isinstance(node.right.func, ast.Name)
            and node.right.func.id == "len"
            for node in function_nodes
        )

        has_empty_guard = any(
            isinstance(node, ast.If)
            and (
                isinstance(node.test, ast.UnaryOp)
                and isinstance(node.test.op, ast.Not)
                or isinstance(node.test, ast.Compare)
            )
            for node in function_nodes
        )

        if has_length_division and not has_empty_guard:
            add_bug(
                "Possible Division by Zero", "High", function.lineno,
                f"Function '{function.name}' divides by the length of a collection. An empty collection may cause division by zero.",
                "Handle empty collections before dividing by their length."
            )

        # Possible incorrect even-number condition
        if "even" in function.name.lower():
            has_wrong_even_check = any(
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.BinOp)
                and isinstance(node.left.op, ast.Mod)
                and any(
                    isinstance(value, ast.Constant)
                    and value.value == 2
                    for value in [node.left.right]
                )
                and any(
                    isinstance(op, ast.Eq)
                    and isinstance(comparator, ast.Constant)
                    and comparator.value == 1
                    for op, comparator in zip(
                        node.ops, node.comparators
                    )
                )
                for node in function_nodes
            )

            if has_wrong_even_check:
                add_bug(
                    "Possible Incorrect Even/Odd Logic", "High",
                    function.lineno,
                    "An even-number function checks whether the remainder after division by 2 equals 1.",
                    "For an even-number check, the remainder should normally equal 0."
                )

        # Possible maximum function initialized to zero
        if "max" in function.name.lower():
            zero_initialization = any(
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and node.value.value == 0
                for node in function_nodes
            )

            has_loop = any(
                isinstance(node, (ast.For, ast.While))
                for node in function_nodes
            )

            if zero_initialization and has_loop:
                add_bug(
                    "Possible Maximum Initialization Bug", "Medium",
                    function.lineno,
                    "A maximum-related function initializes a value to zero and iterates over data. This may fail when all input values are negative.",
                    "Consider initializing from the first element or using an appropriate empty-input strategy."
                )

    # 4. Exception handling and risky functions
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                add_issue(
                    "Bare Exception", "Medium", node.lineno,
                    "A bare except block catches every exception.",
                    "Catch only the exceptions your code expects."
                )
            elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                add_issue(
                    "Broad Exception", "Low", node.lineno,
                    "A broad Exception handler may hide unexpected errors.",
                    "Catch a more specific exception where possible."
                )

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                add_issue(
                    "Risky Function", "High", node.lineno,
                    f"Use of '{node.func.id}' can execute dynamic code.",
                    "Avoid dynamic code execution where possible."
                )

    # 5. TODO and FIXME comments
    for line_number, line in enumerate(source_code.splitlines(), start=1):
        if re.search(r"#.*\b(TODO|FIXME)\b", line, re.IGNORECASE):
            add_issue(
                "Pending Task", "Low", line_number,
                "A TODO or FIXME comment is present.",
                "Review and complete the pending task."
            )

    # 6. Deep nesting
    def check_nesting(node, depth=0):
        current_depth = depth

        if isinstance(node, (
            ast.If, ast.For, ast.AsyncFor,
            ast.While, ast.With, ast.AsyncWith
        )):
            current_depth += 1

            if current_depth == 5:
                add_issue(
                    "Deep Nesting", "Medium", node.lineno,
                    "Code contains more than four nested control structures.",
                    "Reduce nesting using helper functions or early returns."
                )

        for child in ast.iter_child_nodes(node):
            check_nesting(child, current_depth)

    check_nesting(tree)

    # Remove duplicate findings
    def remove_duplicates(items):
        unique = []
        seen = set()

        for item in items:
            key = (
                item["category"],
                item["line"],
                item["message"]
            )
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return sorted(unique, key=lambda item: item["line"])

    issues = remove_duplicates(issues)
    potential_bugs = remove_duplicates(potential_bugs)

    severity_counts = Counter(
        issue["severity"] for issue in issues
    )

    deductions = {"High": 15, "Medium": 7, "Low": 3}

    score = max(
        0,
        100 - sum(
            deductions[issue["severity"]]
            for issue in issues
        )
    )

    bug_counts = Counter(
        bug["severity"] for bug in potential_bugs
    )

    return {
        "success": True,
        "score": score,
        "total_issues": len(issues),
        "issues": issues,
        "potential_bugs": potential_bugs,
        "complexities": complexities,
        "summary": {
            "high": severity_counts.get("High", 0),
            "medium": severity_counts.get("Medium", 0),
            "low": severity_counts.get("Low", 0),
            "functions": len(functions),
            "classes": len(classes),
            "lines": len(source_code.splitlines()),
            "potential_bugs": len(potential_bugs),
            "high_bugs": bug_counts.get("High", 0),
            "medium_bugs": bug_counts.get("Medium", 0),
            "low_bugs": bug_counts.get("Low", 0)
        }
    }
