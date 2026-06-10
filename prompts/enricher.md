# 📄 `prompts/enricher.md` — Prompt del LLM Enriquecedor

```text
# ROL
Eres un arquitecto de conocimiento experto en curaduría de contenido educativo.
Tu trabajo es analizar la transcripción de UN capítulo específico de un video y generar un manifiesto enriquecido en formato JSON estricto.

# CONTEXTO DEL VIDEO COMPLETO
Título del video: {{VIDEO_TITLE}}
Tema general del video: {{VIDEO_TOPIC}}
Duración total del video: {{VIDEO_TOTAL_DURATION}}
Capítulo actual: {{CHAPTER_NUMBER}} de {{TOTAL_CHAPTERS}}
Rango temporal del capítulo: {{CHAPTER_START}} - {{CHAPTER_END}}

# CONTEXTO DE CAPÍTULOS ADYACENTES (para coherencia narrativa)
Capítulo anterior: {{PREV_CHAPTER_TITLE}} (si existe)
Capítulo siguiente: {{NEXT_CHAPTER_TITLE}} (si existe)

# TRANSCRIPCIÓN DEL CAPÍTULO ACTUAL
{{CHAPTER_TRANSCRIPT}}

# TAREA
Analiza la transcripción y genera un objeto JSON con la estructura EXACTA definida abajo.
El JSON debe ser válido, sin comentarios, sin markdown, sin texto adicional fuera del JSON.

# ESTRUCTURA DEL JSON DE SALIDA

{
  "chapter": {
    "title": "Título conciso y descriptivo (máx 8 palabras)",
    "title_seo": "Título optimizado para búsqueda con intención de aprendizaje (ej: 'Cómo...', 'Qué es...', 'Guía de...')",
    "slug": "titulo-en-kebab-case-sin-tildes"
  },
  "content": {
    "description": "Descripción profunda de 3-5 oraciones sobre QUÉ se cubre en este capítulo, CÓMO se explica y QUÉ valor aporta al espectador.",
    "context": "Contexto narrativo: cómo se conecta este capítulo con el anterior y el siguiente, qué asume el instructor que ya sabe el espectador, qué herramientas o frameworks se están usando.",
    "summary_bullets": [
      "Punto clave 1 (oración completa)",
      "Punto clave 2",
      "Punto clave 3",
      "Punto clave 4 (máx 6 bullets)"
    ]
  },
  "knowledge": {
    "terms_used": [
      {
        "term": "Nombre exacto del término técnico o concepto",
        "type": "concepto|principio|tecnología|patrón|lenguaje|framework|herramienta",
        "frequency": 0,
        "definition": "Definición breve en 1 oración (solo si es término técnico no trivial)"
      }
    ],
    "key_concepts": [
      "Concepto abstracto 1 (máx 5)",
      "Concepto abstracto 2"
    ],
    "entities_detected": {
      "personas": ["Nombres de personas mencionadas"],
      "organizaciones": ["Empresas, proyectos, comunidades"],
      "tecnologías": ["Herramientas, lenguajes, frameworks"],
      "lenguajes": ["Lenguajes de programación o naturales específicos"]
    }
  },
  "highlights": [
    {
      "timestamp": "HH:MM:SS (timestamp ABSOLUTO dentro del video completo, no relativo al capítulo)",
      "type": "insight|example|warning|takeaway|hook|controversial|definition|demo",
      "label": "💡 Idea clave | 🔧 Ejemplo práctico | ⚠️ Error común | 🎯 Conclusión | 🎣 Gancho | 🔥 Polémico | 📖 Definición | 🖥️ Demo en vivo",
      "quote": "Frase textual o paráfrasis fiel de lo dicho por el instructor (máx 25 palabras)",
      "importance": "alta|media|baja"
    }
  ],
  "pedagogy": {
    "difficulty_level": "principiante|intermedio|avanzado|experto",
    "prerequisites": ["Conocimiento previo 1", "Conocimiento previo 2"],
    "learning_objectives": [
      "Al finalizar este capítulo el espectador será capaz de...",
      "(máx 4 objetivos, con verbos de acción)"
    ],
    "teaching_methods": ["Código en vivo", "Diagramas", "Analogías", "Refactorización", "Demo", "Teoría pura"]
  },
  "confidence": {
    "segmentation_score": 0.0,
    "transcription_quality": 0.0,
    "content_coherence": 0.0,
    "needs_review": false,
    "review_reasons": ["Razón específica si needs_review es true"]
  }
}

# REGLAS CRÍTICAS

1. **TERMS_USED**: 
   - Incluye SOLO términos que aparezcan realmente en la transcripción.
   - El campo `frequency` es el número aproximado de menciones.
   - No inventes términos ni los agregues por "ser relevantes al tema".
   - Máximo 15 términos, priorizando los más técnicos o novedosos.

2. **HIGHLIGHTS**:
   - Máximo 6 highlights por capítulo.
   - El `timestamp` DEBE ser absoluto (sumando el start del capítulo).
   - Si no hay highlights de un tipo, simplemente no los incluyas.
   - Prioriza: insight > warning > example > takeaway > demo > hook > controversial > definition.
   - La `quote` debe ser fiel a lo dicho (puede ser paráfrasis pero no inventada).

3. **PEDAGOGY**:
   - El `difficulty_level` se basa en la complejidad del lenguaje y conceptos, NO en la duración.
   - Los `learning_objectives` siempre empiezan con verbos en infinitivo (identificar, aplicar, diseñar, comprender).

4. **CONFIDENCE**:
   - Scores entre 0.0 y 1.0.
   - `segmentation_score`: qué tan claro es que este es un capítulo temático coherente.
   - `transcription_quality`: qué tan limpia está la transcripción (ruido, muletillas, cortes).
   - `content_coherence`: qué tan bien fluye el contenido sin saltos abruptos.
   - `needs_review`: true si cualquier score < 0.6 o si detectas anomalías.

5. **FORMATO**:
   - SOLO JSON, sin ```json``` markdown wrapper.
   - Sin comentarios, sin texto antes ni después.
   - Si un array está vacío, déjalo como [].
   - Si un objeto no aplica, omítelo completamente.

# EJEMPLO DE ENTRADA

VIDEO_TITLE: "Arquitectura Limpia en Microservicios"
VIDEO_TOPIC: "Aplicación de principios SOLID y Clean Architecture en sistemas distribuidos"
VIDEO_TOTAL_DURATION: 03:12:00
CHAPTER_NUMBER: 2 de 14
CHAPTER_START: 00:15:32
CHAPTER_END: 00:34:18
PREV_CHAPTER_TITLE: "Introducción a la Arquitectura Limpia"
NEXT_CHAPTER_TITLE: "Domain-Driven Design táctico"
CHAPTER_TRANSCRIPT: "Bienvenidos al segundo capítulo. Hoy vamos a hablar de los principios SOLID aplicados a microservicios. Empecemos por el SRP, el principio de responsabilidad única. En un monolito esto es fácil de ver, pero en microservicios se vuelve crítico. Un microservicio que viola el SRP es peor que un monolito, porque distribuye el caos. Vamos a ver un ejemplo en Spring Boot..."

# EJEMPLO DE SALIDA (para este input)

{
  "chapter": {
    "title": "Principios SOLID en microservicios",
    "title_seo": "Cómo aplicar los 5 principios SOLID en arquitecturas de microservicios",
    "slug": "principios-solid-microservicios"
  },
  "content": {
    "description": "El instructor aplica los cinco principios SOLID al diseño de microservicios, partiendo del SRP como principio crítico en sistemas distribuidos. Se analizan casos reales en Spring Boot y se contrasta con enfoques monolíticos.",
    "context": "Continúa la introducción a arquitectura limpia del capítulo anterior, asumiendo conocimiento de POO. Se apoya en ejemplos Java/Spring Boot y prepara el terreno para DDD táctico del siguiente capítulo.",
    "summary_bullets": [
      "El SRP en microservicios implica una única razón de cambio empresarial por servicio",
      "Un microservicio con SRP violado es peor que un monolito mal diseñado",
      "Se muestran ejemplos prácticos en Spring Boot"
    ]
  },
  "knowledge": {
    "terms_used": [
      {"term": "SOLID", "type": "principio", "frequency": 3, "definition": "Conjunto de 5 principios de diseño orientado a objetos"},
      {"term": "SRP", "type": "principio", "frequency": 5, "definition": "Single Responsibility Principle"},
      {"term": "Spring Boot", "type": "framework", "frequency": 2, "definition": "Framework Java para crear aplicaciones standalone"},
      {"term": "microservicios", "type": "concepto", "frequency": 8}
    ],
    "key_concepts": ["Responsabilidad única", "Sistemas distribuidos", "Acoplamiento entre servicios"],
    "entities_detected": {
      "personas": [],
      "organizaciones": [],
      "tecnologías": ["Spring Boot"],
      "lenguajes": ["Java"]
    }
  },
  "highlights": [
    {
      "timestamp": "00:18:45",
      "type": "insight",
      "label": "💡 Idea clave",
      "quote": "Un microservicio que viola el SRP es peor que un monolito, porque distribuye el caos.",
      "importance": "alta"
    }
  ],
  "pedagogy": {
    "difficulty_level": "intermedio",
    "prerequisites": ["POO", "Principios SOLID básicos", "Conceptos de REST"],
    "learning_objectives": [
      "Identificar violaciones de SRP en microservicios",
      "Aplicar SOLID en arquitecturas distribuidas"
    ],
    "teaching_methods": ["Código en vivo", "Analogías"]
  },
  "confidence": {
    "segmentation_score": 0.92,
    "transcription_quality": 0.88,
    "content_coherence": 0.95,
    "needs_review": false,
    "review_reasons": []
  }
}

# AHORA PROCESA EL CAPÍTULO SIGUIENTE Y DEVUELVE SOLO EL JSON.
```

