#!/usr/bin/env python3
"""
Comprehensive test runner for Telegram Agent

This script runs all tests and generates coverage reports for the key features:
1. Summary Generation (LLM Service)
2. Image Processing Pipeline  
3. Vector Similarity Search
4. Database Operations & Integrity
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False


def main():
    """Main test runner"""
    print("🚀 Starting Telegram Agent Test Suite")
    print("Testing 4 key features:")
    print("1. Summary Generation (LLM Service)")
    print("2. Image Processing Pipeline")
    print("3. Vector Similarity Search") 
    print("4. Database Operations & Integrity")
    
    # Change to project directory
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    # Install dependencies if needed
    if not run_command("python -m pip install -e .", "Installing project dependencies"):
        print("⚠️  Warning: Failed to install dependencies, continuing anyway...")
    
    # Test commands to run
    test_commands = [
        # Run specific test files
        ("python -m pytest tests/test_services/test_llm_service.py -v", 
         "Summary Generation Tests (LLM Service)"),
        
        ("python -m pytest tests/test_services/test_image_service.py -v", 
         "Image Processing Pipeline Tests"),
        
        ("python -m pytest tests/test_services/test_similarity_service.py -v", 
         "Vector Similarity Search Tests"),
        
        ("python -m pytest tests/test_core/test_database.py -v", 
         "Database Operations & Integrity Tests"),
        
        # Run all tests with coverage
        ("python -m pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing", 
         "All Tests with Coverage Report"),
    ]
    
    # Track results
    results = []
    
    # Run each test command
    for cmd, description in test_commands:
        success = run_command(cmd, description)
        results.append((description, success))
    
    # Summary report
    print(f"\n{'='*60}")
    print("📊 TEST RESULTS SUMMARY")
    print(f"{'='*60}")
    
    passed = 0
    failed = 0
    
    for description, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status:<10} {description}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print(f"\n📈 Overall Results: {passed} passed, {failed} failed")
    
    # Coverage report location
    coverage_html = project_dir / "htmlcov" / "index.html"
    if coverage_html.exists():
        print(f"📋 Coverage report available at: {coverage_html}")
    
    # Exit with appropriate code
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())