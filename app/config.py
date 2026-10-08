from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(
    os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "database" / "bordercare.db"))
)

PROJECT_NAME = "BorderCare AI"
SIMULATION_MODE = True

