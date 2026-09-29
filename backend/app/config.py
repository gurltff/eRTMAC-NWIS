"""App settings, read from environment variables (see .env.example)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
REPO_DIR = BASE_DIR.parent
DATA_DIR = Path(os.getenv("NWIS_DATA_DIR", REPO_DIR / "data"))
SAMPLES_DIR = DATA_DIR / "samples"
RAW_DIR = DATA_DIR / "raw"
UPLOAD_DIR = Path(os.getenv("NWIS_UPLOAD_DIR", BASE_DIR / "uploads"))

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'nwis.db'}")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-in-production-please")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

# Optional: when set, document extraction uses Claude; otherwise rule-based.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("NWIS_LLM_MODEL", "claude-opus-5-5")

# Live soil lookups (ISRIC SoilGrids). Set to 0 to always use the offline estimate.
SOILGRIDS_ENABLED = os.getenv("SOILGRIDS_ENABLED", "1") == "1"
SOILGRIDS_TIMEOUT_S = float(os.getenv("SOILGRIDS_TIMEOUT_S", "6"))

# Background simulators
DRILLING_SIM_ENABLED = os.getenv("DRILLING_SIM_ENABLED", "1") == "1"
DRILLING_SIM_STEP_M = float(os.getenv("DRILLING_SIM_STEP_M", "3"))
DRILLING_SIM_INTERVAL_S = float(os.getenv("DRILLING_SIM_INTERVAL_S", "4"))

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Study area: Upper Assam and nearby (lat/lon bounding box)
REGION = {"min_lat": 26.2, "max_lat": 27.95, "min_lon": 93.6, "max_lon": 96.2}
