# ADR-0004: Un único agente de IA común para todas las empresas

- **Estado:** Aceptada
- **Fecha:** 2026-10-29

## Contexto

El nombre de trabajo del proyecto («generador de agentes») sugiere un constructor de agentes por cliente. El producto que se quiere construir es un SaaS administrativo en el que todas las empresas reciben el mismo servicio de IA.

## Decisión

- Hay **un único agente** para toda la plataforma. Su prompt, modelo, proveedor, herramientas, límites y políticas se configuran centralmente, solo por el rol `admin`.
- No hay constructor de agentes, agentes por empresa, BYOK ni configuración del modelo por cliente. Las respuestas solo difieren por los datos de cada empresa.
- La configuración está versionada: cada cambio crea una versión inmutable con autor, fecha y motivo, pasa una suite de regresión antes de promoverse y se despliega de forma gradual, con posibilidad de volver atrás.
- Las credenciales del proveedor de LLM se guardan cifradas y nunca llegan al navegador, a los clientes ni a los logs.
- El agente no ejecuta SQL arbitrario: usa servicios de lectura permitidos y el RAG filtrado por empresa. Sus acciones de escritura requieren confirmación y quedan auditadas.

## Alternativas consideradas

- **Agentes configurables por empresa:** multiplica la superficie de pruebas, de soporte y de coste sin una necesidad identificada.
- **BYOK (cada cliente aporta su clave de LLM):** complica la seguridad, la evaluación y el soporte.

## Consecuencias

- Un cambio de configuración afecta a todas las empresas a la vez: por eso son obligatorias la suite de regresión y el despliegue gradual.
- El coste de LLM lo asume la plataforma y debe controlarse con límites por empresa.
