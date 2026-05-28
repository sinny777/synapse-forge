# Coding Style Guide - Synapse Forge

This document outlines the coding standards and best practices for the Synapse Forge project. All contributors must follow these guidelines to ensure consistency and maintainability.

## Table of Contents

- [Task Verification Requirements](#task-verification-requirements)
- [Frontend Development](#frontend-development)
- [Backend Development](#backend-development)
- [General Python Guidelines](#general-python-guidelines)
- [Code Quality](#code-quality)
- [Testing](#testing)
- [Documentation](#documentation)

## Task Verification Requirements

**MANDATORY**: Before marking any task as complete, you MUST verify that the implementation meets all user requirements.

### Verification Checklist

1. **Requirements Validation**
   - Review all requirements specified by the user in the task description
   - Ensure every requirement has been addressed in the implementation
   - Verify that no requirements have been missed or partially implemented
   - Check that the implementation matches the expected behavior

2. **Browser-Based Verification (When Applicable)**
   - **ALWAYS use browser_action tool** to verify frontend and full-stack implementations
   - Launch the application in an internal browser session
   - Test all implemented features interactively
   - Verify UI components render correctly with Carbon Design System
   - Test user interactions (clicks, form submissions, navigation)
   - Check responsive design across different viewport sizes
   - Verify API integrations work end-to-end

3. **Backend Verification**
   - Test API endpoints using browser_action or execute_command (curl/httpie)
   - Verify request/response payloads match specifications
   - Check error handling and edge cases
   - Validate database operations if applicable
   - Ensure proper HTTP status codes are returned

4. **Integration Testing**
   - When both frontend and backend changes are made, verify the complete flow
   - Test data flow from UI → API → Database → API → UI
   - Verify error messages display correctly in the UI
   - Check loading states and async operations

5. **Code Review**
   - Verify code follows all coding standards in this guide
   - Check that Carbon components are used (frontend)
   - Verify FastAPI patterns are followed (backend)
   - Ensure proper error handling and logging

### Verification Process

```
BEFORE marking task complete:
1. ✅ Read and understand ALL user requirements
2. ✅ Implement the solution
3. ✅ Use browser_action to test the application (if UI involved)
4. ✅ Test API endpoints (if backend involved)
5. ✅ Verify all requirements are met
6. ✅ Document any deviations or limitations
7. ✅ Only then use attempt_completion
```

### Example Verification Flow

```python
# After implementing a new feature:

# 1. Start the application
<execute_command>
<command>cd backend && python main.py</command>
</execute_command>

# 2. Launch browser and verify
<browser_action>
<action>launch</action>
<url>http://localhost:4200</url>
</browser_action>

# 3. Test the feature interactively
<browser_action>
<action>click</action>
<coordinate>x,y@widthxheight</coordinate>
</browser_action>

# 4. Verify expected behavior
# 5. Take screenshots to confirm
# 6. Only then attempt_completion
```

### When Browser Verification is Required

- ✅ Any frontend UI changes or new components
- ✅ Full-stack features involving both frontend and backend
- ✅ Form submissions and data validation
- ✅ Navigation and routing changes
- ✅ Visual design or layout modifications
- ✅ Integration with external APIs or services
- ✅ Authentication and authorization flows

### When Browser Verification is Optional

- ❌ Pure backend API changes with no UI impact
- ❌ Database schema modifications
- ❌ Configuration file updates
- ❌ Documentation-only changes
- ❌ Unit test additions

**IMPORTANT**: Never mark a task complete without verification. If verification reveals issues, fix them before attempting completion.

## Frontend Development

### IBM Carbon Design System

**MANDATORY**: All frontend development MUST use IBM Carbon Design Angular components.

#### Core Principles

1. **Component Usage**
   - Use Carbon Angular components for ALL UI elements (buttons, inputs, modals, tables, etc.)
   - Never create custom components that duplicate Carbon functionality
   - Leverage the Carbon MCP tool for implementation guidance and best practices

2. **Design System Consistency**
   - Use Carbon Design System icons exclusively
   - Apply Carbon themes and color tokens
   - Follow Carbon spacing and layout guidelines
   - Maintain Carbon typography standards

3. **Accessibility**
   - Follow Carbon's built-in accessibility features
   - Ensure WCAG 2.1 AA compliance
   - Test with screen readers and keyboard navigation
   - Use proper ARIA labels and semantic HTML

4. **Responsive Design**
   - Use Carbon's grid system for layouts
   - Implement mobile-first responsive patterns
   - Test across different screen sizes and devices

#### Angular Best Practices

- Use Angular CLI for generating components, services, and modules
- Follow Angular style guide (https://angular.io/guide/styleguide)
- Use TypeScript with strict mode enabled
- Implement lazy loading for feature modules
- Use RxJS operators efficiently and avoid memory leaks
- Follow component-based architecture with smart/dumb component pattern
- Use Angular services for business logic and state management
- Implement proper change detection strategies

#### Code Structure

```typescript
// Example: Using Carbon components
import { ButtonModule } from '@carbon/angular';

@Component({
  selector: 'app-example',
  template: `
    <button ibmButton="primary" (click)="handleClick()">
      Submit
    </button>
  `
})
export class ExampleComponent {
  handleClick(): void {
    // Implementation
  }
}
```

#### Testing

- Write unit tests using Jasmine/Karma
- Aim for >80% code coverage
- Test component interactions and edge cases
- Use TestBed for component testing
- Mock services and dependencies appropriately

## Backend Development

### FastAPI Framework

**MANDATORY**: All Python backend development MUST use FastAPI.

#### Core Principles

1. **API Design**
   - Use RESTful conventions for endpoint design
   - Implement proper HTTP methods (GET, POST, PUT, DELETE, PATCH)
   - Use appropriate HTTP status codes
   - Version your APIs (e.g., `/api/v1/`)

2. **Request/Response Handling**
   - Use Pydantic models for all request and response schemas
   - Implement proper validation with Pydantic validators
   - Use FastAPI's automatic documentation features
   - Handle file uploads and downloads appropriately

3. **Async Operations**
   - Use `async`/`await` for I/O-bound operations
   - Leverage FastAPI's async capabilities for better performance
   - Use async database operations with SQLAlchemy
   - Implement proper connection pooling

4. **Error Handling**
   - Create custom exception classes
   - Use FastAPI's HTTPException for API errors
   - Implement global exception handlers
   - Return consistent error response formats

#### Code Structure

```python
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional

app = FastAPI(
    title="Synapse Forge API",
    description="API for Synapse Forge platform",
    version="1.0.0"
)

class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    price: float = Field(..., gt=0)

class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float

    class Config:
        from_attributes = True

@app.post("/api/v1/items", response_model=ItemResponse, status_code=201)
async def create_item(item: ItemCreate) -> ItemResponse:
    """
    Create a new item.
    
    Args:
        item: Item creation data
        
    Returns:
        Created item with ID
        
    Raises:
        HTTPException: If item creation fails
    """
    try:
        # Implementation
        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### Database Operations

- Use SQLAlchemy ORM for database interactions
- Implement async database sessions
- Use dependency injection for database sessions
- Create proper database models with relationships
- Implement database migrations using Alembic
- Use connection pooling for better performance

#### Authentication & Authorization

- Implement JWT-based authentication
- Use OAuth2 with Password flow for token generation
- Implement role-based access control (RBAC)
- Secure sensitive endpoints with proper dependencies
- Hash passwords using bcrypt or similar

#### Testing

- Write unit tests using pytest
- Use pytest-asyncio for async tests
- Implement integration tests for API endpoints
- Use TestClient for endpoint testing
- Mock external dependencies
- Aim for >80% code coverage

## General Python Guidelines

### Code Style

1. **PEP 8 Compliance**
   - Follow PEP 8 style guide strictly
   - Use 4 spaces for indentation
   - Maximum line length: 100 characters
   - Use snake_case for functions and variables
   - Use PascalCase for classes

2. **Type Hints**
   - Use type hints for all function parameters and return values
   - Use `typing` module for complex types
   - Enable mypy strict mode for type checking

```python
from typing import List, Dict, Optional, Union

def process_data(
    items: List[Dict[str, Union[str, int]]],
    filter_key: Optional[str] = None
) -> List[Dict[str, Union[str, int]]]:
    """Process and filter data items."""
    if filter_key:
        return [item for item in items if filter_key in item]
    return items
```

3. **Docstrings**
   - Use Google-style or NumPy-style docstrings
   - Document all public functions, classes, and modules
   - Include parameter descriptions, return values, and exceptions

```python
def calculate_total(items: List[float], tax_rate: float = 0.1) -> float:
    """
    Calculate total price including tax.
    
    Args:
        items: List of item prices
        tax_rate: Tax rate as decimal (default: 0.1 for 10%)
        
    Returns:
        Total price including tax
        
    Raises:
        ValueError: If tax_rate is negative
        
    Example:
        >>> calculate_total([10.0, 20.0], 0.1)
        33.0
    """
    if tax_rate < 0:
        raise ValueError("Tax rate cannot be negative")
    subtotal = sum(items)
    return subtotal * (1 + tax_rate)
```

### Design Patterns

- Follow SOLID principles
- Use dependency injection
- Implement factory patterns for object creation
- Use repository pattern for data access
- Apply strategy pattern for interchangeable algorithms
- Use singleton pattern sparingly and appropriately

### Error Handling

- Use specific exception types
- Create custom exception classes when needed
- Always clean up resources (use context managers)
- Log exceptions with proper context
- Never use bare `except:` clauses

```python
class DataProcessingError(Exception):
    """Custom exception for data processing errors."""
    pass

def process_file(filepath: str) -> Dict[str, any]:
    """Process file and return data."""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        return process_data(data)
    except FileNotFoundError:
        logger.error(f"File not found: {filepath}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        raise DataProcessingError(f"Failed to parse {filepath}")
    except Exception as e:
        logger.exception(f"Unexpected error processing {filepath}")
        raise
```

### Logging

- Use Python's `logging` module
- Configure appropriate log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Include contextual information in log messages
- Use structured logging for production environments
- Never log sensitive information (passwords, tokens, PII)

```python
import logging

logger = logging.getLogger(__name__)

def process_user_data(user_id: int) -> None:
    """Process user data."""
    logger.info(f"Processing data for user {user_id}")
    try:
        # Processing logic
        logger.debug(f"Data processed successfully for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to process data for user {user_id}: {e}", exc_info=True)
        raise
```

## Code Quality

### Formatting Tools

- **Black**: Automatic code formatting
  ```bash
  black . --line-length 100
  ```

- **isort**: Import sorting
  ```bash
  isort . --profile black
  ```

### Linting Tools

- **mypy**: Static type checking
  ```bash
  mypy . --strict
  ```

- **pylint**: Code analysis
  ```bash
  pylint **/*.py
  ```

- **flake8**: Style guide enforcement
  ```bash
  flake8 . --max-line-length 100
  ```

### Pre-commit Hooks

Configure pre-commit hooks to run formatting and linting automatically:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        args: [--line-length=100]
  
  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: [--profile=black]
  
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.3.0
    hooks:
      - id: mypy
        args: [--strict]
```

## Testing

### Test Coverage

- Maintain minimum 80% code coverage
- Write tests before or alongside code (TDD approach)
- Test edge cases and error conditions
- Use meaningful test names that describe what is being tested

### Test Structure

```python
import pytest
from fastapi.testclient import TestClient

class TestItemAPI:
    """Test suite for Item API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    def test_create_item_success(self, client):
        """Test successful item creation."""
        response = client.post(
            "/api/v1/items",
            json={"name": "Test Item", "price": 10.0}
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Test Item"
    
    def test_create_item_invalid_price(self, client):
        """Test item creation with invalid price."""
        response = client.post(
            "/api/v1/items",
            json={"name": "Test Item", "price": -10.0}
        )
        assert response.status_code == 422
```

## Documentation

### Code Documentation

- Document all public APIs
- Include usage examples in docstrings
- Keep documentation up-to-date with code changes
- Use clear and concise language

### API Documentation

- Leverage FastAPI's automatic documentation
- Add detailed descriptions to endpoints
- Document request/response schemas
- Include example requests and responses
- Document error responses

### Project Documentation

- Maintain up-to-date README.md
- Document setup and installation procedures
- Provide usage examples and tutorials
- Document architecture and design decisions
- Keep CHANGELOG.md updated

## Summary

These coding standards ensure:
- **Consistency**: Uniform code style across the project
- **Quality**: High-quality, maintainable code
- **Efficiency**: Faster development with established patterns
- **Collaboration**: Easier code reviews and team collaboration
- **Maintainability**: Code that is easy to understand and modify

All contributors must adhere to these guidelines. Code that does not follow these standards will not be accepted in pull requests.

## Resources

- [IBM Carbon Design System](https://carbondesignsystem.com/)
- [Carbon Angular Components](https://angular.carbondesignsystem.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Angular Style Guide](https://angular.io/guide/styleguide)
- [PEP 8 Style Guide](https://pep8.org/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)