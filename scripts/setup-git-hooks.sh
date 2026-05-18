#!/bin/bash
# Setup script for git hooks and initial repository configuration
# Run this after initializing a git repository

set -e

echo "🔧 Setting up git hooks for stonks-trading..."

# Check if git repo exists
if [ ! -d ".git" ]; then
    echo "❌ Not a git repository. Initialize first with: git init"
    exit 1
fi

# Check if virtual environment is active
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -f ".venv/bin/activate" ]; then
        echo "📦 Activating virtual environment..."
        source .venv/bin/activate
    else
        echo "⚠️  Warning: No virtual environment found. Install dependencies first:"
        echo "   python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'"
    fi
fi

# Install pre-commit framework
echo "📥 Installing pre-commit..."
pip install pre-commit

# Install pre-commit hooks
echo "🔗 Installing pre-commit hooks..."
pre-commit install

echo ""
echo "✅ Pre-commit hooks installed successfully!"
echo ""
echo "Hooks will now run automatically on every commit."
echo "To run manually: pre-commit run --all-files"
echo "To skip (emergency only): git commit --no-verify"
echo ""
echo "📋 Installed hooks:"
echo "   - Ruff (linting & formatting)"
echo "   - MyPy (type checking)"
echo "   - General file checks"
