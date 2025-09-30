# Agent Factory - Incident Detection System
<img width="1024" height="1024" alt="Diagram" src="https://github.com/user-attachments/assets/8fcf7697-10cd-429a-9858-8aceb643b21e" />

Un sistema de detección de incidencias basado en agentes LLM para monitoreo de fuentes de datos diarias.

## 📋 Descripción del Proyecto

Este proyecto implementa un agente inteligente que analiza automáticamente las fuentes de datos diarias, detecta incidencias y genera reportes ejecutivos. El agente utiliza CVs (Curriculum Vitae) de las fuentes para entender patrones normales y distinguir entre comportamientos esperados e incidencias reales.

### 🎯 Funcionalidades Principales

- **Detección automática de incidencias**: Missing files, volume variations, timing issues, etc.
- **Análisis basado en CVs**: Interpreta documentos de patrones históricos para determinar normalidad
- **Reportes ejecutivos**: Clasifica incidencias por severidad (URGENT, NEEDS ATTENTION, ALL GOOD)
- **Soporte multi-modelo**: Compatible con OpenAI GPT y Google Gemini
- **Análisis inteligente**: El LLM actúa como protagonista en la toma de decisiones

## 🏗️ Arquitectura del Sistema

```
agent_factory/
├── adk_components/          # Definición del agente ADK
├── config/                  # Configuración del sistema
├── data_processing/         # Carga y consolidación de datos
├── report_builder/          # Herramientas del agente
├── datos/                   # Datos de entrada (no incluido)
├── notebooks/               # Análisis y desarrollo
├── reportes_generados/      # Reportes generados por el agente
└── main.py                  # Punto de entrada principal
```

## 🚀 Instalación y Configuración

### 1. Requisitos

```bash
pip install -r requirements.txt
```

### 2. Configuración del Entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
# API Keys (configura al menos una)
OPENAI_API_KEY=tu_openai_api_key_aqui
GOOGLE_API_KEY=tu_google_api_key_aqui

# Modelo a utilizar
AGENT_MODEL=gpt-4o-mini
# Opciones: gpt-4o, gpt-4o-mini, gpt-4-turbo, gemini-2.0-flash, gemini-1.5-pro

# Rutas de datos (opcional - usa defaults si no se especifica)
DATA_BASE_PATH=./datos
DATA_CV_PATH=./datos/cv
DATA_DAILY_PATH=./datos/daily_files
DATA_FEEDBACK_PATH=./datos/feedback

# Configuración del agente (opcional)
APP_NAME=incident_detection_agent
USER_ID=ops_team
```

### 3. Estructura de Datos

Crea la siguiente estructura de carpetas y coloca tus datos:

```
datos/
├── cv/                      # CVs de las fuentes (*.md)
│   ├── 195385_native.md
│   ├── 220504_native.md
│   └── ...
├── daily_files/             # Archivos diarios
│   └── 2025-09-08_20_00_UTC/
│       ├── files.json
│       └── files_last_weekday.json
└── feedback/                # Retroalimentación (para V2)
    └── Feedback - week 9 sept.csv

reportes_generados/          # Reportes del agente (subidos manualmente)
└── (reportes generados con modelo gpt-4.1)
```

## 📖 Uso del Sistema

### Ejecución Básica

```bash
python main.py --date 2025-09-08
```

### Desarrollo y Análisis

Para desarrollo y análisis detallado, utiliza el notebook:

```bash
jupyter notebook notebooks/v1_analysis.ipynb
```

### Ejemplo de Salida

```
🤖 Using model: gpt-4.1

*Report generated at UTC HOUR*: 16:00 UTC

*  Urgent Action Required*
• *__Payments_Layout_1_V3 (id: 220504)* – 2025-09-08: 12 files missing past 08:08–08:18 UTC
• *_Settlement_Layout_1 (id: 196125)* – 2025-09-08: 2 files missing past 08:00–08:00 UTC

*  Needs Attention*
• *_Settlement_Layout_2 (id: 195385)* – 2025-09-08: Early delivery at 08:06 UTC

