import os
import sys
import tempfile
from pathlib import Path

# Isolated database and no background noise for tests.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DRILLING_SIM_ENABLED"] = "0"
os.environ["SOILGRIDS_ENABLED"] = "0"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["NWIS_UPLOAD_DIR"] = f"{_tmp}/uploads"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
