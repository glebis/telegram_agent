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
    
    # Check for Railway-specific environment variables
    # Railway provides RAILWAY_PUBLIC_DOMAIN or RAILWAY_SERVICE_URL or RAILWAY_STATIC_URL
    railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    railway_service_url = os.getenv("RAILWAY_SERVICE_URL") 
    railway_static_url = os.getenv("RAILWAY_STATIC_URL")
    
    # Try Railway public domain first (custom domains)
    if railway_public_domain:
        railway_url = f"https://{railway_public_domain}"
        logger.info(f"Using Railway public domain: {railway_url}")
        return railway_url, True
    
    # Try Railway service URL next (default *.up.railway.app URLs)
    if railway_service_url:
        # Make sure it starts with https://
        if not railway_service_url.startswith("http"):
            railway_service_url = f"https://{railway_service_url}"
        logger.info(f"Using Railway service URL: {railway_service_url}")
        return railway_service_url, True
    
    # Try Railway static URL as fallback
    if railway_static_url:
        # Make sure it starts with https://
        if not railway_static_url.startswith("http"):
            railway_static_url = f"https://{railway_static_url}"
        logger.info(f"Using Railway static URL: {railway_static_url}")
        return railway_static_url, True
    
    # If no Railway variables found, try to use hostname from environment
    hostname = os.getenv("HOSTNAME")
    if hostname:
        logger.info(f"Found HOSTNAME environment variable: {hostname}")
        # Try to construct a Railway URL from the hostname
        if "railway" in hostname.lower():
            railway_url = f"https://{hostname}"
            logger.info(f"Constructed Railway URL from hostname: {railway_url}")
            return railway_url, True
    
    # If all Railway detection methods fail, try to auto-detect using external IP
    logger.info("No Railway environment variables found, attempting to auto-detect external IP")
    external_ip = get_external_ip()
    if not external_ip:
        logger.warning("Could not auto-detect external IP")
        return "", False
    
    # Railway deployments support HTTPS by default
    # Only use HTTP if explicitly set to false
    use_https = os.getenv("WEBHOOK_USE_HTTPS", "true").lower() != "false"
    protocol = "https" if use_https else "http"
    
    # Telegram only allows webhooks on ports 80, 88, 443, or 8443
    # For HTTPS, port 443 is standard and doesn't need to be specified
    # For HTTP, we'll use port 80
    if use_https:
        # For HTTPS, don't specify port (defaults to 443)
        auto_base_url = f"{protocol}://{external_ip}"
        logger.info("Using standard HTTPS port 443 (not specified in URL)")
    else:
        # For HTTP, use port 80
        auto_base_url = f"{protocol}://{external_ip}:80"
        logger.info("Using HTTP port 80 as required by Telegram")
    
    logger.info(f"Auto-detected webhook base URL: {auto_base_url}")
    
    # Log information about Telegram's port restrictions
    logger.info("Note: Telegram only allows webhooks on ports 80, 88, 443, or 8443")
    
    return auto_base_url, True
