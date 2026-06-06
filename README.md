# Echo-Bering

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![uv](https://img.shields.io/badge/uv-dependency_manager-green)
![Coverage 97%](https://img.shields.io/badge/coverage-97%25-brightgreen)

Echo-Bering es una herramienta CLI/TUI que procesa videos de cualquier duración (5min - 6h) y cualquier tema, los segmenta automáticamente en capítulos temáticos, genera cortes físicos del video, subtítulos `.srt` y un **manifiesto enriquecido por capítulo** con contexto, términos técnicos, descripción profunda y momentos clave.

## Características Principales

- 🎯 **Segmentación Semántica**: Divide videos en capítulos temáticos coherentes usando LLM
- 🔧 **Soporte Multi-Proveedor**: Groq, AssemblyAI, OpenAI para ASR; DeepSeek, Groq, OpenAI para LLM
- ⚡ **Chunking Adaptativo**: Procesa videos largos dividiendo solo cuando es técnicamente necesario
- 💰 **Control de Costos**: Presupuesto configurable con monitoreo en tiempo real
- 🔄 **Reanudación**: Recupera desde fallos sin perder trabajo previo
- 📊 **Metadata Enriquecida**: Cada capítulo incluye descripción, contexto, términos, highlights y más
- 🎨 **TUI Interactiva**: Progreso visual con costos y estadísticas en tiempo real

## Arquitectura

Echo-Bering sigue una arquitectura de 4 capas con principios sólidos:

- **Transcripción como contrato único de verdad**
- **Proveedores como visitantes, no participantes**  
- **Capítulo como unidad atómica de valor**
- **Filesystem como base de datos**

```
Orchestration → Processing → Adaptation → External World
```

## Requisitos

- Python 3.10+
- uv (gestor de dependencias)
- ffmpeg (para operaciones de audio/video)
- API keys para proveedores ASR/LLM

## Instalación

```bash
# Clonar repositorio
git clone https://github.com/your-org/echo-bering.git
cd echo-bering

# Instalar dependencias con uv
uv sync

# Configurar credenciales
cp .env.example .env
# Editar .env con tus API keys
```

## Uso Básico

```bash
# Ejecutar con configuración por defecto
uv run python -m src.main

# Ejecutar con configuración personalizada  
uv run python -m src.main --config mi_config.yaml
```

## Configuración

Ejemplo de `config.yaml`:

```yaml
# Proveedores
asr_provider: groq
llm_provider: deepseek

# Procesamiento
input_video: ./videos/mi_video.mp4
output_dir: ./output  
language: es
cut_mode: fast

# Control
max_budget_usd: 2.0
chunk_duration_minutes: 20
```

## Estructura de Salida

```
output/
├── capitulo_01_titulo/
│   ├── capitulo_01_titulo.mp4
│   ├── capitulo_01.srt
│   └── metadata.json
├── capitulo_02_titulo/
│   └── ...
├── processing_report.json
└── .checkpoints/ (durante ejecución)
```

## Documentación Técnica

La documentación completa sigue el estándar de microservicios y está organizada en:

- **[Arquitectura](docs/Arquitectura/)**: Diagramas C4 y principios arquitectónicos
- **[Flujos de Negocio](docs/Flujos_de_Negocio/)**: Diagramas de secuencia del pipeline
- **[Patrones y Mecanismos](docs/Patrones_y_Mecanismos_Internos/)**: Patrones de diseño implementados
- **[Guías Operativas](docs/Guias_Operativas/)**: Deployment, observabilidad, troubleshooting y **[Guía de Inicialización y Pruebas](docs/Guias_Operativas/Guia_de_Inicializacion_y_Pruebas.md)**
- **[Testing](docs/testing/)**: Estrategia de pruebas y cobertura

## Roadmap

### Fase 1: ✅ Core Pipeline + Metadata Básico (COMPLETADO)
- Extractor de audio (ffmpeg)
- Integración Groq ASR + DeepSeek LLM
- Cortes ffmpeg (modo fast)
- TUI básica con Rich
- Generación de `metadata.json` enriquecido

### Fase 2: Próxima - AssemblyAI Completo
- Auto Chapters como segmentador alternativo
- Entity Detection en metadata
- Key Phrases extraction
- LeMUR tasks (summary, action items)

### Fase 3: Robustez
- Chunking automático para videos >1h
- Sistema de checkpoints mejorado
- Validación de config y coste pre-proceso
- Fallback automático entre proveedores

## Testing

- **434 tests** con **97% de cobertura**
- **Strict TDD**: Tests escritos antes de implementación
- **Mocking comprehensivo**: Proveedores, ffmpeg, filesystem
- **Integration tests**: Todas las combinaciones de proveedores

```bash
# Ejecutar todos los tests
uv run pytest

# Ver cobertura
uv run pytest --cov=src --cov-report=html
```

## Contribución

1. Fork el repositorio
2. Crea tu rama de feature (`git checkout -b feature/AmazingFeature`)
3. Haz commit de tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## Licencia

Distribuido bajo la licencia MIT. Ver `LICENSE` para más información.

## Contacto

Tu Nombre - [@tuusuario](https://twitter.com/tuusuario) - tu.email@ejemplo.com

Project Link: [https://github.com/your-org/echo-bering](https://github.com/your-org/echo-bering)