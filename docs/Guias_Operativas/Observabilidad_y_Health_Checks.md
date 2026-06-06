# Observabilidad y Health Checks

Estrategia de observabilidad para monitorear el estado y rendimiento de Echo-Bering durante la ejecución.

**Propósito:** Proporcionar visibilidad en tiempo real del estado del sistema, costos, progreso y posibles problemas durante la ejecución del pipeline.

## Health Checks

Echo-Bering es una aplicación CLI/TUI, por lo que los health checks se implementan como verificaciones previas a la ejecución:

### Verificaciones Previas
| Verificación | Comando | Propósito |
|--------------|---------|-----------|
| **Dependencias** | `uv run python -c "import ffmpeg; print('OK')"` | Verificar que ffmpeg esté disponible |
| **Credenciales** | `uv run python -c "from src.config.loader import load_config; c = load_config(); print('API keys loaded')"` | Validar configuración y credenciales |
| **Espacio en Disco** | `df -h .` | Asegurar suficiente espacio para outputs |
| **Memoria Disponible** | `free -h` | Verificar recursos para procesamiento |

## Métricas Clave

### Métricas de Pipeline
| Métrica | Tipo | Descripción | Umbral de Alerta |
|---------|------|-------------|------------------|
| `pipeline_duration_seconds` | Timer | Tiempo total de ejecución | > 2x duración video |
| `cost_accumulated_usd` | Gauge | Costos acumulados en USD | > presupuesto configurado |
| `chapters_generated` | Counter | Número de capítulos generados | 0 (sin capítulos) |
| `warnings_count` | Counter | Advertencias durante ejecución | > 3 |
| `needs_review_count` | Counter | Capítulos requiriendo revisión | > 1 |

### Métricas de Proveedor  
| Métrica | Tipo | Descripción | Umbral de Alerta |
|---------|------|-------------|------------------|
| `asr_calls_total` | Counter | Llamadas totales a ASR | N/A |
| `llm_calls_total` | Counter | Llamadas totales a LLM | N/A |
| `provider_fallbacks` | Counter | Cambios de proveedor por fallos | > 2 |
| `retry_attempts` | Counter | Reintentos por llamadas fallidas | > 5 |

## Logging Estructurado

Todos los logs se emiten en formato JSON estructurado para integración con sistemas de logging:

```json
{
  "timestamp": "2026-06-06T15:30:00Z",
  "level": "INFO",
  "message": "Pipeline started successfully",
  "context": {
    "video_id": "vid_a1b2c3d4_1686066600",
    "video_duration": 11520,
    "asr_provider": "groq",
    "llm_provider": "deepseek",
    "max_budget_usd": 2.0
  }
}
```

### Niveles de Log
- **DEBUG**: Información detallada para desarrollo (desactivado por defecto)
- **INFO**: Eventos normales del pipeline (activado por defecto)
- **WARNING**: Condiciones que podrían requerir atención (advertencias de confianza)
- **ERROR**: Fallos que interrumpen el flujo normal (errores de proveedor, configuración)

## TUI Display

La interfaz TUI muestra información en tiempo real:

```
╭─────────────────────────────────────────╮
│         Echo-Bering v1.0.0              │
╰─────────────────────────────────────────╯

📹 Video: ./videos/test.mp4
⏱️  Duración: 3h 12min
🎯 ASR: Groq (Whisper Large v3 Turbo)
🧠 LLM: DeepSeek v4 Flash

▶ Extrayendo audio...
  [████████████████████] 100% ✓

▶ Transcribiendo...
  [████████████████████] 100% ✓
  ✓ Transcripción completa (42,831 palabras)

▶ Segmentando capítulos (DeepSeek)...
  [████████████░░░░░░░░] 64% (9/14 capítulos)

💰 Coste real: $1.23 USD (Presupuesto: $2.00)
   ↳ ASR: $0.98 | LLM: $0.25
```

## Alertas Configuradas

### Alertas de Costo
- **Advertencia**: Costo acumulado > 80% del presupuesto
- **Error**: Costo acumulado > 100% del presupuesto (pipeline se detiene)

### Alertas de Calidad  
- **Advertencia**: Capítulo con confidence_score < 0.7
- **Error**: Capítulo con confidence_score < 0.5 (marcado para revisión)

### Alertas de Rendimiento
- **Advertencia**: Tiempo de procesamiento > 2x duración del video
- **Error**: Fallos consecutivos en el mismo proveedor (> 3 intentos)

## Integración con Sistemas Externos

### Filesystem
- **Outputs**: Todos los artefactos se guardan en filesystem para auditoría fácil
- **Checkpoints**: Estado persistente en `output/.checkpoints/`
- **Reportes**: `processing_report.json` con resumen completo

### Stdout/Stderr
- **Logs**: Formato JSON estructurado en stderr
- **Progreso**: TUI interactivo en stdout
- **Errores**: Mensajes de error claros con códigos específicos

### Return Codes
- **0**: Éxito completo
- **1**: Error de configuración
- **2**: Error de procesamiento  
- **3**: Error de proveedor
- **4**: Presupuesto excedido

## Monitoreo Recomendado

Para entornos productivos, se recomienda:

1. **Redirección de logs**: `echo-bering 2> pipeline.log`
2. **Parsing de logs**: Extraer métricas clave para dashboards
3. **Alertas automatizadas**: Monitorear return codes y thresholds
4. **Auditoría periódica**: Revisar `processing_report.json` para tendencias
5. **Capacidad de disco**: Monitorear crecimiento de directorio `output/`