# Guía de Inicialización y Pruebas

Guía paso-a-paso para configurar, inicializar y probar Echo-Bering con videos reales.

**Propósito:** Proporcionar instrucciones claras para configurar el entorno, preparar videos de prueba, y validar que el sistema funciona correctamente antes de usarlo en producción.

## Preparación del Entorno

### 1. Requisitos del Sistema

Verificar que todos los requisitos están instalados:

```bash
# Verificar Python 3.10+
python --version
# Debe mostrar: Python 3.10.x o superior

# Verificar uv
uv --version  
# Debe mostrar versión de uv

# Verificar ffmpeg
ffmpeg -version
# Debe mostrar información de ffmpeg

# Verificar espacio en disco
df -h .
# Recomendado: al menos 2GB libres
```

### 2. Configuración Inicial

```bash
# Clonar repositorio (si no lo has hecho)
git clone https://github.com/tu-usuario/echo-bering.git
cd echo-bering

# Instalar dependencias
uv sync

# Configurar credenciales
cp .env.example .env
nano .env  # Editar con tus API keys reales
```

Contenido mínimo del `.env`:
```bash
GROQ_API_KEY=tu_groq_key_aqui
DEEPSEEK_API_KEY=tu_deepseek_key_aqui
# ASSEMBLYAI_API_KEY=tu_assembly_key_aqui  # Opcional
# OPENAI_API_KEY=tu_openai_key_aqui        # Opcional
```

### 3. Configuración de Prueba

Crear archivo `config.test.yaml` para pruebas:

```yaml
# Proveedores (usar los más económicos para pruebas)
asr_provider: groq
llm_provider: deepseek

# Video de prueba
input_video: ./videos/test_short.mp4
output_dir: ./output_test

# Idioma y procesamiento
language: es
cut_mode: fast

# Control de costos (bajo para pruebas)
max_budget_usd: 0.50
chunk_duration_minutes: 10
```

## Preparación de Videos de Prueba

### Videos de Prueba Recomendados

Crear directorio de videos de prueba:

```bash
mkdir -p videos
```

#### Opción 1: Video Corto de Prueba (< 1 minuto)

Descargar un video corto para pruebas rápidas:

```bash
# Ejemplo: descargar un video corto de prueba
# NOTA: Asegúrate de tener derechos para usar el video
wget -O videos/test_short.mp4 "https://example.com/short_test_video.mp4"

# O crear un video de prueba con ffmpeg
ffmpeg -f lavfi -i testsrc=duration=30:size=640x480:rate=30 -f lavfi -i sine=frequency=1000:duration=30 videos/test_short.mp4
```

#### Opción 2: Video de Audio Limpio

Si solo quieres probar la transcripción:

```bash
# Crear audio de prueba
echo "Hola mundo. Este es un video de prueba para Echo-Bering." | text2wave -o test_audio.wav
ffmpeg -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 -t 10 -acodec aac -vcodec libx264 -y videos/audio_test.mp4
```

### Verificación del Video de Prueba

Antes de procesar, verificar que el video es válido:

```bash
# Verificar duración
ffprobe -v quiet -show_entries format=duration -of csv=p=0 videos/test_short.mp4

# Verificar que tiene pista de audio
ffprobe -v quiet -show_streams videos/test_short.mp4 | grep -A5 "Audio:"

# Reproducir localmente (opcional)
ffplay videos/test_short.mp4
```

## Pruebas de Funcionalidad Básica

### 1. Prueba de Configuración

Verificar que la configuración se carga correctamente:

```bash
# Probar carga de configuración
uv run python -c "
from src.config.loader import load_config
config = load_config('config.test.yaml')
print('✅ Configuración cargada correctamente')
print(f'ASR Provider: {config.asr_provider}')
print(f'LLM Provider: {config.llm_provider}')
print(f'Input Video: {config.input_video}')
"
```

### 2. Prueba de Conexión a Proveedores

Verificar que las credenciales funcionan:

```bash
# Probar conexión a Groq
uv run python -c "
import os
from groq import Groq
client = Groq(api_key=os.getenv('GROQ_API_KEY'))
print('✅ Conexión a Groq exitosa')
"

# Probar conexión a DeepSeek  
uv run python -c "
import os
from openai import OpenAI
client = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url='https://api.deepseek.com/v1'
)
print('✅ Conexión a DeepSeek exitosa')
"
```

### 3. Prueba End-to-End Básica

Ejecutar el pipeline con el video de prueba:

