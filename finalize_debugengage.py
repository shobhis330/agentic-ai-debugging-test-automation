from pathlib import Path
import ast
import shutil
import sys
import textwrap

ROOT = Path(__file__).resolve().parent

def backup(path):
    backup_path = path.with_suffix(path.suffix + ".before_final_fixes.bak")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)

def replace_functions(source, replacements):
    tree = ast.parse(source.lstrip("\ufeff"))
    lines = source.splitlines(keepends=True)
    spans = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in replacements:
            spans.append((node.lineno - 1, node.end_lineno, node.name))
    found = {name for _, _, name in spans}
    missing = set(replacements) - found
    if missing:
        raise RuntimeError("Could not locate functions: " + ", ".join(sorted(missing)))
    for start, end, name in sorted(spans, reverse=True):
        lines[start:end] = [replacements[name].strip() + "\n"]
    return "".join(lines)

def update_app(app_path):
    source = app_path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    target = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(item, ast.Name) and item.id == "EMBEDDED_FEATURE_PAGES"
            for item in node.targets
        ):
            target = node
            break
    if target is None:
        raise RuntimeError("EMBEDDED_FEATURE_PAGES was not found in frontend/app.py")

    pages = ast.literal_eval(target.value)

    coverage = pages["Test_Coverage_Report.py"]
    coverage = coverage.replace(
        'shared_path = st.session_state.get("project_path")\nsource_code = shared_source',
        'shared_path = st.session_state.get("project_path")\n'
        'coverage_source_rel_path = st.session_state.get("central_selected_file") or ""\n'
        'coverage_project_root = shared_path if shared_path and shared_source else None\n'
        'coverage_test_rel_path = None\n'
        'source_code = shared_source'
    )
    coverage = coverage.replace(
        'file_name = shared_name',
        'file_name = shared_name\n'
        '# Use the latest extracted source after an approved repair.\n'
        'if coverage_project_root and coverage_source_rel_path:\n'
        '    current_coverage_path = (Path(coverage_project_root) / coverage_source_rel_path).resolve()\n'
        '    try:\n'
        '        current_coverage_path.relative_to(Path(coverage_project_root).resolve())\n'
        '        if current_coverage_path.is_file():\n'
        '            source_code = current_coverage_path.read_text(encoding="utf-8-sig", errors="replace")\n'
        '    except (OSError, ValueError):\n'
        '        pass'
    )
    coverage = coverage.replace(
        '        source_code = chosen.read_text(encoding="utf-8-sig", errors="replace")\n'
        '        file_name = chosen.name',
        '        source_code = chosen.read_text(encoding="utf-8-sig", errors="replace")\n'
        '        file_name = chosen.name\n'
        '        coverage_source_rel_path = selected\n'
        '        coverage_project_root = shared_path'
    )
    coverage = coverage.replace(
        '        file_name = local_file.name\n'
        '        st.info(f"Using separate file for this feature only: {file_name}")',
        '        file_name = local_file.name\n'
        '        coverage_project_root = None\n'
        '        coverage_source_rel_path = None\n'
        '        st.info(f"Using separate file for this feature only: {file_name}")'
    )
    coverage = coverage.replace(
        '        chosen_test = shared_test_files[test_labels.index(selected_test)]\n'
        '        reused_test_code = chosen_test.read_text(encoding="utf-8-sig", errors="replace")',
        '        chosen_test = shared_test_files[test_labels.index(selected_test)]\n'
        '        coverage_test_rel_path = selected_test\n'
        '        reused_test_code = chosen_test.read_text(encoding="utf-8-sig", errors="replace")'
    )
    coverage = coverage.replace(
        '                    timeout=60\n'
        '                )',
        '                    timeout=60,\n'
        '                    project_root=coverage_project_root,\n'
        '                    source_rel_path=coverage_source_rel_path,\n'
        '                    test_rel_path=coverage_test_rel_path,\n'
        '                )',
        1
    )
    if "project_root=coverage_project_root" not in coverage:
        raise RuntimeError("Could not patch the embedded coverage execution call.")
    pages["Test_Coverage_Report.py"] = coverage

    quality = pages["Code_Quality.py"]
    quality = quality.replace(
        'shared_path = st.session_state.get("project_path")\n'
        'source_code = shared_source\n'
        'source_name = shared_name',
        'shared_path = st.session_state.get("project_path")\n'
        'source_code = shared_source\n'
        'source_name = shared_name\n'
        '# Prefer the current extracted project file so analysis reflects approved repairs.\n'
        'if shared_path and shared_name:\n'
        '    current_source_path = (Path(shared_path) / shared_name).resolve()\n'
        '    try:\n'
        '        current_source_path.relative_to(Path(shared_path).resolve())\n'
        '        if current_source_path.is_file():\n'
        '            source_code = current_source_path.read_text(encoding="utf-8-sig", errors="replace")\n'
        '    except (OSError, ValueError):\n'
        '        pass'
    )
    quality = quality.replace(
        'if st.button("🔍 Analyze Code", type="primary"):',
        'if st.session_state.get("quality_last_source") != source_code:\n'
        '    st.session_state.pop("quality_analysis_result", None)\n'
        '    st.session_state["quality_last_source"] = source_code\n\n'
        'if st.button("🔍 Analyze Code", type="primary"):'
    )
    pages["Code_Quality.py"] = quality

    # Replace only the embedded-page dictionary assignment, preserving the rest of app.py.
    lines = source.splitlines(keepends=True)
    start, end = target.lineno - 1, target.end_lineno
    replacement = "EMBEDDED_FEATURE_PAGES = " + repr(pages) + "\n"
    lines[start:end] = [replacement]
    source = "".join(lines)

    # Shared-project comparison must stage sibling modules and preserve nested test paths.
    old = '        existing_test_files = []\n'
    new = '        existing_test_files = []\n        chosen_label = None\n'
    source = source.replace(old, new, 1)
    old_call = 'comparison_result_value = compare_versions(original_value, corrected_value, test_code_value, Path(selected_rel_value).name)'
    new_call = (
        'comparison_result_value = compare_versions(\n'
        '                        original_value, corrected_value, test_code_value,\n'
        '                        Path(selected_rel_value).name,\n'
        '                        project_root=project_root_value,\n'
        '                        source_rel_path=selected_rel_value,\n'
        '                        test_rel_path=chosen_label,\n'
        '                    )'
    )
    if old_call not in source:
        raise RuntimeError("Could not locate the shared-project comparison call.")
    source = source.replace(old_call, new_call, 1)

    # A failed post-repair validation must close the history record as failed, not pending.
    marker = (
        '                                        if not updated:\n'
        '                                            add_history_entry(\n'
        '                                                file_name=st.session_state.get("central_selected_file") or selected_path.name,\n'
        '                                                status="success",\n'
        '                                                original_code=st.session_state.get("central_original_code") or "",\n'
        '                                                **history_changes\n'
        '                                            )\n'
    )
    failure_branch = marker + (
        '                                    else:\n'
        '                                        failed_status = "failed" if validation_result.get("failed", 0) else "error"\n'
        '                                        failed_summary = (\n'
        '                                            f"{validation_result.get(\'passed\', 0)} passed, "\n'
        '                                            f"{validation_result.get(\'failed\', 0)} failed, "\n'
        '                                            f"{validation_result.get(\'errors\', 0)} errors"\n'
        '                                        )\n'
        '                                        if st.session_state.get("central_history_entry_id"):\n'
        '                                            update_history_entry(\n'
        '                                                st.session_state.get("central_history_entry_id"),\n'
        '                                                status=failed_status,\n'
        '                                                issue="Post-repair validation did not pass",\n'
        '                                                test_summary=failed_summary,\n'
        '                                                details="Post-repair project tests did not all pass. Review the test output and remaining failing files.",\n'
        '                                            )\n'
    )
    if marker not in source:
        raise RuntimeError("Could not locate the post-repair history success block.")
    source = source.replace(marker, failure_branch, 1)

    ast.parse(source)
    app_path.write_text(source, encoding="utf-8")

