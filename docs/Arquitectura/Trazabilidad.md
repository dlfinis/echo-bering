# Trazabilidad

Estrategia de trazabilidad y correlación de operaciones en Echo-Bering para debugging y auditoría.

**Propósito:** Documentar cómo se rastrean las operaciones a través del pipeline y cómo correlacionar eventos para debugging efectivo.

## Identificadores de Correlación

### Video ID
- **Generado**: Hash del path del video de entrada + timestamp
- **Formato**: `vid_<hash>_<timestamp>`
- **Uso**: Correlaciona todas las operaciones relacionadas con un video específico

### Capítulo ID  
- **Generado**: Basado en timestamps de inicio/fin + video ID
- **Formato**: `chap_<video_id>_<start_time>_<end_time>`
- **Uso**: Identifica capítulos individuales para tracking y debugging

### Operación ID
- **Generado**: UUID por cada etapa del pipeline
- **Formato**: UUID estándar
- **Uso**: Rastrea ejecuciones específicas de cada etapa (extracción, transcripción, etc.)

## Logging Estructurado

Todos los logs incluyen campos de contexto para correlación:

```json
{
  "timestamp": "2026-06-06T15:30:00Z",
  "level": "INFO",
  "message": "Transcription completed successfully",
  "context": {
    "video_id": "vid_a1b2c3d4_1686066600",
    "operation_id": "550e8400-e29b-41d4-a716-446655440000",
    "stage": "transcription",
    "provider": "groq",
    "duration_seconds": 182,
    "cost_usd": 0.12,
    "confidence_score": 0.88
  }
}
```

## Checkpoints y Estado

### Estructura de Checkpoints
```
output/
└── .checkpoints/
    ├── vid_a1b2c3d4_1686066600/
    │   ├── audio_extracted.json
    │   ├── transcription_complete.json  
    │   ├── segmentation_complete.json
    │   ├── enrichment_complete.json
    │   └── processing_state.json
    └── processing_report.json
```

### Processing State
Cada checkpoint incluye metadata para reconstrucción:

```json
{
  "video_id": "vid_a1b2c3d4_1686066600",
  "current_stage": "segmentation",
  "completed_stages": ["audio_extraction", "transcription"],
  "provider_used": {
    "asr": "groq",
    "llm": "deepseek"
  },
  "cost_accumulated": 0.12,
  "timestamps": {
    "started_at": "2026-06-06T15:30:00Z",
    "audio_extraction_completed": "2026-06-06T15:31:22Z",
    "transcription_completed": "2026-06-06T15:33:04Z"
  }
}
```

## Correlación de Errores

Cuando ocurre un error, se incluyen todos los identificadores relevantes:

```json
{
  "timestamp": "2026-06-06T15:35:12Z",
  "level": "ERROR", 
  "message": "LLM returned invalid JSON",
  "error_code": "PROCESS_003",
  "context": {
    "video_id": "vid_a1b2c3d4_1686066600",
    "chapter_id": "chap_vid_a1b2c3d4_1686066600_001532_003418",
    "operation_id": "550e8400-e29b-41d4-a716-446655440001",
    "stage": "segmentation",
    "provider": "deepseek",
    "retry_count": 2,
    "llm_response_snippet": "{\"invalid\": json...}"
  }
}
```

## Auditoría y Reportes

### Processing Report
Generado al finalizar el pipeline:

```json
{
  "video_id": "vid_a1b2c3d4_1686066600",
  "input_video": "./videos/test.mp4",
  "duration_seconds": 11520,
  "chapters_generated": 14,
  "providers_used": {
    "asr": "groq",
    "llm": "deepseek" 
  },
  "cost_breakdown": {
    "asr_cost_usd": 0.98,
    "llm_cost_usd": 0.25,
    "total_cost_usd": 1.23
  },
  "processing_timeline": {
    "started_at": "2026-06-06T15:30:00Z",
    "completed_at": "2026-06-06T15:45:22Z",
    "total_duration_seconds": 922
  },
  "warnings": [
    {
      "chapter_id": "chap_vid_a1b2c3d4_1686066600_004530_005210",
      "warning_type": "low_confidence",
      "confidence_score": 0.65,
      "message": "Low segmentation confidence - manual review recommended"
    }
  ]
}
```

## Integración con Sistemas Externos

- **Filesystem**: Todos los artefactos se guardan en el filesystem para auditoría fácil
- **Stdout/Stderr**: Logs estructurados en formato JSON para integración con SIEM
- **Return Codes**: Código de salida 0 (éxito), 1 (error configuración), 2 (error procesamiento), 3 (error proveedor)

## Debugging Recomendado

1. **Identificar video_id** desde el log inicial
2. **Buscar todos los logs** con ese video_id  
3. **Verificar checkpoints** en `output/.checkpoints/<video_id>/`
4. **Analizar processing_report.json** para resumen completo
5. **Revisar capítulos específicos** si hay advertencias de confianza