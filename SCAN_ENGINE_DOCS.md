# 4-Phase Scan Engine Documentation

## Overview
The Scan Engine is a comprehensive penetration testing orchestrator that automates security scanning in 4 distinct phases:

1. **Phase 1: Reachability Check** - Verify the target is accessible
2. **Phase 2: Forced Login** - Authenticate to the application (with credentials or aggressive methods)
3. **Phase 3: Crawling/Discovery** - Discover all accessible endpoints and parameters
4. **Phase 4: Attack/Exploitation** - Execute XSS and SQL Injection attacks

## Architecture

### Components

```
ScanOrchestrator (Main Orchestrator)
├── Requester (HTTP Client)
├── Crawler (Web Application Discovery)
│   └── AuthHandler (Authentication)
├── XSSScanner (Reflected & DOM XSS)
│   ├── ContextAnalyzer
│   └── XSSVerifier
├── SQLiScanner (SQL Injection Detection)
└── Logger (Execution Tracking)
```

## Phase Details

### Phase 1: Reachability Check
**Purpose**: Verify the target application is online and responding to requests

**Implementation**: 
```python
def phase_1_check_reachability(self) -> tuple[bool, str]
```

**What it does**:
- Sends HTTP HEAD request to target
- Checks HTTP status codes (< 400 = success)
- Handles various connection errors (timeout, refused, etc.)
- Returns success status and detailed messages

**Output**:
```
✅ Target is reachable! (Status: 200)
⚠️ Target returned error status: 403
❌ Connection timeout - target took too long to respond
```

---

### Phase 2: Forced Login / Authentication
**Purpose**: Establish an authenticated session to access protected resources

**Implementation**:
```python
async def phase_2_force_login(self) -> bool
```

**Authentication Methods**:

1. **Heuristic Login** (if credentials provided):
   - Detects login form using CSS selectors
   - Identifies username/password/submit inputs
   - Submits credentials
   - Captures session cookies

2. **Aggressive Login** (if heuristic fails):
   - Tries common default credentials (admin/admin, admin/password)
   - Attempts SQLi bypass techniques
   - Uses browser automation to navigate around login

**Session Capture**:
- Extracts all cookies from authenticated browser context
- Creates auth_info structure for scanners
- Stores tokens and auth headers

**Output**:
```
✅ Login successful with provided credentials!
⚠️ Aggressive login succeeded
⚠️ No cookies captured
```

---

### Phase 3: Crawling / Discovery
**Purpose**: Discover all crawlable endpoints, parameters, and the application structure

**Implementation**:
```python
async def phase_3_crawl_application(self) -> list
```

**Crawling Features**:
- **Automated traversal** - Follows links systematically
- **Parameter extraction** - Identifies GET/POST parameters
- **Interaction simulation** - Clicks buttons, fills forms
- **Depth control** - Limits crawl depth to prevent endless loops
- **Session persistence** - Uses authenticated cookies from Phase 2

**Discovered Data Structure**:
```json
{
  "url": "http://target.com/search",
  "method": "GET",
  "params": {
    "q": "search_term",
    "filter": "category"
  },
  "content_type": "form"
}
```

**Output**:
```
🕷️ Starting crawl of http://target.com/
✅ Crawl complete. Discovered 42 endpoints
   - http://target.com/home
   - http://target.com/search
   - ... and 40 more
```

---

### Phase 4: Attack / Exploitation
**Purpose**: Execute penetration tests (XSS and SQLi) on discovered endpoints

**Implementation**:
```python
def phase_4_attack(self, targets: list) -> list
```

#### XSS Scanner (Cross-Site Scripting)
**Tested Contexts**:
- HTML Body context
- HTML Attribute context
- JavaScript variable context
- Polyglot payloads

**Detection Types**:
- **Reflected XSS**: Payload reflected in response
- **DOM XSS**: Payload executed in DOM via JavaScript

**Payloads**:
```javascript
<script>alert('xss')</script>
"><script>alert('xss')</script>
'><script>alert('xss')</script>
"><svg onload=alert('xss')>
```

#### SQL Injection Scanner
**Detection Methods**:

1. **Boolean-based**: 
   ```sql
   ' AND 1=1 -- (true)
   ' AND 1=0 -- (false)
   ```

2. **Time-based**:
   ```sql
   ' OR SLEEP(5) -- (detects delay)
   ```

3. **Union-based**:
   ```sql
   ' UNION SELECT version() --
   ```

4. **Error-based**:
   - Captures error messages from database

**Target Parameters**:
- GET query parameters
- POST form data
- JSON request bodies
- Custom headers

---

## Usage

### Basic Usage

```python
import asyncio
from src.scanner.scan_engine import ScanOrchestrator

# Define the scan job
job_data = {
    "job_id": "SCAN_001",
    "target_url": "http://vulnerable-app.local/",
    "attack_type": "xss",  # or "sql_injection" or "all"
    "credential": {
        "username": "admin",
        "password": "admin"
    }
}

# Create orchestrator and run
orchestrator = ScanOrchestrator(job_data)
result = await orchestrator.run_workflow()

# Process results
print(f"Status: {result['status']}")
print(f"Vulnerabilities found: {len(result['findings'])}")
print(f"Endpoints scanned: {result['target_count']}")
```

