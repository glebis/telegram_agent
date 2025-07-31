"""
Utility functions for IP address detection and management.
"""
import logging
import os
import requests
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# List of services that can be used to detect external IP
IP_SERVICES = [
    "https://api.ipify.org",
    "https://ipinfo.io/ip",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
    "https://ident.me"
]

def get_external_ip() -> Optional[str]:
    """
    Attempts to get the external IP address of the server using multiple services.
    Returns None if all attempts fail.
    """
    for service in IP_SERVICES:
        try:
            logger.info(f"Attempting to get external IP from: {service}")
            response = requests.get(service, timeout=5)
            if response.status_code == 200:
                ip = response.text.strip()
                logger.info(f"Successfully retrieved external IP: {ip}")
                return ip
        except Exception as e:
            logger.warning(f"Failed to get external IP from {service}: {e}")
    
    logger.error("Failed to get external IP from any service")
    return None

def get_webhook_base_url() -> Tuple[str, bool]:
    """
    Determines the webhook base URL to use.
    
    Returns:
        Tuple[str, bool]: (base_url, is_auto_detected)
        - base_url: The webhook base URL to use
        - is_auto_detected: True if the URL was auto-detected, False if it was provided via env var
    """
    # First check if WEBHOOK_BASE_URL is explicitly set
    base_url = os.getenv("WEBHOOK_BASE_URL")
    if base_url:
        logger.info(f"Using provided WEBHOOK_BASE_URL: {base_url}")
        return base_url, False
    
    # If not set, try to auto-detect using external IP
    logger.info("WEBHOOK_BASE_URL not set, attempting to auto-detect external IP")
    external_ip = get_external_ip()
    if not external_ip:
        logger.warning("Could not auto-detect external IP")
        return "", False
    
    # Get the port from environment or use default
    port = os.getenv("PORT", "8000")
    
    # Railway deployments support HTTPS by default
    # Only use HTTP if explicitly set to false
    use_https = os.getenv("WEBHOOK_USE_HTTPS", "true").lower() != "false"
    protocol = "https" if use_https else "http"
    
    # Construct the webhook base URL
    auto_base_url = f"{protocol}://{external_ip}:{port}"
    logger.info(f"Auto-detected webhook base URL: {auto_base_url}")
    
    return auto_base_url, True
