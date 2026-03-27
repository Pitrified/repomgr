"""Load environment variables from .env file."""

from pathlib import Path

from dotenv import load_dotenv
from loguru import logger as lg


def load_env() -> None:
    """Load environment variables from .env file."""
    # standard place to store credentials outside of version control and folder
    cred_path = Path.home() / "cred" / "repomgr" / ".env"
    if cred_path.exists():
        load_dotenv(dotenv_path=cred_path)
        lg.debug(f"Loaded environment variables from {cred_path}")
    else:
        lg.debug(f".env file not found at {cred_path}")
