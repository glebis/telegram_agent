#!/usr/bin/env python3
import os
import sys
import time
import subprocess
import threading
import requests
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
env_file = os.path.join(project_root, '.env.local')
if os.path.exists(env_file):
    load_dotenv(env_file)
    print(f"📁 Loaded environment from .env.local")

def stream_output(process, prefix=''):
    """Stream output from a subprocess in real-time"""
    for line in iter(process.stdout.readline, ''):
        if line:
            print(f"{prefix} {line.strip()}")
    
    # When stdout is done, check stderr
    for line in iter(process.stderr.readline, ''):
        if line:
            print(f"{prefix} ERROR: {line.strip()}")

def test_fastapi_server():
    """Test starting the FastAPI server directly and checking if it responds"""
    print("Starting FastAPI server for testing...")
    print(f"Python executable: {sys.executable}")
    print(f"Current directory: {os.getcwd()}")
    print(f"DATABASE_URL: {os.getenv('DATABASE_URL', 'Not set')}")
    
    # Start FastAPI server with debug logging
    fastapi_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app", "--port", "8001", "--host", "0.0.0.0", "--log-level", "debug"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # Line buffered
    )
    
    # Start threads to stream output
    stdout_thread = threading.Thread(target=stream_output, args=(fastapi_process, 'STDOUT:'))
    stdout_thread.daemon = True
    stdout_thread.start()
    
    # Wait for server to start
    print("Waiting for server to start...")
    max_wait = 15  # Wait up to 15 seconds
    
    for i in range(max_wait):
        # Check if process is still running
        if fastapi_process.poll() is not None:
            print(f"FastAPI server exited with code {fastapi_process.returncode}")
            return False
        
        # Try to connect to server
        try:
            print(f"Attempt {i+1}/{max_wait} to connect to server...")
            response = requests.get("http://localhost:8001/", timeout=1)
            print(f"Success! Server is responding. Status: {response.status_code}")
            break
        except requests.exceptions.ConnectionError:
            print("Server not responding yet...")
        except Exception as e:
            print(f"Error connecting to server: {e}")
        
        time.sleep(1)
    else:
        print("Timeout waiting for server to start")
    
    # Try to connect to server one final time
    try:
        print("\nTesting connection to root endpoint...")
        response = requests.get("http://localhost:8001/", timeout=2)
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
        
        # Try health endpoint
        print("\nTesting health endpoint...")
        health_response = requests.get("http://localhost:8001/health", timeout=2)
        print(f"Health status: {health_response.status_code}")
        print(f"Health body: {health_response.json()}")
        
        return True
    except Exception as e:
        print(f"Error connecting to server: {e}")
        
        # Check if process is still running and get output
        if fastapi_process.poll() is None:
            print("\nServer process is still running but not responding to requests.")
            print("This could indicate a deadlock or infinite loop in the application.")
        else:
            print(f"\nServer process exited with code {fastapi_process.returncode}")
        
        return False
    finally:
        # Terminate server
        print("\nTerminating server...")
        if fastapi_process.poll() is None:
            fastapi_process.terminate()
            try:
                fastapi_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Server did not terminate gracefully, killing...")
                fastapi_process.kill()

if __name__ == "__main__":
    test_fastapi_server()