*  All Good*
• *MyPal_DBR RX (id: 195436)* – 2025-09-08: [347,476] records
• *Soop Transaction PIX 3 (id: 199944)* – 2025-09-08: [179,070] records
```

## 🔧 Componentes Principales

### 1. Detectores de Incidencias

- **Missing File Detector**: Archivos esperados pero no recibidos
- **Volume Variation Detector**: Cambios anómalos en volumen de datos
- **Schedule Detector**: Archivos fuera de horario esperado
- **Duplicated/Failed File Detector**: Archivos duplicados o con errores
- **Empty File Detector**: Archivos vacíos inesperados
- **Historical Upload Detector**: Archivos de períodos anteriores

### 2. Herramientas del Agente

- `list_sources()`: Panorama general de todas las fuentes
- `get_source_cv_and_data(source_id)`: CV completo y datos para análisis
- `get_execution_date_info()`: Información del día de la semana

### 3. Criterios de Severidad

- **🔴 URGENT**: Missing files críticos o 3+ incidentes "needs attention"
- **🟡 NEEDS ATTENTION**: Volume variations, timing issues
- **🟢 ALL GOOD**: Sin incidentes según patrones del CV

## ⚠️ Limitaciones Conocidas

### 1. Validación de Resultados
- **No implementado**: Sistema de validación automática de resultados
- **Impacto**: Requiere validación manual de la precisión del agente
- **Mitigación**: Revisión manual de clasificaciones y detecciones

### 2. Evaluación de Performance
- **No implementado**: Métricas de precisión, recall, F1-score
- **Impacto**: Dificulta la medición objetiva de mejoras
- **Mitigación**: Evaluación cualitativa caso por caso


### 4. Manejo de Errores
- **Limitación**: Manejo básico de errores en carga de datos
- **Impacto**: Fallos silenciosos si faltan archivos o CVs
- **Mitigación**: Verificación manual de estructura de datos

## 🔄 Mejoras Futuras (V2)

### 1. Sistema de Evaluación
- Implementar pipeline de validación automática
- Métricas de performance (precisión, recall)
- Sistema de benchmarking y testing automatizado

### 2. Retroalimentación Continua
- Integración del archivo de feedback
- Aprendizaje iterativo basado en correcciones
- Ajuste automático de thresholds

### 3. Robustez del Sistema
- Mejor manejo de errores y excepciones
- Validación de integridad de datos
- Logging detallado para debugging

### 4. Optimización de Performance
- Cache de CVs para múltiples ejecuciones
- Paralelización de análisis por fuente
- Optimización de prompts para consistencia

## 🛠️ Desarrollo

### Estructura del Código

- **`main.py`**: Punto de entrada principal
- **`adk_components/`**: Definición del agente y configuración
- **`data_processing/`**: Lógica de carga y procesamiento de datos
- **`report_builder/`**: Herramientas y funciones del agente
- **`config/`**: Configuración centralizada del sistema

### Agregar Nuevos Detectores

1. Implementar función en `data_processing/incident_consolidator.py`
2. Agregar llamada en `build_dataset()`
3. Actualizar instrucciones del agente si es necesario

### Cambiar Modelos LLM

Simplemente actualiza `AGENT_MODEL` en tu `.env`:
- OpenAI: `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`
- Gemini: `gemini-2.5-flash`

## 📊 Casos de Uso

### 1. Monitoreo Diario
Ejecutar automáticamente cada mañana para detectar incidencias del día anterior.

### 2. Análisis Retrospectivo
Analizar períodos históricos para identificar patrones de incidencias.

### 3. Validación de Cambios
Verificar el impacto de cambios en sistemas upstream en la calidad de datos.

### 4. Análisis de Reportes
Los reportes generados con modelo gpt-4.1 se almacenan en `reportes_generados/` para:
- Documentar resultados del agente
- Validar consistencia de detecciones
- Mantener historial de análisis para casos específicos

## 🤝 Contribución

Este proyecto fue desarrollado como una prueba técnica demostrando:
- Implementación de agentes LLM con Google ADK
- Procesamiento inteligente de datos no estructurados
- Análisis automatizado de patrones y anomalías
- Integración de múltiples modelos LLM

## 📄 Licencia

Proyecto de demostración técnica.
