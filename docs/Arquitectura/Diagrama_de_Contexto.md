# Diagrama de Contexto

Echo-Bering opera como un pipeline de transformación de señales que convierte video crudo en capítulos semánticos estructurados con metadata enriquecida.

**Propósito:** Mostrar la posición de Echo-Bering en el ecosistema de procesamiento de contenido audiovisual y sus interacciones con sistemas externos.

```mermaid
graph TD
    subgraph "Ecosistema Procesamiento Video"
        A[Usuario Final<br/><i>[Persona]</i>]
        B[Video Input<br/><i>[Archivo]</i>]
        C[Echo-Bering<br/><i>[Sistema de Software]</i>]
        D[Proveedores ASR/LLM<br/><i>[Sistemas Externos]</i>]
        E[Output Capítulos<br/><i>[Directorio]</i>]
    end
    
    A -- "1. Proporciona video + config" --> B
    B -- "2. Procesa video completo" --> C
    C -- "3. Llama APIs proveedores" --> D
    C -- "4. Genera outputs estructurados" --> E
    E -- "5. Consume capítulos" --> A
    
    style C fill:#1E90FF,stroke:#000,stroke-width:2px,color:#fff
```

## Descripción de Interacciones

1. **[Usuario Final] -> [Video Input]**: El usuario proporciona un archivo de video y configuración para procesamiento
2. **[Video Input] -> [Echo-Bering]**: El sistema carga el video y comienza el pipeline de procesamiento
3. **[Echo-Bering] -> [Proveedores ASR/LLM]**: El sistema interactúa con APIs externas (Groq, AssemblyAI, OpenAI, DeepSeek) según configuración
4. **[Echo-Bering] -> [Output Capítulos]**: El sistema genera directorios autocontenidos con capítulos, subtítulos y metadata enriquecida
5. **[Output Capítulos] -> [Usuario Final]**: El usuario consume los capítulos procesados para su uso final