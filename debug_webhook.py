#!/usr/bin/env python
"""
Debug script to test webhook configuration and environment detection
"""
import os
import logging
import asyncio
from src.utils.ngrok_utils import WebhookManager, setup_production_webhook

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("debug_webhook")

async def test_environment_detection():
    """Test environment detection and webhook setup"""
    # Print all environment variables
    logger.info("=== Environment Variables ===")
    for key, value in os.environ.items():
        if key.lower() in ["environment", "webhook_base_url", "telegram_bot_token", "telegram_webhook_secret"]:
            # Mask sensitive values
            if key.lower() == "telegram_bot_token" and value:
                masked_value = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
                logger.info(f"{key}: {masked_value}")
            elif key.lower() == "telegram_webhook_secret" and value:
                logger.info(f"{key}: ***")
            else:
                logger.info(f"{key}: {value}")
    
    # Test environment detection
    environment = os.getenv("ENVIRONMENT", "development").lower()
    logger.info(f"Detected environment: {environment}")
    
    # Test webhook base URL
    base_url = os.getenv("WEBHOOK_BASE_URL")
    logger.info(f"Webhook base URL: {base_url}")
    
    # Test production webhook setup (with dummy token)
    if environment == "production" and base_url:
        logger.info("Testing production webhook setup...")
        dummy_token = "dummy_token"  # Don't use a real token for testing
        success, message, webhook_url = await setup_production_webhook(
            bot_token=dummy_token,
            base_url=base_url,
            webhook_path="/webhook",
            secret_token=None
        )
        logger.info(f"Production webhook setup result: success={success}, message={message}, url={webhook_url}")
    else:
        logger.info("Not in production environment or missing base URL, skipping webhook setup test")

async def main():
    """Main function"""
    logger.info("Starting webhook debug script")
    await test_environment_detection()
    logger.info("Webhook debug script completed")

if __name__ == "__main__":
    asyncio.run(main())
