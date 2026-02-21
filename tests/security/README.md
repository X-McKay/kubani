# Security Tests for Kubani Nexus

This directory contains comprehensive security tests for the Nexus sandbox executor, validating that dangerous operations are properly blocked and isolated.

## Test Coverage

### 28.1 Subprocess Import Blocking (Requirements 11.1)
- `test_subprocess_import_blocked` - Verifies subprocess import has high risk score (>= 8.0)
- `test_subprocess_from_import_blocked` - Verifies "from subprocess import" is blocked
- `test_subprocess_aliased_import_blocked` - Verifies aliased subprocess imports are blocked

### 28.2 eval() Blocking (Requirements 11.2)
- `test_eval_blocked_with_high_risk_score` - Verifies eval() has risk score >= 9.0
- `test_eval_in_conditional_blocked` - Verifies eval() in conditionals is detected
- `test_eval_in_list_comprehension_blocked` - Verifies eval() in comprehensions is detected

### 28.3 os.system Blocking (Requirements 11.3)
- `test_os_system_blocked_with_high_risk_score` - Verifies os.system has risk score >= 9.0
- `test_os_popen_blocked` - Verifies os.popen is blocked
- `test_os_exec_family_blocked` - Verifies os.execv and os.execve are blocked

### 28.4 Secret Isolation (Requirements 11.4)
- `test_openai_api_key_not_accessible` - Verifies OPENAI_API_KEY is not accessible in sandbox
- `test_github_token_not_accessible` - Verifies GITHUB_TOKEN is not accessible
- `test_database_url_not_accessible` - Verifies DATABASE_URL is not accessible
- `test_aws_credentials_not_accessible` - Verifies AWS credentials are not accessible
- `test_multiple_secrets_not_accessible` - Verifies multiple secrets are isolated simultaneously

### 28.5 Filesystem Restriction (Requirements 11.5)
- `test_write_outside_workspace_restricted` - Verifies writes outside workspace are restricted
- `test_read_outside_workspace_restricted` - Verifies reads outside workspace are restricted
- `test_workspace_write_allowed` - Verifies writes within workspace are allowed

### 28.6 Network Access Flagging (Requirements 11.6)
- `test_socket_import_flagged` - Verifies socket import is flagged for network access
- `test_urllib_import_safe` - Verifies urllib is allowed (standard HTTP client)
- `test_requests_import_safe` - Verifies requests library is allowed
- `test_httpx_import_safe` - Verifies httpx library is allowed
- `test_socket_with_subprocess_blocked` - Verifies combining socket with subprocess is blocked

## Running the Tests

Run all security tests:
```bash
uv run pytest tests/security/ -v
```

Run specific test class:
```bash
uv run pytest tests/security/test_sandbox_security.py::TestSubprocessImportBlocking -v
```

Run with coverage:
```bash
uv run pytest tests/security/ --cov=kubani.nexus.sandbox --cov-report=html
```

## Test Results

All 22 security tests pass successfully, validating that:
- Dangerous imports (subprocess, ctypes) are blocked with high risk scores
- Dangerous function calls (eval, exec) are blocked with risk scores >= 9.0
- Dangerous system operations (os.system, os.popen, os.exec*) are blocked
- Sensitive environment variables are not accessible in the sandbox
- Filesystem access is properly restricted to the workspace
- Network access is appropriately flagged and controlled

## Security Model

The sandbox executor uses a multi-layered security approach:

1. **Static Analysis** - AST-based analysis detects dangerous patterns before execution
2. **Environment Sanitization** - Blocked environment variables are stripped from subprocess
3. **Workspace Isolation** - Skills execute in temporary directories
4. **Timeout Enforcement** - Prevents runaway processes
5. **Output Capture** - All stdout/stderr is captured for logging

## Known Limitations

- Filesystem restriction relies on subprocess isolation, not full containerization
- In local development, the sandbox doesn't use chroot/containers
- For production deployment, Kubernetes Jobs with security contexts should be used
- Network access is flagged but not fully blocked (requires network policies in production)
