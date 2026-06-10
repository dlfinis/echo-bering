# Manejo de Errores

Estrategia de manejo de excepciones y errores en Echo-Bering, incluyendo códigos de error, políticas de reintentos y fallbacks.

**Propósito:** Documentar cómo el sistema maneja errores, fallas y condiciones excepcionales para mantener la robustez y la experiencia del usuario.

## Jerarquía de Excepciones

```python
Exception
└── EchoBeringError
    ├── ConfigurationError          # Errores de configuración
    ├── ProviderError              # Errores de proveedores externos  
        ├── ProviderSizeLimitError  # Rechazo por tamaño/duración
        ├── ProviderAPIError        # Errores de API (429, 503, etc.)
        └── ProviderAuthenticationError  # Credenciales inválidas
    ├── ProcessingError            # Errores durante el procesamiento
        ├── AudioExtractionError    # Fallos en extracción de audio
        ├── TranscriptionError      # Fallos en transcripción
        ├── SegmentationError       # Fallos en segmentación LLM
        └── MaterializationError    # Fallos en generación de outputs
    └── CheckpointError           # Errores en gestión de checkpoints
```

## Políticas de Reintento y Fallback

### Reintentos por Proveedor
- **Máximo**: 2 reintentos por llamada fallida
- **Backoff**: Exponencial con jitter (1s, 2s, 4s)
- **Condiciones**: Solo para errores transitorios (5xx, timeouts)

### Fallback entre Proveedores
- **Automático**: Después de fallos persistentes en un proveedor
- **Orden**: Configurable en `config.yaml` (Groq → AssemblyAI → OpenAI por defecto)
- **Costo**: Se rastrea en tiempo real y se detiene si excede presupuesto

### Manejo de Fallos Parciales
- **Chunks fallidos**: Se marcan como `[TRANSCRIPTION_FAILED]` pero se continúa procesando
- **Capítulos incompletos**: Se generan con `needs_review: true` y advertencias visibles
- **Checkpointing**: Permite reanudar desde el último punto exitoso

## Códigos de Error Comunes

| Código | Tipo | Descripción | Acción Recomendada |
|--------|------|-------------|-------------------|
| `CONFIG_001` | ConfigurationError | Archivo config.yaml inválido | Validar sintaxis YAML |
| `CONFIG_002` | ConfigurationError | API key faltante para proveedor | Añadir credenciales en .env |
| `PROVIDER_001` | ProviderSizeLimitError | Video excede límites del proveedor | El sistema dividirá automáticamente en chunks |
| `PROVIDER_002` | ProviderAPIError | Rate limit excedido (429) | Esperar o cambiar de proveedor |
| `PROVIDER_003` | ProviderAuthenticationError | Credenciales inválidas | Verificar API keys en .env |
| `PROCESS_001` | AudioExtractionError | ffmpeg no disponible | Instalar ffmpeg en el sistema |
| `PROCESS_002` | TranscriptionError | Transcripción vacía/nula | Verificar calidad del audio de entrada |
| `PROCESS_003` | SegmentationError | LLM devolvió JSON inválido | Reintentar o ajustar temperatura del LLM |

## Umbrales de Confianza

| Métrica | Umbral Advertencia | Umbral Revisión Requerida | Comportamiento |
|---------|-------------------|--------------------------|----------------|
| `segmentation_score` | < 0.7 | < 0.5 | Advertencia visible en TUI |
| `transcription_quality` | < 0.8 | < 0.6 | Marcar capítulo para revisión |
| `content_coherence` | < 0.8 | < 0.7 | Sugerir re-procesamiento |

## Logging y Observabilidad

- **Niveles**: DEBUG (desarrollo), INFO (producción), WARNING/ERROR (problemas)
- **Campos**: `stage`, `provider`, `video_id`, `chapter_number`, `error_code`
- **Formato**: JSON estructurado para integración con sistemas de logging