### Attack Types

```python
# XSS Only
{"attack_type": "xss"}

# SQL Injection Only
{"attack_type": "sql_injection"}

# Both
{"attack_type": "all"}
```

### With and Without Credentials

```python
# With credentials (will attempt login)
{"credential": {"username": "user", "password": "pass"}}

# Without credentials (anonymous scan)
{"credential": None}
```

### Individual Phase Testing

```python
orchestrator = ScanOrchestrator(job_data)

# Phase 1: Check reachability
is_reachable, msg = orchestrator.phase_1_check_reachability()
print(f"Reachable: {is_reachable}")

# Phase 2: Authenticate
auth_success = await orchestrator.phase_2_force_login()
print(f"Authenticated: {auth_success}")

# Phase 3: Crawl
targets = await orchestrator.phase_3_crawl_application()
print(f"Found {len(targets)} endpoints")

# Phase 4: Attack
findings = orchestrator.phase_4_attack(targets)
print(f"Found {len(findings)} vulnerabilities")
```

---

## Response Structure

```python
{
    "job_id": 1,
    "status": "found",  # "found" | "not found" | "failed"
    "findings": [
        {
            "type": "XSS",
            "severity": "high",
            "url": "http://target.com/search",
            "parameter": "q",
            "payload": "<script>alert('xss')</script>",
            "evidence": "..."
        },
        ...
    ],
    "target_count": 42,
    "crawler_urls": [
        "http://target.com/home",
        "http://target.com/search",
        ...
    ],
    "error_log": null,
    "execution_logs": [
        "2024-03-09 10:30:45 [INFO] Target is reachable!",
        "2024-03-09 10:30:47 [INFO] Login successful!",
        ...
    ]
}
```

---

## Error Handling

The scan engine includes comprehensive error handling:

1. **Connection Errors**: Network issues, timeouts
2. **Authentication Errors**: Login failures, invalid credentials
3. **Crawling Errors**: Page load failures, timeout
4. **Attack Errors**: Payload injection errors, response parsing failures

All errors are logged and included in the response:
```
"error_log": "Failed to authenticate: Invalid credentials"
"execution_logs": ["[ERROR] message"]
```

---

## Performance Optimization

### Concurrent Operations
- Multiple endpoints scanned in parallel (limited by semaphore)
- Asynchronous crawling and authentication

### Resource Management
- Automatic browser cleanup
- Connection pooling via Requester
- Memory cleanup after scan completion

### Deduplication
- Duplicate URLs removed during crawling
- Prevents redundant scanning

---

## Security Considerations

### Scope Limitation
- Crawls only within target domain
- Respects application boundaries

### SSL/TLS
- Supports self-signed certificates (for testing)
- Uses `verify=False` for internal security labs

### Session Management
- Preserves authenticated sessions across phases
- Reuses cookies for efficient scanning

---

## Logging

Each scan is fully logged with timestamps and levels:

```
[INFO] Target is reachable!
[INFO] Login successful! Session captured.
[DEBUG] Testing Reflected XSS...
[WARNING] No tables found for Union-based SQLi
[ERROR] Critical Error: timeout
```

Logs are captured in:
- Console output (real-time)
- Response execution_logs (post-scan review)

---

## Common Use Cases

### 1. Test DVWA (Damn Vulnerable Web Application)
```python
job_data = {
    "job_id": "DVWA_TEST",
    "target_url": "http://localhost/dvwa/",
    "attack_type": "all",
    "credential": {"username": "admin", "password": "password"}
}
```

### 2. Anonymous Testing
```python
job_data = {
    "job_id": "ANON_TEST",
    "target_url": "http://public-app.com/",
    "attack_type": "xss",
    "credential": None
}
```

### 3. API Testing (XSS)
```python
job_data = {
    "job_id": "API_TEST",
    "target_url": "http://api.target.com/v1/",
    "attack_type": "xss",
    "credential": None
}
```

---

## Testing

Run the test suite:
```bash
python scan_test.py
```

Select from interactive menu:
1. DVWA - XSS Scan
2. DVWA - SQLi Scan
3. All Attacks
4. Unauthenticated Scan
5. Manual Phase Test

---

## Troubleshooting

### Issue: "Target Unreachable"
- Check network connectivity
- Verify URL is correct
- Check if target firewall blocks your IP

### Issue: "Authentication failed"
- Verify credentials are correct
- Check if login form structure matches expectations
- Try with `credential: None` for unauthenticated scan

### Issue: "No endpoints discovered"
- Target might require JavaScript rendering
- Try increasing crawl depth
- Manually visit endpoints

### Issue: "No vulnerabilities found"
- Target might be patched
- Payloads might be filtered
- Try different attack types

---

## Future Enhancements

- [ ] Custom payload injection
- [ ] Authentication token refresh
- [ ] Proxy support
- [ ] Custom header injection
- [ ] Rate limiting evasion
- [ ] CORS bypass
- [ ] Advanced XPath injection
- [ ] NoSQL injection
- [ ] LDAP injection
