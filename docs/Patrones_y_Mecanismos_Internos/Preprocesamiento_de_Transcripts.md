# Preprocesamiento de Transcripts

## Resumen

El sistema de preprocesamiento de transcripts limpia y normaliza el texto transcrito por los proveedores ASR antes de enviarlo al LLM para segmentación. Esto mejora la calidad de la segmentación y reduce el ruido en los resultados.

## Problemas que Resuelve

### 1. Caracteres Unicode Escapados
Los proveedores ASR pueden devolver caracteres especiales como secuencias de escape Unicode:
- `\u00a1` → ¡ (signo de exclamación invertido)
- `\u00bf` → ¿ (signo de interrogación invertido)
- `\u00ed` → í, `\u00e9` → é, etc.

**Impacto**: El LLM procesa texto con secuencias `\uXXXX` en lugar de caracteres legibles, lo que degrada la calidad de la segmentación.

### 2. Marcadores ASR
Los transcriptores automáticos pueden incluir marcadores para eventos no verbales:
- `[aplausos]`, `[risas]`, `[música]`
- `(aplausos)`, `(risas)`, `(música)`
- `<aplausos>`, `<risas>`, `<música>`

**Impacto**: Estos marcadores interrumpen el flujo del texto y confunden al LLM durante la segmentación.

### 3. Palabras de Relleno
Expresiones de hesitación y muletillas:
- `um`, `uh`, `eh`, `este`, `bueno`, `pues`
- Repeticiones excesivas: `la la la la casa` → `la la casa`

**Impacto**: Ruido en el texto que no aporta valor semántico para la segmentación.

### 4. Problemas de Puntuación
- Espacios múltiples: `palabra  palabra` → `palabra palabra`
- Puntuación inconsistente: `palabra ,` → `palabra,`
- Caracteres de control: bytes no imprimibles que causan errores

## Implementación

### Módulo: `src/processors/transcript_preprocessor.py`

El preprocesador aplica las siguientes transformaciones en orden:

```python
def preprocess_transcript(text: str, remove_fillers: bool = True) -> str:
    """Pipeline completo de preprocesamiento."""
    # 1. Normalizar puntuación española (unicode escapes → caracteres)
    text = normalize_spanish_punctuation(text)
    
    # 2. Limpiar caracteres unicode (control chars, non-breaking spaces)
    text = clean_unicode(text)
    
    # 3. Remover marcadores ASR ([aplausos], (risas), etc.)
    text = remove_asr_markers(text)
    
    # 4. Reducir repeticiones excesivas
    text = remove_repetitions(text, max_repeats=2)
    
    # 5. Normalizar puntuación
    text = normalize_punctuation(text)
    
    # 6. Remover palabras de relleno (si está habilitado)
    if remove_fillers:
        text = remove_filler_words(text)
    
    return text
```

### Integración en el Pipeline

El preprocesamiento se aplica en **dos puntos críticos**:

#### 1. Durante la Transcripción (`src/processors/transcriber.py`)

```python
async def transcribe(self, audio_path: Path) -> TranscriptResult:
    """Transcribe audio with preprocessing applied before returning."""
    # ... transcription logic ...
    
    # Apply preprocessing before saving AND returning
    cleaned_result = self._preprocess_transcript(result)
    self._save_checkpoint(cleaned_result)
    return cleaned_result  # Return preprocessed transcript

def _preprocess_transcript(self, result: TranscriptResult) -> TranscriptResult:
    """Apply preprocessing to clean the transcript."""
    cleaned_text = preprocess_transcript(result.text, remove_fillers=True)
    return TranscriptResult(
        text=cleaned_text,
        confidence=result.confidence,
        # ... other fields ...
    )
```

**Importante**: 
- El preprocesamiento se aplica **antes de retornar** el transcript al pipeline
- Esto asegura que el checkpoint de transcribe (`transcribe/data.json`) contenga texto limpio
- El checkpoint de ASR (`asr/raw_transcript.json`) también contiene texto limpio
- Se usa `ensure_ascii=False` para que los caracteres especiales se guarden como caracteres Unicode reales, no como secuencias de escape

#### 2. Durante la Segmentación (`src/processors/transcript_processor.py`)

```python
class CleanTranscriptProcessor(TranscriptProcessor):
    """Procesador que usa el transcript ya preprocesado."""
    
    def prepare_transcript_text(self, transcript: TranscriptResult) -> str:
        """Retorna el texto ya preprocesado por el transcriber."""
        return transcript.text
```

