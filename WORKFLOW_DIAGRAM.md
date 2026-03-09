```mermaid
graph TD
    Start([Start Scan Job]) --> P1{Phase 1:<br/>Check Reachability}
    
    P1 -->|Timeout/Error| Failed1["❌ Target Unreachable"]
    P1 -->|HTTP 400+| Failed2["❌ Target Error"]
    P1 -->|HTTP 200-399| P2["Phase 2:<br/>Force Login"]
    
    Failed1 --> End1([Scan Failed])
    Failed2 --> End1
    
    P2 --> P2A{"Has<br/>Credentials?"}
    P2A -->|Yes| P2B["Try Heuristic Login"]
    P2A -->|No| P2C["Skip Heuristic"]
    
    P2B -->|Success| P2D["✅ Login Successful"]
    P2B -->|Failed| P2E["Try Aggressive Login"]
    P2C --> P2E
    
    P2E -->|Success| P2D
    P2E -->|Failed| P2F["⚠️ Continue Unauthenticated"]
    
    P2D --> P2G["Capture Session Cookies"]
    P2F --> P2G
    
    P2G --> P3["Phase 3:<br/>Crawl Application"]
    
    P3 --> P3A["Browser Launch"]
    P3A --> P3B["Follow Links Systematically"]
    P3B --> P3C["Extract Parameters"]
    P3C --> P3D["Limit Depth (max_depth=2)"]
    P3D --> P3E["Deduplicate URLs"]
    P3E --> P3F{Found<br/>Endpoints?}
    
    P3F -->|0 Endpoints| P3G["Use Entry Point as Fallback"]
    P3F -->|N Endpoints| P3H["Normalize URLs"]
    P3G --> P3H
    
    P3H --> P4["Phase 4:<br/>Attack & Exploit"]
    
    P4 --> P4A["Sync Session to Scanners"]
    P4A --> P4B{"Attack<br/>Type?"}
    
    P4B -->|XSS| P4C["Run XSS Scanner"]
    P4B -->|SQLi| P4D["Run SQLi Scanner"]
    P4B -->|All| P4E["Run Both Scanners"]
    
    P4C --> P4C1["Test Reflected XSS"]
    P4C --> P4C2["Test DOM XSS"]
    P4C1 --> P4F["Collect Findings"]
    P4C2 --> P4F
    
    P4D --> P4D1["Test Boolean-Based SQLi"]
    P4D --> P4D2["Test Time-Based SQLi"]
    P4D --> P4D3["Test Union-Based SQLi"]
    P4D1 --> P4F
    P4D2 --> P4F
    P4D3 --> P4F
    
    P4E --> P4C1
    P4E --> P4D1
    
    P4F --> P4G{Vulnerabilities<br/>Found?}
    
    P4G -->|Yes| P4H["✅ Status: FOUND"]
    P4G -->|No| P4I["✅ Status: NOT FOUND"]
    
    P4H --> P5["Build Response"]
    P4I --> P5
    
    P5 --> P5A["Compile Findings"]
    P5A --> P5B["Compile Crawler URLs"]
    P5B --> P5C["Capture Execution Logs"]
    P5C --> P5D["Cleanup Resources"]
    P5D --> End2([Scan Complete])
    
    style P1 fill:#e1f5ff
    style P2 fill:#f3e5f5
    style P3 fill:#e8f5e9
    style P4 fill:#fff3e0
    style Failed1 fill:#ffebee
    style Failed2 fill:#ffebee
    style P4H fill:#c8e6c9
    style P4I fill:#c8e6c9
    style End2 fill:#c8e6c9
```

## Workflow Description

### Phase 1: Reachability Check ✅
- **Input**: Target URL
- **Process**: 
  - Send HTTP HEAD/GET request
  - Check response status code
  - Handle timeouts and connection errors
- **Output**: Reachable (bool), Status Message
- **Outcome if Failed**: Abort scan

### Phase 2: Authentication ✅
- **Input**: Target URL, Credentials (optional)
- **Process**:
  1. Launch headless browser
  2. Navigate to target
  3. If credentials provided: Try heuristic login
  4. If login fails: Try aggressive login methods
  5. Capture session cookies and auth tokens
- **Output**: Authentication success (bool), Session state
- **Note**: Continues even if authentication fails (unauthenticated scan)

### Phase 3: Crawling/Discovery ✅
- **Input**: Target URL, Authenticated session (optional)
- **Process**:
  1. Queue management with asyncio
  2. Browser automation with Playwright
  3. Link extraction from HTML
  4. Parameter extraction (GET/POST)
  5. URL deduplication
  6. Depth limiting to prevent infinite loops
- **Output**: List of discovered endpoints with methods and parameters
- **Fallback**: If no endpoints found, use entry point

### Phase 4: Attack/Exploitation ✅
- **Input**: List of endpoints, Attack type (XSS/SQLi/All)
- **Process**:
  1. **XSS Scanner**:
     - Test Reflected XSS on GET/POST parameters
     - Test DOM XSS on non-API endpoints
     - Multiple payload contexts (HTML, JS, Attribute)
     - Verify findings to reduce false positives
  
  2. **SQLi Scanner**:
     - Test Boolean-based SQLi
     - Test Time-based SQLi (SLEEP)
     - Test Union-based SQLi
     - Error-based detection
     - Support for different databases (MySQL, MSSQL, PostgreSQL)

- **Output**: List of vulnerabilities with:
  - Type (XSS or SQLi)
  - Severity
  - Target URL
  - Vulnerable parameter
  - Payload used
  - Evidence

### Output & Reporting
- **Status**: "found", "not found", or "failed"
- **Findings**: Detailed vulnerability list
- **Target Count**: Number of endpoints tested
- **Crawler URLs**: List of discovered endpoints
- **Execution Logs**: Complete log messages
