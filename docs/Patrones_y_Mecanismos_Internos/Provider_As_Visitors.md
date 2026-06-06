# Provider As Visitors

Patrón de abstracción que permite a Echo-Bering interactuar con múltiples proveedores externos (ASR/LLM) manteniendo la lógica core completamente agnóstica.

**Propósito:** Implementar el principio arquitectónico "Los proveedores son traductores, no participantes" permitiendo cambiar proveedores sin modificar la lógica de dominio.

## Componentes Clave

| Componente | Responsabilidad | Archivo |
|------------|-----------------|---------|
| `ASRProvider` | Interfaz abstracta para proveedores ASR | [`src/providers/asr/base.py`](src/providers/asr/base.py) |
| `LLMProvider` | Interfaz abstracta para proveedores LLM | [`src/providers/llm/base.py`](src/providers/llm/base.py) |
| `ProviderFactory` | Crea instancias de proveedores según configuración | [`src/factories/provider_factory.py`](src/factories/provider_factory.py) |
| `GroqASRProvider` | Implementación concreta para Groq ASR | [`src/providers/asr/groq_asr.py`](src/providers/asr/groq_asr.py) |
| `AssemblyAIASRProvider` | Implementación concreta para AssemblyAI ASR | [`src/providers/asr/assemblyai_asr.py`](src/providers/asr/assemblyai_asr.py) |
| `DeepSeekLLMProvider` | Implementación concreta para DeepSeek LLM | [`src/providers/llm/deepseek_llm.py`](src/providers/llm/deepseek_llm.py) |

## Diagrama de Arquitectura

```mermaid
graph TD
    subgraph "Core Logic (Agnóstico)"
        A[Transcriber]
        B[ChapterSegmenter] 
        C[MetadataEnricher]
    end
    
    subgraph "Adaptation Layer"
        D[ASRProvider <<Interface>>]
        E[LLMProvider <<Interface>>]
        F[GroqASRProvider]
        G[AssemblyAIASRProvider]
        H[OpenAIASRProvider]
        I[DeepSeekLLMProvider]
        J[GroqLLMProvider]
        K[OpenAILLMProvider]
    end
    
    A --> D
    B --> E
    C --> E
    
    D <|-- F
    D <|-- G  
    D <|-- H
    E <|-- I
    E <|-- J
    E <|-- K
    
    style A fill:#2ECC71
    style B fill:#2ECC71
    style C fill:#2ECC71
    style D fill:#F39C12
    style E fill:#F39C12
    style F fill:#E74C3C
    style G fill:#E74C3C
    style H fill:#E74C3C
    style I fill:#E74C3C
    style J fill:#E74C3C
    style K fill:#E74C3C
```

## Flujo de Operación

1. **Configuración**: El usuario define `asr_provider: groq` y `llm_provider: deepseek` en `config.yaml`
2. **Inicialización**: `ProviderFactory` crea instancias de `GroqASRProvider` y `DeepSeekLLMProvider`
3. **Inyección de Dependencias**: Los componentes core reciben las instancias abstractas (`ASRProvider`, `LLMProvider`)
4. **Ejecución**: La lógica core llama métodos en las interfaces abstractas sin conocer los proveedores concretos
5. **Extensibilidad**: Añadir nuevos proveedores solo requiere implementar las interfaces abstractas

## Configuración

| Propiedad | Default | Descripción |
|-----------|---------|-------------|
| `asr_provider` | `groq` | Proveedor ASR a utilizar (groq, assemblyai, openai) |
| `llm_provider` | `deepseek` | Proveedor LLM a utilizar (deepseek, groq, openai) |
| `asr_model` | `whisper-large-v3-turbo` | Modelo ASR específico |
| `llm_model` | `deepseek-chat` | Modelo LLM específico |

## Beneficios del Patrón

- **Desacoplamiento**: La lógica core no depende de implementaciones específicas
- **Extensibilidad**: Nuevo proveedor = nueva implementación de interfaz
- **Testabilidad**: Las interfaces se pueden mockear fácilmente en pruebas
- **Flexibilidad**: Cambio de proveedor vía configuración sin recompilación
- **Mantenibilidad**: Actualizaciones de SDKs solo afectan implementaciones concretas

> **Filosofía:** "Los proveedores visitan el sistema, no participan en él. La lógica de dominio permanece pura e independiente de las implementaciones externas."