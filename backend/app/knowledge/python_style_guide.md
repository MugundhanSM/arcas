# Python Style Guide (PEP 8 & Google Highlights)

Reference material used by the documentation, metrics and refactoring agents
to ground Python-specific recommendations. Summarised from PEP 8 and the
Google Python Style Guide.

## Layout

- Indent with 4 spaces; never mix tabs and spaces.
- Limit lines to 79 characters (72 for docstrings/comments). Many teams use
  88 or 100; be consistent within a project.
- Surround top-level function and class definitions with two blank lines;
  method definitions inside a class with one blank line.
- Imports at the top, grouped: standard library, third party, local; each
  group separated by a blank line. One import per line.

## Naming Conventions

- `lower_case_with_underscores` for functions, methods, variables, modules.
- `CapWords` (PascalCase) for classes.
- `UPPER_CASE_WITH_UNDERSCORES` for constants.
- Prefix non-public attributes with a single underscore `_internal`.
- Avoid single-character names except for counters/iterators.

## Docstrings

- Every public module, class and function should have a docstring.
- Use triple double-quotes. First line is a concise summary in imperative
  mood ("Return the sum", not "Returns the sum").
- For functions, document Args, Returns, and Raises (Google style):

```python
def divide(a: float, b: float) -> float:
    """Divide a by b.

    Args:
        a: The numerator.
        b: The denominator; must be non-zero.

    Returns:
        The quotient a / b.

    Raises:
        ZeroDivisionError: If b is zero.
    """
```

## Idioms & Best Practices

- Prefer `is` / `is not` when comparing to `None`.
- Use truthiness (`if seq:`) rather than `len(seq) == 0`.
- Use context managers (`with open(...) as f:`) for resources.
- Prefer list/dict/set comprehensions over manual loops where readable.
- Use f-strings for formatting over `%` and `.format()`.
- Catch specific exceptions, never a bare `except:`.
- Use `enumerate` instead of manual index counters; `zip` to iterate in
  parallel.
- Type-annotate public function signatures.

## Anti-patterns to Flag

- Mutable default arguments (`def f(x=[])`).
- Wildcard imports (`from module import *`).
- Bare `except:` that swallows all errors including `KeyboardInterrupt`.
- Manual string concatenation in loops (use `str.join`).
- Comparing types with `==` instead of `isinstance`.
