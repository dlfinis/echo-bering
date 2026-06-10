# Deployment

Procedimientos para desplegar y configurar Echo-Bering en diferentes entornos.

**Propósito:** Documentar los pasos necesarios para instalar, configurar y ejecutar Echo-Bering en entornos de desarrollo y producción.

## Requisitos del Sistema

### Requisitos Mínimos
- **Sistema Operativo**: Linux, macOS, o Windows con WSL2
- **Python**: 3.10 o superior
- **uv**: Última versión estable
- **ffmpeg**: Última versión estable (para operaciones de audio/video)
- **Espacio en Disco**: 2x el tamaño del video de entrada (para outputs)

### Requisitos Opcionales
- **Docker**: Para entornos containerizados
- **tmux/screen**: Para sesiones largas en servidores remotos

## Instalación

### Instalación Local con uv

```bash
# Clonar el repositorio
git clone https://github.com/your-org/echo-bering.git
cd echo-bering

# Instalar dependencias con uv
uv sync

# Verificar instalación
uv run python -m src.main --help
```

### Configuración de Credenciales

Crear archivo `.env` basado en `.env.example`:

```bash
# Copiar template
cp .env.example .env

# Editar credenciales
nano .env
```

Contenido del `.env`:
```bash
# Proveedores ASR
GROQ_API_KEY=tu_groq_key_aqui
ASSEMBLYAI_API_KEY=tu_assembly_key_aqui  
OPENAI_API_KEY=tu_openai_key_aqui

# Proveedores LLM
DEEPSEEK_API_KEY=tu_deepseek_key_aqui
```

### Configuración del Pipeline

Editar `config.yaml` según necesidades:

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

## Ejecución

### Ejecución Básica

```bash
# Ejecutar con configuración por defecto
uv run python -m src.main

# Ejecutar con configuración personalizada
uv run python -m src.main --config mi_config.yaml
```

### Ejecución en Background

Para videos largos, usar tmux/screen:

```bash
# Iniciar sesión tmux
tmux new-session -s echo-bering

# Ejecutar pipeline
uv run python -m src.main --config config.yaml

# Desconectar (Ctrl+B, D)
# Reconectar: tmux attach-session -t echo-bering
```

## Despliegue en Producción

### Consideraciones de Producción

- **Monitoreo**: Redirigir logs a sistema centralizado
- **Backup**: Backup periódico del directorio `output/`
- **Límites de Recursos**: Establecer límites de CPU/memoria
- **Seguridad**: Restringir acceso al directorio de outputs
- **Actualizaciones**: Probar nuevas versiones en staging antes de producción

### Script de Automatización

Crear script `run-pipeline.sh`:

```bash
#!/bin/bash
set -e

VIDEO_PATH="$1"
CONFIG_PATH="${2:-config.yaml}"
OUTPUT_DIR="${3:-output}"

# Validar entradas
if [ -z "$VIDEO_PATH" ]; then
    echo "Uso: $0 <video_path> [config_path] [output_dir]"
    exit 1
fi

if [ ! -f "$VIDEO_PATH" ]; then
    echo "Error: Video no encontrado: $VIDEO_PATH"
    exit 1
fi

# Crear timestamp para tracking
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="pipeline_${TIMESTAMP}.log"

echo "Iniciando pipeline para: $VIDEO_PATH"
echo "Configuración: $CONFIG_PATH"
echo "Output: $OUTPUT_DIR"
echo "Log: $LOG_FILE"

# Ejecutar pipeline
uv run python -m src.main \
    --config "$CONFIG_PATH" \
    --input-video "$VIDEO_PATH" \
    --output-dir "$OUTPUT_DIR" \
    2> "$LOG_FILE"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Pipeline completado exitosamente"
    echo "Logs: $LOG_FILE"
else
    echo "❌ Pipeline falló con código: $EXIT_CODE"
    echo "Ver logs en: $LOG_FILE"
    exit $EXIT_CODE
fi
```

### Docker (Opcional)

Crear `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Instalar ffmpeg y uv
RUN apt-get update && apt-get install -y ffmpeg && \
    pip install uv

# Copiar código
WORKDIR /app
COPY . .

# Instalar dependencias
RUN uv sync --no-dev

# Comando por defecto
CMD ["uv", "run", "python", "-m", "src.main"]
```

Construir y ejecutar:

```bash
# Construir imagen
docker build -t echo-bering .

# Ejecutar con montaje de volúmenes
docker run -v $(pwd)/videos:/app/videos \
           -v $(pwd)/output:/app/output \
           -v $(pwd)/.env:/app/.env \
           echo-bering
```

## Troubleshooting Común

### Problemas de Instalación
- **ffmpeg no encontrado**: Instalar ffmpeg en el sistema (`brew install ffmpeg` en macOS, `apt install ffmpeg` en Ubuntu)
- **Errores de dependencias**: Asegurar que Python 3.10+ está instalado y activo
- **Permisos denegados**: Verificar permisos de escritura en directorios de output

### Problemas de Ejecución  
- **API keys inválidas**: Verificar formato y permisos de las credenciales
- **Videos no soportados**: Asegurar que el formato de video es compatible con ffmpeg
- **Memoria insuficiente**: Reducir `chunk_duration_minutes` para videos muy largos
- **Costos excesivos**: Ajustar `max_budget_usd` y monitorear durante ejecución

## Actualización y Mantenimiento

### Actualización de Dependencias

```bash
# Actualizar dependencias con uv
uv lock --upgrade
uv sync

# Verificar compatibilidad
uv run pytest
```

### Backup de Configuración

Mantener backups de configuraciones exitosas:

```bash
# Backup de configuración actual
cp config.yaml configs/backup_$(date +%Y%m%d).yaml

# Backup de credenciales (¡cuidado con seguridad!)
cp .env secrets/backup_$(date +%Y%m%d).env
```

### Monitoreo de Uso

Trackear métricas clave:

- **Videos procesados por día**
- **Costo promedio por video**  
- **Tasa de éxito/fallo**
- **Tiempo promedio de procesamiento**
- **Capítulos generados por video**

Estas métricas ayudan a optimizar configuración y predecir costos futuros.