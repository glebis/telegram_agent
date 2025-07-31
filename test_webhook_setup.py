#!/usr/bin/env python
"""
Test script to verify webhook setup in production environment
"""
import os
import asyncio
import logging
from typing import Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("webhook_test")

class MockWebhookManager:
    """Mock webhook manager for testing"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        
    async def set_webhook(self, webhook_url: str, secret_token: Optional[str] = None) -> Tuple[bool, str]:
        """Mock setting webhook"""
        logger.info(f"🔄 MOCK: Setting webhook to {webhook_url}")
        logger.info(f"🔑 MOCK: Secret token provided: {bool(secret_token)}")
        return True, f"Mock webhook set to {webhook_url}"

async def setup_production_webhook(
    bot_token: str,
    base_url: str,
    webhook_path: str = "/webhook",
    secret_token: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """Test production webhook setup"""
    logger.info(f"🔄 TEST: Setting up production webhook: {base_url}{webhook_path}")
    
    if not base_url:
        logger.error("❌ TEST: base_url is empty or None")
        return False, "Base URL is required for production webhook setup", None
    
    try:
        # Ensure base_url doesn't end with a slash
        if base_url.endswith("/"):
            base_url = base_url[:-1]
            
        # Ensure webhook_path starts with a slash
        if not webhook_path.startswith("/"):
            webhook_path = f"/{webhook_path}"
            
        webhook_url = f"{base_url}{webhook_path}"
        webhook_manager = MockWebhookManager(bot_token)
        
        logger.info(f"🔄 TEST: Full webhook URL: {webhook_url}")
        logger.info(f"🔑 TEST: Secret token provided: {bool(secret_token)}")
        
        success, message = await webhook_manager.set_webhook(webhook_url, secret_token)
        
        if success:
            logger.info(f"✅ TEST: Successfully set webhook to {webhook_url}")
            return True, f"Webhook set up successfully: {webhook_url}", webhook_url
        else:
            logger.error(f"❌ TEST: Failed to set webhook: {message}")
            return False, f"Failed to set webhook: {message}", None
    except Exception as e:
        logger.error(f"❌ TEST: Exception during setup: {str(e)}", exc_info=True)
        return False, f"Failed to set up production webhook: {str(e)}", None

async def test_webhook_setup():
    """Test webhook setup with different environment configurations"""
    # Test with production environment
    os.environ["ENVIRONMENT"] = "production"
    os.environ["WEBHOOK_BASE_URL"] = "http://localhost:8000"
    
    environment = os.getenv("ENVIRONMENT", "development").lower()
    base_url = os.getenv("WEBHOOK_BASE_URL")
    
    logger.info(f"🔍 TEST: Environment detected: '{environment}'")
    logger.info(f"🔍 TEST: WEBHOOK_BASE_URL: '{base_url}'")
    
    if environment == "production" and base_url:
        logger.info("🌐 TEST: Production environment detected, testing webhook setup")
        success, message, webhook_url = await setup_production_webhook(
            bot_token="dummy_token",
            base_url=base_url,
            webhook_path="/webhook",
            secret_token="test_secret"
        )
        
        logger.info(f"📊 TEST RESULT: success={success}, message={message}, url={webhook_url}")
    else:
        logger.warning("⚠️ TEST: Not in production environment or missing base URL")
    
    # Test with development environment
    os.environ["ENVIRONMENT"] = "development"
    os.environ["WEBHOOK_BASE_URL"] = ""
    
    environment = os.getenv("ENVIRONMENT", "development").lower()
    base_url = os.getenv("WEBHOOK_BASE_URL")
    
    logger.info(f"🔍 TEST: Environment detected: '{environment}'")
    logger.info(f"🔍 TEST: WEBHOOK_BASE_URL: '{base_url}'")
    
    if environment == "production" and base_url:
        logger.info("🌐 TEST: Production environment detected, testing webhook setup")
        await setup_production_webhook(
            bot_token="dummy_token",
            base_url=base_url,
            webhook_path="/webhook",
            secret_token="test_secret"
        )
    else:
        logger.warning("⚠️ TEST: Not in production environment or missing base URL")

async def main():
    """Main function"""
    logger.info("🚀 Starting webhook setup test")
    await test_webhook_setup()
    logger.info("✅ Webhook setup test completed")

if __name__ == "__main__":
    asyncio.run(main())
