# SaaS administrativo con asistente de IA

SaaS multi-tenant para que cada empresa gestione sus clientes, proveedores, facturas y presupuestos. Un agente de IA común analiza los documentos que la empresa sube, registra los datos y los archiva en el Google Drive de la empresa.

El plan completo está en [docs/proyecto/plan-de-construccion.md](docs/proyecto/plan-de-construccion.md). Las decisiones de arquitectura están en [docs/adr/](docs/adr/README.md).

## Estado

| Fase | Contenido | Estado |
| --- | --- | --- |
| 0 | Estructura del repositorio, documentación y ADR iniciales | Hecho |
| 1 | Fundación y tenant: Docker Compose, CI, autenticación, roles, RLS, logs JSON | Pendiente |
| 2 | SaaS administrativo y CRUD | Pendiente |
| 3 | Ficheros, Google Drive e ingesta | Pendiente |
| 4 | Agente común y RAG | Pendiente |
| 5 | Validación y lanzamiento | Pendiente |
| 6 | Servidor MCP (post-MVP) | Pendiente |

## Resumen funcional

- **Dos roles:** `admin` (equipo de la plataforma, panel interno) y `cliente` (un único usuario por empresa).
- **Aislamiento total entre empresas.** Un cliente o proveedor compartido por dos empresas es un registro distinto en cada una.
- **Google Drive por empresa.** El usuario de la empresa conecta su propio Drive al darse de alta, con OAuth y el permiso `drive.file`. La plataforma no ve contraseñas ni el resto del Drive.
- **«Subir archivos» es la única vía de entrada de documentos.** El agente analiza cada fichero y lo archiva en `Proveedores/<proveedor>`, `Facturas/<cliente>`, `Presupuestos/<cliente>`, `Revisión` o `Por clasificar`.
- **«Por clasificar»:** listado con un desplegable por documento: Es factura, Es presupuesto, Es proveedor, Verificado / Almacenar o Eliminar.
- **Facturas y presupuestos** se editan solo en borrador; al enviarse quedan bloqueados y se corrigen con rectificativa o nueva versión.
- **Chat con el agente** sobre los datos y documentos de la propia empresa, con citas.

## Stack

| Capa | Tecnología |
| --- | --- |
| Web y API | PHP 8.3, Laravel 12, Inertia.js, Vue 3, TypeScript, Tailwind CSS |
| Procesamiento y agente | Python 3.12, FastAPI |
| Base de datos | PostgreSQL 16 + pgvector |
| Colas y caché | Redis 7, Laravel Horizon |
| Ficheros | Almacenamiento S3 compatible (copia privada) + Google Drive API v3 |
| Observabilidad | Logs JSON, Opik o Langfuse autoalojado en la UE |
| Entorno | Docker Compose, GitHub Actions |

## Estructura del repositorio

```text
.
├── apps/
│   ├── web/                  # Laravel + Inertia + Vue (se crea en la Fase 1 con composer create-project)
│   └── agent/                # FastAPI: agente común, extracción, RAG y Drive
│       ├── app/
│       │   ├── api/          # Endpoints internos
│       │   ├── agent/        # Runtime del agente común
│       │   ├── rag/          # Búsqueda híbrida y citas
│       │   ├── rerank/       # Reranker
│       │   ├── ingest/       # Extracción, clasificación y normalización
│       │   ├── drive/        # Integración con Google Drive
│       │   ├── models/       # Esquemas y modelos
│       │   ├── observability/# Logs JSON y trazas
│       │   └── mcp/          # Servidor MCP (post-MVP)
│       └── tests/
├── .claude/
│   ├── agents/               # Agentes expertos de Claude Code
│   └── skills/               # Skills del proyecto
├── CLAUDE.md                 # Reglas comunes para trabajar con IA en el repositorio
├── infra/                    # Configuración de despliegue
├── .github/workflows/        # CI, publicación de versiones y comprobación de títulos de PR
├── .releaserc.json           # Reglas de versionado de semantic-release
└── docs/
    ├── proyecto/             # Documentación interna del proyecto (plan, guías técnicas)
    ├── clientes/             # Documentación para los clientes (guías de uso)
    └── adr/                  # Registro de decisiones de arquitectura
```

`apps/web/` no existe todavía a propósito: `composer create-project` necesita que la carpeta de destino esté vacía o no exista.

## Agentes y skills de Claude Code

Las reglas comunes para trabajar con IA en este repositorio están en [CLAUDE.md](CLAUDE.md).