def main():
    coverage_path = ROOT / "core" / "test_coverage.py"
    comparison_path = ROOT / "core" / "test_comparison.py"
    app_path = ROOT / "frontend" / "app.py"

    for path in (coverage_path, comparison_path, app_path):
        if not path.is_file():
            raise SystemExit(f"Required project file is missing: {path}")

    backup(coverage_path)
    backup(comparison_path)
    backup(app_path)

    coverage_source = coverage_path.read_text(encoding="utf-8-sig")
    coverage_source = replace_functions(
        coverage_source,
        {"run_coverage_tests": COVERAGE_FUNCTION},
    )
    ast.parse(coverage_source)
    coverage_path.write_text(coverage_source, encoding="utf-8")

    comparison_source = comparison_path.read_text(encoding="utf-8-sig")
    comparison_source = replace_functions(
        comparison_source,
        {
            "run_test_comparison": COMPARISON_FUNCTION,
            "compare_versions": COMPARE_VERSIONS_FUNCTION,
        },
    )
    ast.parse(comparison_source)
    comparison_path.write_text(comparison_source, encoding="utf-8")

    update_app(app_path)

    print("DebugEngage AI final integration fixes applied.")
    print("Updated: core/test_coverage.py")
    print("Updated: core/test_comparison.py")
    print("Updated: frontend/app.py")
    print("Backups saved beside the original files with .before_final_fixes.bak")
    print("Next: restart Streamlit and retest coverage, comparison, and ZIP validation.")

