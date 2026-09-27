# Clean Code & Refactoring Principles

Curated guidance used by the refactoring and review agents to ground their
recommendations. Derived from widely accepted software-engineering practice
(Martin Fowler's *Refactoring*, Robert C. Martin's *Clean Code*, and the
SOLID principles).

## Naming

- Use intention-revealing names. A name should answer why it exists, what it
  does, and how it is used.
- Avoid disinformation and meaningless distinctions (`data1`, `data2`).
- Class names should be nouns; method names should be verbs.
- Pick one word per concept (`fetch`, `get`, `retrieve` — choose one).

## Functions

- Functions should be small and do one thing at one level of abstraction.
- Prefer fewer arguments. Three or more arguments is a smell; consider an
  argument object.
- Avoid flag arguments; they signal a function doing more than one thing.
- Command/Query separation: a function should either do something or answer
  something, not both.
- Avoid side effects that are not implied by the function name.

## Comments

- Prefer self-explanatory code over comments. Comments should explain *why*,
  not *what*.
- Delete commented-out code; version control already remembers it.
- Keep comments close to the code they describe and update them together.

## Error Handling

- Use exceptions rather than return codes for exceptional conditions.
- Don't return or pass `null`/`None` where a value is expected; prefer empty
  collections or optionals.
- Fail fast and provide context in error messages.

## SOLID Principles

- **S**ingle Responsibility: a class should have one reason to change.
- **O**pen/Closed: open for extension, closed for modification.
- **L**iskov Substitution: subtypes must be substitutable for their base
  types.
- **I**nterface Segregation: prefer many small, client-specific interfaces.
- **D**ependency Inversion: depend on abstractions, not concretions.

## Common Refactorings

- **Extract Function**: turn a fragment into a named function.
- **Inline Function/Variable**: remove needless indirection.
- **Rename Variable/Field**: improve clarity.
- **Replace Magic Number with Named Constant**.
- **Decompose Conditional**: extract the condition and branches into
  well-named functions.
- **Replace Nested Conditional with Guard Clauses** to reduce nesting.
- **Replace Temp with Query** to remove mutable local state.
- **Introduce Parameter Object** to group related arguments.
- **Replace Conditional with Polymorphism** for type-based branching.

## Code Smells

- Long Method, Large Class, Long Parameter List.
- Duplicated Code (apply the Rule of Three before extracting).
- Feature Envy: a method more interested in another class than its own.
- Data Clumps: groups of variables that always travel together.
- Primitive Obsession: using primitives instead of small value objects.
- Shotgun Surgery: one change forces many small edits across classes.