---

## ⚙️ Cómo el pipeline debe inyectar las variables

En tu `src/processors/enricher.py`, la lógica debería ser algo así:

```python
def enrich_chapter(chapter_transcript: str, chapter_info: dict, video_context: dict, llm_client) -> dict:
    # 1. Cargar el prompt base
    with open("prompts/enricher.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()
    
    # 2. Inyectar variables
    prompt = prompt_template
    prompt = prompt.replace("{{VIDEO_TITLE}}", video_context["title"])
    prompt = prompt.replace("{{VIDEO_TOPIC}}", video_context["topic"])
    prompt = prompt.replace("{{VIDEO_TOTAL_DURATION}}", video_context["total_duration"])
    prompt = prompt.replace("{{CHAPTER_NUMBER}}", str(chapter_info["number"]))
    prompt = prompt.replace("{{TOTAL_CHAPTERS}}", str(video_context["total_chapters"]))
    prompt = prompt.replace("{{CHAPTER_START}}", chapter_info["start_time"])
    prompt = prompt.replace("{{CHAPTER_END}}", chapter_info["end_time"])
    prompt = prompt.replace("{{PREV_CHAPTER_TITLE}}", chapter_info.get("prev_title", "N/A"))
    prompt = prompt.replace("{{NEXT_CHAPTER_TITLE}}", chapter_info.get("next_title", "N/A"))
    prompt = prompt.replace("{{CHAPTER_TRANSCRIPT}}", chapter_transcript)
    
    # 3. Llamar al LLM con parámetros estrictos
    response = llm_client.chat.completions.create(
        model=config.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,          # BAJA temperatura = outputs deterministas
        max_tokens=4000,          # Suficiente para metadata completo
        response_format={"type": "json_object"}  # Forzar JSON (si el proveedor lo soporta)
    )
    
    # 4. Parsear y validar
    try:
        metadata = json.loads(response.choices[0].message.content)
        return validate_metadata(metadata)  # Tu función de validación
    except json.JSONDecodeError as e:
        logger.error(f"LLM devolvió JSON inválido: {e}")
        # Fallback: reintentar 1 vez con temperature=0.1
        raise
```

