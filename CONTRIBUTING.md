# Contributing to odoo-mcp-multi

First off, thank you for considering contributing to `odoo-mcp-multi`. It's people like you that make open-source software such a great community!

## 1. Where do I go from here?

If you've noticed a bug or have a feature request, make sure to check our **Issues** first. If the issue doesn't already exist, feel free to open a new one. Provide as much detail as possible to help us understand and resolve the problem.

## 2. Setting up your environment

1. Fork the repository and clone your fork locally.
2. Ensure you have Python 3.10+ installed.
3. Install the project along with its development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

## 3. Making Changes

- Create a new branch for your feature or bug fix: `git checkout -b feature/your-feature-name`
- Write tests for your changes where applicable.
- Make your changes in the codebase.

## 4. Code Quality and Testing

We strictly enforce clean code through `ruff` and test coverage via `pytest`.

Before submitting a Merge Request, you must ensure all checks pass:

```bash
# 1. Check for syntax and style errors
ruff check odoo_mcp_multi/ tests/

# 2. Auto-format your code
ruff format odoo_mcp_multi/ tests/

# 3. Run the complete test suite
pytest
```

> **Note:** The CI pipeline will automatically block Merge Requests that fail formatting, linting, or tests.

## 5. Submitting a Merge Request

1. Push your branch to your remote fork: `git push origin feature/your-feature-name`
2. Open a Merge Request against the `main` branch of this repository.
3. Ensure the MR description clearly describes what the change does and references any related active Issues.
4. Wait for the CI pipeline to execute and address any feedback provided by the maintainers during code review.
