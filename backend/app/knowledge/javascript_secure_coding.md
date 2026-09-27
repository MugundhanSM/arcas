# JavaScript / TypeScript Secure Coding Guidelines

## Injection & XSS
Never build HTML with untrusted input; use safe DOM APIs and framework
escaping. Avoid `innerHTML` with user data. (OWASP A03: Injection)

## Code Execution
Never use `eval()`, `new Function()`, or pass strings to `setTimeout`.
(OWASP A03)

## Command Injection (Node)
Avoid `child_process.exec` with untrusted input; prefer `execFile`/`spawn`
with an argument array and `shell: false`. (OWASP A03)

## Prototype Pollution
Validate object keys; avoid unsafe recursive merge of untrusted objects.
Guard against `__proto__` / `constructor` keys. (OWASP A08)

## Secrets Management
Never commit API keys or tokens. Use environment variables and a secrets
manager. (OWASP A05: Security Misconfiguration)

## Input Validation
Validate all external input with a schema validator (e.g. zod, Joi).
(OWASP A04: Insecure Design)

## Dependencies
Audit dependencies (`npm audit`) and pin versions. (OWASP A06)

## SSRF & Requests
Validate and allow-list outbound URLs; never disable TLS verification.
(OWASP A10: SSRF, A02)
