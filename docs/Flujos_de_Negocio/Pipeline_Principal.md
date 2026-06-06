# Pipeline Principal

Flujo completo del pipeline de procesamiento de Echo-Bering desde la entrada de video hasta la generación de capítulos estructurados.

**Propósito:** Documentar el flujo principal de ejecución del sistema y las interacciones entre componentes.

**Endpoint:** CLI `python -m src.main --config config.yaml`

```mermaid
sequenceDiagram
    participant User as Usuario
    participant CLI as CLI/Main
    participant Orchestrator as PipelineOrchestrator
    participant AudioExtractor as AudioExtractor
    participant Transcriber as Transcriber
    participant Segmenter as ChapterSegmenter
    participant Enricher as MetadataEnricher
    participant Materializer as ChapterMaterializer
    participant Checkpoint as CheckpointManager
    participant TUI as TUIRenderer
    
    User->>+CLI: Ejecuta con config.yaml
    CLI->>+Orchestrator: Inicializa pipeline
    Orchestrator->>Checkpoint: Verifica checkpoints existentes
    Checkpoint-->>Orchestrator: Estado de reanudación
    Orchestrator->>TUI: Inicia display progreso
    TUI-->>Orchestrator: Callbacks de progreso registrados
    
    alt Reanudación desde checkpoint
        Orchestrator->>Orchestrator: Salta etapas completadas
    end
    
    Orchestrator->>+AudioExtractor: Extrae audio (ffmpeg)
    AudioExtractor-->>-Orchestrator: Audio WAV 16kHz mono
    Orchestrator->>Checkpoint: Guarda estado audio_extracted
    Orchestrator->>TUI: Actualiza progreso
    
    Orchestrator->>+Transcriber: Transcribe audio
    Transcriber->>Transcriber: Intenta transcripción completa
    alt Proveedor rechaza por tamaño
        Transcriber->>Transcriber: Divide en chunks adaptativos
        loop Por cada chunk
            Transcriber->>ASRProvider: Transcribe chunk
            ASRProvider-->>Transcriber: Transcripción parcial
        end
        Transcriber->>Transcriber: Reconstruye transcripción completa
    else Transcripción exitosa
        Transcriber->>ASRProvider: Transcribe audio completo
        ASRProvider-->>Transcriber: Transcripción completa
    end
    Transcriber-->>-Orchestrator: Transcripción con timestamps
    Orchestrator->>Checkpoint: Guarda estado transcription_complete
    Orchestrator->>TUI: Actualiza progreso + costos
    
    Orchestrator->>+Segmenter: Segmenta en capítulos
    Segmenter->>LLMProvider: LLM segmentación semántica
    LLMProvider-->>Segmenter: Capítulos con timestamps
    Segmenter-->>-Orchestrator: Lista de capítulos
    Orchestrator->>Checkpoint: Guarda estado segmentation_complete
    Orchestrator->>TUI: Actualiza progreso
    
    loop Por cada capítulo
        Orchestrator->>+Enricher: Enriquece metadata capítulo
        Enricher->>LLMProvider: LLM enriquecimiento metadata
        LLMProvider-->>Enricher: Metadata enriquecida JSON
        Enricher-->>-Orchestrator: Metadata capítulo validada
        Orchestrator->>Checkpoint: Guarda estado enrichment_complete
        Orchestrator->>TUI: Actualiza progreso
        
        Orchestrator->>+Materializer: Materializa capítulo
        Materializer->>Materializer: Corta video con ffmpeg
        Materializer->>Materializer: Genera subtítulos .srt
        Materializer->>Materializer: Crea metadata.json
        Materializer-->>-Orchestrator: Capítulo materializado
        Orchestrator->>TUI: Actualiza progreso
    end
    
    Orchestrator->>Checkpoint: Limpia checkpoints (éxito)
    Orchestrator->>TUI: Muestra resumen final
    TUI-->>CLI: Reporte final con costos
    CLI-->>-User: Pipeline completado exitosamente
```

## Fases del Flujo

1. **Inicialización**: Carga configuración, verifica checkpoints existentes, inicializa TUI
2. **Extracción de Audio**: Convierte video input a audio WAV mono 16kHz usando ffmpeg
3. **Transcripción Adaptativa**: Intenta transcripción completa, fallback a chunks si proveedor rechaza
4. **Segmentación Semántica**: Usa LLM para dividir transcripción en capítulos temáticos coherentes  
5. **Enriquecimiento por Capítulo**: Para cada capítulo, usa LLM para generar metadata enriquecida
6. **Materialización**: Genera cortes físicos de video, subtítulos .srt y archivos metadata.json
7. **Finalización**: Limpia checkpoints, muestra resumen final con costos y estadísticas

## Consideraciones

- **Chunking Adaptativo**: Solo se aplica cuando el proveedor rechaza el audio completo por límites técnicos
- **Reanudación**: El sistema puede reanudar desde cualquier checkpoint guardado después de fallos
- **Costos en Tiempo Real**: El TUI muestra costos acumulados y estimación final durante la ejecución
- **Manejo de Errores**: Fallos parciales (chunks fallidos) no detienen el pipeline completo
- **Validación de Outputs**: Todos los JSON generados por LLM se validan contra esquemas Pydantic
- **Límites de Presupuesto**: El pipeline se detiene si los costos acumulados exceden el presupuesto configurado