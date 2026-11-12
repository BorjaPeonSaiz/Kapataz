# ADR-001 — Arquitectura hexagonal ligera

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-01, RN-02, RN-04, RN-11, RN-F-01, RN-F-02, RN-F-07, RNF-08

## Contexto

Kapataz tiene un núcleo fiscal que debe ser correcto pase lo que pase alrededor: importes, numeración sin huecos, inmutabilidad de lo emitido y cadena de registros de facturación. Ese núcleo convive con muchos servicios externos que van a cambiar: la API de Claude (ADR-005), la seudonimización (ADR-030), los embeddings (ADR-007), Whisper (ADR-011), la lectura y generación de PDF (ADR-010), la pasarela de pago (ADR-016) y un proveedor de envío a la AEAT que aún no está elegido (ADR-012).

Fuerzas:

- Las reglas RN y RN-F deben probarse sin E/S, rápido y con pruebas de propiedades.
- Cambiar de modelo, de proveedor de Verifactu o de pasarela no debe tocar las reglas fiscales.
- Si Claude no responde, todo lo que no usa IA sigue funcionando (RNF-08).
- El trabajo lo hacen varios agentes en muchas sesiones: las fronteras se comprueban por máquina, no por disciplina.

## Opciones consideradas

1. **Hexagonal ligera con cuatro capas** (`domain`, `application`, `infrastructure`, `api`) y un puerto por servicio externo.
   - Ventajas: dominio en Python puro, probado sin base de datos; cambiar un proveedor es escribir un adaptador; cada puerto tiene su `Fake` para CI (ADR-008).
   - Inconvenientes: más ficheros y más mapeos (entidad, fila, esquema de API); riesgo de crear abstracciones que no aportan.
2. **Capas dictadas por el framework:** routers de FastAPI que trabajan directamente con modelos de SQLAlchemy que contienen la lógica.
   - Ventajas: menos código al principio; patrón conocido.
   - Inconvenientes: las reglas fiscales quedan mezcladas con ORM y HTTP; probar el redondeo o la numeración exige base de datos; cambiar de proveedor de IA toca la lógica de negocio.
3. **Hexagonal completa con DDD estricto:** contextos delimitados separados, eventos de dominio y CQRS.
   - Ventajas: máxima separación.
   - Inconvenientes: sobredimensionada para un monolito con un equipo pequeño; coste de mantenimiento sin beneficio claro en la v1.

## Decisión

Opción 1, según §4.1 del plan:

- **`domain/`**: entidades, objetos de valor, reglas RN y puertos. Python puro: no importa FastAPI, SQLAlchemy, el SDK `anthropic` ni nada de `infrastructure`. El tiempo entra por el puerto `Clock`, nunca con `datetime.now()`.
- **`application/`**: casos de uso (un caso de uso, una transacción), orquestador del agente y DTO. Depende solo de `domain`.
- **`infrastructure/`**: adaptadores que implementan los puertos del dominio y de la aplicación (§4.3).
- **`api/`**: routers FastAPI, contexto de cuenta, esquemas propios de la API, errores RFC 9457 y SSE. No expone entidades del dominio.
- **`bootstrap.py`** compone las dependencias: es el único sitio que decide qué adaptador va detrás de cada puerto.

«Ligera» significa: sin bus de eventos ni CQRS, y con los módulos de §4.2 dentro de una sola capa de dominio.

## Consecuencias

- **Positivas**
  - Las reglas fiscales se prueban con unitarias rápidas, hypothesis y mutmut sobre `domain/billing`.
  - Cambiar de modelo, de proveedor de Verifactu o de pasarela no toca el dominio.
  - Un fallo de un servicio externo queda acotado a su adaptador (RNF-08).
- **Negativas y mitigación**
  - Más mapeo entre capas → se mapea solo en los bordes (repositorios y esquemas de API).
  - Puertos innecesarios → solo se crea un puerto si hay un servicio externo detrás o un `Fake` que lo justifique.
  - Lógica de negocio en routers o repositorios → la Definición de Terminado lo prohíbe y `revisor-codigo` lo comprueba en cada bloque.
- **Qué haría reconsiderarla**
  - Que los mapeos frenen el desarrollo sin que ningún puerto haya necesitado un segundo adaptador al llegar al Bloque 12.
  - Que el producto se divida en servicios desplegados por separado.

## Verificación

- **import-linter** en CI, desde el Bloque 1:
  - Contrato `layers`: `kapataz.api` > `kapataz.infrastructure` > `kapataz.application` > `kapataz.domain`. Una capa no importa otra superior.
  - Contrato `forbidden`: `kapataz.domain` no importa `fastapi`, `sqlalchemy`, `alembic`, `anthropic`, `stripe` ni `procrastinate`.
  - Contrato `forbidden`: `kapataz.application` no importa `fastapi`, `sqlalchemy` ni `anthropic`.
- **ruff** (`flake8-tidy-imports.banned-api`) prohíbe `datetime.datetime.now` y `datetime.date.today`; solo `SystemClock` queda exceptuado.
- **mypy `--strict`** sobre `domain` y `application`, en CI.
- **Prueba unitaria sin E/S**, como la del Anexo C: `tests/unit/billing/test_invoice.py::test_factura_emitida_no_admite_cambios_en_lineas` con `@pytest.mark.req("RN-F-02")`. Las pruebas de `tests/unit` no usan base de datos ni red.
