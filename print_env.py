#!/usr/bin/env python
"""
Simple script to print all environment variables
"""
import os
import json

# Print all environment variables
print("=== Environment Variables ===")
env_vars = {k: v for k, v in os.environ.items()}
print(json.dumps(env_vars, indent=2, sort_keys=True))
