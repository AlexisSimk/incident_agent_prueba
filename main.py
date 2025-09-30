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
OBJECTIVE: Generate a precise report based solely on CV analysis and real data.

AVAILABLE TOOLS (USE ONLY THESE):
- list_sources(): general overview of all sources
- get_source_cv_and_data(source_id): complete CV and raw data for expert analysis

SPECIFIC INSTRUCTIONS:
1. USE ONLY list_sources() and get_source_cv_and_data() - DO NOT use other tools
2. For EACH source in list_sources(), use get_source_cv_and_data() for complete analysis
3. Read each source's CV completely to understand their normal patterns
4. Intelligently interpret whether events are normal according to the CV or true incidents
5. Determine what day of the week {execution_date} is and verify specific patterns for that day in each CV

SPECIAL CASE TO VALIDATE:
- Source 195385: Are the files that arrived normal according to its CV?
- Is the timing 08:06 UTC within expected windows?
- Is lag -1 (Saturday files arriving Sunday) normal according to the CV?

CRITICAL RULES FOR ANALYSIS:
- If the CV says something is normal, it is NOT an incident
- Only report true deviations from CV patterns
- Use real record numbers in "All Good"
- Each source appears only once in the highest severity section
- IGNORE "raw_incidents" data if it contradicts CV analysis

⚠️ CRITICAL RULE ABOUT VOLUME VARIATIONS:
- IF VOLUME DECREASE IS CAUSED BY MISSING FILES, DO NOT REPORT VOLUMNE VARIATION!
- Only report volume variation if files arrived but with fewer/more rows
- Example: If 0 files arrived and 0 rows → Only missing files (NOT volume variation)
- Example: If 2 files arrived but with 50% fewer rows → Volume variation

SEVERITY CLASSIFICATION:
🔴 URGENT: Critical missing files according to CV OR 3+ "needs attention" incidents
🟡 NEEDS ATTENTION: Volume deviations, timing outside CV windows
🟢 ALL GOOD: Everything within normal CV patterns

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