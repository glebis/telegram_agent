import asyncio
import json
import logging
from typing import Dict, List, Optional, Tuple

import httpx
import psutil
from pyngrok import ngrok
from pyngrok.conf import PyngrokConfig
from pyngrok.exception import PyngrokNgrokError

logger = logging.getLogger(__name__)


class NgrokManager:
    def __init__(
        self,
        auth_token: Optional[str] = None,
        port: int = 8000,
        region: str = "us",
        tunnel_name: str = "telegram-agent",
    ):
        self.auth_token = auth_token
        self.port = port
        self.region = region
        self.tunnel_name = tunnel_name
        self.tunnel = None
        self._config = None
        
    def _get_config(self) -> PyngrokConfig:
        if self._config is None:
            self._config = PyngrokConfig(
                auth_token=self.auth_token,
                region=self.region,
            )
        return self._config

    def start_tunnel(self) -> str:
        try:
            if self.auth_token:
                ngrok.set_auth_token(self.auth_token)
            
            # Create HTTP tunnel
            self.tunnel = ngrok.connect(
                self.port, 
                "http",
                name=self.tunnel_name,
                pyngrok_config=self._get_config()
            )
            
            public_url = self.tunnel.public_url
            logger.info(f"ngrok tunnel started: {public_url}")
            
            # Print prominent URL display
            print("\n" + "=" * 60)
            print("🔗 NGROK TUNNEL ACTIVE")
            print(f"📡 Public URL: {public_url}")
            print(f"🔀 Forwarding: {public_url} -> http://localhost:{self.port}")
            print("=" * 60 + "\n")
            
            return public_url
            
        except PyngrokNgrokError as e:
            logger.error(f"Failed to start ngrok tunnel: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error starting ngrok: {e}")
            raise

    def stop_tunnel(self) -> None:
        try:
            if self.tunnel:
                ngrok.disconnect(self.tunnel.public_url)
                self.tunnel = None
                logger.info("ngrok tunnel stopped")
        except Exception as e:
            logger.error(f"Error stopping ngrok tunnel: {e}")

    def get_tunnel_url(self) -> Optional[str]:
        if self.tunnel:
            return self.tunnel.public_url
        return None

    def is_tunnel_active(self) -> bool:
        return self.tunnel is not None

    def get_tunnel_status(self) -> Dict:
        if not self.tunnel:
            return {"active": False, "url": None}
        
        try:
            # Check if tunnel is still active by querying ngrok API
            tunnels = ngrok.get_tunnels()
            for tunnel in tunnels:
                if tunnel.name == self.tunnel_name:
                    return {
                        "active": True,
                        "url": tunnel.public_url,
                        "name": tunnel.name,
                        "config": tunnel.config,
                    }
        except Exception as e:
            logger.error(f"Error checking tunnel status: {e}")
        
        return {"active": False, "url": None}

    @staticmethod
    def kill_existing_ngrok_processes() -> int:
        killed_count = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if 'ngrok' in proc.info['name'].lower():
                    proc.kill()
                    killed_count += 1
                    logger.info(f"Killed ngrok process: PID {proc.info['pid']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return killed_count

    @staticmethod
    async def get_ngrok_api_tunnels() -> List[Dict]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:4040/api/tunnels")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("tunnels", [])
        except Exception as e:
            logger.error(f"Failed to get ngrok API tunnels: {e}")
        return []

    @staticmethod
    async def get_public_url_from_api(port: int = 8000) -> Optional[str]:
        tunnels = await NgrokManager.get_ngrok_api_tunnels()
        for tunnel in tunnels:
            config = tunnel.get("config", {})
            if config.get("addr") == f"http://localhost:{port}":
                return tunnel.get("public_url")
        return None


class WebhookManager:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    async def set_webhook(self, url: str, secret_token: Optional[str] = None) -> Tuple[bool, str]:
        try:
            data = {"url": url}
            if secret_token:
                data["secret_token"] = secret_token

            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.base_url}/setWebhook", json=data)
                result = response.json()
                
                if result.get("ok"):
                    logger.info(f"Webhook set successfully: {url}")
                    return True, "Webhook set successfully"
                else:
                    error_msg = result.get("description", "Unknown error")
                    logger.error(f"Failed to set webhook: {error_msg}")
                    return False, error_msg
        except Exception as e:
            error_msg = f"Exception setting webhook: {e}"
            logger.error(error_msg)
            return False, error_msg

    async def get_webhook_info(self) -> Dict:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/getWebhookInfo")
                result = response.json()
                
                if result.get("ok"):
                    return result.get("result", {})
                else:
                    logger.error(f"Failed to get webhook info: {result}")
                    return {}
        except Exception as e:
            logger.error(f"Exception getting webhook info: {e}")
            return {}

    async def delete_webhook(self) -> Tuple[bool, str]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.base_url}/deleteWebhook")
                result = response.json()
                
                if result.get("ok"):
                    logger.info("Webhook deleted successfully")
                    return True, "Webhook deleted successfully"
                else:
                    error_msg = result.get("description", "Unknown error")
                    logger.error(f"Failed to delete webhook: {error_msg}")
                    return False, error_msg
        except Exception as e:
            error_msg = f"Exception deleting webhook: {e}"
            logger.error(error_msg)
            return False, error_msg


async def setup_ngrok_webhook(
    bot_token: str,
    auth_token: Optional[str] = None,
    port: int = 8000,
    region: str = "us",
    tunnel_name: str = "telegram-agent",
    webhook_path: str = "/webhook",
    secret_token: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    try:
        # Initialize managers
        ngrok_manager = NgrokManager(auth_token, port, region, tunnel_name)
        webhook_manager = WebhookManager(bot_token)
        
        # Start ngrok tunnel
        public_url = ngrok_manager.start_tunnel()
        webhook_url = f"{public_url}{webhook_path}"
        
        # Set Telegram webhook
        success, message = await webhook_manager.set_webhook(webhook_url, secret_token)
        
        if success:
            return True, f"Webhook setup successful: {webhook_url}", webhook_url
        else:
            # Clean up tunnel on failure
            ngrok_manager.stop_tunnel()
            return False, f"Failed to set webhook: {message}", None
            
    except Exception as e:
        error_msg = f"Failed to setup ngrok webhook: {e}"
        logger.error(error_msg)
        return False, error_msg, None


async def auto_update_webhook_on_restart(
    bot_token: str,
    port: int = 8000,
    webhook_path: str = "/webhook",
    secret_token: Optional[str] = None,
    max_retries: int = 5,
) -> Tuple[bool, str, Optional[str]]:
    for retry in range(max_retries):
        try:
            # Wait for ngrok to be ready
            await asyncio.sleep(2 * (retry + 1))
            
            # Get public URL from ngrok API
            public_url = await NgrokManager.get_public_url_from_api(port)
            
            if public_url:
                webhook_url = f"{public_url}{webhook_path}"
                webhook_manager = WebhookManager(bot_token)
                
                success, message = await webhook_manager.set_webhook(webhook_url, secret_token)
                
                if success:
                    logger.info(f"Auto-updated webhook: {webhook_url}")
                    return True, f"Webhook auto-updated: {webhook_url}", webhook_url
                else:
                    logger.warning(f"Failed to set webhook (retry {retry + 1}): {message}")
            else:
                logger.warning(f"No ngrok tunnel found (retry {retry + 1})")
                
        except Exception as e:
            logger.error(f"Error during auto-update (retry {retry + 1}): {e}")
    
    return False, f"Failed to auto-update webhook after {max_retries} retries", None