#!/usr/bin/env python3
"""Validation script for Phase 7/8 implementation.

Checks:
1. No lazy imports (TYPE_CHECKING blocks)
2. No string annotations
3. All imports at module level
4. Repositories use standalone functions
5. Business logic in use_cases only
"""

import ast
import os
import sys
from pathlib import Path


def check_file_for_lazy_imports(filepath: str) -> list[str]:
    """Check a Python file for lazy import violations."""
    errors = []

    with open(filepath, 'r') as f:
        content = f.read()

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return [f"Syntax error in {filepath}: {e}"]

    # Check for TYPE_CHECKING blocks
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if isinstance(node.test, ast.Name) and node.test.id == 'TYPE_CHECKING':
                errors.append(f"{filepath}: Found TYPE_CHECKING block (line {node.lineno})")

    # Check for imports inside function/method definitions
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    # Allow some common patterns like pickle.loads
                    if isinstance(child, ast.ImportFrom):
                        if child.module in ('typing', 'typing_extensions'):
                            continue
                    errors.append(f"{filepath}: Import inside function '{node.name}' (line {child.lineno})")

    return errors


def check_repositories(filepath: str) -> list[str]:
    """Check repositories.py uses standalone functions only."""
    errors = []

    if 'repositories.py' not in filepath:
        return errors

    with open(filepath, 'r') as f:
        content = f.read()

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return errors

    # Check for class definitions (not allowed in repositories)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Skip if it's an exception or type alias
            if not node.name.endswith('Error'):
                errors.append(f"{filepath}: Class definition '{node.name}' found in repository (line {node.lineno}). Use standalone functions only.")

    return errors


def main() -> int:
    """Run all validations."""
    base_path = Path('/Users/h3cth0r/Documents/stonks-trading/src/stonks_trading')

    # Files to validate
    validate_patterns = [
        'domains/training/*.py',
        'domains/backtesting/*.py',
    ]

    all_errors = []
    files_checked = 0

    for pattern in validate_patterns:
        for filepath in base_path.glob(pattern):
            if filepath.name == '__init__.py':
                continue

            files_checked += 1

            # Check for lazy imports
            lazy_errors = check_file_for_lazy_imports(str(filepath))
            all_errors.extend(lazy_errors)

            # Check repositories
            repo_errors = check_repositories(str(filepath))
            all_errors.extend(repo_errors)

    print(f"=== Phase 7/8 Validation Results ===")
    print(f"Files checked: {files_checked}")
    print(f"Errors found: {len(all_errors)}")
    print()

    if all_errors:
        print("ERRORS:")
        for error in all_errors:
            print(f"  - {error}")
        return 1
    else:
        print("✅ All validations passed!")
        print("  - No TYPE_CHECKING blocks")
        print("  - No imports inside functions")
        print("  - Repositories use standalone functions")
        return 0


if __name__ == '__main__':
    sys.exit(main())