**Nota**: El preprocesamiento se aplica **solo una vez** (en el transcriber) para evitar procesamiento duplicado.

### Configuración

No hay configuración explícita en `config.yaml`. El preprocesamiento está **siempre habilitado** por defecto.

Si necesitas deshabilitarlo temporalmente para debugging, modifica `src/processors/transcriber.py`:

```python
# Línea ~231
cleaned_text = preprocess_transcript(result.text, remove_fillers=False)
```

## Aprendizajes Clave

### 1. Preprocesamiento en el Origen
**Problema inicial**: El preprocesamiento se aplicaba en el segmenter, después de cargar el transcript del checkpoint. Esto causaba que el checkpoint contuviera texto sin procesar.

**Solución**: Aplicar preprocesamiento en el transcriber **antes** de guardar el checkpoint. Así el checkpoint siempre contiene texto limpio.

**Beneficio**: 
- El transcript en el checkpoint ya está limpio
- No se reprocesa en cada ejecución
- Facilita debugging manual del checkpoint

### 2. ensure_ascii=False en JSON
**Problema**: `json.dump()` por defecto escapa caracteres no-ASCII como `\uXXXX`, lo que causaba que los caracteres especiales aparecieran como secuencias de escape en el archivo.

**Solución**: Usar `ensure_ascii=False` al guardar el checkpoint:

```python
json.dump(data, f, ensure_ascii=False)
```

**Beneficio**: Los caracteres especiales se guardan como caracteres Unicode reales, mejorando la legibilidad del checkpoint.

### 3. Evitar Procesamiento Duplicado
**Problema inicial**: El preprocesamiento se aplicaba tanto en el transcriber como en el segmenter, procesando el texto dos veces.

**Solución**: 
- Transcriber: Aplica preprocesamiento completo y guarda en checkpoint
- Segmenter: Usa el texto ya preprocesado del checkpoint sin reprocesar

**Beneficio**: 
- Reduce tiempo de procesamiento
- Evita inconsistencias
- Más fácil de debuggear

### 4. Eliminación de Marcadores ASR
**Patrones a eliminar**:
```python
markers = [
    r"\[aplausos\]", r"\[risas\]", r"\[música\]",
    r"\(aplausos\)", r"\(risas\)", r"\(música\)",
    r"<aplausos>", r"<risas>", r"<música>",
    r"\[.*?ininteligible.*?\]",  # [ininteligible]
    r"\[.*?inaudible.*?\]",      # [inaudible]
]
```

**Importante**: Usar `re.IGNORECASE` para capturar variaciones de capitalización.

### 5. Reducción de Repeticiones
**Algoritmo**:
```python
def remove_repetitions(text: str, max_repeats: int = 2) -> str:
    """Reduce repeticiones excesivas."""
    words = text.split()
    result = []
    
    for i, word in enumerate(words):
        # Contar repeticiones consecutivas
        count = 1
        while (i + count < len(words) and 
               words[i + count].lower() == word.lower()):
            count += 1
        
        # Mantener solo max_repeats
        if count > max_repeats:
            result.extend([word] * max_repeats)
        else:
            result.extend([word] * count)
    
    return " ".join(result)
```

**Ejemplo**: `"la la la la casa"` → `"la la casa"` (max_repeats=2)

## Testing

### Tests Unitarios
Los tests están en `tests/unit/processors/test_transcript_preprocessor.py`:

```bash
uv run pytest tests/unit/processors/test_transcript_preprocessor.py -v
```

**Cobertura**:
- Normalización de unicode
- Eliminación de marcadores ASR
- Reducción de repeticiones
- Eliminación de palabras de relleno
- Pipeline completo

### Verificación Manual
Para verificar que el preprocesamiento funciona correctamente:

```bash
# Ejecutar pipeline
uv run python -m src.main --config config.default.yaml

# Verificar checkpoint de ASR
python3 -c "
import json
data = json.load(open('output/*/\.checkpoint/asr/raw_transcript.json'))
text = data['text']
print('¿Tiene unicode escapes?', '\\\\u' in text)
print('¿Tiene marcadores ASR?', any(m in text.lower() for m in ['aplausos', 'risas']))
print('¿Tiene palabras de relleno?', any(w in text.lower() for w in [' um ', ' eh ']))
"
```

## Métricas de Impacto

### Antes del Preprocesamiento
- Transcript con unicode escapes: `\u00a1Gracias! \u00bfC\u00f3mo est\u00e1s?`
- Marcadores ASR: `[aplausos]`, `[risas]`
- Palabras de relleno: `um`, `eh`, `este`
- Repeticiones: `la la la la casa`
- LLM recibe texto ruidoso → segmentación de menor calidad

