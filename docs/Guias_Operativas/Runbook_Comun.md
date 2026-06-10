# Runbook Común

Procedimientos de troubleshooting para errores comunes en Echo-Bering.

**Propósito:** Proporcionar guías paso-a-paso para diagnosticar y resolver problemas frecuentes durante la ejecución del pipeline.

## Códigos de Error Comunes

### CONFIG_001 - Configuración YAML Inválida

**Síntomas**:
- Mensaje: "Invalid YAML configuration"
- Código de salida: 1
- Log: "yaml.parser.ParserError"

**Diagnóstico**:
```bash
# Validar sintaxis YAML
yamllint config.yaml

# Verificar indentación
python -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

**Resolución**:
1. Corregir indentación (usar espacios, no tabs)
2. Asegurar que los valores string con caracteres especiales estén entre comillas
3. Verificar que las listas usen `-` correctamente
4. Validar que las claves no tengan caracteres inválidos

**Prevención**:
- Usar editor con resaltado de sintaxis YAML
- Validar configuración antes de ejecutar: `uv run python -m src.config.loader`

### CONFIG_002 - API Key Faltante

**Síntomas**:
- Mensaje: "Missing API key for provider: groq"
- Código de salida: 1  
- Log: "ConfigurationError: Missing required environment variable"

**Diagnóstico**:
```bash
# Verificar variables de entorno
env | grep -E "(GROQ|ASSEMBLY|OPENAI|DEEPSEEK)_API_KEY"

# Verificar archivo .env
cat .env | grep API_KEY
```

**Resolución**:
1. Asegurar que el archivo `.env` existe en el directorio raíz
2. Verificar que las variables tienen el nombre correcto (mayúsculas, guiones bajos)
3. Confirmar que las API keys son válidas y tienen permisos adecuados
4. Si se usa Docker, asegurar que el archivo `.env` está montado correctamente

**Prevención**:
- Usar `.env.example` como template
- Validar credenciales periódicamente
- Implementar health check previo a ejecución

### PROVIDER_001 - Límite de Tamaño Excedido

**Síntomas**:
- Mensaje: "Provider rejected audio due to size limits"
- Código de salida: 3
- Log: "ProviderSizeLimitError"

**Diagnóstico**:
```bash
# Verificar duración del video
ffprobe -v quiet -show_entries format=duration -of csv=p=0 input_video.mp4

# Verificar tamaño del archivo
ls -lh input_video.mp4
```

**Resolución**:
1. **No requiere acción**: El sistema automáticamente dividirá en chunks
2. Verificar que `chunk_duration_minutes` está configurado adecuadamente (default: 20)
3. Monitorear costos ya que múltiples chunks = múltiples llamadas API
4. Si persiste, considerar pre-procesar el video para reducir tamaño

**Prevención**:
- Conocer límites de cada proveedor:
  - Groq: ~30 minutos
  - AssemblyAI: ~5 horas  
  - OpenAI: ~60 minutos

### PROVIDER_002 - Rate Limit Excedido

**Síntomas**:
- Mensaje: "Rate limit exceeded for provider"
- Código de salida: 3
- Log: "ProviderAPIError: 429 Too Many Requests"

**Diagnóstico**:
```bash
# Verificar logs para identificar proveedor específico
grep "429" pipeline.log

# Contar llamadas recientes
grep "provider_call" pipeline.log | tail -20
```

**Resolución**:
1. **Esperar**: El sistema reintentará automáticamente con backoff exponencial
2. **Cambiar proveedor**: Modificar `asr_provider` o `llm_provider` en config.yaml
3. **Reducir paralelismo**: Si procesando múltiples videos, espaciar las ejecuciones
4. **Actualizar plan**: Considerar actualizar plan del proveedor si es uso intensivo

**Prevención**:
- Monitorear cuotas de API regularmente
- Implementar throttling en aplicaciones que llaman a Echo-Bering
- Usar múltiples proveedores para distribuir carga

### PROCESS_001 - ffmpeg No Disponible

**Síntomas**:
- Mensaje: "ffmpeg not found in PATH"
- Código de salida: 2
- Log: "AudioExtractionError: Command 'ffmpeg' not found"

**Diagnóstico**:
```bash
# Verificar instalación de ffmpeg
which ffmpeg
ffmpeg -version

# Verificar PATH en el entorno de ejecución
echo $PATH
```

**Resolución**:
1. **Instalar ffmpeg**:
   - macOS: `brew install ffmpeg`
   - Ubuntu: `sudo apt install ffmpeg`
   - Windows: Descargar desde ffmpeg.org
2. **Verificar PATH**: Asegurar que ffmpeg está en el PATH del usuario que ejecuta
3. **Docker**: Asegurar que ffmpeg está instalado en la imagen
4. **Entornos virtuales**: Instalar ffmpeg a nivel de sistema, no en entorno virtual

**Prevención**:
- Incluir verificación de ffmpeg en health check inicial
- Documentar requisitos del sistema claramente
- Usar contenedores con ffmpeg preinstalado

### PROCESS_002 - Transcripción Vacía

**Síntomas**:
- Mensaje: "Transcription returned empty result"
- Código de salida: 2
- Log: "TranscriptionError: Empty transcription received"

**Diagnóstico**:
```bash
# Verificar calidad del audio de entrada
ffprobe -v quiet -show_streams input_audio.wav

