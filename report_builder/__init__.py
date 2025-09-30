from typing import Any, Dict, List

from .toolkit import IncidentAnalysisToolkit


def build_incident_toolkit(dataset: Dict[str, Dict[str, Any]], execution_date: str) -> List:
    """Devuelve una lista de funciones que el agente puede usar como herramientas."""
    return IncidentAnalysisToolkit(dataset, execution_date).to_tools()


__all__ = ["build_incident_toolkit", "IncidentAnalysisToolkit"]
