#!/usr/bin/env python3

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.ngrok_utils import WebhookManager, auto_update_webhook_on_restart

app = typer.Typer(help="Webhook setup utility for Telegram Agent")


@app.command()
def set_webhook(
    url: str = typer.Argument(..., help="Webhook URL to set"),
    token: Optional[str] = typer.Option(None, help="Bot token (or use TELEGRAM_BOT_TOKEN env var)"),
    secret: Optional[str] = typer.Option(None, help="Webhook secret token"),
    env_file: str = typer.Option(".env.local", help="Environment file to load"),
):
    """Set the Telegram webhook URL."""
    
    # Load environment variables
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
        typer.echo(f"📁 Loaded environment from {env_file}")
    
    # Get bot token
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        typer.echo("❌ Bot token not provided. Use --token or set TELEGRAM_BOT_TOKEN")
        raise typer.Exit(1)
    
    # Get secret token
    secret_token = secret or os.getenv("TELEGRAM_WEBHOOK_SECRET")
    
    async def _set_webhook():
        webhook_manager = WebhookManager(bot_token)
        success, message = await webhook_manager.set_webhook(url, secret_token)
        
        if success:
            typer.echo(f"✅ Webhook set successfully: {url}")
            if secret_token:
                typer.echo("🔐 Secret token configured")
        else:
            typer.echo(f"❌ Failed to set webhook: {message}")
            raise typer.Exit(1)
    
    asyncio.run(_set_webhook())


@app.command()
def get_webhook(
    token: Optional[str] = typer.Option(None, help="Bot token (or use TELEGRAM_BOT_TOKEN env var)"),
    env_file: str = typer.Option(".env.local", help="Environment file to load"),
):
    """Get current webhook information."""
    
    # Load environment variables
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
    
    # Get bot token
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        typer.echo("❌ Bot token not provided. Use --token or set TELEGRAM_BOT_TOKEN")
        raise typer.Exit(1)
    
    async def _get_webhook():
        webhook_manager = WebhookManager(bot_token)
        info = await webhook_manager.get_webhook_info()
        
        if info:
            typer.echo("📊 Current Webhook Info:")
            typer.echo(f"   URL: {info.get('url', 'Not set')}")
            typer.echo(f"   Has custom certificate: {info.get('has_custom_certificate', False)}")
            typer.echo(f"   Pending updates: {info.get('pending_update_count', 0)}")
            typer.echo(f"   Last error date: {info.get('last_error_date', 'None')}")
            typer.echo(f"   Last error message: {info.get('last_error_message', 'None')}")
            typer.echo(f"   Max connections: {info.get('max_connections', 'Default')}")
            typer.echo(f"   Allowed updates: {info.get('allowed_updates', 'All')}")
        else:
            typer.echo("❌ Failed to get webhook info")
            raise typer.Exit(1)
    
    asyncio.run(_get_webhook())


@app.command()
def delete_webhook(
    token: Optional[str] = typer.Option(None, help="Bot token (or use TELEGRAM_BOT_TOKEN env var)"),
    env_file: str = typer.Option(".env.local", help="Environment file to load"),
):
    """Delete the current webhook."""
    
    # Load environment variables
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
    
    # Get bot token
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        typer.echo("❌ Bot token not provided. Use --token or set TELEGRAM_BOT_TOKEN")
        raise typer.Exit(1)
    
    async def _delete_webhook():
        webhook_manager = WebhookManager(bot_token)
        success, message = await webhook_manager.delete_webhook()
        
        if success:
            typer.echo("✅ Webhook deleted successfully")
        else:
            typer.echo(f"❌ Failed to delete webhook: {message}")
            raise typer.Exit(1)
    
    asyncio.run(_delete_webhook())


