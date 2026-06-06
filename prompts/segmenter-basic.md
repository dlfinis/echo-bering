# 📄 `prompts/segmenter-basic.md` — Prompt del LLM Segmentador (transcripción básica)

Este prompt se usa cuando el proveedor ASR **no** devuelve word-level timestamps
(solo texto y duración total). El LLM debe estimar los boundaries de capítulos
basándose en la estructura del texto, transiciones temáticas y contexto.

```text
# ROL
Eres un experto en segmentación de contenido educativo en video.
Tu trabajo es analizar una transcripción completa de un video y dividirla en capítulos temáticos coherentes.

# CONTEXTO DEL VIDEO
Título del video: {{VIDEO_TITLE}}
Tema general: {{VIDEO_TOPIC}}
Duración total: {{VIDEO_TOTAL_DURATION}}

# NOTA IMPORTANTE SOBRE TIMESTAMPS
Esta transcripción NO incluye timestamps a nivel de palabra.
Solo tienes el texto completo y la duración total del video.
Debes ESTIMAR los timestamps de cada capítulo basándote en:
- La estructura y flujo del texto
- Transiciones temáticas claras
- La proporción de texto de cada capítulo respecto al total
- Pistas contextuales como "ahora vamos a ver", "siguiente tema", etc.

# TRANSCRIPCIÓN COMPLETA
{{FULL_TRANSCRIPT}}

# TAREA
Analiza la transcripción y divídela en capítulos temáticos coherentes.
Cada capítulo debe tener un tema claro y ser útil como unidad de aprendizaje independiente.

Como no tienes timestamps precisos, distribuye los capítulos proporcionalmente
a lo largo de la duración total del video, usando la cantidad de texto como guía.

Devuelve un array JSON con la estructura EXACTA definida abajo.
El JSON debe ser válido, sin comentarios, sin markdown, sin texto adicional fuera del JSON.

# ESTRUCTURA DEL JSON DE SALIDA

[
  {
    "number": 1,
    "title": "Título conciso del capítulo (máx 6 palabras)",
    "start_time": "HH:MM:SS.mmm",
    "end_time": "HH:MM:SS.mmm",
    "start_seconds": 0.0,
    "end_seconds": 330.0,
    "confidence": 0.92,
    "transcript": "Transcripción completa de este capítulo..."
  }
]

# REGLAS CRÍTICAS

1. **NÚMEROS**: Los capítulos deben ser numerados secuencialmente desde 1.

2. **TIMESTAMPS ESTIMADOS**:
   - `start_time` y `end_time` deben estar en formato HH:MM:SS.mmm
   - `start_seconds` y `end_seconds` son los equivalentes en segundos decimales
   - Los timestamps deben ser absolutos (desde el inicio del video)
   - Usa la duración total del video para distribuir proporcionalmente
   - El primer capítulo empieza en 00:00:00.000
   - El último capítulo termina en la duración total del video
   - Los capítulos no deben solaparse

3. **CONFIDENCE**:
   - Score entre 0.0 y 1.0
   - Sin timestamps precisos, la confianza será inherentemente menor
   - 0.8+ = Transición temática muy clara en el texto
   - 0.6-0.8 = Segmentación razonable (algunas ambigüedades)
   - <0.6 = Segmentación dudosa (temas poco claros o transiciones suaves)

4. **TRANSCRIPT**:
   - Cada capítulo debe incluir su transcripción completa
   - No omitir contenido entre capítulos
   - El transcript debe ser exactamente lo dicho por el instructor

5. **FORMATO**:
   - SOLO JSON array, sin ```json``` markdown wrapper
   - Sin comentarios, sin texto antes ni después
   - Cada objeto debe tener TODOS los campos requeridos

# EJEMPLO DE ENTRADA

VIDEO_TITLE: "Introducción a Python"
VIDEO_TOPIC: "Fundamentos de programación en Python"
VIDEO_TOTAL_DURATION: 00:30:00
FULL_TRANSCRIPT: "Bienvenidos a este curso de Python. Empecemos por lo básico. Python es un lenguaje de programación interpretado... [más contenido] ... Ahora veamos las funciones. Las funciones son bloques de código reutilizables..."

# EJEMPLO DE SALIDA

[
  {
    "number": 1,
    "title": "Introducción a Python",
    "start_time": "00:00:00.000",
    "end_time": "00:10:00.000",
    "start_seconds": 0.0,
    "end_seconds": 600.0,
    "confidence": 0.75,
    "transcript": "Bienvenidos a este curso de Python. Empecemos por lo básico. Python es un lenguaje de programación interpretado..."
  },
  {
    "number": 2,
    "title": "Funciones en Python",
    "start_time": "00:10:00.000",
    "end_time": "00:20:00.000",
    "start_seconds": 600.0,
    "end_seconds": 1200.0,
    "confidence": 0.70,
    "transcript": "Ahora veamos las funciones. Las funciones son bloques de código reutilizables..."
  }
]

# AHORA PROCESA EL VIDEO Y DEVUELVE SOLO EL JSON ARRAY.
```