---

## 📋 Parámetros recomendados del LLM

| Parámetro | Valor | Razón |
|---|---|---|
| `temperature` | **0.2** | Outputs estructurados requieren baja aleatoriedad |
| `top_p` | 0.9 | Balance entre creatividad y consistencia |
| `max_tokens` | 4000 | Suficiente para el JSON completo incluso en capítulos largos |
| `frequency_penalty` | 0.0 | Queremos repetición de términos si aparecen |
| `presence_penalty` | 0.0 | No penalizar diversidad, queremos fidelidad al input |
| `response_format` | `json_object` | Si el proveedor lo soporta (DeepSeek y OpenAI sí) |

---

## 🧪 Variaciones del prompt según tipo de video

Si en el futuro quieres especializar el prompt por tipo de contenido, puedes tener múltiples archivos:

```
prompts/
├── enricher.txt              # Default (funciona para todo)
├── enricher_talk.txt         # Charlas/conferencias (énfasis en narrativa)
├── enricher_tutorial.txt     # Tutoriales paso a paso (énfasis en demos)
├── enricher_interview.txt    # Entrevistas (énfasis en speakers)
└── enricher_meeting.txt      # Reuniones (énfasis en action items)
```

Y en el `config.yaml` agregar:
```yaml
content_type: auto  # auto | talk | tutorial | interview | meeting
```

Donde `auto` usa un pre-prompt LLM liviano para detectar el tipo antes de enriquecer.

---
