# Python Secure Coding Guidelines

## Command Injection
Never use `shell=True` with untrusted input in `subprocess`. Prefer passing
an argument list (e.g. `subprocess.run(["ls", "-l"], shell=False)`). Avoid
`os.system`. (OWASP A03: Injection)

## SQL Injection
Always use parameterized queries / bound parameters. Never build SQL with
string concatenation or f-strings from user input. (OWASP A03)

## Code Execution
Never call `eval()`, `exec()`, or `compile()` on untrusted input. Avoid
`pickle.load`/`pickle.loads` on untrusted data; prefer `json`. (OWASP A08)

## Input Validation
Validate and sanitise all external input at the boundary. Use allow-lists,
type checks and length limits. (OWASP A04: Insecure Design)

## Secrets Management
Never hardcode credentials, API keys or tokens. Load secrets from environment
variables or a secrets manager. (OWASP A05: Security Misconfiguration)

## Cryptography
Do not use MD5 or SHA1 for security. Use SHA-256+ and `secrets` for tokens.
Never set `verify=False` on TLS requests. (OWASP A02: Cryptographic Failures)

## Deserialization
Avoid `yaml.load` without `SafeLoader`; use `yaml.safe_load`. (OWASP A08)

## Least Privilege & Error Handling
Run with least privilege. Do not leak stack traces or secrets in error
responses. Log security events without logging sensitive data. (OWASP A09)

## Path Traversal
Normalise and validate file paths; reject `..` segments. Never join untrusted
input directly into filesystem paths. (OWASP A01: Broken Access Control)

## SSRF
Validate and allow-list outbound URLs; block internal address ranges.
(OWASP A10: SSRF)