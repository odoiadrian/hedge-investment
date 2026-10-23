"""Read server-side configuration without exposing credentials to the browser."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)


def credential_fields_present() -> bool:
    # Presence is not validation or a successful connection.
    return all(
        os.getenv(name, "").strip()
        for name in (
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_DEPLOYMENT",
        )
    )
