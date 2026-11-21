"""Generador de datos sintéticos de Kapataz (ADR-020, Bloque 3).

Uso, desde ``backend/``::

    uv run python tools/gen_synthetic.py                  # escribe en la raíz del repo
    uv run python tools/gen_synthetic.py --seed 7 --out /tmp/demo
    uv run python tools/gen_synthetic.py --check          # falla si no coincide

Escribe los PDF en ``samples/<profesional>/`` y su verdad de referencia en
``evals/extraction/<profesional>/``, con el esquema y el manifiesto. La API de
datos pura, para ``seed_demo.py``, es ``synthetic.build.build_dataset``.

``--check`` regenera en memoria y compara con lo versionado: el manifiesto
(semilla, periodo, versiones, resumen y el mismo conjunto de rutas), cada
fichero de disco con su ``sha256``, los JSON byte a byte, cada PDF por el
``content_sha256`` del fichero entero de disco (con la estructura validada: sin
actualizaciones incrementales, cifrado ni filtros raros) y los escaneados,
además, por sus metadatos, la fuente que declaran y la imagen de cada página
(``synthetic.output.check``). Sale con 1 si hay diferencias.
"""

import argparse
import sys
import time
from pathlib import Path

from synthetic.build import DEFAULT_SEED, build_dataset
from synthetic.output import check, files_to_write, render_all, write

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="semilla (por defecto, fija)"
    )
    parser.add_argument("--out", type=Path, default=REPO_ROOT, help="raíz de la salida")
    parser.add_argument("--check", action="store_true", help="compara con lo versionado")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    dataset = build_dataset(args.seed)
    rendered = render_all(dataset)
    root: Path = args.out.resolve()
    if args.check:
        problems = check(root, dataset, rendered)
        for problem in problems:
            print(problem, file=sys.stderr)
        print(f"{len(rendered)} documentos comprobados, {len(problems)} diferencias.")
        return 1 if problems else 0
    files = files_to_write(dataset, rendered)
    write(root, files, [data.professional.slug for data in dataset.professionals])
    size = sum(len(item.pdf) for item in rendered)
    elapsed = time.perf_counter() - started
    print(f"{len(rendered)} documentos, {size / 1_000_000:.2f} MB de PDF, en {elapsed:.1f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
