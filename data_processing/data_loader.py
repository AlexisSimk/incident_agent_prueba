# data_processing/data_loader.py
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings


class DataLoader:
    """Carga datos necesarios para la ejecución del agente v1."""

    def __init__(
        self,
        base_path: Optional[Path] = None,
        cv_path: Optional[Path] = None,
        daily_path: Optional[Path] = None,
        feedback_path: Optional[Path] = None,
    ) -> None:
        self.base_path = (base_path or settings.BASE_DATA_PATH).expanduser().resolve()
        self.cv_path = (cv_path or settings.CV_PATH).expanduser().resolve()
        self.daily_path = (daily_path or settings.DAILY_DATA_PATH).expanduser().resolve()
        self.feedback_path = (feedback_path or settings.FEEDBACK_PATH).expanduser().resolve()

    def get_all_source_ids(self) -> List[str]:
        if not self.cv_path.exists():
            return []
        return sorted({path.stem.split("_")[0] for path in self.cv_path.glob("*_native.md")})

    def load_cv_data(self, source_id: str) -> Dict[str, Any]:
        cv_path = self.cv_path / settings.CV_MD_TEMPLATE.format(source_id=source_id)
        if not cv_path.exists():
            raise FileNotFoundError(f"No se encontró CV para source {source_id}")

        with cv_path.open("r", encoding="utf-8") as fh:
            content = fh.read()

        return {
            "source_id": source_id,
            "raw_text": content,
        }

    def load_daily_payload(self, execution_date: str) -> Dict[str, Any]:
        folder = settings.DAILY_DATA_PATH_TEMPLATE.format(date_str=execution_date)
        data_dir = self.daily_path / folder
        files_path = data_dir / settings.FILES_JSON
        last_week_path = data_dir / settings.FILES_LAST_WEEKDAY_JSON

        with files_path.open("r", encoding="utf-8") as fh:
            daily_files = json.load(fh)

        with last_week_path.open("r", encoding="utf-8") as fh:
            last_week_files = json.load(fh)

        return {"daily": daily_files, "last_weekday": last_week_files}

    def load_feedback(self) -> List[Dict[str, str]]:
        feedback_path = self.feedback_path / "Feedback - week 9 sept.csv"
        if not feedback_path.exists():
            return []
        with feedback_path.open("r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            return [row for row in reader]

    @staticmethod
    def execution_day(execution_date: str) -> str:
        return datetime.strptime(execution_date, "%Y-%m-%d").strftime("%A").lower()
