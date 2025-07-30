#!/usr/bin/env python3
"""
Simple script to check what's using a specific port.
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.start_dev import get_port_info, is_port_in_use, kill_processes_on_port
import typer

app = typer.Typer(help="Port checking utility")


@app.command()
def check(port: int = typer.Argument(8000, help="Port to check")):
    """Check what's using a specific port."""
    in_use, info = get_port_info(port)
    
    if in_use:
        typer.echo(f"🚨 Port {port} is in use:")
        typer.echo(f"   {info}")
    else:
        typer.echo(f"✅ Port {port} is free")


@app.command()
def kill(port: int = typer.Argument(8000, help="Port to kill processes on")):
    """Kill processes using a specific port."""
    in_use, info = get_port_info(port)
    
    if not in_use:
        typer.echo(f"✅ Port {port} is already free")
        return
    
    typer.echo(f"🚨 Port {port} is in use: {info}")
    
    if typer.confirm(f"Kill processes using port {port}?"):
        killed = kill_processes_on_port(port)
        if killed > 0:
            typer.echo(f"✅ Killed {killed} process(es)")
        else:
            typer.echo("❌ No processes were killed")
    else:
        typer.echo("❌ Cancelled")


@app.command()
def scan(
    start: int = typer.Argument(8000, help="Start port"),
    end: int = typer.Argument(8010, help="End port")
):
    """Check a range of ports."""
    typer.echo(f"🔍 Checking ports {start}-{end}:")
    
    for port in range(start, end + 1):
        in_use = is_port_in_use(port)
        status = "🚨 IN USE" if in_use else "✅ FREE"
        typer.echo(f"   Port {port}: {status}")


if __name__ == "__main__":
    app()
