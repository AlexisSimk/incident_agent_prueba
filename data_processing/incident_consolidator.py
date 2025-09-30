"""Prepara dataset estructurado para que el LLM analice incidencias."""

from datetime import datetime, timedelta
import re
from typing import Any, Dict, List, Optional


def _parse_filename_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    filename = (item.get("filename") or "").split("/")[-1]
    meta: Dict[str, Any] = {"filename": filename}

    date_token = None
    date_match = re.search(r"(\d{4})[\-_]?(\d{2})[\-_]?(\d{2})", filename)
    if date_match:
        year, month, day = date_match.groups()
        date_token = f"{year}{month}{day}"

    meta["date_token"] = date_token
    if date_token and len(date_token) == 8:
        try:
            meta["coverage_date"] = datetime.strptime(date_token, "%Y%m%d").date().isoformat()
        except ValueError:
            meta["coverage_date"] = None

    core = _normalize_filename(filename) or filename
    meta["pattern"] = core

    entity = core
    if "_" in core:
        tokens = core.split("_")
        if len(tokens) >= 2:
            entity = "_".join(tokens[:2])
    if "__" in filename:
        entity_part = filename.split("__", 1)[1]
        tokens = entity_part.split("_")
        if len(tokens) >= 2:
            entity = "_".join(tokens[:2])
        elif tokens:
            entity = tokens[0]
    meta["entity"] = entity
    meta["uploaded_at"] = item.get("uploaded_at")
    return meta


def _build_pattern_map(files: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    mapping: Dict[str, List[Dict[str, Any]]] = {}
    for file in files:
        meta = _parse_filename_metadata(file)
        pattern = meta.get("pattern")
        if not pattern:
            continue
        mapping.setdefault(pattern, []).append({"file": file, "meta": meta})
    return mapping


def _format_window(entries: List[Dict[str, Any]]) -> Optional[str]:
    times = []
    for entry in entries:
        uploaded_at = entry["file"].get("uploaded_at")
        if not uploaded_at:
            continue
        try:
            times.append(datetime.fromisoformat(uploaded_at.replace("Z", "+00:00")).time())
        except ValueError:
            continue
    if not times:
        return None
    start = min(times)
    end = max(times)
    if start == end:
        return f"{start.strftime('%H:%M')} UTC"
    return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} UTC"


class IncidentConsolidator:
    """Agrupa información mínima por fuente."""

    def __init__(self, execution_date: str) -> None:
        self.execution_date = execution_date

    def build_dataset(self, source_ids: List[str], loader) -> Dict[str, Dict[str, Any]]:
        dataset: Dict[str, Dict[str, Any]] = {}
        payload = loader.load_daily_payload(self.execution_date)

        for source_id in source_ids:
            cv_data = loader.load_cv_data(source_id)
            raw_daily = payload.get("daily", {}).get(source_id, [])

            daily_files = _filter_files_by_date(raw_daily, self.execution_date)
            incidents = detect_incidents(
                source_id=source_id,
                cv_text=cv_data.get("raw_text", ""),
                daily_files=daily_files,
                last_week_files=payload.get("last_weekday", {}).get(source_id, []),
                execution_date=self.execution_date,
            )

            dataset[source_id] = {
                "cv_text": cv_data.get("raw_text", ""),
                "daily_files": daily_files,
                "last_week_files": payload.get("last_weekday", {}).get(source_id, []),
                "incidents": incidents,
            }

        return dataset


def _filter_files_by_date(files: List[Dict[str, Any]], execution_date: str) -> List[Dict[str, Any]]:
    if not files:
        return []

    try:
        target_date = datetime.fromisoformat(execution_date).date()
    except ValueError:
        return files

    filtered: List[Dict[str, Any]] = []
    for item in files:
        uploaded_at = item.get("uploaded_at")
        if not uploaded_at:
            continue
        try:
            uploaded_date = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if uploaded_date == target_date:
            filtered.append(item)

    return filtered


def detect_incidents(
    source_id: str,
    cv_text: str,
    daily_files: List[Dict[str, Any]],
    last_week_files: List[Dict[str, Any]],
    execution_date: str,
) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "missing": _detect_missing_files(source_id, cv_text, daily_files, last_week_files, execution_date),
        "duplicated": _detect_duplicates(daily_files),
        "empty": _detect_unexpected_empty(cv_text, daily_files, execution_date),
        "volume_variation": _detect_volume_variation(cv_text, daily_files, last_week_files, execution_date),
        "schedule": _detect_schedule_anomaly(cv_text, daily_files, execution_date),
        "historical": _detect_historical_uploads(daily_files, execution_date),
    }


