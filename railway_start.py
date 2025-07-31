#!/usr/bin/env python
"""
Railway startup script for Telegram Agent
This script properly handles the PORT environment variable for Railway deployment
"""
import os
import sys
import logging
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("railway_start")

def main():
    """Start the FastAPI application with the correct port configuration"""
    try:
        # Get PORT from environment or use 8000 as default
        port_str = os.environ.get("PORT", "8000")
        logger.info(f"PORT environment variable: {port_str}")
        
        # Convert port to integer
        try:
            port = int(port_str)
        except ValueError:
            logger.error(f"Invalid PORT value: '{port_str}'. Using default 8000.")
            port = 8000
        
        host = "0.0.0.0"
        logger.info(f"Starting server on {host}:{port}")
        
        # Start the application
        uvicorn.run(
            "src.main:app",
            host=host,
            port=port,
            log_level="info"
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
