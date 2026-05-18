#!/bin/bash
# Simple pre-commit hook for ruff and mypy
# Copy this to .git/hooks/pre-commit and make it executable
# chmod +x .git/hooks/pre-commit

set -e

echo "🔍 Running pre-commit checks..."

# Get list of staged Python files
STAGED_PY_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true)

if [ -z "$STAGED_PY_FILES" ]; then
    echo "✅ No Python files staged. Skipping checks."
    exit 0
fi

echo "📁 Checking files:"
echo "$STAGED_PY_FILES"
echo ""

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run Ruff linter
echo "🔧 Running Ruff linter..."
if ! echo "$STAGED_PY_FILES" | xargs ruff check; then
    echo "❌ Ruff linting failed. Fix errors before committing."
    exit 1
fi

# Run Ruff format check
echo "🎨 Running Ruff format check..."
if ! echo "$STAGED_PY_FILES" | xargs ruff format --check; then
    echo "❌ Ruff formatting check failed. Run 'ruff format' to fix."
    exit 1
fi

# Run MyPy on source files (not tests)
echo "📋 Running MyPy type checker..."
if ! mypy src/stonks_trading --strict --ignore-missing-imports 2>/dev/null; then
    echo "❌ MyPy type checking failed. Fix type errors before committing."
    exit 1
fi

echo ""
echo "✅ All pre-commit checks passed!"
exit 0
