import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


SUMMARY_ACTIONS = {
    "missing": "Notify provider to generate/re-send; re-run ingestion and verify completeness.",
    "volume": "Confirm coverage/window; monitor next run. Validate downstream completed.",
    "schedule": "Confirm schedule change; adjust downstream triggers if needed.",
    "historical": "Identify if this is an intentional historical upload or a system anomaly.",
    "duplicates": "Investigate the root cause of duplicated files. Check data pipeline for errors.",
    "empty": "Investigate the root cause of unexpected empty files. Confirm data integrity.",
    "default": "Investigate root cause and take corrective actions as needed.",
}


class IncidentAnalysisToolkit:
    """Expone herramientas ligeras para que el LLM consulte datos operativos."""

    def __init__(self, dataset: Dict[str, Dict[str, Any]], execution_date: str) -> None:
        self.dataset = dataset
        self.execution_date = execution_date

    def to_tools(self) -> List:
        dataset = self.dataset
        execution_date = self.execution_date

        def list_sources() -> str:
            """Lista las fuentes disponibles con métricas básicas del día."""
            summary: List[Dict[str, Any]] = []
            for source_id, payload in dataset.items():
                today = payload.get("daily_files", [])
                last_week = payload.get("last_week_files", [])
                expected = _extract_expected_from_cv(payload.get("cv_text", ""), execution_date)
                missing = max(expected - len(today), 0) if expected else None
                summary.append(
                    {
                        "source_id": source_id,
                        "display_name": _extract_title(payload.get("cv_text", "")) or source_id,
                        "files_today": len(today),
                        "files_last_weekday": len(last_week),
                        "expected_files": expected,
                        "missing_estimate": missing,
                        "has_cv": bool(payload.get("cv_text")),
                        "first_upload_utc": _first_upload(today),
                        "last_upload_utc": _last_upload(today),
                    }
                )
            return json.dumps(
                {
                    "execution_date": execution_date,
                    "sources": summary,
                },
                ensure_ascii=False,
            )

        list_sources.__name__ = "list_sources"

        def get_source_profile(source_id: str) -> str:
            """Devuelve CV resumido y métricas clave de los archivos del día."""
            payload = dataset.get(source_id)
            if not payload:
                return json.dumps(
                    {
                        "source_id": source_id,
                        "error": "SOURCE_NOT_FOUND",
                    },
                    ensure_ascii=False,
                )

            daily = payload.get("daily_files", [])
            statuses = _count_by_key(daily, "status")
            duplicated = sum(1 for item in daily if item.get("is_duplicated"))
            empty = [item["filename"] for item in daily if (item.get("rows") or 0) == 0]
            cv_excerpt = (payload.get("cv_text", "") or "").strip()
            cv_excerpt = cv_excerpt[:2000]

            return json.dumps(
                {
                    "source_id": source_id,
                    "display_name": _extract_title(payload.get("cv_text", "")) or source_id,
                    "cv_excerpt": cv_excerpt,
                    "files_today": len(daily),
                    "status_counts": statuses,
                    "duplicated_today": duplicated,
                    "empty_files": empty,
                    "first_upload_utc": _first_upload(daily),
                    "last_upload_utc": _last_upload(daily),
                },
                ensure_ascii=False,
            )

        get_source_profile.__name__ = "get_source_profile"

        def compare_with_last_week(source_id: str) -> str:
            """Compara volumen de registros contra el mismo día de la semana anterior."""
            payload = dataset.get(source_id, {})
            today = payload.get("daily_files", [])
            last_week = payload.get("last_week_files", [])

            def aggregate(files: List[Dict[str, Any]]) -> Dict[str, Any]:
                total_rows = sum(item.get("rows") or 0 for item in files)
                max_rows = max((item.get("rows") or 0) for item in files) if files else 0
                return {
                    "file_count": len(files),
                    "total_rows": total_rows,
                    "max_rows": max_rows,
                }

            return json.dumps(
                {
                    "source_id": source_id,
                    "today": aggregate(today),
                    "last_weekday": aggregate(last_week),
                },
                ensure_ascii=False,
            )

        compare_with_last_week.__name__ = "compare_with_last_week"

        def get_source_summary(source_id: str) -> str:
            """Devuelve información agregada lista para el formato Golden Copy."""
            payload = dataset.get(source_id)
            if not payload:
                return json.dumps(
                    {
                        "source_id": source_id,
                        "error": "SOURCE_NOT_FOUND",
                    },
                    ensure_ascii=False,
                )

            today = payload.get("daily_files", [])
            last_week = payload.get("last_week_files", [])
            expected = _extract_expected_from_cv(payload.get("cv_text", ""), execution_date)

            incidents = payload.get("incidents", {})

            missing_summary = []
            for incident in incidents.get("missing", []):
                seen = set()
                for pattern in incident.get("patterns", []):
                    key = (pattern.get("pattern"), pattern.get("entity"))
                    if key in seen:
                        continue
                    seen.add(key)
                    missing_summary.append(
                        {
                            "pattern": pattern.get("pattern"),
                            "entity": pattern.get("entity"),
                            "files": pattern.get("files", []),
                            "window": pattern.get("window"),
                            "expected_count": pattern.get("expected_count"),
                            "received_count": pattern.get("received_count"),
                            "coverage_date": pattern.get("coverage_date"),
                        }
                    )

            return json.dumps(
                {
                    "source_id": source_id,
                    "display_name": _extract_title(payload.get("cv_text", "")) or source_id,
                    "expected_files": expected,
                    "received_files": len(today),
                    "first_upload": _first_upload(today),
                    "last_upload": _last_upload(today),
                    "today_rows_total": sum(item.get("rows") or 0 for item in today),
                    "last_week_rows_total": sum(item.get("rows") or 0 for item in last_week),
                    "incidents": {
                        "missing": missing_summary,
                        "volume_variation": incidents.get("volume_variation", []),
                        "schedule": incidents.get("schedule", []),
                        "historical": incidents.get("historical", []),
                        "duplicates": incidents.get("duplicated", []),
                        "empty": incidents.get("empty", []),
                    },
                    "no_data_last_week": not bool(last_week),
                },
                ensure_ascii=False,
            )

        get_source_summary.__name__ = "get_source_summary"

        def build_report_sections() -> str:
            sections = {
                "urgent": [],
                "needs_attention": [],
                "all_good": [],
            }

            for source_id, payload in dataset.items():
                entry = _format_summary_entry(
                    source_id=source_id,
                    payload=payload,
                    execution_date=execution_date,
                )
                sections[entry["severity"]].append(entry)

            for key in sections:
                sections[key].sort(key=lambda item: item.get("display_name", ""))

            return json.dumps(sections, ensure_ascii=False)

        build_report_sections.__name__ = "build_report_sections"

        def get_source_cv_and_data(source_id: str) -> str:
            """
            Obtiene el CV completo y datos crudos de una fuente para análisis detallado.
            
            Esta herramienta proporciona acceso directo al CV y datos sin interpretación previa,
            permitiendo al LLM analizar las reglas específicas de cada fuente.
            
            Args:
                source_id: ID de la fuente a analizar
                
            Returns:
                JSON con CV completo, archivos del día, archivos de la semana pasada,
                y metadatos para análisis experto
            """
            if source_id not in self.dataset:
                return json.dumps({"error": f"Fuente {source_id} no encontrada"}, ensure_ascii=False)
            
            source_data = self.dataset[source_id]
            
            # Preparar datos completos para análisis
            analysis_data = {
                "source_id": source_id,
                "execution_date": self.execution_date,
                "cv_text": source_data.get('cv_text', ''),
                "daily_files": source_data.get('daily_files', []),
                "last_week_files": source_data.get('last_week_files', []),
                "incidents": source_data.get('incidents', {}),
                "analysis_context": {
                    "total_daily_files": len(source_data.get('daily_files', [])),
                    "total_daily_records": sum(f.get('rows', 0) for f in source_data.get('daily_files', [])),
                    "total_last_week_files": len(source_data.get('last_week_files', [])),
                    "total_last_week_records": sum(f.get('rows', 0) for f in source_data.get('last_week_files', [])),
                    "cv_length": len(source_data.get('cv_text', '')),
                    "incident_types_detected": list(source_data.get('incidents', {}).keys())
                }
            }
            
            return json.dumps(analysis_data, ensure_ascii=False, indent=2)

        get_source_cv_and_data.__name__ = "get_source_cv_and_data"

        def get_execution_date_info() -> str:
            """Obtiene información sobre la fecha de ejecución y día de la semana"""
            from datetime import datetime
            try:
                date_obj = datetime.strptime(execution_date, "%Y-%m-%d")
                day_name = date_obj.strftime("%A")  # Monday, Tuesday, etc.
                day_abbr = date_obj.strftime("%a")  # Mon, Tue, etc.
                
                return f"""INFORMACIÓN DE FECHA DE EJECUCIÓN:
• Fecha: {execution_date}
• Día de la semana: {day_name} ({day_abbr})
• Para buscar en CVs: usa la fila "{day_abbr}" en las tablas "File Processing Statistics by Day"

IMPORTANTE: Cuando leas las tablas del CV, busca la fila que corresponde a "{day_abbr}", NO asumas otros días.
Ejemplo: Si es Monday, busca "Mon | X | X | X" en la tabla del CV."""
            except ValueError:
                return f"Error: No se pudo parsear la fecha {execution_date}"

        get_execution_date_info.__name__ = "get_execution_date_info"

        return [
            list_sources,
            get_source_cv_and_data,
            get_execution_date_info,
        ]


