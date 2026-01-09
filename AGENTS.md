# Project Rules

## Python

### Guidelines

When fixing type errors, writing any new code, or modifying exsiting code:

1. No `Any` typing -- if absolutely necessary, ensure the case for its use is presented to the user.
2. No use of `cast()`
3. No use of `object` as a type.
4. No use of `object.__setattr__` or `__dict__`
5. No use of `hasattr`
6. Use `getattr` only when necessary — prefer accessing using dot notation or .get().
7. Whenever possible, use dot notation instead of square brackets to access attributes.
8. No string/byte annotations.
9. For Pydantic `model_config`, use frozen and disallow extra whenever possible.
10. For Pydantic, never use SkipValidation.
11. Do not create new Protocol types.
12. Do not use reserved Python keywords or function names.
13. Type annotations and aliases should follow guidelines for Python v3.13.9.