COVERAGE_FUNCTION = 'def run_coverage_tests(\n    source_code,\n    file_name,\n    test_code,\n    timeout=60,\n    project_root=None,\n    source_rel_path=None,\n    test_rel_path=None,\n):\n    """Run pytest with the selected source and its sibling project modules.\n\n    When project_root is supplied, all safe Python files are staged into an\n    isolated temporary workspace so imports such as ``from pricing import ...``\n    continue to work. Only the selected source and selected test file are\n    replaced; the user\'s project is never modified.\n    """\n    import shutil\n\n    if not isinstance(source_code, str) or not source_code.strip():\n        raise ValueError("Python source code is empty.")\n    if not isinstance(test_code, str) or not test_code.strip():\n        raise ValueError("Pytest test code is empty.")\n    if len(source_code) > 100000 or len(test_code) > 100000:\n        raise ValueError("Source or test code exceeds 100,000 characters.")\n\n    try:\n        ast.parse(source_code, filename=str(file_name))\n        test_tree = ast.parse(test_code, filename="test_generated.py")\n    except SyntaxError as error:\n        raise ValueError(f"Python syntax error: {error}") from error\n\n    if not any(\n        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))\n        and n.name.startswith("test_")\n        for n in ast.walk(test_tree)\n    ):\n        raise ValueError("The test file contains no test_ functions.")\n\n    module_name = get_safe_module_name(file_name)\n\n    def safe_relative(value, fallback):\n        candidate = Path(value).as_posix() if value else fallback\n        pure = Path(candidate)\n        if pure.is_absolute() or ".." in pure.parts:\n            raise ValueError("Project file path must stay inside the project folder.")\n        if pure.suffix.lower() != ".py":\n            raise ValueError("Project source and test paths must end in .py.")\n        return pure\n\n    source_relative = safe_relative(source_rel_path, f"{module_name}.py")\n    test_relative = safe_relative(test_rel_path, "tests/test_generated.py")\n\n    with tempfile.TemporaryDirectory(prefix="debugengage_coverage_") as temp_dir:\n        root = Path(temp_dir)\n\n        if project_root:\n            project = Path(project_root).resolve()\n            if not project.is_dir():\n                raise ValueError("The shared project folder no longer exists.")\n            excluded = {\n                ".git", ".venv", "venv", "env", "node_modules",\n                "__pycache__", ".pytest_cache", ".mypy_cache",\n                ".ruff_cache", "dist", "build", "htmlcov",\n            }\n            for candidate in project.rglob("*.py"):\n                relative = candidate.relative_to(project)\n                if any(part.lower() in excluded for part in relative.parts):\n                    continue\n                if candidate.is_symlink():\n                    continue\n                destination = root / relative\n                destination.parent.mkdir(parents=True, exist_ok=True)\n                shutil.copy2(candidate, destination)\n\n        source_path = root / source_relative\n        source_path.parent.mkdir(parents=True, exist_ok=True)\n        source_path.write_text(source_code, encoding="utf-8")\n\n        test_path = root / test_relative\n        test_path.parent.mkdir(parents=True, exist_ok=True)\n        test_path.write_text(test_code, encoding="utf-8")\n\n        coverage_data = root / ".coverage"\n        coverage_json = root / "coverage.json"\n        env = os.environ.copy()\n        env["COVERAGE_FILE"] = str(coverage_data)\n        old_pythonpath = env.get("PYTHONPATH", "")\n        env["PYTHONPATH"] = str(root) + (os.pathsep + old_pythonpath if old_pythonpath else "")\n\n        command = [\n            sys.executable, "-m", "coverage", "run", "--branch",\n            f"--source={module_name}", "-m", "pytest", "-q",\n            "--tb=short", "--color=no", str(test_relative),\n        ]\n        try:\n            execution = subprocess.run(\n                command, cwd=str(root), env=env, capture_output=True,\n                text=True, timeout=timeout, errors="replace",\n            )\n        except subprocess.TimeoutExpired as error:\n            raise RuntimeError(\n                f"Test execution exceeded the {timeout}-second timeout."\n            ) from error\n        except FileNotFoundError as error:\n            raise RuntimeError(\n                "Python could not start pytest/coverage. Install pytest and coverage."\n            ) from error\n\n        output = (execution.stdout or "") + "\\n" + (execution.stderr or "")\n        counts = parse_pytest_counts(output)\n\n        coverage_result = {\n            "available": False, "percent": 0.0, "covered_lines": 0,\n            "total_lines": 0, "missing_lines": [], "error": None,\n        }\n        coverage_process = subprocess.run(\n            [sys.executable, "-m", "coverage", "json", "-o", str(coverage_json)],\n            cwd=str(root), env=env, capture_output=True, text=True,\n            timeout=30, errors="replace",\n        )\n        if coverage_process.returncode == 0 and coverage_json.exists():\n            try:\n                report = json.loads(coverage_json.read_text(encoding="utf-8"))\n                file_data = next(\n                    (data for path, data in report.get("files", {}).items()\n                     if str(path).replace("\\\\\\\\", "/").endswith(source_relative.as_posix())),\n                    None,\n                )\n                if file_data is not None:\n                    summary = file_data.get("summary", {})\n                    coverage_result = {\n                        "available": True,\n                        "percent": round(float(summary.get("percent_covered", 0.0)), 2),\n                        "covered_lines": int(summary.get("covered_lines", 0)),\n                        "total_lines": int(summary.get("num_statements", 0)),\n                        "missing_lines": file_data.get("missing_lines", []),\n                        "error": None,\n                    }\n                else:\n                    coverage_result["error"] = (\n                        f"Coverage data for {source_path.as_posix()} was not found. "\n                        "Confirm that the tests import the selected source module."\n                    )\n            except (ValueError, OSError, TypeError) as error:\n                coverage_result["error"] = str(error)\n        else:\n            coverage_result["error"] = (\n                coverage_process.stderr or coverage_process.stdout\n                or "Coverage report could not be generated."\n            )\n\n        total = counts["total"]\n        return {\n            "success": (\n                execution.returncode == 0 and total > 0\n                and counts["failed"] == 0 and counts["errors"] == 0\n            ),\n            "return_code": execution.returncode,\n            "passed": counts["passed"], "failed": counts["failed"],\n            "errors": counts["errors"], "skipped": counts["skipped"],\n            "total": total,\n            "pass_percentage": round(counts["passed"] / total * 100, 2) if total else 0.0,\n            "output": output, "coverage": coverage_result,\n            "module_name": module_name,\n        }'
COMPARISON_FUNCTION = 'def run_test_comparison(\n    source_code,\n    test_code,\n    file_name="target.py",\n    timeout=60,\n    project_root=None,\n    source_rel_path=None,\n    test_rel_path=None,\n):\n    """Execute one code version with its sibling modules and the same tests."""\n    import shutil\n\n    if not isinstance(source_code, str) or not source_code.strip():\n        return {"success": False, "error": "Source code is empty."}\n    if not isinstance(test_code, str) or not test_code.strip():\n        return {"success": False, "error": "Test code is empty."}\n\n    module_name = _module_name(file_name)\n\n    def safe_relative(value, fallback):\n        candidate = Path(value) if value else Path(fallback)\n        if candidate.is_absolute() or ".." in candidate.parts:\n            raise ValueError("Project file path must stay inside the project folder.")\n        if candidate.suffix.lower() != ".py":\n            raise ValueError("Project source and test paths must end in .py.")\n        return candidate\n\n    try:\n        source_relative = safe_relative(source_rel_path, f"{module_name}.py")\n        test_relative = safe_relative(test_rel_path, "tests/test_comparison.py")\n\n        with tempfile.TemporaryDirectory(prefix="debug_compare_") as temp:\n            workspace = Path(temp)\n\n            if project_root:\n                project = Path(project_root).resolve()\n                if not project.is_dir():\n                    raise ValueError("The shared project folder no longer exists.")\n                excluded = {\n                    ".git", ".venv", "venv", "env", "node_modules",\n                    "__pycache__", ".pytest_cache", ".mypy_cache",\n                    ".ruff_cache", "dist", "build", "htmlcov",\n                }\n                for candidate in project.rglob("*.py"):\n                    relative = candidate.relative_to(project)\n                    if any(part.lower() in excluded for part in relative.parts):\n                        continue\n                    if candidate.is_symlink():\n                        continue\n                    destination = workspace / relative\n                    destination.parent.mkdir(parents=True, exist_ok=True)\n                    shutil.copy2(candidate, destination)\n\n            source_path = workspace / source_relative\n            source_path.parent.mkdir(parents=True, exist_ok=True)\n            source_path.write_text(source_code, encoding="utf-8")\n\n            test_path = workspace / test_relative\n            test_path.parent.mkdir(parents=True, exist_ok=True)\n            test_path.write_text(test_code, encoding="utf-8")\n\n            environment = os.environ.copy()\n            old_pythonpath = environment.get("PYTHONPATH", "")\n            environment["PYTHONPATH"] = (\n                str(workspace) + (os.pathsep + old_pythonpath if old_pythonpath else "")\n            )\n            command = [\n                sys.executable, "-m", "pytest", "-q", "--tb=short", "--color=no",\n                str(test_relative),\n            ]\n            process = subprocess.run(\n                command, cwd=str(workspace), env=environment,\n                capture_output=True, text=True, timeout=timeout,\n                errors="replace",\n            )\n            output = (process.stdout or "") + "\\n" + (process.stderr or "")\n            counts = _parse_results(output)\n            return {\n                "success": process.returncode == 0,\n                "return_code": process.returncode,\n                "counts": counts,\n                "output": output,\n                "module_name": module_name,\n            }\n    except subprocess.TimeoutExpired:\n        return {"success": False, "error": f"Tests exceeded the {timeout}-second time limit."}\n    except Exception as exc:\n        return {"success": False, "error": str(exc)}\n'
COMPARE_VERSIONS_FUNCTION = 'def compare_versions(\n    original_code,\n    corrected_code,\n    test_code,\n    file_name="target.py",\n    project_root=None,\n    source_rel_path=None,\n    test_rel_path=None,\n):\n    """Run identical tests against original and corrected project versions."""\n    common = {\n        "file_name": file_name,\n        "project_root": project_root,\n        "source_rel_path": source_rel_path,\n        "test_rel_path": test_rel_path,\n    }\n    original = run_test_comparison(original_code, test_code, **common)\n    corrected = run_test_comparison(corrected_code, test_code, **common)\n\n    if not original.get("counts") or not corrected.get("counts"):\n        return {\n            "success": False, "original": original, "corrected": corrected,\n            "error": "Could not compare both versions. Check the execution outputs.",\n        }\n\n    original_counts = original["counts"]\n    corrected_counts = corrected["counts"]\n    return {\n        "success": True,\n        "original": original,\n        "corrected": corrected,\n        "comparison": {\n            "passed_change": corrected_counts["passed"] - original_counts["passed"],\n            "failed_change": corrected_counts["failed"] - original_counts["failed"],\n            "original_success_rate": original_counts["success_rate"],\n            "corrected_success_rate": corrected_counts["success_rate"],\n            "improved": (\n                corrected_counts["passed"] > original_counts["passed"]\n                or corrected_counts["failed"] < original_counts["failed"]\n            ),\n        },\n    }'

if __name__ == "__main__":
    main()