```bash
# Ejecutar con modo verbose para ver logs detallados
uv run python -m src.main --config config.test.yaml --verbose

# O ejecutar en background para videos largos
nohup uv run python -m src.main --config config.test.yaml > pipeline.log 2>&1 &
```

### 4. Verificación de Resultados

Después de la ejecución, verificar los outputs:

```bash
# Verificar que se crearon capítulos
ls -la output_test/

# Verificar estructura de un capítulo
ls -la output_test/capitulo_*/

# Verificar metadata.json
cat output_test/capitulo_*/metadata.json | jq '.'

# Verificar subtítulos
cat output_test/capitulo_*/capitulo_*.srt

# Verificar reporte final
cat output_test/processing_report.json | jq '.'
```

## Checklist de Validación

Antes de considerar el sistema listo para producción, verificar:

### ✅ Funcionalidad Básica
- [ ] Configuración se carga correctamente
- [ ] Conexión a proveedores funciona
- [ ] Extracción de audio exitosa
- [ ] Transcripción generada correctamente
- [ ] Segmentación en capítulos funciona
- [ ] Metadata enriquecida generada
- [ ] Cortes de video creados
- [ ] Subtítulos .srt generados

### ✅ Calidad de Outputs
- [ ] Transcripción coincide con el audio original
- [ ] Capítulos tienen sentido temático
- [ ] Metadata incluye descripción, contexto, términos relevantes
- [ ] Timestamps son precisos (±3 segundos)
- [ ] Costos están dentro del presupuesto

### ✅ Manejo de Errores
- [ ] Configuración inválida muestra errores claros
- [ ] Credenciales inválidas se detectan temprano
- [ ] Videos sin audio se manejan graciosamente
- [ ] Presupuesto excedido detiene el pipeline ordenadamente

### ✅ Rendimiento
- [ ] Tiempo de procesamiento razonable (< 2x duración del video)
- [ ] Uso de memoria estable
- [ ] No hay fugas de recursos

## Pruebas Específicas por Escenario

### Prueba 1: Video Muy Corto (< 30 segundos)
- **Objetivo**: Verificar que no falla con videos mínimos
- **Configuración**: `max_budget_usd: 0.10`
- **Validación**: Al menos 1 capítulo generado

### Prueba 2: Video con Múltiples Temas (2-5 minutos)
- **Objetivo**: Verificar segmentación semántica
- **Configuración**: Video con cambios temáticos claros
- **Validación**: Capítulos corresponden a cambios temáticos

### Prueba 3: Video Largo (> 30 minutos)
- **Objetivo**: Verificar chunking adaptativo
- **Configuración**: `chunk_duration_minutes: 20`
- **Validación**: Sistema divide automáticamente y reconstruye correctamente

### Prueba 4: Fallo de Proveedor
- **Objetivo**: Verificar fallback automático
- **Configuración**: Configurar API key inválida para Groq
- **Validación**: Sistema cambia a AssemblyAI/OpenAI automáticamente

## Troubleshooting Común en Pruebas

### Problema: "No module named 'src'"
**Solución**: Asegurar que estás en el directorio raíz del proyecto y ejecutar con `uv run python -m src.main`

### Problema: "API key not found"
**Solución**: Verificar que el archivo `.env` está en el directorio raíz y contiene las variables correctas

### Problema: "ffmpeg not found"
**Solución**: Instalar ffmpeg en el sistema (`brew install ffmpeg` en macOS, `apt install ffmpeg` en Ubuntu)

### Problema: Transcripción vacía
**Solución**: Verificar que el video tiene pista de audio y calidad adecuada

### Problema: Costos excesivos
**Solución**: Reducir `max_budget_usd` y usar proveedores más económicos para pruebas

## Validación Antes de Producción

Antes de usar en producción, asegurar:

1. **Pruebas completadas**: Todas las pruebas del checklist pasan
2. **Costos verificados**: Presupuesto realista basado en pruebas
3. **Calidad aceptable**: Outputs cumplen con expectativas de calidad
4. **Documentación actualizada**: README y docs reflejan configuración real
5. **Monitoreo configurado**: Logs y métricas disponibles para producción

## Comandos Útiles para Pruebas

```bash
# Limpiar outputs de prueba
rm -rf output_test/

# Ver logs en tiempo real
tail -f pipeline.log

# Monitorear uso de recursos durante ejecución
htop

# Verificar tamaño de outputs
du -sh output_test/

# Comparar costos reales vs estimados
grep -E "(cost|budget)" pipeline.log
```

Esta guía te permite validar completamente el funcionamiento de Echo-Bering antes de considerarlo listo para producción.