# Contributing Guide

## Development Setup

### Prerequisites

- Python 3.11+
- Git
- Virtual environment (recommended)

### Initial Setup

```bash
# Clone the repository
git clone <repo-url>
cd stonks-trading

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"
```

## Pre-Commit Hooks

We use **pre-commit** hooks to ensure code quality before committing. These hooks run:

- **Ruff** - Fast Python linter and formatter
- **MyPy** - Static type checking
- **General checks** - JSON/YAML validation, trailing whitespace, etc.

### Option 1: Using Pre-Commit Framework (Recommended)

```bash
# Install pre-commit hooks
pre-commit install

# Test hooks on all files
pre-commit run --all-files
```

The hooks will now run automatically on every `git commit`.

### Option 2: Using Simple Bash Hook

If you prefer not to use the pre-commit framework:

```bash
# Copy the hook to .git/hooks
cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### Skipping Hooks (Emergency Only)

If you need to bypass hooks in exceptional circumstances:

```bash
git commit --no-verify -m "Your message"
```

**Note:** This is discouraged. Fix the issues instead.

## Code Quality Standards

### Linting and Formatting

We use **Ruff** for both linting and formatting:

```bash
# Check for linting issues
ruff check src/stonks_trading

# Auto-fix linting issues
ruff check src/stonks_trading --fix

# Check formatting
ruff format --check src/stonks_trading

# Apply formatting
ruff format src/stonks_trading
```

### Type Checking

We use **MyPy** with strict mode:

```bash
# Type check all source files
mypy src/stonks_trading --strict

# Type check specific files
mypy src/stonks_trading/domains/trading/repositories.py --strict
```

### Testing

Run tests with coverage:

```bash
# Run all tests
pytest

# Run with coverage (repositories and use cases only)
pytest --cov=stonks_trading.domains.trading.repositories \
       --cov=stonks_trading.domains.trading.use_cases \
       --cov-fail-under=80

# Run specific test file
pytest tests/parity/test_neat_main_py_parity.py -v
```

## Commit Message Guidelines

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters
- Reference issues and PRs where appropriate

Example:
```
Add validation for transaction fee rate

- Ensure fee_rate is between 0 and 0.01
- Add unit tests for edge cases
- Fixes #123
```

## Pull Request Process

1. Ensure all tests pass
2. Ensure code coverage for repositories/use cases is ≥80%
3. Ensure mypy passes with `--strict`
4. Ensure ruff passes with no warnings
5. Update documentation if needed
6. Request review from 1 team member

## Phase 1 Success Criteria

Before marking Phase 1 complete:

- [ ] All pattern compliance checks pass
- [ ] Parity tests pass (extracted code matches NEAT/main.py)
- [ ] 93% coverage on repositories and use cases
- [ ] MyPy passes with `--strict`
- [ ] Ruff passes with no warnings
- [ ] Pre-commit hooks installed and working