def _count_by_key(items: List[Dict[str, Any]], key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        label = str(item.get(key) or "UNKNOWN")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _first_upload(files: List[Dict[str, Any]]) -> Optional[str]:
    timestamps = [item.get("uploaded_at") for item in files if item.get("uploaded_at")]
    if not timestamps:
        return None
    return min(timestamps)


def _last_upload(files: List[Dict[str, Any]]) -> Optional[str]:
    timestamps = [item.get("uploaded_at") for item in files if item.get("uploaded_at")]
    if not timestamps:
        return None
    return max(timestamps)


def _extract_expected_from_cv(cv_text: str, execution_date: str = "2025-09-08") -> Optional[int]:
    """Extrae archivos esperados del CV para el día específico de la semana"""
    if not cv_text:
        return None
    
    # Determinar día de la semana
    from datetime import datetime
    try:
        date_obj = datetime.strptime(execution_date, "%Y-%m-%d")
        day_name = date_obj.strftime("%a")  # Mon, Tue, Wed, etc.
    except:
        return None
    
    # Buscar la tabla "File Processing Statistics by Day"
    lines = cv_text.splitlines()
    in_table = False
    found_header = False
    
    for line in lines:
        if "File Processing Statistics by Day" in line:
            in_table = True
            continue
        
        # Buscar la línea de headers (Day | Mean Files | Median Files...)
        if in_table and not found_header and "Day" in line and "Mean Files" in line:
            found_header = True
            continue
            
        # Solo procesar líneas después de encontrar el header
        if in_table and found_header and day_name in line and "|" in line:
            # Parsear línea como: | Sun | 17 | 17 | 18 |
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 4 and parts[0] == day_name:
                try:
                    # Verificar que el segundo elemento sea un número
                    mean_files = int(parts[1])  # Segunda columna es Mean Files
                    return mean_files
                except (ValueError, IndexError):
                    continue
        
        # Si salimos de la tabla sin encontrar, parar
        if in_table and line.startswith("##"):
            break
    
    return None


def _infer_missing_files(daily_files: List[Dict[str, Any]], expected: Optional[int]) -> List[str]:
    if not expected:
        return []
    received = len(daily_files)
    if received >= expected:
        return []
    # No tenemos nombres exactos en V1, devolvemos un placeholder sencillo
    return ["Archivo faltante " + str(i + 1) for i in range(expected - received)]


def _extract_upload_window(cv_text: str) -> Optional[str]:
    if not cv_text:
        return None
    for line in cv_text.splitlines():
        if "Upload Time Window" in line:
            return line.split("|")[-1].strip()
    return None


def _extract_title(cv_text: str) -> Optional[str]:
    if not cv_text:
        return None
    for line in cv_text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("# ")
    return None


def _format_summary_entry(
    source_id: str,
    payload: Dict[str, Any],
    execution_date: str,
) -> Dict[str, Any]:
    display_name = _extract_title(payload.get("cv_text", "")) or source_id
    incidents = payload.get("incidents", {})
    missing_patterns: List[Dict[str, Any]] = []
    for incident in incidents.get("missing", []):
        missing_patterns.extend(incident.get("patterns", []))

    needs_incidents: List[Dict[str, Any]] = []
    for key in ("volume_variation", "schedule", "historical", "duplicated", "empty"):
        needs_incidents.extend(incidents.get(key, []))

    missing_count = len(missing_patterns)
    needs_count = len(needs_incidents)

    if missing_count >= 1 or needs_count >= 3:
        severity = "urgent"
    elif needs_count >= 1:
        severity = "needs_attention"
    else:
        severity = "all_good"

    if severity == "urgent":
        formatted = _build_missing_bullet(display_name, source_id, missing_patterns, execution_date)
    elif severity == "needs_attention":
        formatted = _build_needs_attention_bullet(display_name, source_id, needs_incidents, execution_date)
    else:
        formatted = _build_all_good_bullet(display_name, source_id, payload, execution_date)

    return {
        "source_id": source_id,
        "display_name": display_name,
        "severity": severity,
        "messages": [formatted],
        "action": "",
        "execution_date": execution_date,
        "formatted": formatted,
    }


def _action_from_type(incident_type: Optional[str]) -> str:
    if not incident_type:
        return SUMMARY_ACTIONS["default"]
    mapping = {
        "missing_files": "missing",
        "volume_variation": "volume",
        "schedule_anomaly": "schedule",
        "historical_upload": "historical",
        "duplicated_or_failed": "duplicates",
        "unexpected_empty_file": "empty",
    }
    key = mapping.get(incident_type, incident_type)
    return SUMMARY_ACTIONS.get(key, SUMMARY_ACTIONS["default"])


def _build_missing_bullet(
    display_name: str,
    source_id: str,
    patterns: List[Dict[str, Any]],
    execution_date: str,
) -> str:
    total_missing = 0
    coverage_dates: List[str] = []
    windows: List[str] = []
    entities: List[str] = []
    expected_files: List[str] = []

    for pattern in patterns:
        expected = pattern.get("expected_count")
        received = pattern.get("received_count", 0)
        if expected is None:
            expected = 1
        total_missing += max(expected - received, expected if received == 0 else expected - received)
        coverage_dates.append(pattern.get("coverage_date") or execution_date)
        if pattern.get("window"):
            windows.append(pattern.get("window"))
        if pattern.get("entity"):
            entities.append(pattern["entity"])
        expected_files.extend(pattern.get("files", []))

    coverage_label = ", ".join(sorted(set(filter(None, coverage_dates)))) or execution_date
    window_label = _combine_window_labels(windows)
    entities_label = ", ".join(sorted({entity for entity in entities if entity}))
    expected_pretty = [_pretty_filename(name) for name in sorted(set(expected_files)) if name]

    detail_parts: List[str] = []
    base_detail = f"{coverage_label}: {total_missing} files missing"
    if window_label:
        base_detail += f" past {window_label}"
    detail_parts.append(base_detail)

    if entities_label:
        detail_parts.append(f"entities: {entities_label}")

    if expected_pretty:
        if len(expected_pretty) == 1:
            detail_parts.append(f"expected: {expected_pretty[0]}")
        elif len(expected_pretty) <= 4:
            detail_parts.append("expected: " + "; ".join(expected_pretty))
        else:
            detail_parts.append(
                f"expected: {expected_pretty[0]}, {expected_pretty[1]}, … ({len(expected_pretty)} total)"
            )

    detail = " — ".join(detail_parts)
    action = SUMMARY_ACTIONS["missing"]

    return f"• * {display_name} (id: {source_id})* – {detail} → *Action:* {action}"


def _build_needs_attention_bullet(
    display_name: str,
    source_id: str,
    incidents: List[Dict[str, Any]],
    execution_date: str,
) -> str:
    if not incidents:
        action = SUMMARY_ACTIONS["default"]
        detail = "Incident requires investigation."
        return f"• * {display_name} (id: {source_id})* – {detail} → *Action:* {action}"

    descriptions: List[str] = []
    primary_action = SUMMARY_ACTIONS["default"]

    for incident in incidents:
        incident_type = incident.get("type")
        primary_action = _action_from_type(incident_type)
        desc = incident.get("description")
        if desc:
            descriptions.append(desc)
            continue

        if incident_type == "historical_upload":
            files = ", ".join(_pretty_filename(name) for name in incident.get("files", []))
            descriptions.append(f"Historical upload detected: {files}")
        elif incident_type == "duplicated_or_failed":
            files = ", ".join(_pretty_filename(name) for name in incident.get("files", []))
            descriptions.append(f"Duplicated/failed files: {files}")
        elif incident_type == "unexpected_empty_file":
            files = ", ".join(_pretty_filename(name) for name in incident.get("files", []))
            descriptions.append(f"Unexpected empty files: {files}")
        else:
            descriptions.append(incident_type or "Incident requires investigation.")

    detail = " — ".join(filter(None, descriptions)) or "Incident requires investigation."
    return f"• * {display_name} (id: {source_id})* – {detail} → *Action:* {primary_action}"


def _build_all_good_bullet(
    display_name: str,
    source_id: str,
    payload: Dict[str, Any],
    execution_date: str,
) -> str:
    rows_total = sum(item.get("rows") or 0 for item in payload.get("daily_files", []))
    return f"• * {display_name} (id: {source_id})* – {execution_date}: `[ {rows_total} ] records`"


def _combine_window_labels(windows: List[str]) -> Optional[str]:
    if not windows:
        return None
    times: List[str] = []
    for window in windows:
        if not window:
            continue
        matches = re.findall(r"(\d{2}:\d{2})", window)
        times.extend(matches)
    if not times:
        return windows[0]
    times_sorted = sorted(times)
    if len(times_sorted) == 1:
        return f"{times_sorted[0]} UTC"
    return f"{times_sorted[0]}–{times_sorted[-1]} UTC"


def _pretty_filename(filename: str) -> str:
    if "__" in filename:
        return "*" + filename.split("__", 1)[1]
    return filename
