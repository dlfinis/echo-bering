# Guía para Casos Extremos: Videos Largos y Múltiples Interlocutores

## Videos de 4+ Horas

### Estrategia Recomendada: Chunking Adaptativo Inteligente

Para videos extremadamente largos (4-6 horas), se recomienda una estrategia en capas:

#### **Opción 1: Pre-procesamiento + Chunking (Recomendado)**

```yaml
# config.long-video.yaml
asr_provider: groq
asr_model: whisper-large-v3-turbo
llm_provider: deepseek
llm_model: deepseek-v4-flash
language: es
cut_mode: precise
max_budget_usd: 5.0

# Chunking agresivo para videos largos
chunk_duration_minutes: 8    # Más pequeño para mayor fiabilidad
chunk_overlap_seconds: 60   # Mayor overlap para evitar cortes abruptos
batch_processing: true
segment_timestamps: true
```

**Pasos adicionales requeridos**:

1. **Pre-cortar el video en segmentos manejables** (opcional pero recomendado):
   ```bash
   # Dividir video de 4h en segmentos de 30min
   ffmpeg -i input_4h.mp4 -c copy -f segment -segment_time 1800 -reset_timestamps 1 segment_%03d.mp4
   ```

2. **Procesar cada segmento individualmente**:
   ```bash
   for segment in segment_*.mp4; do
     echo "input_video: ./$segment" > config_temp.yaml
     uv run python -m src.main --config config_temp.yaml
   done
   ```

3. **Unificar resultados manualmente** si se necesita un solo output.

#### **Opción 2: AssemblyAI para Máxima Calidad**

```yaml
# config.assemblyai.long.yaml  
asr_provider: assemblyai
llm_provider: deepseek
llm_model: deepseek-v4-flash
language: es
cut_mode: precise
max_budget_usd: 15.0  # Presupuesto realista para 4h

# AssemblyAI maneja automáticamente videos largos
batch_processing: false
word_timestamps: true
segment_timestamps: false
```

**Ventajas**: 
- Procesamiento automático sin chunking manual
- Diarización de hablantes incluida
- Word-level timestamps precisos

**Desventajas**:
- Costo muy alto (~$12-15 para 4h)
- Tiempo de procesamiento largo (30-60 minutos)

#### **Opción 3: mlx-whisper Local (Sin Costos)**

```yaml
# config.mlx.long.yaml
asr_provider: mlx-whisper
asr_model: large
llm_provider: deepseek  
llm_model: deepseek-v4-flash
language: es
cut_mode: precise
max_budget_usd: 0.5  # Solo para LLM

batch_processing: false
word_timestamps: true
segment_timestamps: false
```

**Requisitos**:
- RAM suficiente (>16GB recomendado)
- Paciencia (puede tomar 2-4 horas para 4h de video)
- GPU recomendada para aceleración

### Consideraciones Específicas para Videos Largos

1. **Memoria y Recursos**:
   - Monitorear uso de RAM durante procesamiento
   - Considerar procesamiento por lotes para evitar OOM
   - Usar `--verbose` para monitorear progreso

2. **Calidad vs Costo**:
   - Videos >2h justifican inversión en AssemblyAI
   - Videos <2h funcionan bien con Groq + chunking
   - Videos >4h considerar pre-corte manual

3. **Estrategia Híbrida**:
   ```bash
   # Detectar duración y elegir proveedor automáticamente
   DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 input.mp4)
   if [ $(echo "$DURATION > 7200" | bc) -eq 1 ]; then
     # >2h, usar AssemblyAI
     CONFIG="config.assemblyai.long.yaml"
   else
     # <=2h, usar Groq
     CONFIG="config.groq.yaml"  
   fi
   uv run python -m src.main --config $CONFIG
   ```

## Múltiples Interlocutores (Contenido Conversacional)

### Estrategia Recomendada: AssemblyAI con Diarización

Para contenido con múltiples hablantes (entrevistas, podcasts, debates):

```yaml
# config.multi-speaker.yaml
asr_provider: assemblyai
llm_provider: deepseek
llm_model: deepseek-v4-flash
language: es
cut_mode: precise
max_budget_usd: 3.0

# Configuración específica para múltiples hablantes
required_asr_features: ["speaker_diarization"]  # Asegura diarización
batch_processing: false
word_timestamps: true
segment_timestamps: false
```

### Características Especiales para Multi-Hablante

1. **Diarización Automática**:
   - AssemblyAI identifica automáticamente diferentes hablantes
   - Los subtítulos incluyen etiquetas de hablante
   - La transcripción preserva quién dijo qué