def _detect_missing_files(
    source_id: str,
    cv_text: str,
    daily_files: List[Dict[str, Any]],
    last_week_files: List[Dict[str, Any]],
    execution_date: str,
) -> List[Dict[str, Any]]:
    """Proporciona datos descriptivos puros sobre archivos - SIN decidir qué es 'missing'"""
    
    # Solo proporcionar datos crudos para que el LLM decida
    return [
        {
            "type": "file_comparison_data",
            "execution_date": execution_date,
            "daily_files_summary": [
                {
                    "filename": f.get("filename"),
                    "uploaded_at": f.get("uploaded_at"),
                    "coverage_date": f.get("coverage_date"),
                    "rows": f.get("rows", 0),
                    "entity": f.get("entity"),
                    "status": f.get("status")
                } for f in daily_files
            ],
            "last_week_files_summary": [
                {
                    "filename": f.get("filename"),
                    "uploaded_at": f.get("uploaded_at"),
                    "coverage_date": f.get("coverage_date"),
                    "rows": f.get("rows", 0),
                    "entity": f.get("entity"),
                    "status": f.get("status")
                } for f in last_week_files
            ],
            "note": "LLM should analyze CV patterns and decide what files are expected vs actually missing based on day of week, lag rules, etc."
        }
    ]


