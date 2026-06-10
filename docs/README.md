# Documentación Técnica — Echo-Bering

Echo-Bering es una herramienta CLI/TUI que procesa videos de cualquier duración (5min - 6h) y cualquier tema, los segmenta automáticamente en capítulos temáticos, genera cortes físicos del video, subtítulos `.srt` y un **manifiesto enriquecido por capítulo** con contexto, términos técnicos, descripción profunda y momentos clave.

## Estructura de Directorios

| Directorio | Propósito |
|------------|-----------|
| **[Arquitectura](./Arquitectura/)** | Diagramas C4, diseño sistémico y principios arquitectónicos |
| **[Flujos de Negocio](./Flujos_de_Negocio/)** | Diagramas de secuencia del pipeline de procesamiento |
| **[Patrones y Mecanismos Internos](./Patrones_y_Mecanismos_Internos/)** | Patrones de diseño, abstracciones de proveedores, manejo de errores |
| **[Guias Operativas](./Guias_Operativas/)** | Observabilidad, runbooks y procedimientos operativos |
| **[testing](./testing/)** | Estrategia de pruebas y cobertura |

## Quick Links

- [Diagrama de Contexto](./Arquitectura/Diagrama_de_Contexto.md)
- [Diagrama de Componentes](./Arquitectura/Diagrama_de_Componentes.md)
- [Pipeline Principal](./Flujos_de_Negocio/Pipeline_Principal.md)
- [Estrategia de Pruebas](./testing/Estrategia_de_Pruebas.md)
- [Guía para Casos Extremos](./Guias_Operativas/Guia_Casos_Extremos.md)

## Convenciones de Documentación

- **Diagramas**: Mermaid para secuencia, arquitectura y componentes
- **Enlaces**: Relativos con ruta completa
- **Código**: Snippets con sintaxis específica (Python, YAML, Bash)
- **Referencias**: [`NombreClase`](ruta/archivo.py:linea)