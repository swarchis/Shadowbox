"""Keep tests offline: never load the real API key from .env (must run before engine.config is imported)."""
import os

os.environ["SHADOWBOX_NO_DOTENV"] = "1"
os.environ.pop("CRUSOE_API_KEY", None)