2. **Segmentación Temática Adaptada**:
   - El LLM considera cambios de hablante como posibles puntos de corte
   - Los capítulos pueden agrupar turnos de habla relacionados
   - Se evitan cortes en medio de intervenciones individuales

3. **Metadata Enriquecida**:
   ```json
   {
     "speakers": ["Entrevistador", "Invitado"],
     "speaker_turns": [
       {"speaker": "Entrevistador", "start": 0, "end": 45},
       {"speaker": "Invitado", "start": 45, "end": 120}
     ]
   }
   ```

### Alternativas para Multi-Hablante

#### **Si AssemblyAI no está disponible**:

1. **Pre-procesamiento con herramientas externas**:
   ```bash
   # Usar pyannote.audio para diarización previa
   python diarize.py --audio input.mp4 --output segments.json
   ```

2. **Procesar segmentos por hablante**:
   - Extraer segmentos de audio por hablante
   - Procesar cada segmento individualmente
   - Unificar resultados manualmente

3. **Configuración Groq con contexto**:
   ```yaml
   # config.groq.multi.yaml
   asr_provider: groq
   # ... otros settings ...
   
   # Añadir contexto al prompt del LLM
   video_topic: "Entrevista con múltiples participantes sobre salud mental"
   ```

### Mejores Prácticas para Contenido Conversacional

1. **Evitar forzar segmentación artificial**:
   - Las conversaciones naturales no siempre tienen cambios temáticos claros
   - Priorizar coherencia de turnos de habla sobre número de capítulos

2. **Considerar formato del contenido**:
   - **Entrevistas**: 1 capítulo por tema/segmento grande
   - **Debates**: 1 capítulo por punto de discusión
   - **Podcasts**: 1 capítulo por sección temática

3. **Validación manual recomendada**:
   - Revisar que los cortes no interrumpan intervenciones
   - Verificar que la diarización sea precisa
   - Ajustar manualmente timestamps si es necesario

## Flujo de Trabajo Recomendado para Casos Extremos

### Paso 1: Análisis Preliminar
```bash
# Verificar duración
DURATION=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 input.mp4)
echo "Duración: $(echo "$DURATION/60" | bc) minutos"

# Verificar canales de audio (mono/stereo)
CHANNELS=$(ffprobe -v quiet -show_entries stream=channels -select_streams a -of csv=p=0 input.mp4)
echo "Canales de audio: $CHANNELS"
```

### Paso 2: Selección de Estrategia
| Duración | Hablantes | Recomendación |
|----------|-----------|---------------|
| <30 min | 1 | Groq (rápido y económico) |
| <2h | 1 | Groq + chunking |
| <2h | múltiples | AssemblyAI |
| 2-4h | 1 | AssemblyAI o mlx-whisper |
| 2-4h | múltiples | AssemblyAI |
| >4h | cualquier | Pre-corte manual + procesamiento por segmentos |

### Paso 3: Ejecución con Monitoreo
```bash
# Para videos largos, usar logging detallado
nohup uv run python -m src.main --config config.long.yaml --verbose > processing.log 2>&1 &

# Monitorear progreso
tail -f processing.log
```

### Paso 4: Validación Post-Procesamiento
1. **Verificar completitud**: Todos los segmentos procesados
2. **Calidad de diarización**: Hablantes correctamente identificados
3. **Coherencia temática**: Capítulos tienen sentido en contexto
4. **Costos reales**: Dentro del presupuesto estimado

## Limitaciones Conocidas y Workarounds

### Limitación 1: RAM insuficiente para mlx-whisper en videos largos
**Workaround**: 
- Usar modelo `base` en lugar de `large`
- Procesar en chunks más pequeños
- Aumentar swap space temporalmente

### Limitación 2: Groq no soporta diarización
**Workaround**:
- Usar AssemblyAI cuando sea crítico
- Implementar post-procesamiento con pyannote.audio
- Aceptar limitación y enfocarse en contenido monólogo

### Limitación 3: Costos prohibitivos para AssemblyAI en videos muy largos
**Workaround**:
- Combinar Groq (transcripción) + post-procesamiento externo (diarización)
- Usar muestras representativas en lugar del video completo
- Implementar compresión de audio sin pérdida de calidad

## Configuraciones Base Actualizadas

Las configuraciones base deben incluir estas variantes:

- `config.base.groq.short.yaml` - Para videos <30min
- `config.base.groq.medium.yaml` - Para videos 30min-2h  
- `config.base.assemblyai.conversation.yaml` - Para múltiples hablantes
- `config.base.mlx.long.yaml` - Para videos >2h offline
- `config.base.hybrid.long.yaml` - Estrategia híbrida para videos extremos

Estas configuraciones deben estar documentadas en la guía principal con ejemplos de uso específicos para cada caso extremo.