# -*- coding: utf-8 -*-
"""PyInstaller Runtime Hook - Load .env from _internal folder."""

import os
import sys

def _get_internal_env_path():
    """Get the path to .env file inside the bundled app."""
    if getattr(sys, 'frozen', False):
        # Running as a bundled executable
        # _MEIPASS is the temporary folder where PyInstaller extracts files
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        env_path = os.path.join(base_path, '.env')
        if os.path.exists(env_path):
            return env_path
    return None

# Load .env from bundled location
env_path = _get_internal_env_path()
if env_path:
    # Set environment variable so pydantic-settings can find it
    # pydantic-settings looks for .env in current directory by default
    # We'll load it manually using python-dotenv
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=True)
    except ImportError:
        # Fallback: manually parse and set environment variables
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    os.environ[key.strip()] = value.strip()
