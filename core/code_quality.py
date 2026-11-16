"""Static code-quality analysis for DebugEngage AI.

The analyzer uses Python's AST and conservative heuristics. Findings are warnings,
not proof of defects. The public analyze_code_quality(source_code) API and
existing result keys are preserved for compatibility with the Streamlit UI.
"""

import ast
import re
from collections import Counter


def analyze_code_quality(source_code):
    """Analyze Python source and return quality issues, bug warnings and complexity."""
    issues, potential_bugs, complexities = [], [], []

    if not isinstance(source_code, str):
        return {
            "success": False,
            "error": "Source code must be provided as text.",
            "score": 0,
            "total_issues": 0,
            "issues": [],
            "potential_bugs": [],
            "complexities": [],
            "summary": {},
        }

    lines = source_code.splitlines()

    def source_line(line_number):
        if line_number and 1 <= line_number <= len(lines):
            return lines[line_number - 1].strip()
        return ""

    def add_issue(category, severity, line, message, suggestion):
        line = line or 1
        issues.append({
            "category": category,
            "severity": severity,
            "line": line,
            "message": message,
            "suggestion": suggestion,
            "code": source_line(line),
        })

    def add_bug(category, severity, line, message, suggestion, explanation=None,
                confidence="Medium"):
        """Add a consistent, UI-friendly potential-bug finding."""
        line = line or 1
        potential_bugs.append({
            "category": category,
            "severity": severity,
            "line": line,
            "message": message,
            "explanation": explanation or message,
            "suggestion": suggestion,
            "code": source_line(line),
            "confidence": confidence,
        })

    try:
        tree = ast.parse(source_code)
    except SyntaxError as error:
        line_no = error.lineno or 1
        return {
            "success": False,
            "error": f"Syntax error at line {line_no}: {error.msg}",
            "score": 0,
            "total_issues": 0,
            "issues": [],
            "potential_bugs": [],
            "complexities": [],
            "summary": {},
        }

    functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    loaded_names = {
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }

    # Module-level list variables are useful context for detecting add-functions
    # that construct and return a record without persisting it.
    module_list_names = set()
    for statement in tree.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            value = statement.value
            if isinstance(value, (ast.List, ast.ListComp)):
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                module_list_names.update(
                    target.id for target in targets if isinstance(target, ast.Name)
                )

    # Unused imports (simple static check; dynamic imports are outside its scope).
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_name = alias.asname or alias.name.split(".")[0]
                if imported_name not in loaded_names:
                    add_issue(
                        "Unused Import", "Low", node.lineno,
                        f"Import '{imported_name}' is not used.",
                        "Remove the unused import if it is not needed.",
                    )
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    imported_name = alias.asname or alias.name
                    if imported_name not in loaded_names:
                        add_issue(
                            "Unused Import", "Low", node.lineno,
                            f"Imported name '{imported_name}' is not used.",
                            "Remove the unused import if it is not needed.",
                        )

    for function in functions:
        nodes = list(ast.walk(function))
        doc = ast.get_docstring(function) or ""
        context = f"{function.name} {doc}".lower()
        function_line = function.lineno
        length = getattr(function, "end_lineno", function_line) - function_line + 1

        # A likely persistence omission: an add/create function builds a record,
        # returns it, and has access to a module-level list but never appends to it.
        if any(word in function.name.casefold() for word in ("add", "create", "record", "save")) and module_list_names:
            returned_names = {
                node.value.id for node in nodes
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Name)
            }
            record_assignments = {
                target.id: statement
                for statement in nodes if isinstance(statement, ast.Assign)
                and isinstance(statement.value, (ast.Dict, ast.Call))
                for target in statement.targets if isinstance(target, ast.Name)
            }
            returned_records = returned_names.intersection(record_assignments)
            appended_lists = {
                node.func.value.id for node in nodes
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "append" and isinstance(node.func.value, ast.Name)
            }
            if returned_records and not module_list_names.intersection(appended_lists):
                add_bug(
                    "Possible Missing Record Persistence", "Medium",
                    record_assignments[next(iter(returned_records))].lineno,
                    f"Function '{function.name}' creates and returns a record but does not append it to the module-level list.",
                    "If this function is expected to store the record, append it to the appropriate collection before returning it.",
                    "Returning a record does not automatically save it; later summary and lookup functions may not see the new record.",
                    "Medium",
                )

        if length > 50:
            add_issue(
                "Long Function", "Medium", function_line,
                f"Function '{function.name}' has {length} lines.",
                "Split the function into smaller, focused functions.",
            )

        positional_args = len(function.args.posonlyargs) + len(function.args.args)
        total_args = positional_args + len(function.args.kwonlyargs)
        if function.args.vararg:
            total_args += 1
        if function.args.kwarg:
            total_args += 1
        if total_args > 5:
            add_issue(
                "Too Many Arguments", "Medium", function_line,
                f"Function '{function.name}' has {total_args} arguments.",
                "Group related arguments into a configuration object where appropriate.",
            )

        decisions = sum(
            isinstance(node, (
                ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp,
                ast.ExceptHandler, ast.Assert,
            ))
            for node in nodes
        )
        decisions += sum(
            isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or))
            for node in nodes
        )
        complexity = 1 + decisions
        rating = (
            "Low" if complexity <= 5 else
            "Moderate" if complexity <= 10 else
            "High" if complexity <= 20 else
            "Very High"
        )
        complexities.append({
            "function": function.name,
            "line": function_line,
            "complexity": complexity,
            "rating": rating,
        })
        if complexity > 10:
            add_issue(
                "High Complexity", "Medium", function_line,
                f"Function '{function.name}' has estimated cyclomatic complexity {complexity}.",
                "Break decision-heavy logic into smaller functions and test each path.",
            )

        # A total/sum function should not multiply a value by itself inside sum().
        if any(word in function.name.casefold() for word in ("total", "sum")):
            for node in nodes:
                if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)
                        and ast.dump(node.left, include_attributes=False) == ast.dump(node.right, include_attributes=False)):
                    add_bug(
                        "Possible Squared Value in Total", "High", node.lineno,
                        f"Function '{function.name}' multiplies an expression by itself while calculating a total.",
                        "Check whether the calculation should add the value once rather than square it.",
                        "Squaring each amount changes a sum into a sum of squares and produces an incorrect total.",
                        "High",
                    )
                    break

        # If a function promises case-insensitive matching, direct equality between
        # an input parameter and a stored field is suspicious when input is not normalized.
        promises_case_insensitive = any(
            phrase in context for phrase in (
                "case-insensitive", "case insensitive", "ignoring letter case",
                "ignore letter case", "regardless of case",
            )
        )
        if promises_case_insensitive:
            parameter_names = {
                arg.arg for arg in (function.args.posonlyargs + function.args.args + function.args.kwonlyargs)
            }
            normalized_parameter_names = {
                node.func.value.id for node in nodes
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"lower", "casefold", "upper"}
                and isinstance(node.func.value, ast.Name)
            }
            for node in nodes:
                if not isinstance(node, ast.Compare) or len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
                    continue
                sides = (node.left, *node.comparators)
                parameter_side = next((side for side in sides if isinstance(side, ast.Name)
                                        and side.id in parameter_names), None)
                field_side = next((side for side in sides if isinstance(side, (ast.Subscript, ast.Attribute))), None)
                if parameter_side is not None and field_side is not None and parameter_side.id not in normalized_parameter_names:
                    add_bug(
                        "Possible Case-Sensitive Matching", "Medium", node.lineno,
                        f"Function '{function.name}' promises case-insensitive matching but compares the input directly with a stored field.",
                        "Normalize both values with casefold() or lower() before comparing them.",
                        "A direct string equality comparison is case-sensitive, so differently cased values may not match.",
                        "High",
                    )
                    break

        # A largest/max-named function returning min() is a likely selection error.
        if any(word in function.name.casefold() for word in ("largest", "maximum", "max_", "max")):
            for node in nodes:
                if (isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
                        and isinstance(node.value.func, ast.Name) and node.value.func.id == "min"):
                    add_bug(
                        "Possible Min/Max Selection Error", "High", node.lineno,
                        f"Function '{function.name}' appears to return min() even though its name indicates a maximum.",
                        "Use max() when the required result is the item with the greatest value.",
                        "min() selects the smallest item, which conflicts with a largest/maximum function's apparent purpose.",
                        "High",
                    )
                    break

        # Mutable defaults can retain state between function calls.
        defaults = list(function.args.defaults) + [
            value for value in function.args.kw_defaults if value is not None
        ]
        if any(isinstance(value, (ast.List, ast.Dict, ast.Set)) for value in defaults):
            add_issue(
                "Mutable Default Argument", "High", function_line,
                f"Function '{function.name}' uses a mutable default argument.",
                "Use None as the default and create a new list, dictionary or set inside the function.",
            )

        # Division by len(collection) can fail when the collection is empty.
        divides_by_len = any(
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and isinstance(node.right, ast.Call)
            and isinstance(node.right.func, ast.Name)
            and node.right.func.id == "len"
            for node in nodes
        )
        empty_guard = any(
            isinstance(node, ast.If) and (
                (isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not))
                or isinstance(node.test, ast.Compare)
            )
            for node in nodes
        )
        if divides_by_len and not empty_guard:
            division_node = next(
                node for node in nodes
                if isinstance(node, ast.BinOp)
                and isinstance(node.op, ast.Div)
                and isinstance(node.right, ast.Call)
                and isinstance(node.right.func, ast.Name)
                and node.right.func.id == "len"
            )
            add_bug(
                "Possible Division by Zero", "High", division_node.lineno,
                f"Function '{function.name}' divides by the length of a collection without an obvious empty-input guard.",
                "Handle an empty collection before dividing by len(collection), for example by returning 0 or raising a clear ValueError.",
                "If the collection is empty, len(collection) is zero and the division raises ZeroDivisionError.",
                "High",
            )

        # A function named for even-number checking should not compare remainder to 1.
        if "even" in function.name.lower():
            for node in nodes:
                if isinstance(node, ast.Compare) and isinstance(node.left, ast.BinOp):
                    if (
                        isinstance(node.left.op, ast.Mod)
                        and isinstance(node.left.right, ast.Constant)
                        and node.left.right.value == 2
                        and any(
                            isinstance(op, ast.Eq)
                            and isinstance(value, ast.Constant)
                            and value.value == 1
                            for op, value in zip(node.ops, node.comparators)
                        )
                    ):
                        add_bug(
                            "Possible Incorrect Even/Odd Logic", "High", node.lineno,
                            "An even-number function checks whether number % 2 equals 1.",
                            "For an even-number check, compare the remainder with 0 (number % 2 == 0).",
                            "A remainder of 1 identifies odd integers, not even integers.",
                            "High",
                        )
                        break

        # Initializing a maximum to zero fails for an all-negative input list.
        if "max" in function.name.lower():
            zero_init = any(
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and node.value.value == 0
                for node in nodes
            )
            has_loop = any(isinstance(node, (ast.For, ast.While)) for node in nodes)
            if zero_init and has_loop:
                add_bug(
                    "Possible Maximum Initialization Bug", "Medium", function_line,
                    "A maximum-related function initializes its result to zero before iterating over values.",
                    "Consider initializing from the first element, or use max() with an explicit empty-input strategy.",
                    "If every input value is negative, a starting value of zero can incorrectly remain the maximum.",
                    "Medium",
                )

        # Addition-like functions should not normally decrement a stock/quantity field.
        if any(word in context for word in ("add", "increase", "increment")):
            for node in nodes:
                if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Sub):
                    target = ast.dump(node.target, include_attributes=False).lower()
                    if any(word in target for word in ("stock", "quantity", "count", "amount")):
                        add_bug(
                            "Possible Incorrect Addition Logic", "High", node.lineno,
                            f"Function '{function.name}' appears to add a quantity but subtracts from a stock or quantity field.",
                            "Check whether this operation should use '+=' instead of '-='.",
                            "The function name or documentation indicates an increase, but the update decreases the stored quantity.",
                            "High",
                        )
                        break

        # Discount functions returning price + a percentage amount may increase the price.
        if any(word in context for word in ("discount", "reduce price", "price reduction")):
            for node in nodes:
                if not isinstance(node, ast.Return):
                    continue
                expression = node.value
                # Support return round(price + amount, 2) as well as a bare expression.
                if isinstance(expression, ast.Call) and expression.args:
                    expression = expression.args[0]
                if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
                    contains_percentage = any(
                        isinstance(part, ast.BinOp) and isinstance(part.op, ast.Mult)
                        and any(isinstance(name, ast.Name) and name.id.casefold() in {"percentage", "percent", "discount_rate"} for name in ast.walk(part))
                        for side in (expression.left, expression.right)
                        for part in ast.walk(side)
                    )
                    if contains_percentage:
                        add_bug(
                            "Possible Discount Calculation Error", "High", node.lineno,
                            f"Function '{function.name}' adds a percentage amount to the price.",
                            "Verify that the percentage amount is subtracted from the original price for a discount.",
                            "Adding the calculated percentage increases the price; a conventional discount reduces it.",
                            "High",
                        )
                        break

        # Inventory valuation must multiply unit price by quantity, not a field by itself.
        if any(word in context for word in ("value", "inventory value", "total value")):
            for node in nodes:
                if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mult):
                    continue
                left = ast.dump(node.left, include_attributes=False)
                right = ast.dump(node.right, include_attributes=False)
                left_text = ast.unparse(node.left).casefold()
                right_text = ast.unparse(node.right).casefold()
                repeated_field = left == right and any(word in left_text for word in ("stock", "price", "quantity"))
                repeated_price = '"price"' in left_text and '"price"' in right_text
                repeated_stock = '"stock"' in left_text and '"stock"' in right_text
                if repeated_field or repeated_price or repeated_stock:
                    add_bug(
                        "Possible Inventory Value Calculation Error", "High", node.lineno,
                        f"Function '{function.name}' multiplies the same inventory field by itself while calculating value.",
                        "Calculate each product's unit price multiplied by its stock quantity.",
                        "Inventory value should use unit price × quantity in stock; squaring price or stock produces an incorrect total.",
                        "High",
                    )
                    break

    # Exception handling and risky dynamic execution.
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                add_issue(
                    "Bare Exception", "Medium", node.lineno,
                    "A bare except block catches every exception.",
                    "Catch only the exceptions your code expects.",
                )
            elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                add_issue(
                    "Broad Exception", "Low", node.lineno,
                    "A broad Exception handler may hide unexpected errors.",
                    "Catch a more specific exception where possible.",
                )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"eval", "exec"}
        ):
            add_issue(
                "Risky Function", "High", node.lineno,
                f"Use of '{node.func.id}' can execute dynamic code.",
                "Avoid dynamic code execution where possible; validate inputs and use safer alternatives.",
            )

    # Pending TODO/FIXME comments.
    for line_number, line in enumerate(lines, 1):
        if re.search(r"#.*\b(TODO|FIXME)\b", line, re.IGNORECASE):
            add_issue(
                "Pending Task", "Low", line_number,
                "A TODO or FIXME comment is present.",
                "Review and complete the pending task or remove the comment.",
            )

    # Deeply nested control structures.
    def check_nesting(node, depth=0):
        current_depth = depth + 1 if isinstance(
            node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)
        ) else depth
        if current_depth == 5:
            add_issue(
                "Deep Nesting", "Medium", getattr(node, "lineno", 1),
                "Code contains at least five nested control structures.",
                "Reduce nesting using helper functions, guard clauses or early returns.",
            )
        for child in ast.iter_child_nodes(node):
            check_nesting(child, current_depth)

    check_nesting(tree)

    def deduplicate(items):
        unique, seen = [], set()
        for item in items:
            key = (item["category"], item["line"], item["message"])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return sorted(unique, key=lambda item: (item["line"], item["category"]))

    issues = deduplicate(issues)
    potential_bugs = deduplicate(potential_bugs)

    issue_counts = Counter(item["severity"] for item in issues)
    bug_counts = Counter(item["severity"] for item in potential_bugs)
    deductions = {"High": 15, "Medium": 7, "Low": 3}
    # Potential bug findings must affect the score too; previously a file could
    # report a high-severity bug and still display 100/100.
    issue_penalty = sum(deductions.get(item["severity"], 0) for item in issues)
    bug_penalty = sum(deductions.get(item["severity"], 0) for item in potential_bugs)
    score = max(0, 100 - issue_penalty - bug_penalty)

    return {
        "success": True,
        "score": score,
        "total_issues": len(issues),
        "issues": issues,
        "potential_bugs": potential_bugs,
        "complexities": complexities,
        "summary": {
            "high": issue_counts.get("High", 0),
            "medium": issue_counts.get("Medium", 0),
            "low": issue_counts.get("Low", 0),
            "functions": len(functions),
            "classes": len(classes),
            "lines": len(lines),
            "potential_bugs": len(potential_bugs),
            "high_bugs": bug_counts.get("High", 0),
            "medium_bugs": bug_counts.get("Medium", 0),
            "low_bugs": bug_counts.get("Low", 0),
        },
    }


