import sys
from pathlib import Path

# Add services/api to sys.path so we can import continuum_api
services_api_path = str(Path(__file__).parent.parent / "services" / "api")
if services_api_path not in sys.path:
    sys.path.insert(0, services_api_path)

from continuum_api.main import app

# Vercel will use 'app' as the ASGI entry point
__all__ = ["app"]
