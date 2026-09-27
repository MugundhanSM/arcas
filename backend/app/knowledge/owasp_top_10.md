# OWASP Top 10 (2021)

## A01 Broken Access Control
Enforce authorization server-side on every request. Deny by default. Prevent
IDOR, path traversal and privilege escalation.

## A02 Cryptographic Failures
Use strong, up-to-date algorithms (AES-GCM, SHA-256+). Encrypt data in transit
(TLS) and at rest. Never disable certificate verification.

## A03 Injection
Use parameterized queries and safe APIs. Validate and encode all untrusted
input. Covers SQL, command, LDAP and template injection.

## A04 Insecure Design
Apply threat modelling and secure design patterns. Validate input at trust
boundaries; fail securely.

## A05 Security Misconfiguration
Harden defaults, disable debug in production, manage secrets securely, and keep
configurations consistent across environments.

## A06 Vulnerable and Outdated Components
Track dependencies, patch promptly, and remove unused libraries.

## A07 Identification and Authentication Failures
Use strong authentication, secure session management and protection against
credential stuffing and brute force.

## A08 Software and Data Integrity Failures
Verify integrity of updates and serialized data. Avoid unsafe deserialization
and untrusted CI/CD inputs.

## A09 Security Logging and Monitoring Failures
Log security-relevant events, monitor for anomalies, and avoid logging
sensitive data.

## A10 Server-Side Request Forgery (SSRF)
Validate and allow-list outbound URLs; block internal/metadata endpoints.