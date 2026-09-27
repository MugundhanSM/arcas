# Java Secure Coding Guidelines

## SQL Injection
Use `PreparedStatement` with bound parameters for all database queries.
Never concatenate user input into SQL strings. (OWASP A03: Injection)

## Command Injection
Avoid `Runtime.exec()` / `ProcessBuilder` with untrusted input. Use strict
allow-lists and avoid shell interpretation. (OWASP A03)

## Input Validation
Validate all external input at the boundary using allow-lists and bean
validation. (OWASP A04: Insecure Design)

## Cryptography
Use vetted libraries; avoid MD5/SHA1 and ECB mode. Use AES-GCM and strong
key management. (OWASP A02: Cryptographic Failures)

## Secrets Management
Do not hardcode passwords or keys. Use a secrets vault or environment
configuration. (OWASP A05: Security Misconfiguration)

## Deserialization
Avoid native Java deserialization of untrusted data. Use safe formats (JSON)
and object input filters. (OWASP A08: Software & Data Integrity Failures)

## Access Control & Least Privilege
Enforce least privilege; check authorization on every sensitive operation.
(OWASP A01: Broken Access Control)

## Sensitive Data & Error Handling
Protect sensitive data in transit (TLS) and at rest. Handle exceptions
securely without leaking internal details. (OWASP A09: Logging Failures)

## SSRF
Validate outbound request targets and block internal network ranges.
(OWASP A10: SSRF)