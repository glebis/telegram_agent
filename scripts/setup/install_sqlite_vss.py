#!/usr/bin/env python3
"""
SQLite VSS Extension Installer

This script downloads and installs the SQLite VSS extension
for vector similarity search capabilities in the Telegram Agent.

The extension enables efficient similarity search for image embeddings.
"""

import argparse
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("sqlite-vss-installer")

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
EXTENSION_DIR = PROJECT_ROOT / "extensions"
TEMP_DIR = Path(tempfile.mkdtemp(prefix="sqlite-vss-"))

# GitHub release info
GITHUB_REPO = "asg017/sqlite-vss"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def check_prerequisites():
    """Check if SQLite is installed and get version."""
    try:
        result = subprocess.run(
            ["sqlite3", "--version"], 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        sqlite_version = result.stdout.strip().split()[0]
        logger.info(f"Found SQLite version: {sqlite_version}")
        return True
    except subprocess.CalledProcessError:
        logger.error("SQLite3 not found. Please install SQLite3 before continuing.")
        return False
    except Exception as e:
        logger.error(f"Error checking SQLite version: {e}")
        return False


def get_platform_info():
    """Get platform information to determine which binary to download."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    if system == "darwin":
        if machine in ["arm64", "aarch64"]:
            return "macos-aarch64"
        else:
            return "macos-x86_64"
    elif system == "linux":
        if machine in ["arm64", "aarch64"]:
            return "linux-aarch64"
        else:
            return "linux-x86_64"
    elif system == "windows":
        return "windows-x86_64"
    else:
        return None


def download_prebuilt_extension():
    """Download pre-built SQLite VSS extension."""
    platform_id = get_platform_info()
    if not platform_id:
        logger.error(f"Unsupported platform: {platform.system()} {platform.machine()}")
        return False
    
    logger.info(f"Detected platform: {platform_id}")
    
    try:
        # Get latest release info
        logger.info(f"Fetching latest release info from GitHub: {GITHUB_REPO}")
        with urllib.request.urlopen(GITHUB_API_URL) as response:
            release_info = json.loads(response.read().decode())
        
        # Find the asset for our platform
        asset_url = None
        asset_name = None
        for asset in release_info.get("assets", []):
            name = asset.get("name", "")
            if platform_id in name and name.endswith(".tar.gz"):
                asset_url = asset.get("browser_download_url")
                asset_name = name
                break
        
        if not asset_url:
            logger.error(f"Could not find release asset for platform: {platform_id}")
            return False
        
        # Download the asset
        logger.info(f"Downloading {asset_name} from {asset_url}")
        archive_path = TEMP_DIR / asset_name
        urllib.request.urlretrieve(asset_url, archive_path)
        
        # Extract the archive
        logger.info(f"Extracting {asset_name}")
        extract_dir = TEMP_DIR / "extract"
        extract_dir.mkdir(exist_ok=True)
        
        if sys.platform == "win32":
            # Use 7-zip on Windows
            subprocess.run(
                ["7z", "x", str(archive_path), f"-o{extract_dir}"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            # Use tar on Unix-like systems
            subprocess.run(
                ["tar", "-xzf", str(archive_path), "-C", str(extract_dir)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        
        return extract_dir
    
    except Exception as e:
        logger.error(f"Error downloading pre-built extension: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def install_extensions(extract_dir):
    """Install the SQLite VSS and Vector extensions."""
    logger.info("Installing SQLite extensions...")
    
    # Create extension directory if it doesn't exist
    EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
    
    # Determine the extension file extensions based on platform
    system = platform.system().lower()
    if system == "darwin":
        file_ext = ".dylib"
    elif system == "linux":
        file_ext = ".so"
    elif system == "windows":
        file_ext = ".dll"
    else:
        logger.error(f"Unsupported platform: {system}")
        return False
    
    # Extensions to install (in order)
    extensions = ["vector0", "vss0"]
    installed = []
    
    for ext_name in extensions:
        ext_file = f"{ext_name}{file_ext}"
        
        # Find the extension file in the extracted directory
        extension_paths = list(extract_dir.glob(f"**/{ext_file}"))
        
        if not extension_paths:
            logger.warning(f"Extension file {ext_file} not found in extracted directory: {extract_dir}")
            # Try to download from another release if not found
            if not download_additional_extension(ext_name):
                if ext_name == "vector0":
                    # Vector0 is required for VSS0
                    logger.error(f"Required extension {ext_name} could not be installed")
                    return False
                else:
                    logger.warning(f"Extension {ext_name} could not be installed but continuing")
                    continue
            
            # If we successfully downloaded the additional extension, it's already installed
            installed.append(ext_name)
            continue
        
        source_path = extension_paths[0]
        dest_path = EXTENSION_DIR / ext_file
        
        # Copy the extension file
        try:
            shutil.copy2(str(source_path), str(dest_path))
            logger.info(f"Extension {ext_name} installed to: {dest_path}")
            installed.append(ext_name)
        except Exception as e:
            logger.error(f"Failed to install extension {ext_name}: {e}")
            if ext_name == "vector0":
                # Vector0 is required for VSS0
                return False
    
    if installed:
        logger.info(f"Successfully installed extensions: {', '.join(installed)}")
        return True
    else:
        logger.error("No extensions were installed")
        return False


def download_additional_extension(ext_name):
    """Download an additional extension that wasn't found in the main package."""
    logger.info(f"Attempting to download {ext_name} extension separately...")
    
    # For vector0, we need to get it from sqlite-vector repo
    if ext_name == "vector0":
        repo = "asg017/sqlite-vector"
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        platform_id = get_platform_info()
        
        try:
            # Get latest release info
            logger.info(f"Fetching latest release info from GitHub: {repo}")
            with urllib.request.urlopen(api_url) as response:
                release_info = json.loads(response.read().decode())
            
            # Find the asset for our platform
            asset_url = None
            asset_name = None
            for asset in release_info.get("assets", []):
                name = asset.get("name", "")
                if platform_id in name and name.endswith(".tar.gz"):
                    asset_url = asset.get("browser_download_url")
                    asset_name = name
                    break
            
            if not asset_url:
                logger.error(f"Could not find release asset for platform: {platform_id}")
                return False
            
            # Download the asset
            logger.info(f"Downloading {asset_name} from {asset_url}")
            archive_path = TEMP_DIR / asset_name
            urllib.request.urlretrieve(asset_url, archive_path)
            
            # Extract the archive
            logger.info(f"Extracting {asset_name}")
            extract_dir = TEMP_DIR / f"extract_{ext_name}"
            extract_dir.mkdir(exist_ok=True)
            
            if sys.platform == "win32":
                # Use 7-zip on Windows
                subprocess.run(
                    ["7z", "x", str(archive_path), f"-o{extract_dir}"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            else:
                # Use tar on Unix-like systems
                subprocess.run(
                    ["tar", "-xzf", str(archive_path), "-C", str(extract_dir)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            
            # Determine file extension based on platform
            system = platform.system().lower()
            if system == "darwin":
                file_ext = ".dylib"
            elif system == "linux":
                file_ext = ".so"
            elif system == "windows":
                file_ext = ".dll"
            else:
                logger.error(f"Unsupported platform: {system}")
                return False
            
            # Find the extension file
            ext_file = f"{ext_name}{file_ext}"
            extension_paths = list(extract_dir.glob(f"**/{ext_file}"))
            
            if not extension_paths:
                logger.error(f"Extension file {ext_file} not found in extracted directory: {extract_dir}")
                return False
            
            # Copy the extension file
            source_path = extension_paths[0]
            dest_path = EXTENSION_DIR / ext_file
            
            shutil.copy2(str(source_path), str(dest_path))
            logger.info(f"Extension {ext_name} installed to: {dest_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading {ext_name} extension: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    return False


def update_config():
    """Update the application configuration to use the extension."""
    logger.info("Updating application configuration...")
    
    # Create .env file if it doesn't exist
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        with open(env_file, "w") as f:
            f.write("# Environment variables for Telegram Agent\n")
    
    # Read existing .env file
    with open(env_file, "r") as f:
        lines = f.readlines()
    
    # Check if SQLITE_EXTENSIONS_PATH is already set
    extensions_path_set = False
    for i, line in enumerate(lines):
        if line.startswith("SQLITE_EXTENSIONS_PATH="):
            lines[i] = f"SQLITE_EXTENSIONS_PATH={EXTENSION_DIR}\n"
            extensions_path_set = True
            break
    
    # Add SQLITE_EXTENSIONS_PATH if not set
    if not extensions_path_set:
        lines.append(f"SQLITE_EXTENSIONS_PATH={EXTENSION_DIR}\n")
    
    # Write updated .env file
    with open(env_file, "w") as f:
        f.writelines(lines)
    
    logger.info(f"Updated .env file with SQLITE_EXTENSIONS_PATH={EXTENSION_DIR}")
    return True


def test_extensions():
    """Test if the SQLite VSS and Vector extensions can be loaded."""
    logger.info("Testing SQLite extensions...")
    
    test_script = """
import sqlite3
import os

# Get extension path from environment variable
extensions_path = os.environ.get('SQLITE_EXTENSIONS_PATH', './extensions')

# Connect to in-memory database
conn = sqlite3.connect(':memory:')
conn.enable_load_extension(True)

# Load vector0 extension first
try:
    vector0_path = os.path.join(extensions_path, 'vector0')
    conn.load_extension(vector0_path)
    print("Vector0 extension loaded successfully!")
    
    # Test creating a vector table
    conn.execute("CREATE VIRTUAL TABLE vector_test USING vector0(embedding(384))")
    print("Created vector test table successfully!")
    
    # Now load vss0 extension
    vss0_path = os.path.join(extensions_path, 'vss0')
    conn.load_extension(vss0_path)
    print("VSS0 extension loaded successfully!")
    
    # Test creating a vss table
    conn.execute("CREATE VIRTUAL TABLE vss_test USING vss0(embedding(384))")
    print("Created VSS test table successfully!")
    
    # Test inserting a vector
    conn.execute("INSERT INTO vector_test(embedding) VALUES (json_array(1,2,3,4))")
    print("Inserted test vector successfully!")
    
    conn.close()
    exit(0)
except sqlite3.OperationalError as e:
    print(f"Error loading or using extensions: {e}")
    conn.close()
    exit(1)
"""
    
    # Create a temporary test script
    test_script_path = TEMP_DIR / "test_vss.py"
    with open(test_script_path, "w") as f:
        f.write(test_script)
    
    # Set environment variable for the test
    env = os.environ.copy()
    env["SQLITE_EXTENSIONS_PATH"] = str(EXTENSION_DIR)
    
    # Run the test script
    try:
        result = subprocess.run(
            [sys.executable, str(test_script_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        logger.info(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Test failed: {e}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        return False
    finally:
        # Clean up test script
        test_script_path.unlink(missing_ok=True)


def update_vector_db_code():
    """Update the vector_db.py code to use the environment variable for extension path."""
    vector_db_path = PROJECT_ROOT / "src" / "core" / "vector_db.py"
    
    if not vector_db_path.exists():
        logger.error(f"Vector DB file not found: {vector_db_path}")
        return False
    
    with open(vector_db_path, "r") as f:
        content = f.read()
    
    # Check if we need to update the code
    if "os.environ.get('SQLITE_EXTENSIONS_PATH')" in content:
        logger.info("Vector DB code already updated to use environment variable.")
        return True
    
    # Update the code to use the environment variable
    updated_content = content.replace(
        "await db.execute(\"SELECT load_extension('vss0')\")\n",
        """extension_path = os.environ.get('SQLITE_EXTENSIONS_PATH', './extensions')
                    extension_file = os.path.join(extension_path, 'vss0')
                    await db.execute(f"SELECT load_extension('{extension_file}')")
"""
    )
    
    # Add os import if not present
    if "import os" not in updated_content:
        updated_content = updated_content.replace(
            "import logging",
            "import logging\nimport os"
        )
    
    # Write updated content
    with open(vector_db_path, "w") as f:
        f.write(updated_content)
    
    logger.info("Updated vector_db.py to use environment variable for extension path.")
    return True


def cleanup():
    """Clean up temporary files."""
    try:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        logger.info(f"Cleaned up temporary directory: {TEMP_DIR}")
    except Exception as e:
        logger.warning(f"Failed to clean up temporary directory: {e}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="SQLite VSS Extension Installer")
    parser.add_argument("--skip-tests", action="store_true", help="Skip testing the extension")
    args = parser.parse_args()
    
    logger.info("Starting SQLite VSS extension installation...")
    
    try:
        # Check prerequisites
        if not check_prerequisites():
            return 1
        
        # Download pre-built extension
        extract_dir = download_prebuilt_extension()
        if not extract_dir:
            return 1
        
        # Install extensions
        if not install_extensions(extract_dir):
            return 1
        
        # Update configuration
        if not update_config():
            return 1
        
        # Update vector_db.py code
        if not update_vector_db_code():
            return 1
        
        # Test extensions
        if not args.skip_tests:
            try:
                test_extensions()
            except Exception as e:
                logger.warning(f"Extension test failed, but installation may still be usable: {e}")
        
        logger.info("SQLite VSS extension installation completed successfully!")
        logger.info(f"Extensions installed to: {EXTENSION_DIR}")
        logger.info("Please restart your application for the changes to take effect.")
        
        return 0
    
    finally:
        cleanup()


if __name__ == "__main__":
    sys.exit(main())
