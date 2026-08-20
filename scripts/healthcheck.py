#!/usr/bin/env python3
"""
Health check script for Docker container.
Returns exit code 0 if healthy, 1 if unhealthy.
"""
import sys
import urllib.request
import urllib.error

def check_health():
    try:
        response = urllib.request.urlopen('http://localhost:8000/health', timeout=5)
        if response.status == 200:
            print("✓ Health check passed")
            return 0
        else:
            print(f"✗ Health check failed with status {response.status}")
            return 1
    except urllib.error.URLError as e:
        print(f"✗ Health check failed: {e}")
        return 1
    except Exception as e:
        print(f"✗ Health check failed with exception: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(check_health())