def _detect_duplicates(daily_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flagged: List[str] = []
    seen: Dict[str, int] = {}

    for item in daily_files:
        filename = item.get("filename")
        if not filename:
            continue

        status = (item.get("status") or "").lower()
        if item.get("is_duplicated") or status == "stopped":
            flagged.append(filename)

        seen[filename] = seen.get(filename, 0) + 1

    repeated = [name for name, count in seen.items() if count > 1]

    if flagged or repeated:
        all_files = sorted(set(flagged + repeated))
        return [
            {
                "type": "duplicated_or_failed_data",
                "files": all_files,
                "note": "LLM should evaluate if duplicates/failures are critical based on CV and business rules"
            }
        ]

    return []


def _detect_unexpected_empty(cv_text: str, daily_files: List[Dict[str, Any]], execution_date: str) -> List[Dict[str, Any]]:
    """Extrae datos crudos sobre archivos vacíos - SIN clasificar severidad"""
    empty_files = [item for item in daily_files if (item.get("rows") or 0) == 0]
    if not empty_files:
        return []

    return [
        {
            "type": "empty_files_data",
            "files": [item.get("filename") for item in empty_files],
            "date": execution_date,
            "cv_mentions_empty": "allow empty" in cv_text.lower(),
            "note": "LLM should evaluate if empty files are normal based on CV rules and day patterns"
        }
    ]


def _detect_volume_variation(
    cv_text: str,
    daily_files: List[Dict[str, Any]],
    last_week_files: List[Dict[str, Any]],
    execution_date: str,
) -> List[Dict[str, Any]]:
    """Extrae datos crudos sobre variaciones de volumen - SIN clasificar severidad"""
    current_rows = sum(item.get("rows") or 0 for item in daily_files)
    last_week_rows = sum(item.get("rows") or 0 for item in last_week_files)
    
    try:
        threshold = _extract_volume_threshold(cv_text)
    except ValueError:
        threshold = None

    day_stats = _extract_day_of_week_stats(cv_text)
    try:
        day_key = datetime.fromisoformat(execution_date).strftime("%a").lower()
    except ValueError:
        day_key = ""
    day_info = day_stats.get(day_key, {})

    volume_data: List[Dict[str, Any]] = []

    # Solo reportar datos crudos de volumen - NO clasificar severidad
    upper_bound = threshold or day_info.get("max")
    if upper_bound and current_rows > upper_bound:
        volume_data.append(
            {
                "type": "volume_variation_data",
                "current_rows": current_rows,
                "upper_bound": upper_bound,
                "context": "95pct" if threshold else "day_max",
                "note": "LLM should evaluate if this volume spike is concerning based on CV patterns"
            }
        )

    # Detectar cambios significativos (aumentos Y disminuciones)
    if last_week_rows > 0:  # Solo si hay datos de la semana pasada
        change_ratio = current_rows / last_week_rows if last_week_rows > 0 else 0
        
        # Detectar aumentos significativos (>50% más)
        if change_ratio > 1.5:
            volume_data.append(
                {
                    "type": "volume_variation_data",
                    "current_rows": current_rows,
                    "last_week_rows": last_week_rows,
                    "change_ratio": change_ratio,
                    "context": "week_comparison_increase",
                    "note": "LLM should evaluate if this volume increase is normal based on CV and business context"
                }
            )
        
        # Detectar disminuciones significativas (<50% del original)
        elif change_ratio < 0.5:
            volume_data.append(
                {
                    "type": "volume_variation_data",
                    "current_rows": current_rows,
                    "last_week_rows": last_week_rows,
                    "change_ratio": change_ratio,
                    "context": "week_comparison_decrease",
                    "note": "LLM should evaluate if this volume decrease is normal based on CV and business context"
                }
            )

    return volume_data


def _detect_schedule_anomaly(cv_text: str, daily_files: List[Dict[str, Any]], execution_date: str) -> List[Dict[str, Any]]:
    window = _extract_upload_window(cv_text)
    if not window:
        return []

    try:
        start, end = [segment.strip() for segment in window.split("–")]
        start_time = datetime.strptime(start, "%H:%M:%S").time()
        end_time = datetime.strptime(end, "%H:%M:%S").time()
    except ValueError:
        return []

    anomalies: List[Dict[str, Any]] = []
    for item in daily_files:
        uploaded_at = item.get("uploaded_at")
        if not uploaded_at:
            continue
        try:
            upload_time = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00")).time()
        except ValueError:
            continue

        late_margin = datetime.combine(datetime.min, end_time) + timedelta(hours=4)
        early_margin = datetime.combine(datetime.min, start_time) - timedelta(hours=4)
        upload_dt = datetime.combine(datetime.min, upload_time)

        if upload_dt > late_margin or upload_dt < early_margin:
            anomalies.append(item.get("filename"))

    if not anomalies:
        return []

    return [
        {
            "type": "schedule_anomaly_data",
            "files": anomalies,
            "window": window,
            "date": execution_date,
            "note": "LLM should evaluate if timing anomalies are concerning based on CV patterns and business context"
        }
    ]


def _detect_historical_uploads(daily_files: List[Dict[str, Any]], execution_date: str) -> List[Dict[str, Any]]:
    historical_files = []
    date_token = execution_date.replace("-", "")

    for item in daily_files:
        filename = item.get("filename", "")
        if date_token in filename:
            continue

        bare_name = filename.split("/")[-1]
        matches = re.findall(r"(\d{8})", bare_name)
        if not matches:
            historical_files.append(filename)
            continue

        normalized = [m for m in matches if m != date_token]
        if normalized:
            historical_files.append(filename)

    if not historical_files:
        return []

    return [
        {
            "type": "historical_upload_data",
            "files": historical_files,
            "note": "LLM should evaluate if historical uploads are concerning or normal maintenance based on CV and business context"
        }
    ]


def _extract_volume_threshold(cv_text: str) -> Optional[int]:
    for line in cv_text.splitlines():
        if "Normal (95%) interval:" in line:
            parts = line.split("-")
            try:
                return int(parts[-1].strip())
            except ValueError:
                raise
    return None


def _extract_upload_window(cv_text: str) -> Optional[str]:
    if not cv_text:
        return None
    for line in cv_text.splitlines():
        if "Upload Time Window" in line:
            parts = line.split("|")
            if parts:
                return parts[-1].strip()
    return None


def _normalize_filename(filename: Optional[str]) -> Optional[str]:
    """Reduce el nombre del archivo a su patrón lógico sin sufijos de fecha/lote."""

    if not filename:
        return None

    name = filename.lower()

    # Separar extensión para trabajar solo con el cuerpo del nombre
    if "." in name:
        stem, _ext = name.rsplit(".", 1)
    else:
        stem = name

    # Eliminar prefijos aleatorios antes del doble guion bajo
    if "__" in stem:
        stem = stem.split("__", 1)[1]

    # Retirar indicadores de batch explícitos
    stem = re.sub(r"_batch_\d+", "", stem)

    # Eliminar fechas en distintos formatos (YYYYMMDD, YYYY-MM-DD, YYYY_MM_DD)
    stem = re.sub(r"(_\d{4}_\d{2}_\d{2})+", "", stem)
    stem = re.sub(r"(-\d{4}-\d{2}-\d{2})+", "", stem)
    stem = re.sub(r"(?:[-_]\d{8,14})+", "", stem)  # timestamps compactos

    # Eliminar sufijos de fecha/hora residuales al final
    stem = re.sub(r"(?:[-_]\d{4}-\d{2}-\d{2})+$", "", stem)
    stem = re.sub(r"(?:[-_]\d{8,14})+$", "", stem)

    # Normalizar separadores residuales
    stem = re.sub(r"[-_]+", "_", stem).strip("_-")

    return stem or name


def _normalize_filenames(files: List[Dict[str, Any]]) -> set:
    patterns = set()
    for item in files:
        normalized = _normalize_filename(item.get("filename"))
        if normalized:
            patterns.add(normalized)
    return patterns


def _extract_day_of_week_stats(cv_text: str) -> Dict[str, Dict[str, int]]:
    stats: Dict[str, Dict[str, int]] = {}
    if not cv_text:
        return stats

    day_map = {
        "mon": "mon",
        "tue": "tue",
        "wed": "wed",
        "thu": "thu",
        "fri": "fri",
        "sat": "sat",
        "sun": "sun",
    }

    lines = iter(cv_text.splitlines())
    capture = False
    for line in lines:
        if "Day-of-Week Summary" in line:
            capture = True
            continue
        if capture and line.startswith("|") and "|" in line:
            columns = [col.strip() for col in line.strip("|").split("|")]
            if len(columns) < 2:
                continue
            day_token = columns[0][:3].lower()
            day_key = day_map.get(day_token)
            if not day_key:
                continue
            stats[day_key] = _parse_row_stats(columns[1])
        elif capture and not line.strip():
            break

    return stats


def _parse_row_stats(cell: str) -> Dict[str, int]:
    matches = re.findall(r"(Min|Max|Mean|Median):\s*([0-9,\.]+)", cell)
    stats = {}
    for key, value in matches:
        try:
            stats[key.lower()] = int(value.replace(",", ""))
        except ValueError:
            continue
    return stats