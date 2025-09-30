# main.py
import argparse
import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict
from dotenv import load_dotenv


from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_components.agent_definition import create_report_agent
from config import settings
from data_processing.data_loader import DataLoader
from data_processing.incident_consolidator import IncidentConsolidator
from report_builder import build_incident_toolkit

load_dotenv()


async def run_agent(dataset: Dict[str, Dict[str, Any]], execution_date: str) -> str:
    tools = build_incident_toolkit(dataset, execution_date)
    
    # Debug: Mostrar configuración
    print(f"📁 .env file exists: {os.path.exists('.env')}")
    print(f"🔧 AGENT_MODEL from env: {os.getenv('AGENT_MODEL')}")
    print(f"⚙️  AGENT_MODEL from settings: {settings.AGENT_MODEL}")
    
    # Forzar recarga del módulo settings
    import importlib
    importlib.reload(settings)
    print(f"🔄 AGENT_MODEL after reload: {settings.AGENT_MODEL}")
    
    # Mostrar modelo configurado
    model_name = settings.AGENT_MODEL
    print(f"🤖 Using model: {model_name}")
    
    agent = create_report_agent(tools)
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=settings.APP_NAME,
        user_id=settings.USER_ID,
    )

    runner = Runner(agent=agent, app_name=settings.APP_NAME, session_service=session_service)

    prompt = f"""
OBJETIVO: Generar un reporte preciso basado únicamente en el análisis de los CVs y los datos reales.

HERRAMIENTAS DISPONIBLES (USAR SOLO ESTAS):
- list_sources(): panorama general de todas las fuentes
- get_source_cv_and_data(source_id): CV completo y datos crudos para análisis experto

INSTRUCCIONES ESPECÍFICAS:
1. USA SOLO list_sources() y get_source_cv_and_data() - NO uses otras herramientas
2. Para CADA fuente en list_sources(), usa get_source_cv_and_data() para análisis completo
3. Lee completamente el CV de cada fuente para entender sus patrones normales
4. Interpreta inteligentemente si los eventos son normales según el CV o verdaderos incidentes
5. Determina qué día de la semana es {execution_date} y verifica patrones específicos para ese día en cada CV

CASO ESPECIAL A VALIDAR:
- Fuente 195385: ¿Los archivos que llegaron son normales según su CV?
- ¿El timing 08:06 UTC está dentro de las ventanas esperadas?
- ¿El lag -1 (archivos del sábado llegando domingo) es normal según el CV?

REGLAS CRÍTICAS PARA ANÁLISIS:
- Si el CV dice que algo es normal, NO es un incidente
- Solo reporta verdaderos desvíos de los patrones del CV
- Usa números reales de records en "All Good"
- Cada fuente aparece solo una vez en la sección de mayor severidad
- IGNORA datos de "raw_incidents" si contradicen el análisis del CV

⚠️ REGLA CRÍTICA SOBRE VOLUME VARIATIONS:
- Si volume decrease es causado por missing files → NO reportar volume variation
- Solo reportar volume variation si los archivos llegaron pero con menos/más rows
- Ejemplo: Si 0 files llegaron y 0 rows → Solo missing files (NO volume variation)
- Ejemplo: Si 2 files llegaron pero con 50% menos rows → Volume variation

CLASIFICACIÓN DE SEVERIDAD:
🔴 URGENT: Missing files críticos según CV O 3+ incidentes "needs attention"
🟡 NEEDS ATTENTION: Desvíos de volumen, timing fuera de ventanas del CV
🟢 ALL GOOD: Todo dentro de patrones normales del CV

GENERATE THE EXECUTIVE REPORT IN ENGLISH for {execution_date}
"""
    content = types.Content(role="user", parts=[types.Part(text=prompt)])

    final_message = ""
    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=content,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_message = event.content.parts[0].text
            break

    return final_message


async def run_agent_with_prompt(execution_date: str, custom_prompt: str) -> str:
    """Función auxiliar para ejecutar el agente con un prompt personalizado (útil para notebooks)"""
    # Configurar paths explícitos
    from pathlib import Path
    project_root = Path(__file__).parent
    datos_path = project_root / "datos"
    
    loader = DataLoader(
        base_path=datos_path,
        cv_path=datos_path / "cv",
        daily_path=datos_path / "daily_files",
        feedback_path=datos_path / "feedback"
    )
    
    # Obtener source IDs de archivos CV disponibles
    cv_files = list((datos_path / "cv").glob("*.md"))
    source_ids = [f.stem.replace("_native", "") for f in cv_files]
    
    if not source_ids:
        return "No se encontraron fuentes de datos."

    consolidator = IncidentConsolidator(execution_date)
    dataset = consolidator.build_dataset(source_ids, loader)
    
    # Crear agente con prompt personalizado
    tools = build_incident_toolkit(dataset, execution_date)
    agent = create_report_agent(tools)
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=settings.APP_NAME,
        user_id=settings.USER_ID,
    )

    runner = Runner(agent=agent, app_name=settings.APP_NAME, session_service=session_service)
    content = types.Content(role="user", parts=[types.Part(text=custom_prompt)])

    final_message = ""
    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=content,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_message = event.content.parts[0].text
            break

    return final_message


async def main(execution_date: str) -> None:
    # Configurar paths explícitos
    from pathlib import Path
    project_root = Path(__file__).parent
    datos_path = project_root / "datos"
    
    loader = DataLoader(
        base_path=datos_path,
        cv_path=datos_path / "cv",
        daily_path=datos_path / "daily_files",
        feedback_path=datos_path / "feedback"
    )
    
    # Obtener source IDs de archivos CV disponibles
    cv_files = list((datos_path / "cv").glob("*.md"))
    source_ids = [f.stem.replace("_native", "") for f in cv_files]
    
    if not source_ids:
        print("Error: No se encontraron archivos CV en la carpeta datos/cv/")
        return

    consolidator = IncidentConsolidator(execution_date)
    dataset = consolidator.build_dataset(source_ids, loader)

    report = await run_agent(dataset, execution_date)
    print(report)


def _parse_execution_date() -> str:
    parser = argparse.ArgumentParser(description="Run incident detection agent")
    parser.add_argument(
        "--date",
        dest="execution_date",
        help="Fecha de ejecución en formato YYYY-MM-DD",
    )
    args = parser.parse_args()

    if args.execution_date:
        return args.execution_date

    env_date = os.getenv("EXECUTION_DATE")
    if env_date:
        return env_date

    return datetime.utcnow().strftime("%Y-%m-%d")


if __name__ == "__main__":
    execution_date = _parse_execution_date()
    asyncio.run(main(execution_date))