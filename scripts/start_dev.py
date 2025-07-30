#!/usr/bin/env python3

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.ngrok_utils import setup_ngrok_webhook

app = typer.Typer(help="Development startup script for Telegram Agent")


class ProcessManager:
    def __init__(self):
        self.processes = []
        self.ngrok_manager = None
        
    def add_process(self, process):
        self.processes.append(process)
        
    def cleanup(self):
        typer.echo("🔄 Cleaning up processes...")
        for process in self.processes:
            try:
                if process.poll() is None:  # Process is still running
                    process.terminate()
                    process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                typer.echo(f"Error cleaning up process: {e}")
        
        if self.ngrok_manager:
            try:
                self.ngrok_manager.stop_tunnel()
            except Exception as e:
                typer.echo(f"Error stopping ngrok: {e}")


process_manager = ProcessManager()


def signal_handler(signum, frame):
    typer.echo(f"\n🛑 Received signal {signum}, shutting down...")
    process_manager.cleanup()
    sys.exit(0)


@app.command()
def start(
    port: int = typer.Option(8000, help="Port to run the FastAPI server on"),
    ngrok_auth: Optional[str] = typer.Option(None, help="ngrok auth token"),
    skip_ngrok: bool = typer.Option(False, help="Skip ngrok tunnel setup"),
    skip_webhook: bool = typer.Option(False, help="Skip webhook setup"),
    env_file: str = typer.Option(".env.local", help="Environment file to load"),
):
    """Start the development environment with FastAPI server and ngrok tunnel."""
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        typer.echo("🚀 Starting Telegram Agent development environment...")
        
        # Load environment variables
        env_path = Path(env_file)
        if env_path.exists():
            load_dotenv(env_path)
            typer.echo(f"📁 Loaded environment from {env_file}")
        else:
            typer.echo(f"⚠️  Warning: {env_file} not found, using system environment")
        
        # Get required environment variables
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token and not skip_webhook:
            typer.echo("❌ TELEGRAM_BOT_TOKEN not found in environment")
            raise typer.Exit(1)
        
        # Start FastAPI server
        typer.echo(f"🌐 Starting FastAPI server on port {port}...")
        uvicorn_cmd = [
            sys.executable, "-m", "uvicorn",
            "src.main:app",
            "--reload",
            "--port", str(port),
            "--host", "0.0.0.0"
        ]
        
        fastapi_process = subprocess.Popen(uvicorn_cmd)
        process_manager.add_process(fastapi_process)
        
        # Wait for FastAPI to start
        typer.echo("⏳ Waiting for FastAPI to start...")
        time.sleep(3)
        
        if not skip_ngrok:
            # Setup ngrok and webhook
            asyncio.run(setup_development_webhook(
                bot_token=bot_token,
                port=port,
                ngrok_auth=ngrok_auth or os.getenv("NGROK_AUTHTOKEN"),
                skip_webhook=skip_webhook
            ))
        
        typer.echo("✅ Development environment started successfully!")
        typer.echo("\n" + "=" * 60)
        typer.echo("🚀 DEVELOPMENT ENVIRONMENT READY")
        typer.echo(f"📝 FastAPI server: http://localhost:{port}")
        typer.echo(f"📚 API docs: http://localhost:{port}/docs")
        typer.echo(f"🔧 Admin API: http://localhost:{port}/admin/webhook/status")
        typer.echo("🔄 Press Ctrl+C to stop all services")
        typer.echo("=" * 60)
        
        # Keep the script running
        try:
            while True:
                time.sleep(1)
                # Check if FastAPI process is still running
                if fastapi_process.poll() is not None:
                    typer.echo("❌ FastAPI server stopped unexpectedly")
                    break
        except KeyboardInterrupt:
            pass
            
    except Exception as e:
        typer.echo(f"❌ Error starting development environment: {e}")
        raise typer.Exit(1)
    finally:
        process_manager.cleanup()


