---
name: code_review
description: "Perform comprehensive code reviews focused on code quality, error handling, testing, documentation, and actionable feedback. When deeper verification is needed, consider using a subagent with the tester role to inspect test coverage, run focused checks, or validate risky changes."
---

# Code Review Skill

## Purpose
Perform comprehensive code reviews to ensure quality, readability, and maintainability.

## Review Checklist

### 1. Code Quality
- [ ] Clear and descriptive variable/function names
- [ ] Proper function decomposition (single responsibility)
- [ ] Avoid code duplication
- [ ] Appropriate comments where necessary
- [ ] Consistent coding style

### 2. Error Handling
- [ ] Proper exception handling
- [ ] Input validation
- [ ] Edge case consideration
- [ ] Meaningful error messages

### 3. Testing
- [ ] Unit tests exist for new functionality
- [ ] Tests cover edge cases
- [ ] All existing tests pass
- [ ] Test descriptions are clear

### 4. Documentation
- [ ] Docstrings for public functions/classes
- [ ] README updates if needed
- [ ] Examples for complex functionality

## Review Process

1. **Read the code** to understand what it does
2. **Check against the checklist** above
3. **Suggest improvements** with specific examples
4. **Ask questions** about unclear parts
5. **Provide constructive feedback** that helps the developer learn

## Common Issues to Look For

- Magic numbers without explanation
- Overly complex functions that do too much
- Missing error handling
- Inconsistent naming conventions
- Unused imports or variables
- Hardcoded paths or configurations
- Lack of type hints (for Python)

## Feedback Format

When providing review feedback:
1. Start with what's done well
2. Then suggest improvements
3. Provide specific code examples when possible
4. Explain the reasoning behind suggestions
