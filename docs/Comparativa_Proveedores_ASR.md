# Comparativa de Proveedores ASR para Echo-Bering

## Resultados de pruebas con video de 20 minutos

### AssemblyAI
- **Capítulos generados**: 1 (demasiado conservador)
- **Calidad de transcripción**: Excelente (⭐⭐⭐⭐⭐)
- **Timing**: Word-level preciso con diarización de hablantes
- **Costo**: Alto (~$2.00 para 20min)
- **Ventajas**: Máxima calidad, soporta archivos grandes
- **Desventajas**: No segmenta bien el contenido, muy costoso

### Groq  
- **Capítulos generados**: 5 (segmentación natural y equilibrada)
- **Calidad de transcripción**: Muy buena (⭐⭐⭐⭐)
- **Timing**: Segment-level (suficiente para capítulos)
- **Costo**: Moderado (~$1.00 para 20min con chunking)
- **Ventajas**: Buen balance calidad/costo, segmentación óptima
- **Desventajas**: Límite de 25MB requiere chunking inteligente

### mlx-whisper (large)
- **Capítulos generados**: 3 (segmentación razonable)
- **Calidad de transcripción**: Buena (⭐⭐⭐) 
- **Timing**: Word-level decente
- **Costo**: $0 (offline)
- **Ventajas**: Sin costos API, funciona offline, sin límites de tamaño
- **Desventajas**: Errores de transcripción en audio complejo, más lento

## Recomendaciones

### Escenario 1: Calidad máxima (contenido premium)
- **Proveedor**: AssemblyAI
- **Uso**: Videos cortos (<30min) donde la calidad justifica el costo
- **Configuración**: `config.base.assemblyai.yaml`

### Escenario 2: Balance óptimo (uso general)
- **Proveedor**: Groq con chunking  
- **Uso**: La mayoría de videos (5-30min)
- **Configuración**: `config.base.groq.yaml`
- **Chunking**: 12 minutos por chunk (~25MB límite)

### Escenario 3: Procesamiento masivo/offline
- **Proveedor**: mlx-whisper large
- **Uso**: Bulk processing, entornos sin internet, prototipado
- **Configuración**: `config.base.mlx.yaml`

## Problemas identificados

1. **Enriquecimiento LLM falla**: El LLM de enriquecimiento no parsea correctamente JSON
   - **Solución**: Implementar mejor manejo de errores y validación flexible

2. **Segmentación demasiado conservadora (AssemblyAI)**: 
   - **Solución**: Ajustar prompts para forzar mejor segmentación temática

3. **Errores de transcripción en mlx-whisper**:
   - **Solución**: Implementar post-procesamiento con diccionarios contextuales

## Próximos pasos

1. **Arreglar el módulo de enriquecimiento** para manejar mejor el parsing JSON
2. **Implementar post-procesamiento de transcripción** con limpieza de errores comunes
3. **Optimizar prompts de segmentación** para diferentes proveedores
4. **Documentar configuraciones base** para diferentes escenarios de uso