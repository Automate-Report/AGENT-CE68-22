#!/usr/bin/env python3
"""
Test script for the 4-phase Scan Engine
Demonstrates:
1. Reachability check
2. Forced login/authentication
3. Crawling/Discovery
4. Attack (XSS & SQLi)
"""

import asyncio
import json
from src.scanner.scan_engine import ScanOrchestrator


async def test_xss_scan_dvwa():
    """Test with DVWA (XSS target)"""
    print("\n" + "="*70)
    print("TEST 1: DVWA - XSS Scan")
    print("="*70)
    
    job_data = {
        "job_id": "JOB_001",
        "target_url": "http://localhost/dvwa/",
        "attack_type": "xss",
        "credential": {
            "username": "admin",
            "password": "password"
        }
    }
    
    orchestrator = ScanOrchestrator(job_data)
    result = await orchestrator.run_workflow()
    
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    print(json.dumps(result, indent=2))
    return result


async def test_sqli_scan_dvwa():
    """Test with DVWA (SQLi target)"""
    print("\n" + "="*70)
    print("TEST 2: DVWA - SQLi Scan")
    print("="*70)
    
    job_data = {
        "job_id": "JOB_002",
        "target_url": "http://localhost/dvwa/",
        "attack_type": "sql_injection",
        "credential": {
            "username": "admin",
            "password": "password"
        }
    }
    
    orchestrator = ScanOrchestrator(job_data)
    result = await orchestrator.run_workflow()
    
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    print(json.dumps(result, indent=2))
    return result


async def test_all_attacks():
    """Test with all attack types"""
    print("\n" + "="*70)
    print("TEST 3: All Attacks (XSS + SQLi)")
    print("="*70)
    
    job_data = {
        "job_id": "JOB_003",
        "target_url": "http://localhost/dvwa/",
        "attack_type": "all",
        "credential": {
            "username": "admin",
            "password": "password"
        }
    }
    
    orchestrator = ScanOrchestrator(job_data)
    result = await orchestrator.run_workflow()
    
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    print(json.dumps(result, indent=2))
    return result


async def test_without_credentials():
    """Test without credentials (unauthenticated scan)"""
    print("\n" + "="*70)
    print("TEST 4: Unauthenticated Scan (No Credentials)")
    print("="*70)
    
    job_data = {
        "job_id": "JOB_004",
        "target_url": "http://localhost/dvwa/",
        "attack_type": "xss",
        "credential": None
    }
    
    orchestrator = ScanOrchestrator(job_data)
    result = await orchestrator.run_workflow()
    
    print("\n" + "="*70)
    print("RESULTS:")
    print("="*70)
    print(json.dumps(result, indent=2))
    return result


async def manual_phase_test():
    """Test phases individually"""
    print("\n" + "="*70)
    print("MANUAL PHASE TEST")
    print("="*70)
    
    job_data = {
        "job_id": "JOB_MANUAL",
        "target_url": "http://localhost/dvwa/",
        "attack_type": "xss",
        "credential": {
            "username": "admin",
            "password": "password"
        }
    }
    
    orchestrator = ScanOrchestrator(job_data)
    
    # Phase 1: Reachability
    print("\n[PHASE 1] Checking reachability...")
    is_reachable, msg = orchestrator.phase_1_check_reachability()
    print(f"Result: {is_reachable} - {msg}")
    
    if not is_reachable:
        print("❌ Target not reachable, cannot continue")
        return
    
    # Phase 2: Login
    print("\n[PHASE 2] Attempting authentication...")
    auth_success = await orchestrator.phase_2_force_login()
    print(f"Result: {'✅ Success' if auth_success else '⚠️ Failed/Skipped'}")
    
    # Phase 3: Crawl
    print("\n[PHASE 3] Crawling application...")
    targets = await orchestrator.phase_3_crawl_application()
    print(f"Result: Found {len(targets)} endpoints")
    for i, target in enumerate(targets[:5], 1):
        url = target["url"] if isinstance(target, dict) else str(target)
        print(f"  {i}. {url}")
    
    # Phase 4: Attack
    print("\n[PHASE 4] Running attacks...")
    findings = orchestrator.phase_4_attack(targets)
    print(f"Result: Found {len(findings)} vulnerabilities")
    for i, finding in enumerate(findings[:5], 1):
        print(f"  {i}. {finding}")


def main():
    """Run tests"""
    print("\n" + "="*70)
    print("SCAN ENGINE TEST SUITE")
    print("4-Phase Penetration Testing Workflow")
    print("="*70)
    
    # Run individual tests
    choice = input("\nSelect test:\n"
                  "1. DVWA - XSS Scan\n"
                  "2. DVWA - SQLi Scan\n"
                  "3. All Attacks\n"
                  "4. Unauthenticated Scan\n"
                  "5. Manual Phase Test\n"
                  "0. Exit\n"
                  "Choice: ").strip()
    
    if choice == "1":
        asyncio.run(test_xss_scan_dvwa())
    elif choice == "2":
        asyncio.run(test_sqli_scan_dvwa())
    elif choice == "3":
        asyncio.run(test_all_attacks())
    elif choice == "4":
        asyncio.run(test_without_credentials())
    elif choice == "5":
        asyncio.run(manual_phase_test())
    elif choice == "0":
        print("Exit")
        return
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
