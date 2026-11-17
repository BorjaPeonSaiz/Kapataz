"""Proceso worker: ``python -m kapataz.worker``.

En el Bloque 1 no hay tareas: el proceso arranca, lo registra y espera a
SIGTERM para que Compose pueda gestionarlo igual que tendrá que hacerlo con
la cola de procrastinate del Bloque 4 (ADR-026).
"""

import signal
import threading
from types import FrameType

import structlog

from kapataz.infrastructure.logging.setup import configure_logging

_IDLE_WAKE_SECONDS = 3600.0


def run(stop: threading.Event) -> None:
    log = structlog.get_logger("kapataz.worker")
    log.info("worker_iniciado", tareas=0, detalle="Sin tareas hasta el Bloque 4 (ADR-026).")
    while not stop.wait(_IDLE_WAKE_SECONDS):
        pass
    log.info("worker_detenido")


def main() -> None:
    configure_logging()
    stop = threading.Event()

    def _request_stop(_signum: int, _frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    run(stop)


if __name__ == "__main__":
    main()