### Después del Preprocesamiento
- Transcript limpio: `¡Gracias! ¿Cómo estás?`
- Sin marcadores ASR
- Sin palabras de relleno
- Repeticiones reducidas
- LLM recibe texto limpio → segmentación de mayor calidad

**Reducción típica**: 5-10% del tamaño del transcript (dependiendo del contenido)

## Configuración Avanzada

### Personalizar Palabras de Relleno
Edita `src/processors/transcript_preprocessor.py`:

```python
def remove_filler_words(text: str) -> str:
    fillers = [
        r"\bum\b",
        r"\buh\b",
        r"\beh\b",
        r"\beste\b",
        # Agrega tus propias palabras de relleno aquí
        r"\byour_custom_filler\b",
    ]
    # ... resto del código
```

### Cambiar max_repeats
```python
# En transcript_preprocessor.py
text = remove_repetitions(text, max_repeats=1)  # Más agresivo
```

### Deshabilitar Preprocesamiento Completo
Si necesitas mantener el texto original para algún caso de uso específico:

```python
# En transcriber.py, línea ~231
cleaned_text = result.text  # Sin preprocesamiento
```

## Troubleshooting

### El checkpoint de transcribe todavía tiene unicode escapes
**Causa**: El `Transcriber.transcribe()` estaba retornando el transcript sin preprocesar

**Solución**: Aplicar preprocesamiento **antes de retornar** el transcript al pipeline:

```python
async def transcribe(self, audio_path: Path) -> TranscriptResult:
    result = await self._transcribe_with_retry(audio_path)
    # Apply preprocessing before saving AND returning
    cleaned_result = self._preprocess_transcript(result)
    self._save_checkpoint(cleaned_result)
    return cleaned_result  # Return preprocessed transcript
```

**Verificación**:
```bash
# Verificar checkpoint de transcribe
python3 -c "
import json
data = json.load(open('output/*/.checkpoint/transcribe/data.json'))
text = data['transcript']['text']
print('¿Tiene unicode escapes?', '\\\\u' in text)
"
```

### El checkpoint de ASR todavía tiene unicode escapes
**Causa**: Falta `ensure_ascii=False` en `json.dump()`

**Solución**: Verifica que `_save_checkpoint()` use:
```python
json.dump(cleaned_result.model_dump(), f, indent=2, ensure_ascii=False)
```

### El SRT está vacío
**Causa**: El transcript del capítulo está vacío

**Solución**: Verifica que el checkpoint de segmentación tenga transcripts:
```bash
python3 -c "
import json
data = json.load(open('output/*/\.checkpoint/segment/data.json'))
for chapter in data['chapters']:
    print(f\"Capítulo {chapter['number']}: {len(chapter['transcript'])} chars\")
"
```

### El preprocesamiento elimina palabras importantes
**Causa**: Una palabra de relleno es demasiado genérica

**Solución**: Ajusta los patrones en `remove_filler_words()` para ser más específicos:
```python
# En lugar de r"\besto\b" (muy genérico)
r"\besto\.\s*$"  # Solo al final de oración
```

## Referencias

- **Módulo de preprocesamiento**: `src/processors/transcript_preprocessor.py`
- **Tests**: `tests/unit/processors/test_transcript_preprocessor.py`
- **Integración en transcriber**: `src/processors/transcriber.py:_save_checkpoint()`
- **Integración en processor**: `src/processors/transcript_processor.py:CleanTranscriptProcessor`

## Changelog

### 2025-06-08 (Fix)
- ✅ **Bug fix**: Transcriber ahora aplica preprocesamiento antes de retornar transcript
- ✅ **Problema resuelto**: Checkpoint de transcribe contenía texto sin preprocesar
- ✅ **Solución**: Refactorizar `_preprocess_transcript()` como método separado
- ✅ **Resultado**: Todos los checkpoints (asr, transcribe, segment) ahora contienen texto limpio
- ✅ **Commit**: `a0a4fe1` - "fix: apply preprocessing before returning transcript to pipeline"

### 2025-06-08
- ✅ Implementación inicial del preprocesamiento
- ✅ Integración en transcriber (antes de guardar checkpoint)
- ✅ Eliminación de unicode escapes con `ensure_ascii=False`
- ✅ Eliminación de marcadores ASR
- ✅ Reducción de repeticiones
- ✅ Eliminación de palabras de relleno
- ✅ Tests unitarios completos
- ✅ Documentación completa