def analyze_project_quality(project_path):
    """Run static quality analysis on every eligible Python source file in a project."""
    from pathlib import Path

    root = Path(project_path).resolve()
    if not root.is_dir():
        return {"success": False, "error": "A valid project directory is required."}

    excluded = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
                "node_modules", "site-packages", "dist", "build", ".tox"}
    files = [p for p in root.rglob("*.py") if p.is_file()
             and not any(part.casefold() in excluded for part in p.relative_to(root).parts)
             and not p.name.startswith("test_") and not p.name.endswith("_test.py")
             and not any(part.casefold() in {"test", "tests"} for part in p.relative_to(root).parts)]
    if not files:
        return {"success": False, "error": "No eligible Python source files were found."}

    per_file, all_issues, all_bugs, all_complexities = [], [], [], []
    totals = {"high": 0, "medium": 0, "low": 0, "functions": 0, "classes": 0,
              "lines": 0, "potential_bugs": 0, "high_bugs": 0, "medium_bugs": 0, "low_bugs": 0}
    for path in sorted(files):
        relative = str(path.relative_to(root))
        try:
            source = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            per_file.append({"file": relative, "success": False, "error": str(exc)})
            continue
        result = analyze_code_quality(source)
        if not result.get("success"):
            per_file.append({"file": relative, "success": False, "error": result.get("error", "Analysis failed")})
            continue
        summary = result["summary"]
        totals["functions"] += summary["functions"]
        totals["classes"] += summary["classes"]
        totals["lines"] += summary["lines"]
        totals["potential_bugs"] += summary["potential_bugs"]
        for key in ("high", "medium", "low", "high_bugs", "medium_bugs", "low_bugs"):
            totals[key] += summary.get(key, 0)
        for item in result["issues"]:
            all_issues.append({"file": relative, **item})
        for item in result["potential_bugs"]:
            all_bugs.append({"file": relative, **item})
        for item in result["complexities"]:
            all_complexities.append({"file": relative, **item})
        per_file.append({"file": relative, "success": True, "score": result["score"],
                         "issues": result["total_issues"], "potential_bugs": summary["potential_bugs"],
                         "functions": summary["functions"], "classes": summary["classes"], "lines": summary["lines"]})

    successful = [item for item in per_file if item.get("success")]
    if not successful:
        return {"success": False, "error": "No Python files could be analyzed.", "files": per_file}
    average_score = round(sum(item["score"] for item in successful) / len(successful), 2)
    return {"success": True, "score": average_score, "total_issues": len(all_issues),
            "issues": all_issues, "potential_bugs": all_bugs, "complexities": all_complexities,
            "summary": totals, "files": per_file, "files_analyzed": len(successful),
            "files_skipped": len(per_file) - len(successful)}
