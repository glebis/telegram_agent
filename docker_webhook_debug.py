#!/usr/bin/env python
"""
Debug script for Docker webhook setup
This script can be added to the Docker image and run to verify webhook setup
without requiring a valid bot token
"""
import os
import sys
import json
import asyncio
import logging
from typing import Optional, Tuple, Dict, Any
import traceback
import requests

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("docker_webhook_debug")

class MockTelegramAPI:
    """Mock Telegram API for testing webhook setup"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def set_webhook(self, url: str, secret_token: Optional[str] = None) -> Dict[str, Any]:
        """Mock setting webhook"""
        logger.info(f"🔄 MOCK API: Setting webhook to {url}")
        
        params = {"url": url}
        if secret_token:
            params["secret_token"] = secret_token
            
        # In a real scenario, we'd make an actual API call
        # response = requests.post(f"{self.base_url}/setWebhook", json=params)
        # return response.json()
        
        # For testing, we'll just return a mock success response
        return {
            "ok": True,
            "result": True,
            "description": "Webhook was set"
        }

async def setup_production_webhook(
    bot_token: str,
    base_url: str,
    webhook_path: str = "/webhook",
    secret_token: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """Set up webhook for production environment"""
    logger.info(f"🔄 SETUP: Setting up production webhook with base URL: {base_url}")
    
    if not base_url:
        logger.error("❌ SETUP: base_url is empty or None")
        return False, "Base URL is required for production webhook setup", None
    
    try:
        # Ensure base_url doesn't end with a slash
        if base_url.endswith("/"):
            base_url = base_url[:-1]
            
        # Ensure webhook_path starts with a slash
        if not webhook_path.startswith("/"):
            webhook_path = f"/{webhook_path}"
            
        webhook_url = f"{base_url}{webhook_path}"
        
        logger.info(f"🔄 SETUP: Full webhook URL: {webhook_url}")
        logger.info(f"🔑 SETUP: Secret token provided: {bool(secret_token)}")
        
        # Use mock API for testing
        api = MockTelegramAPI(bot_token)
        response = api.set_webhook(webhook_url, secret_token)
        
        if response.get("ok", False):
            logger.info(f"✅ SETUP: Successfully set webhook to {webhook_url}")
            logger.info(f"📊 SETUP: API Response: {json.dumps(response, indent=2)}")
            return True, "Webhook set successfully", webhook_url
        else:
            error_msg = response.get("description", "Unknown error")
            logger.error(f"❌ SETUP: Failed to set webhook: {error_msg}")
            logger.error(f"📊 SETUP: API Response: {json.dumps(response, indent=2)}")
            return False, f"Failed to set webhook: {error_msg}", None
    except Exception as e:
        logger.error(f"❌ SETUP: Exception during setup: {str(e)}")
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return False, f"Failed to set up production webhook: {str(e)}", None

async def debug_webhook_setup():
    """Debug webhook setup in Docker container"""
    # Print all environment variables
    logger.info("=== Environment Variables ===")
    env_vars = {k: v for k, v in os.environ.items() if not k.startswith("PATH")}
    logger.info(json.dumps(env_vars, indent=2, sort_keys=True))
    
    # Get environment settings
    environment = os.getenv("ENVIRONMENT", "development").lower()
    base_url = os.getenv("WEBHOOK_BASE_URL")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "dummy_token")
    webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    
    logger.info(f"🔍 DEBUG: Environment detected: '{environment}'")
    logger.info(f"🔍 DEBUG: WEBHOOK_BASE_URL: '{base_url}'")
    logger.info(f"🔍 DEBUG: TELEGRAM_BOT_TOKEN: '{'***' if bot_token else 'None'}'")
    logger.info(f"🔍 DEBUG: TELEGRAM_WEBHOOK_SECRET: '{'***' if webhook_secret else 'None'}'")
    
    # Check if we're in production environment
    if environment == "production":
        logger.info("🌐 DEBUG: Production environment detected")
        
        # Check if base_url is set
        if base_url:
            logger.info(f"🌐 DEBUG: Using base URL: {base_url}")
            
            # Test webhook setup
            success, message, webhook_url = await setup_production_webhook(
                bot_token=bot_token,
                base_url=base_url,
                webhook_path="/webhook",
                secret_token=webhook_secret
            )
            
            logger.info(f"📊 DEBUG RESULT: success={success}, message={message}, url={webhook_url}")
            
            # Test webhook connectivity
            try:
                logger.info(f"🔄 DEBUG: Testing webhook connectivity to {webhook_url}")
                response = requests.get(base_url + "/health", timeout=5)
                logger.info(f"📊 DEBUG: Health endpoint status code: {response.status_code}")
                logger.info(f"📊 DEBUG: Health endpoint response: {response.text[:200]}")
            except Exception as e:
                logger.error(f"❌ DEBUG: Failed to connect to health endpoint: {str(e)}")
        else:
            logger.warning("⚠️ DEBUG: WEBHOOK_BASE_URL not set, cannot set up webhook")
    else:
        logger.warning(f"⚠️ DEBUG: Not in production environment (ENVIRONMENT={environment})")

async def main():
    """Main function"""
    logger.info("🚀 Starting Docker webhook debug")
    await debug_webhook_setup()
    logger.info("✅ Docker webhook debug completed")

if __name__ == "__main__":
    asyncio.run(main())
