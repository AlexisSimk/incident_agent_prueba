# config/settings.py
from pathlib import Path
import os


def _resolve_base_data_path() -> Path:
    env_path = os.getenv("DATA_BASE_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "datos").resolve()


def _resolve_sub_path(env_var: str, default: Path) -> Path:
    env_path = os.getenv(env_var)
    if env_path:
        return Path(env_path).expanduser().resolve()
    return default.resolve()


# --- Rutas de Datos ---
BASE_DATA_PATH = _resolve_base_data_path()
CV_PATH = _resolve_sub_path("DATA_CV_PATH", BASE_DATA_PATH / "cv")
DAILY_DATA_PATH = _resolve_sub_path("DATA_DAILY_PATH", BASE_DATA_PATH / "daily_files")
FEEDBACK_PATH = _resolve_sub_path("DATA_FEEDBACK_PATH", BASE_DATA_PATH / "feedback")
DAILY_DATA_PATH_TEMPLATE = "{date_str}_20_00_UTC"


# --- Nombres de Archivos ---
FILES_JSON = "files.json"
FILES_LAST_WEEKDAY_JSON = "files_last_weekday.json"
CV_MD_TEMPLATE = "{source_id}_native.md"


# --- Configuración del Agente ADK ---
AGENT_MODEL = os.getenv("AGENT_MODEL", "gemini-2.5-flash")  # Gemini por defecto
APP_NAME = os.getenv("APP_NAME", "incident_detection_agent")
USER_ID = os.getenv("USER_ID", "ops_team")

# --- Configuración de APIs ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# --- Modelos disponibles ---
AVAILABLE_MODELS = {
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "gemini": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
}