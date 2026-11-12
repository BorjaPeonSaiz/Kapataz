# ADR-026 — Cola de tareas en PostgreSQL

- **Estado:** Aceptado
- **Fecha:** 2026-11-12
- **Decide:** arquitecto-python (aprueba: Borja)
- **Requisitos relacionados:** RN-10, RNF-05, RNF-14, RNF-16, RF-IN-01, RF-VO-02, RF-VO-03
- **Se cierra en:** Bloque 4

## Contexto

Varias operaciones no caben en una petición HTTP: leer y extraer PDFs (con OCR si son escaneados), calcular embeddings, transcribir audio con Whisper y, más adelante, enviar registros a Verifactu con reintentos. Todas consumen CPU o esperan a servicios externos.

Hay que ejecutarlas en segundo plano sin bloquear la API, con reintentos, con progreso visible (SSE) y sin romper el aislamiento entre cuentas (RN-10). Un PDF que falla no puede detener los demás, y una cuenta que sube cien PDFs no puede acaparar el worker.

El despliegue es un VPS con Docker Compose operado por una persona (ADR-014). Cada servicio más es algo más que vigilar, copiar y actualizar.

## Opciones consideradas

1. **Tareas en segundo plano de FastAPI** (dentro del proceso de la API).
   - Ventajas: nada que añadir.
   - Inconvenientes: se pierden si el proceso se reinicia; compiten por CPU con las peticiones; sin reintentos ni reparto.
2. **Celery o RQ con Redis.**
   - Ventajas: maduros y muy usados.
   - Inconvenientes: añaden Redis, otro servicio con su persistencia, sus copias y su seguridad; el estado de la tarea queda fuera de la transacción de PostgreSQL.
3. **Cola en PostgreSQL con procrastinate y un proceso worker.**
   - Ventajas: sin servicios nuevos; la tarea se encola en la misma transacción que el dato que la origina; copias y RLS ya resueltos.
   - Inconvenientes: menos rendimiento que Redis a gran escala; añade carga a la base.

## Decisión

Se elige la opción 3.

- Cola en PostgreSQL con **procrastinate** y un proceso worker en su propio contenedor.
- Cada tarea lleva su `tenant_id` y fija la cuenta en su transacción igual que una petición (ADR-024). Una tarea sin cuenta no toca datos de negocio.
- La tarea se encola en la misma transacción que crea el dato del que depende.
- Un PDF que falla queda marcado con su motivo y no detiene la cola.
- Ninguna cuenta acapara la cola: el reparto justo entre cuentas se concreta y se prueba en el Bloque 4.
- La transcripción tiene concurrencia limitada para no agotar la CPU (ADR-011). El audio se borra al terminar, también si falla (RF-VO-03).
- El progreso se informa al frontend por SSE.
- El health check comprueba que el worker está vivo; hay alerta de cola atascada.

## Consecuencias

- **Positivas:**
  - Sin Redis: menos piezas que operar y que asegurar.
  - Encolado transaccional: no hay tareas huérfanas ni datos sin su tarea.
  - El aislamiento entre cuentas se aplica igual en la API y en el worker.
- **Negativas y mitigación:**
  - La cola compite con la carga de la base. Se mide en la prueba de carga (RNF-16) y en los tiempos de ingesta (RNF-05).
  - procrastinate es menos conocido que Celery. Se mitiga encapsulando el encolado detrás de una interfaz pequeña de la aplicación.
- **Qué haría reconsiderarla:** que la carga de la cola degrade las consultas de la API, o un volumen que exija varios workers en máquinas distintas.

## Verificación

- Prueba de aislamiento del worker: cada tarea corre en el contexto de su cuenta y no ve datos de otra (`@pytest.mark.req("RN-10")`).
- Prueba de que una tarea sin `tenant_id` se rechaza.
- Prueba de reparto: con muchas tareas de una cuenta en cola, la tarea de otra cuenta no espera a que terminen todas.
- Prueba de ingesta: un PDF que falla no bloquea la cola y su motivo se ve en la interfaz.
- Prueba de caos: worker parado con tareas en cola; al volver, se procesan.
- Prueba de borrado del audio tras transcribir, también si falla (`req("RF-VO-03")`).
- Tiempos de RNF-05 y RNF-14 medidos en el servidor de referencia.