# Escuchar audio de prueba
afplay input_audio.wav  # macOS
aplay input_audio.wav   # Linux
```

**Resolución**:
1. **Verificar audio de entrada**: Asegurar que el video tiene pista de audio
2. **Calidad del audio**: Videos con audio muy bajo/noisy pueden causar transcripciones vacías
3. **Idioma**: Verificar que el idioma del audio coincide con `language` en config.yaml
4. **Probar otro proveedor**: Algunos proveedores manejan mejor ciertos tipos de audio

**Prevención**:
- Validar videos de entrada antes del procesamiento
- Implementar detección automática de idioma si no se especifica
- Probar con clips cortos antes de procesar videos largos

### PROCESS_003 - JSON Inválido del LLM

**Síntomas**:
- Mensaje: "LLM returned invalid JSON"
- Código de salida: 2  
- Log: "SegmentationError: Invalid JSON response from LLM"

**Diagnóstico**:
```bash
# Verificar logs para ver respuesta cruda del LLM
grep "llm_response_snippet" pipeline.log

# Verificar temperatura del LLM
cat config.yaml | grep temperature
```

**Resolución**:
1. **Reintentar**: El sistema reintentará automáticamente con temperatura más baja
2. **Ajustar temperatura**: Reducir `temperature` en prompts (default: 0.2)
3. **Verificar prompt**: Asegurar que el prompt incluye instrucciones claras de formato JSON
4. **Cambiar modelo LLM**: Algunos modelos son más confiables para JSON estructurado

**Prevención**:
- Usar `response_format={"type": "json_object"}` cuando el proveedor lo soporta
- Implementar validación robusta de respuestas LLM
- Mantener prompts actualizados con mejores prácticas

## Procedimientos de Recuperación

### Pipeline Interrumpido (Ctrl+C)

**Síntomas**:
- Ejecución detenida manualmente
- Archivos de checkpoint existentes

**Recuperación**:
1. **Verificar checkpoints**: `ls output/.checkpoints/<video_id>/`
2. **Reanudar ejecución**: Ejecutar el mismo comando nuevamente
3. **El sistema detectará automáticamente** el último punto de checkpoint
4. **Continuará desde la etapa incompleta**

### Fallo de Sistema (Crash/Power Loss)

**Síntomas**:
- Sistema se apagó durante ejecución
- Archivos de checkpoint potencialmente corruptos

**Recuperación**:
1. **Verificar integridad de checkpoints**: 
   ```bash
   # Verificar que archivos JSON son válidos
   for file in output/.checkpoints/*/ *.json; do
       python -m json.tool "$file" > /dev/null || echo "Corrupt: $file"
   done
   ```
2. **Si checkpoints corruptos**: Eliminar directorio de checkpoints específico
3. **Reiniciar desde cero**: El pipeline comenzará nuevamente
4. **Monitorear más de cerca**: Usar tmux/screen para sesiones largas

### Presupuesto Excedido

**Síntomas**:
- Mensaje: "Budget exceeded: $2.50 > $2.00"
- Código de salida: 4
- Pipeline detenido abruptamente

**Recuperación**:
1. **Aumentar presupuesto**: Modificar `max_budget_usd` en config.yaml
2. **Optimizar configuración**: 
   - Usar proveedores más económicos
   - Reducir `chunk_duration_minutes` para menos llamadas
   - Cambiar a `cut_mode: fast` para evitar recodificación
3. **Reanudar ejecución**: El sistema continuará desde el último checkpoint válido

## Monitoreo Proactivo

### Alertas Recomendadas

- **Uso de disco > 80%**: Prevenir fallos por espacio insuficiente
- **Tiempo de ejecución > 3x duración video**: Detectar problemas de rendimiento  
- **Tasa de error > 10%**: Identificar problemas sistemáticos
- **Costo por minuto > threshold**: Detectar configuraciones ineficientes

### Métricas Clave para Dashboard

- **Videos procesados por hora**
- **Costo promedio por minuto de video**
- **Tasa de éxito vs fallo por proveedor**
- **Tiempo promedio de procesamiento por etapa**
- **Número de capítulos generados por video**

Estas métricas permiten optimizar configuración y predecir costos operativos.

## Contacto de Soporte

Para problemas que no se resuelven con este runbook:

- **Issues en GitHub**: https://github.com/your-org/echo-bering/issues
- **Documentación completa**: docs/README.md
- **Comunidad**: [Enlace a Discord/Slack si aplica]

> **Nota**: Antes de reportar un issue, incluir:
> - Versión de Echo-Bering
> - Sistema operativo y versión de Python
> - Archivo de log completo (con información sensible removida)
> - Archivo de configuración (con API keys removidas)
> - Comando exacto ejecutado