You are performing a focused security and code quality audit on: $ARGUMENTS

Run these steps in order:

1. **Static analysis** — Run all available tools on the target:
   - `bandit -r <target> -c pyproject.toml -f json` — Python security scan. Parse the JSON output for real findings.
   - `python -m mypy <target> --config-file pyproject.toml` — Type checking. Focus on errors that indicate real bugs (wrong types, missing returns), not missing stubs.
   - `ruff check <target>` — Lint.

2. **Read the code** — Read every line of the target file(s). Don't skim.

3. **Check for these specific issues:**
   - OWASP Top 10: injection, broken auth, XSS, SSRF, insecure deserialization
   - Race conditions and TOCTOU bugs
   - Resource leaks (DB sessions, file handles, HTTP clients not closed)
   - Cryptographic misuse (weak algorithms, hardcoded keys, nonce reuse)
   - Input validation gaps at system boundaries
   - Error handling that swallows context or masks failures
   - Business logic flaws (invalid state transitions, missing authorization)
   - Information disclosure (error messages, logs, stack traces)
   - Data integrity (split commits, missing rollbacks, partial writes)
   - Performance (N+1 queries, loading all rows into memory, repeated lookups)

4. **For each finding, report:**
   - Severity: Critical / High / Medium / Low
   - File and line number
   - The problematic code snippet
   - Why it's a problem (exploit scenario or failure mode)
   - Concrete fix with code

5. **Apply fixes** — Fix each issue found. Then verify with:
   - `ruff check .`
   - `python -m pytest tests/ -x -q`
   - `bandit -r backend/ -c pyproject.toml -ll -q`

Skip style issues, missing docstrings, and hypothetical concerns. Only report real, actionable bugs.
