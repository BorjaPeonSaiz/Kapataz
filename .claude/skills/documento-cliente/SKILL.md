---
name: documento-cliente
description: Redacta o actualiza una guía para los clientes en docs/clientes (por ejemplo, primeros pasos, subir archivos, carpetas de Google Drive, documentos por clasificar, facturas y presupuestos, privacidad). Úsala cuando haya que explicar a una empresa usuaria, sin tecnicismos, cómo funciona una parte de la aplicación.
---

# Redactar una guía para clientes

Lector: el usuario de una pequeña empresa o un autónomo, sin perfil técnico, que usa la aplicación para gestionar sus facturas.

## Antes de escribir

1. Lee `docs/clientes/README.md` para ver qué guías existen y cuáles están pendientes.
2. Lee las secciones del plan y los ADR de la funcionalidad, y, si ya existe, el código o las pantallas, para describir el comportamiento real y no el previsto.

## Estilo

- Español claro, frases cortas, tuteo.
- Empieza por lo que el usuario quiere conseguir, no por cómo funciona por dentro.
- Pasos numerados con los nombres exactos de botones y secciones de la aplicación («Subir archivos», «Por clasificar», «Marcar como enviado»).
- Explica qué pasa después de cada acción y qué hacer si algo sale mal.
- Sin términos internos: nada de «tenant», «OAuth», «token», «RLS», «RAG», «ADR», «S3» ni nombres de tablas. Di «tu empresa», «conectar tu Google Drive», «la aplicación».
- Sé honesto con las limitaciones (por ejemplo, que los ficheros añadidos directamente en Google Drive no se procesan, o que una factura enviada no se puede modificar y se corrige con una rectificativa).
- Ningún dato real de clientes, secretos ni detalles de infraestructura o seguridad interna.

## Estructura

```markdown
# Título orientado a la tarea

Una o dos frases sobre para qué sirve.

## Pasos
1. ...

## Qué ocurre después

## Preguntas frecuentes
```

## Al terminar

- Guarda en `docs/clientes/<titulo-corto>.md`.
- Actualiza la tabla de `docs/clientes/README.md` (enlace y estado).
- Si la guía revela una contradicción con el plan o con el comportamiento de la aplicación, avísalo en lugar de esconderla.