async def setup_development_webhook(
    bot_token: str,
    port: int,
    ngrok_auth: Optional[str],
    skip_webhook: bool = False
):
    """Setup ngrok tunnel and Telegram webhook."""
    try:
        if skip_webhook:
            typer.echo("⏭️  Skipping webhook setup")
            return
            
        typer.echo("🔗 Setting up ngrok tunnel and webhook...")
        
        success, message, webhook_url = await setup_ngrok_webhook(
            bot_token=bot_token,
            auth_token=ngrok_auth,
            port=port,
            region=os.getenv("NGROK_REGION", "us"),
            tunnel_name=os.getenv("NGROK_TUNNEL_NAME", "telegram-agent"),
            webhook_path="/webhook",
            secret_token=os.getenv("TELEGRAM_WEBHOOK_SECRET")
        )
        
        if success:
            typer.echo(f"✅ Webhook setup successful!")
            
            # Prominent webhook URL display
            typer.echo("\n" + "=" * 60)
            typer.echo("🤖 TELEGRAM WEBHOOK CONFIGURED")
            typer.echo(f"🔗 Webhook URL: {webhook_url}")
            typer.echo(f"🎯 Bot: @toolbuildingape_bot ready to receive messages!")
            typer.echo("=" * 60 + "\n")
            
            # Save webhook URL to environment for other processes
            os.environ["CURRENT_WEBHOOK_URL"] = webhook_url
        else:
            typer.echo(f"❌ Webhook setup failed: {message}")
            
    except Exception as e:
        typer.echo(f"❌ Error setting up webhook: {e}")


@app.command()
def stop():
    """Stop all development services."""
    typer.echo("🛑 Stopping development environment...")
    
    # Kill existing processes
    from src.utils.ngrok_utils import NgrokManager
    killed = NgrokManager.kill_existing_ngrok_processes()
    if killed > 0:
        typer.echo(f"🔥 Killed {killed} ngrok processes")
    
    # Kill uvicorn processes
    import psutil
    killed_uvicorn = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and any('uvicorn' in arg for arg in proc.info['cmdline']):
                proc.kill()
                killed_uvicorn += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if killed_uvicorn > 0:
        typer.echo(f"🔥 Killed {killed_uvicorn} uvicorn processes")
    
    typer.echo("✅ Development environment stopped")


@app.command()
def webhook():
    """Manage webhook settings."""
    typer.echo("🔗 Webhook management - use the FastAPI admin interface at /admin/webhook")
    typer.echo("Available endpoints:")
    typer.echo("  GET    /admin/webhook/status")
    typer.echo("  POST   /admin/webhook/update")
    typer.echo("  POST   /admin/webhook/refresh")
    typer.echo("  DELETE /admin/webhook/")


@app.command()
def status():
    """Check status of development services."""
    import psutil
    import httpx
    
    typer.echo("📊 Development Environment Status")
    typer.echo("=" * 40)
    
    # Check FastAPI server
    try:
        response = httpx.get("http://localhost:8000/health", timeout=5)
        if response.status_code == 200:
            typer.echo("✅ FastAPI server: Running")
        else:
            typer.echo(f"⚠️  FastAPI server: Responded with {response.status_code}")
    except Exception:
        typer.echo("❌ FastAPI server: Not running")
    
    # Check ngrok
    try:
        response = httpx.get("http://localhost:4040/api/tunnels", timeout=5)
        if response.status_code == 200:
            tunnels = response.json().get("tunnels", [])
            if tunnels:
                typer.echo(f"✅ ngrok: {len(tunnels)} tunnel(s) active")
                for tunnel in tunnels:
                    typer.echo(f"   🔗 {tunnel['public_url']} -> {tunnel['config']['addr']}")
            else:
                typer.echo("⚠️  ngrok: Running but no tunnels")
        else:
            typer.echo("⚠️  ngrok: API responded with error")
    except Exception:
        typer.echo("❌ ngrok: Not running")
    
    # Check processes
    running_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline']:
                cmdline = ' '.join(proc.info['cmdline'])
                if 'uvicorn' in cmdline and 'telegram_agent' in cmdline:
                    running_processes.append(f"uvicorn (PID: {proc.info['pid']})")
                elif 'ngrok' in proc.info['name'].lower():
                    running_processes.append(f"ngrok (PID: {proc.info['pid']})")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if running_processes:
        typer.echo(f"🏃 Running processes: {', '.join(running_processes)}")
    else:
        typer.echo("💤 No telegram-agent processes found")


if __name__ == "__main__":
    app()