@app.command()
def auto_update(
    port: int = typer.Option(8000, help="Port where your app is running"),
    webhook_path: str = typer.Option("/webhook", help="Webhook endpoint path"),
    token: Optional[str] = typer.Option(None, help="Bot token (or use TELEGRAM_BOT_TOKEN env var)"),
    secret: Optional[str] = typer.Option(None, help="Webhook secret token"),
    max_retries: int = typer.Option(5, help="Maximum number of retries"),
    env_file: str = typer.Option(".env.local", help="Environment file to load"),
):
    """Auto-detect ngrok URL and update webhook."""
    
    # Load environment variables
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
        typer.echo(f"📁 Loaded environment from {env_file}")
    
    # Get bot token
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        typer.echo("❌ Bot token not provided. Use --token or set TELEGRAM_BOT_TOKEN")
        raise typer.Exit(1)
    
    # Get secret token
    secret_token = secret or os.getenv("TELEGRAM_WEBHOOK_SECRET")
    
    async def _auto_update():
        typer.echo(f"🔍 Looking for ngrok tunnel on port {port}...")
        
        success, message, webhook_url = await auto_update_webhook_on_restart(
            bot_token=bot_token,
            port=port,
            webhook_path=webhook_path,
            secret_token=secret_token,
            max_retries=max_retries,
        )
        
        if success:
            typer.echo(f"✅ Webhook auto-updated successfully!")
            typer.echo(f"🔗 Webhook URL: {webhook_url}")
        else:
            typer.echo(f"❌ Auto-update failed: {message}")
            raise typer.Exit(1)
    
    asyncio.run(_auto_update())


@app.command()
def test_webhook(
    url: str = typer.Argument(..., help="Webhook URL to test"),
    method: str = typer.Option("POST", help="HTTP method to use"),
):
    """Test if a webhook URL is reachable."""
    import httpx
    
    async def _test_webhook():
        try:
            async with httpx.AsyncClient() as client:
                typer.echo(f"🧪 Testing webhook: {url}")
                
                # Send a test request
                if method.upper() == "GET":
                    response = await client.get(url, timeout=10)
                else:
                    # Send a minimal test payload
                    test_payload = {"test": True}
                    response = await client.post(url, json=test_payload, timeout=10)
                
                typer.echo(f"📊 Response Status: {response.status_code}")
                typer.echo(f"📊 Response Headers: {dict(response.headers)}")
                
                if response.status_code < 400:
                    typer.echo("✅ Webhook URL is reachable")
                else:
                    typer.echo(f"⚠️  Webhook returned error status: {response.status_code}")
                    
        except httpx.TimeoutException:
            typer.echo("❌ Webhook test timed out")
            raise typer.Exit(1)
        except httpx.ConnectError:
            typer.echo("❌ Could not connect to webhook URL")
            raise typer.Exit(1)
        except Exception as e:
            typer.echo(f"❌ Webhook test failed: {e}")
            raise typer.Exit(1)
    
    asyncio.run(_test_webhook())


@app.command()
def validate_bot(
    token: Optional[str] = typer.Option(None, help="Bot token (or use TELEGRAM_BOT_TOKEN env var)"),
    env_file: str = typer.Option(".env.local", help="Environment file to load"),
):
    """Validate bot token and get bot information."""
    import httpx
    
    # Load environment variables
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
    
    # Get bot token
    bot_token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        typer.echo("❌ Bot token not provided. Use --token or set TELEGRAM_BOT_TOKEN")
        raise typer.Exit(1)
    
    async def _validate_bot():
        try:
            async with httpx.AsyncClient() as client:
                url = f"https://api.telegram.org/bot{bot_token}/getMe"
                response = await client.get(url, timeout=10)
                result = response.json()
                
                if result.get("ok"):
                    bot_info = result["result"]
                    typer.echo("✅ Bot token is valid!")
                    typer.echo("🤖 Bot Information:")
                    typer.echo(f"   ID: {bot_info.get('id')}")
                    typer.echo(f"   Username: @{bot_info.get('username')}")
                    typer.echo(f"   First Name: {bot_info.get('first_name')}")
                    typer.echo(f"   Can join groups: {bot_info.get('can_join_groups')}")
                    typer.echo(f"   Can read all group messages: {bot_info.get('can_read_all_group_messages')}")
                    typer.echo(f"   Supports inline queries: {bot_info.get('supports_inline_queries')}")
                else:
                    error_msg = result.get("description", "Unknown error")
                    typer.echo(f"❌ Bot token is invalid: {error_msg}")
                    raise typer.Exit(1)
                    
        except Exception as e:
            typer.echo(f"❌ Failed to validate bot token: {e}")
            raise typer.Exit(1)
    
    asyncio.run(_validate_bot())


if __name__ == "__main__":
    app()