| Agente (`.claude/agents/`) | Para qué |
| --- | --- |
| `arquitecto` | Diseño y revisión de arquitectura, división en tareas, ADR |
| `ux-ui` | Pantallas, flujos, textos de interfaz y accesibilidad |
| `cicd-devops` | Docker Compose, GitHub Actions, despliegues, secretos, copias de seguridad |
| `qa` | Estrategia de pruebas, tests y verificación de criterios de aceptación |
| `desarrollador-laravel` | Implementación en `apps/web` (Laravel, Inertia, Vue) |
| `desarrollador-python-ia` | Implementación en `apps/agent` (FastAPI, ingesta, Drive, agente) |
| `seguridad` | Revisión de seguridad, aislamiento, OAuth, secretos, RGPD (solo lectura) |
| `base-de-datos` | Modelo de datos, migraciones, RLS, triggers, índices y rendimiento |
| `especialista-ia-rag` | Prompts, extracción, clasificación, RAG, inyección de prompts y evaluación |
| `fiscal-facturacion` | Normativa española de facturación, IVA, rectificativas y VeriFactu (solo lectura) |

| Skill (`.claude/skills/`) | Para qué |
| --- | --- |
| `nuevo-adr` | Crear un ADR, actualizar el índice y el plan |
| `revisar-aislamiento` | Comprobar que una empresa no puede acceder a datos de otra |
| `tabla-tenant` | Crear una tabla de negocio con `tenant_id`, RLS, modelo, política y tests |
| `documento-cliente` | Redactar guías para los clientes en `docs/clientes/` |
| `cerrar-tarea` | Verificar, documentar y actualizar el estado y el registro de cambios |
| `tdd` | Implementar con TDD: test primero, rojo-verde-refactorizar |

## Puesta en marcha

Pendiente de la Fase 1 (Docker Compose con healthchecks). Se documentará aquí.

## Versiones

Cada merge a `main` publica automáticamente una versión nueva (etiqueta `vX.Y.Z` y GitHub Release) con [semantic-release](.releaserc.json), según el tipo de commit ([ADR-0016](docs/adr/0016-versionado-automatico.md)):

| Commit / título del PR | Versión |
| --- | --- |
| `feat: ...` | MINOR (`0.3.0` → `0.4.0`) |
| `fix:`, `docs:`, `refactor:`, `test:`, `ci:`, `chore:`… | PATCH (`0.3.0` → `0.3.1`) |
| `feat!: ...` o `BREAKING CHANGE:` | MAJOR (`0.3.0` → `1.0.0`) |

- Los PR se fusionan con **squash merge**; el workflow [pr-title.yml](.github/workflows/pr-title.yml) bloquea los títulos que no siguen Conventional Commits.
- La versión se inyecta en las imágenes (`APP_VERSION`, `APP_COMMIT`) y se muestra en pequeño en el footer de la aplicación.
- Las notas de cada versión están en las GitHub Releases del repositorio.

## Convenciones

- **Idioma:** la documentación y los mensajes al usuario, en español. El código, los identificadores y los nombres de tablas, en inglés.
- **Decisiones:** toda decisión de arquitectura o cambio relevante respecto al plan se registra como ADR en `docs/adr/` antes de implementarla.
- **Documentación:** lo interno va a `docs/proyecto/`; lo que se entrega o se muestra a los clientes va a `docs/clientes/`.
- **TDD:** todo el código de producción se escribe con test primero ([ADR-0017](docs/adr/0017-desarrollo-guiado-por-tests.md)).
- **Seguridad:** ningún secreto en el repositorio; todo dato de negocio lleva `tenant_id`; cada endpoint lleva tests de permisos y de acceso cruzado entre empresas.

## Registro de cambios

| Fecha | Cambio |
| --- | --- |
| 2026-10-29 | Estructura inicial del repositorio, carpeta `docs/` y ADR 0001-0014 a partir del plan de construcción |
| 2026-10-29 | `CLAUDE.md`, 10 agentes y 5 skills de Claude Code para el proyecto |
| 2026-10-29 | ADR-0015: Python extrae y devuelve los datos; Laravel los guarda con sus servicios de dominio. Plan actualizado |
| 2026-10-29 | ADR-0016: versionado automático con semantic-release en cada merge a `main`, comprobación de títulos de PR y versión en el footer |
| 2026-10-29 | ADR-0017: desarrollo con TDD (test primero) y skill `tdd` |
| 2026-10-29 | ADR-0018: estrategia de escalado (preparación desde la Fase 1 y umbrales para activar cada medida) |
| 2026-10-29 | Estimación de costes de operación para 100 empresas en `docs/proyecto/estimacion-de-costes.md` |
| 2026-10-29 | ADR-0019: cobro por transferencia bancaria (sin Stripe); estimación actualizada a 20 €/mes IVA incluido con Sonnet 5.5 |
| 2026-10-29 | ADR-0020: el impago solo desactiva la IA, sin cortar el acceso; la aplicación solo envía el email de recuperación de contraseña |
| 2026-10-29 | ADR-0021: copias de seguridad con pgBackRest en el VPS y en Backblaze B2 gratuito, intercambiable por un proveedor de pago solo con configuración |
| 2026-10-29 | ADR-0022: panel de configuración de la plataforma para el `admin`, versionado y auditado |
| 2026-10-29 | Google Drive sale del panel de configuración del `admin`: cada empresa conecta el suyo; las credenciales OAuth de Google de la plataforma pasan a variables de entorno del servidor |
