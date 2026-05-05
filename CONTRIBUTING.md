# Contributing to NeuralToolRouter

Thank you for your interest in contributing to NeuralToolRouter! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for all contributors.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/neural-tool-router.git`
3. Add upstream remote: `git remote add upstream https://github.com/ORIGINAL_OWNER/neural-tool-router.git`

## Development Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and add your API keys:
   ```bash
   cp .env.example .env
   ```

4. Run tests to ensure everything works:
   ```bash
   pytest
   ```

## Making Changes

1. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following the [coding standards](#coding-standards)

3. Add tests for new functionality

4. Run tests and linting:
   ```bash
   pytest
   black .
   mypy .
   ```

5. Commit your changes with clear, descriptive messages:
   ```bash
   git commit -m "Add feature: description of your changes"
   ```

## Testing

- Write unit tests for new functionality
- Ensure all tests pass before submitting
- Aim for high test coverage
- Test with different configurations

Run tests:
```bash
pytest
pytest --cov=. --cov-report=html  # With coverage report
```

## Submitting Changes

1. Push your changes to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Create a Pull Request (PR) from your fork to the main repository

3. In your PR description:
   - Describe the changes you made
   - Reference any related issues
   - Include screenshots for UI changes
   - List any breaking changes

4. Wait for review and address any feedback

## Coding Standards

### Python Style

- Follow PEP 8 guidelines
- Use type hints for function parameters and return values
- Write docstrings for all public functions and classes
- Use meaningful variable and function names

### Code Formatting

- Use `black` for code formatting
- Use `mypy` for type checking
- Maximum line length: 100 characters

### Documentation

- Update README.md if you add new features
- Add docstrings to new functions and classes
- Update relevant documentation files

### Commit Messages

- Use clear, descriptive commit messages
- Start with a verb in present tense (e.g., "Add", "Fix", "Update")
- Reference issue numbers when applicable

Example:
```
Add hybrid retrieval support for Phase 2

- Implement BM25 + Dense retrieval
- Add RRF (Reciprocal Rank Fusion)
- Update documentation

Fixes #123
```

## Project Structure

```
neural-tool-router/
├── config.py              # Configuration management
├── mcp_client.py          # MCP server client
├── phase1_generator.py    # Synthetic data generation
├── phase2_trainer.py      # Model training
├── phase3_runtime.py      # Runtime agentic loop
├── data/                  # Data files
├── models/                # Trained models
├── logs/                  # Log files
├── examples/              # Example implementations
└── docs/                  # Documentation
```

## Areas for Contribution

- **New Features**: Implement new retrieval strategies, tool types, or integrations
- **Bug Fixes**: Fix reported issues
- **Documentation**: Improve or expand documentation
- **Tests**: Add or improve test coverage
- **Examples**: Create example implementations
- **Performance**: Optimize existing code

## Questions?

If you have questions or need help, please:
- Open an issue for discussion
- Check existing issues and documentation
- Reach out to maintainers

Thank you for contributing to NeuralToolRouter!