#!/usr/bin/env python3

import asyncio
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import psutil
import typer
from dotenv import load_dotenv

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.ngrok_utils import setup_ngrok_webhook

app = typer.Typer(help="Development startup script for Telegram Agent")


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return False
        except OSError:
            return True


def find_free_port(start_port: int = 8000, max_attempts: int = 10) -> int:
    """Find a free port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        if not is_port_in_use(port):
            return port
    raise RuntimeError(f"Could not find a free port in range {start_port}-{start_port + max_attempts}")


def kill_processes_on_port(port: int) -> int:
    """Kill processes using the specified port."""
    killed_count = 0
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            # Get connections separately to handle processes that don't have them
            connections = proc.connections()
            if connections:
                for conn in connections:
                    if hasattr(conn, 'laddr') and conn.laddr and conn.laddr.port == port:
                        typer.echo(f"🔥 Killing process {proc.info['name']} (PID: {proc.info['pid']}) using port {port}")
                        proc.kill()
                        killed_count += 1
                        break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, AttributeError, OSError):
            pass
    return killed_count


def get_port_info(port: int) -> Tuple[bool, str]:
    """Get information about what's using a port."""
    if not is_port_in_use(port):
        return False, "Port is free"
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Get connections separately to handle processes that don't have them
            connections = proc.connections()
            if connections:
                for conn in connections:
                    if hasattr(conn, 'laddr') and conn.laddr and conn.laddr.port == port:
                        cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                        return True, f"Process: {proc.info['name']} (PID: {proc.info['pid']}) - {cmdline[:100]}..."
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, AttributeError, OSError):
            pass
    
    return True, "Port in use by unknown process"


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
    auto_port: bool = typer.Option(True, help="Automatically find free port if specified port is in use"),
    kill_existing: bool = typer.Option(False, help="Kill existing processes on the port"),
):
    """Start the development environment with FastAPI server and ngrok tunnel."""
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        typer.echo("🚀 Starting Telegram Agent development environment...")
        
        # Load environment variables
        # Load order (later files override earlier):
        # 1. ~/.env (global user API keys)
        # 2. project .env (project defaults)
        # 3. project .env.local (local overrides)
        home_env = Path.home() / ".env"
        project_env = project_root / ".env"
        env_path = Path(env_file)

        if home_env.exists():
            load_dotenv(home_env, override=False)
            typer.echo(f"📁 Loaded global environment from {home_env}")

        if project_env.exists():
            load_dotenv(project_env, override=True)
            typer.echo(f"📁 Loaded environment from {project_env}")

        if env_path.exists():
            load_dotenv(env_path, override=True)
            typer.echo(f"📁 Loaded environment from {env_file}")
        elif not home_env.exists() and not project_env.exists():
            typer.echo(f"⚠️  Warning: No .env files found, using system environment")
        
        # Get required environment variables
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token and not skip_webhook:
            typer.echo("❌ TELEGRAM_BOT_TOKEN not found in environment")
            raise typer.Exit(1)
        
        # Handle port conflicts
        original_port = port
        try:
            port_in_use, port_info = get_port_info(port)
        except Exception as e:
            typer.echo(f"⚠️  Could not inspect port {port} ({e}); continuing with basic check")
            port_in_use = is_port_in_use(port)
            port_info = "Unknown (permission denied)"
        
        if port_in_use:
            typer.echo(f"⚠️  Port {port} is already in use: {port_info}")
            
            if kill_existing:
                typer.echo(f"🔥 Attempting to kill processes on port {port}...")
                killed = kill_processes_on_port(port)
                if killed > 0:
                    typer.echo(f"✅ Killed {killed} process(es) on port {port}")
                    time.sleep(2)  # Wait for processes to fully terminate
                    if is_port_in_use(port):
                        typer.echo(f"❌ Port {port} is still in use after killing processes")
                        if auto_port:
                            port = find_free_port(original_port + 1)
                            typer.echo(f"🔄 Using alternative port: {port}")
                        else:
                            typer.echo("💡 Try running with --kill-existing or --auto-port flags")
                            raise typer.Exit(1)
                else:
                    typer.echo(f"❌ Could not kill processes on port {port}")
                    if auto_port:
                        port = find_free_port(original_port + 1)
                        typer.echo(f"🔄 Using alternative port: {port}")
                    else:
                        typer.echo("💡 Try running with --auto-port flag to use a different port")
                        raise typer.Exit(1)
            elif auto_port:
                port = find_free_port(original_port + 1)
                typer.echo(f"🔄 Using alternative port: {port}")
            else:
                typer.echo("💡 Options to resolve this:")
                typer.echo(f"   1. Run: python scripts/start_dev.py start --kill-existing")
                typer.echo(f"   2. Run: python scripts/start_dev.py start --auto-port")
                typer.echo(f"   3. Run: python scripts/start_dev.py start --port <different_port>")
                typer.echo(f"   4. Manually kill the process and try again")
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
        
        try:
            fastapi_process = subprocess.Popen(
                uvicorn_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            process_manager.add_process(fastapi_process)
            
            # Wait for FastAPI to start and check if it's running
            typer.echo("⏳ Waiting for FastAPI to start...")
            startup_timeout = 10
            for i in range(startup_timeout):
                if fastapi_process.poll() is not None:
                    # Process has terminated
                    stdout, stderr = fastapi_process.communicate()
                    typer.echo(f"❌ FastAPI server failed to start:")
                    if stderr:
                        typer.echo(f"Error: {stderr}")
                    if stdout:
                        typer.echo(f"Output: {stdout}")
                    raise typer.Exit(1)
                
                # Check if server is responding
                if i >= 3:  # Start checking after 3 seconds
                    try:
                        import httpx
                        # First try root endpoint (simpler)
                        response = httpx.get(f"http://localhost:{port}/", timeout=2)
                        if response.status_code == 200:
                            typer.echo("✅ FastAPI server is running")
                            # Now try health endpoint
                            try:
                                health_response = httpx.get(f"http://localhost:{port}/health", timeout=2)
                                if health_response.status_code == 200:
                                    health_data = health_response.json()
                                    if health_data.get("status") in ["healthy", "degraded"]:
                                        typer.echo(f"🌡️  Health check: {health_data.get('status', 'unknown')}")
                                    else:
                                        typer.echo("⚠️  Health check returned unexpected status")
                                else:
                                    typer.echo(f"⚠️  Health endpoint returned {health_response.status_code}")
                            except Exception as e:
                                typer.echo(f"⚠️  Health check failed: {e}")
                            break
                    except Exception:
                        pass  # Server not ready yet
                
                time.sleep(1)
            else:
                # Timeout reached, check if process is still running
                if fastapi_process.poll() is None:
                    typer.echo("⚠️  FastAPI server started but health check failed")
                else:
                    stdout, stderr = fastapi_process.communicate()
                    typer.echo(f"❌ FastAPI server stopped unexpectedly:")
                    if stderr:
                        typer.echo(f"Error: {stderr}")
                    if stdout:
                        typer.echo(f"Output: {stdout}")
                    raise typer.Exit(1)
        
        except FileNotFoundError:
            typer.echo("❌ uvicorn not found. Please install it with: pip install uvicorn")
            raise typer.Exit(1)
        except Exception as e:
            typer.echo(f"❌ Failed to start FastAPI server: {e}")
            raise typer.Exit(1)
        
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
def stop(
    port: int = typer.Option(None, help="Specific port to stop processes on"),
):
    """Stop all development services."""
    typer.echo("🛑 Stopping development environment...")
    
    total_killed = 0
    
    # Kill existing processes
    try:
        from src.utils.ngrok_utils import NgrokManager
        killed = NgrokManager.kill_existing_ngrok_processes()
        if killed > 0:
            typer.echo(f"🔥 Killed {killed} ngrok processes")
            total_killed += killed
    except ImportError:
        typer.echo("⚠️  Could not import NgrokManager, skipping ngrok cleanup")
    
    # Kill uvicorn processes
    killed_uvicorn = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['cmdline'] and any('uvicorn' in arg for arg in proc.info['cmdline']):
                # If specific port is requested, check if this process uses it
                if port is not None:
                    if f'--port {port}' in ' '.join(proc.info['cmdline']) or f'--port={port}' in ' '.join(proc.info['cmdline']):
                        typer.echo(f"🔥 Killing uvicorn process on port {port} (PID: {proc.info['pid']})")
                        proc.kill()
                        killed_uvicorn += 1
                else:
                    typer.echo(f"🔥 Killing uvicorn process (PID: {proc.info['pid']})")
                    proc.kill()
                    killed_uvicorn += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    if killed_uvicorn > 0:
        typer.echo(f"🔥 Killed {killed_uvicorn} uvicorn processes")
        total_killed += killed_uvicorn
    
    # If specific port was requested, also kill any other processes on that port
    if port is not None:
        killed_port = kill_processes_on_port(port)
        total_killed += killed_port
    
    if total_killed > 0:
        typer.echo(f"✅ Development environment stopped ({total_killed} processes killed)")
    else:
        typer.echo("✅ Development environment stopped (no processes found)")


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
    import httpx

    typer.echo("📊 Development Environment Status")
    typer.echo("=" * 60)

    # Check FastAPI server and get health details
    health_data = None
    try:
        response = httpx.get("http://localhost:8000/health", timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            health_status = health_data.get("status", "unknown")
            if health_status == "healthy":
                typer.echo("✅ FastAPI server: Running (healthy)")
            elif health_status == "degraded":
                typer.echo(f"⚠️  FastAPI server: Running (degraded)")
                errors = health_data.get("error_details", {})
                if errors:
                    for key, msg in errors.items():
                        typer.echo(f"   ⚠️  {key}: {msg}")
            else:
                typer.echo(f"❌ FastAPI server: Running ({health_status})")
        else:
            typer.echo(f"⚠️  FastAPI server: Responded with {response.status_code}")
    except Exception:
        typer.echo("❌ FastAPI server: Not running")

    # Check ngrok
    ngrok_url = None
    try:
        response = httpx.get("http://localhost:4040/api/tunnels", timeout=5)
        if response.status_code == 200:
            tunnels = response.json().get("tunnels", [])
            if tunnels:
                typer.echo(f"✅ ngrok: {len(tunnels)} tunnel(s) active")
                for tunnel in tunnels:
                    ngrok_url = tunnel['public_url']
                    typer.echo(f"   🔗 {tunnel['public_url']} -> {tunnel['config']['addr']}")
            else:
                typer.echo("⚠️  ngrok: Running but no tunnels")
        else:
            typer.echo("⚠️  ngrok: API responded with error")
    except Exception:
        typer.echo("❌ ngrok: Not running")

    # Check Telegram webhook (from health data or direct API call)
    typer.echo("-" * 60)
    telegram_status = health_data.get("telegram", {}) if health_data else {}

    if not telegram_status:
        # Try direct check if health endpoint didn't provide it
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            if bot_token:
                resp = httpx.get(f"https://api.telegram.org/bot{bot_token}/getWebhookInfo", timeout=10)
                if resp.status_code == 200:
                    result = resp.json().get("result", {})
                    telegram_status = {
                        "webhook_url": result.get("url"),
                        "webhook_configured": bool(result.get("url")),
                        "pending_updates": result.get("pending_update_count", 0),
                        "last_error": result.get("last_error_message"),
                    }
        except Exception as e:
            typer.echo(f"⚠️  Could not check Telegram webhook: {e}")

    if telegram_status:
        webhook_url = telegram_status.get("webhook_url")
        if webhook_url:
            typer.echo(f"✅ Telegram webhook: Configured")
            typer.echo(f"   🔗 URL: {webhook_url}")

            # Check if webhook URL matches ngrok URL
            if ngrok_url and ngrok_url not in webhook_url:
                typer.echo(f"   ⚠️  WARNING: Webhook URL doesn't match ngrok URL!")
                typer.echo(f"   🔧 Run: python scripts/setup_webhook.py auto-update --port 8000")
        else:
            typer.echo("❌ Telegram webhook: NOT CONFIGURED")
            typer.echo("   🔧 Run: python scripts/setup_webhook.py auto-update --port 8000")

        pending = telegram_status.get("pending_updates", 0)
        if pending > 0:
            typer.echo(f"   📬 Pending updates: {pending}")

        last_error = telegram_status.get("last_error")
        if last_error:
            typer.echo(f"   ❌ Last error: {last_error}")

        bot_username = telegram_status.get("bot_username")
        if bot_username:
            typer.echo(f"   🤖 Bot: @{bot_username}")

        if telegram_status.get("bot_responsive"):
            typer.echo("✅ Bot: Responsive")
        elif telegram_status.get("bot_responsive") is False:
            typer.echo("❌ Bot: Not responding")
    else:
        typer.echo("⚠️  Telegram status: Unknown (no token or API error)")

    typer.echo("-" * 60)

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
