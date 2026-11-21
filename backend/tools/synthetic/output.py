"""Render de los PDF y de su verdad de referencia, manifiesto y escritura (ADR-020).

Salida, relativa a la raíz del repositorio:

- ``samples/<profesional>/doc-NNN.pdf``: los PDF;
- ``evals/extraction/<profesional>/doc-NNN.json``: su JSON esperado, con el
  mismo nombre (los PDF no se duplican en ``evals/``);
- ``evals/extraction/extraction.schema.v1.json``: el JSON Schema;
- ``evals/extraction/manifest.json``: SHA-256 de cada fichero y del conjunto.
"""

import json
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from synthetic.fingerprint import PdfStructureError, content_fingerprint, sha256
from synthetic.layouts import LAYOUTS
from synthetic.model import DocumentSpec, ProfessionalDataset, SeededErrorKind, SyntheticDataset
from synthetic.pdfkit import RenderInfo, render_pdf
from synthetic.printed import printed_document
from synthetic.scan import scan_differences, scan_metadata, scan_pdf, scan_source
from synthetic.schema import SCHEMA_FILENAME, SCHEMA_VERSION, extraction_schema
from synthetic.truth import Json, ground_truth

SAMPLES_DIR = "samples"
EVALS_DIR = "evals/extraction"
MANIFEST = f"{EVALS_DIR}/manifest.json"
_VERSIONED = ("faker", "reportlab", "pypdfium2", "pillow")


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    """Un documento ya generado. ``source_pdf`` es el vectorial; en un escaneado, su origen."""

    spec: DocumentSpec
    pdf: bytes
    source_pdf: bytes
    info: RenderInfo
    truth: Json

    @property
    def pdf_path(self) -> str:
        return f"{SAMPLES_DIR}/{self.spec.trade.value}/{self.spec.doc_id}.pdf"

    @property
    def json_path(self) -> str:
        return f"{EVALS_DIR}/{self.spec.trade.value}/{self.spec.doc_id}.json"

    @property
    def json_bytes(self) -> bytes:
        return to_json(self.truth)


def to_json(value: object) -> bytes:
    """JSON en UTF-8, con sangría y fin de línea LF, igual en cualquier sistema."""
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def render_document(spec: DocumentSpec, data: ProfessionalDataset) -> RenderedDocument:
    doc = printed_document(spec, data)
    split = spec.seeded_error is SeededErrorKind.SPLIT_LINE
    vector, info = render_pdf(doc, LAYOUTS[spec.layout], split_line=split)
    pdf = vector
    if spec.scanned:
        pdf = scan_pdf(
            vector,
            seed=spec.scan_seed,
            title=f"Documento {spec.doc_id}",
            source_fingerprint=content_fingerprint(vector),
        )
    return RenderedDocument(spec, pdf, vector, info, ground_truth(doc, info))


def render_all(
    dataset: SyntheticDataset,
    *,
    select: Callable[[DocumentSpec], bool] | None = None,
) -> list[RenderedDocument]:
    return [
        render_document(spec, data)
        for data in dataset.professionals
        for spec in data.documents
        if select is None or select(spec)
    ]


def manifest(dataset: SyntheticDataset, rendered: Iterable[RenderedDocument]) -> Json:
    """Huellas de cada fichero y del conjunto, con un resumen de lo generado."""
    documents = list(rendered)
    files = _file_entries(documents)
    return {
        "schema_version": SCHEMA_VERSION,
        "seed": dataset.seed,
        "period": {
            "start": dataset.period_start.isoformat(),
            "end": dataset.period_end.isoformat(),
        },
        "generator_versions": {name: version(name) for name in _VERSIONED},
        "fingerprints": _FINGERPRINTS,
        "dataset_sha256": dataset_digest(files),
        "summary": summary(documents),
        "files": files,
    }


def dataset_digest(files: Iterable[dict[str, Any]]) -> str:
    """SHA-256 de las líneas «sha256  ruta» de los ficheros, en el orden dado."""
    lines = "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in files)
    return sha256(lines.encode("utf-8"))


_FINGERPRINTS = {
    "sha256": "SHA-256 de los bytes del fichero.",
    "content_sha256": (
        "SHA-256 del PDF completo en forma canónica: flujos Flate descomprimidos, datos "
        "de las imágenes JPEG sustituidos por un marcador, sin /Length ni desplazamientos "
        "de la tabla de referencias. No depende de zlib ni de libjpeg; los píxeles de los "
        "escaneados se comparan aparte."
    ),
    "dataset_sha256": "SHA-256 de las líneas «sha256  ruta» de todos los ficheros, en orden.",
}


def _file_entries(documents: Iterable[RenderedDocument]) -> list[dict[str, str | int]]:
    files: list[dict[str, str | int]] = []
    for item in documents:
        files.append(
            {
                "path": item.pdf_path,
                "sha256": sha256(item.pdf),
                "content_sha256": content_fingerprint(item.pdf),
                "bytes": len(item.pdf),
            },
        )
        files.append(
            {
                "path": item.json_path,
                "sha256": sha256(item.json_bytes),
                "bytes": len(item.json_bytes),
            },
        )
    schema = to_json(extraction_schema())
    files.append(
        {"path": f"{EVALS_DIR}/{SCHEMA_FILENAME}", "sha256": sha256(schema), "bytes": len(schema)},
    )
    files.sort(key=lambda entry: str(entry["path"]))
    return files


def summary(rendered: Iterable[RenderedDocument]) -> Json:
    """Cifras por profesional: tipos, maquetaciones, escaneados, errores, trampas y tamaño."""
    groups: dict[str, list[RenderedDocument]] = {}
    for item in rendered:
        groups.setdefault(item.spec.trade.value, []).append(item)
    professionals: Json = {}
    for trade, items in groups.items():
        specs = [item.spec for item in items]
        professionals[trade] = {
            "documents": len(specs),
            "by_type": _counts(spec.document_type.value for spec in specs),
            "by_layout": _counts(spec.layout.value for spec in specs),
            "scanned": sum(spec.scanned for spec in specs),
            "seeded_errors": _counts(s.seeded_error.value for s in specs if s.seeded_error),
            "traps": _counts(_trap_label(s) for s in specs if s.trap is not None),
            "bytes": sum(len(item.pdf) for item in items),
        }
    total = sum(len(item.pdf) for items in groups.values() for item in items)
    return {"professionals": professionals, "samples_bytes": total}


def _trap_label(spec: DocumentSpec) -> str:
    """La técnica de la trampa; la del escaneado aparte, porque se lee por OCR."""
    if spec.trap is None:
        raise AssertionError("Solo se etiqueta un documento trampa.")
    suffix = "_escaneado" if spec.scanned else ""
    return f"{spec.trap.technique.value}{suffix}"


def _counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def files_to_write(dataset: SyntheticDataset, rendered: list[RenderedDocument]) -> dict[str, bytes]:
    """Todos los ficheros de la salida, por ruta relativa a la raíz."""
    files: dict[str, bytes] = {}
    for item in rendered:
        files[item.pdf_path] = item.pdf
        files[item.json_path] = item.json_bytes
    files[f"{EVALS_DIR}/{SCHEMA_FILENAME}"] = to_json(extraction_schema())
    files[MANIFEST] = to_json(manifest(dataset, rendered))
    return files


def write(root: Path, files: dict[str, bytes], trades: Iterable[str]) -> None:
    """Escribe la salida y borra los ``doc-*`` que ya no se generan."""
    for trade in trades:
        for folder, pattern in (
            (root / SAMPLES_DIR / trade, "doc-*.pdf"),
            (root / EVALS_DIR / trade, "doc-*.json"),
        ):
            if folder.is_dir():
                for stale in folder.glob(pattern):
                    if stale.relative_to(root).as_posix() not in files:
                        stale.unlink()
    for relative, data in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def check(root: Path, dataset: SyntheticDataset, rendered: list[RenderedDocument]) -> list[str]:
    """Diferencias entre lo regenerado y lo que hay en disco, comparando lo que es estable.

    - El manifiesto: la misma versión del esquema, semilla, periodo y versiones del
      generador; el resumen, igual salvo los bytes, que tienen que ser los de disco; el
      mismo conjunto de rutas que lo regenerado; y su ``dataset_sha256`` coherente.
    - Cada fichero en disco coincide con el ``sha256`` y los ``bytes`` del manifiesto, y
      no sobra ningún ``doc-*`` sin entrada.
    - Los JSON y el esquema, byte a byte con lo regenerado.
    - Cada PDF, por el ``content_sha256`` de los bytes de disco: el fichero entero en
      forma canónica, con la estructura validada (``content_fingerprint``).
    - Los escaneados, además, por sus metadatos, por la fuente que declaran (el
      ``content_sha256`` del vectorial que se rasterizó) y por la imagen de cada
      página, comparada con la regenerada (``scan_differences``).
    """
    stored = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    expected = manifest(dataset, rendered)
    problems = _manifest_header_problems(stored, expected)
    entries = {entry["path"]: entry for entry in stored["files"]}
    regenerated = {str(entry["path"]): entry for entry in _file_entries(rendered)}
    problems += [f"{path}: no está en el manifiesto" for path in regenerated if path not in entries]
    problems += [
        f"{path}: está en el manifiesto pero no se regenera"
        for path in entries
        if path not in regenerated
    ]
    problems += _disk_problems(root, entries, rendered)
    by_path = {item.pdf_path: item for item in rendered}
    by_path |= {item.json_path: item for item in rendered}
    for path, entry in regenerated.items():
        old = entries.get(path)
        on_disk = root / path
        if old is None or not on_disk.is_file():
            continue
        key = "content_sha256" if "content_sha256" in entry else "sha256"
        if old.get(key) != entry[key]:
            problems.append(f"{path}: {key} distinto del versionado")
        item = by_path.get(path)
        if item is None:
            if on_disk.read_bytes() != to_json(extraction_schema()):
                problems.append(f"{path}: no coincide con el esquema regenerado")
        elif path == item.json_path:
            if on_disk.read_bytes() != item.json_bytes:
                problems.append(f"{path}: no coincide con el JSON regenerado")
        else:
            problems += [f"{path}: {problem}" for problem in _pdf_problems(on_disk, item)]
    return problems


def _manifest_header_problems(stored: Json, expected: Json) -> list[str]:
    problems = [
        f"{MANIFEST}: {key} distinto del regenerado"
        for key in ("schema_version", "seed", "period", "generator_versions", "fingerprints")
        if stored.get(key) != expected[key]
    ]
    if _without_bytes(stored.get("summary")) != _without_bytes(expected["summary"]):
        problems.append(f"{MANIFEST}: summary distinto del regenerado")
    files = stored.get("files")
    if not isinstance(files, list):
        return [*problems, f"{MANIFEST}: sin lista de ficheros"]
    if dataset_digest(files) != stored.get("dataset_sha256"):
        problems.append(f"{MANIFEST}: dataset_sha256 no corresponde a sus ficheros")
    return problems


def _without_bytes(value: object) -> object:
    """El resumen sin los tamaños, que dependen de la zlib y del JPEG de la máquina."""
    if isinstance(value, dict):
        return {k: _without_bytes(v) for k, v in value.items() if k not in _BYTE_KEYS}
    return value


_BYTE_KEYS = frozenset({"bytes", "samples_bytes"})


def _disk_problems(
    root: Path,
    entries: dict[str, dict[str, object]],
    rendered: list[RenderedDocument],
) -> list[str]:
    """Cada entrada del manifiesto está en disco con su huella y su tamaño; no sobra nada."""
    problems: list[str] = []
    sizes: dict[str, int] = {}
    for path, entry in entries.items():
        on_disk = root / path
        if not on_disk.is_file():
            problems.append(f"{path}: falta en disco")
            continue
        data = on_disk.read_bytes()
        sizes[path] = len(data)
        if sha256(data) != entry["sha256"]:
            problems.append(f"{path}: el fichero no coincide con su sha256 del manifiesto")
        elif len(data) != entry.get("bytes"):
            problems.append(f"{path}: el tamaño no coincide con el del manifiesto")
    trades = sorted({item.spec.trade.value for item in rendered})
    for trade in trades:
        for folder, pattern in (
            (root / SAMPLES_DIR / trade, "doc-*.pdf"),
            (root / EVALS_DIR / trade, "doc-*.json"),
        ):
            for stray in sorted(folder.glob(pattern)) if folder.is_dir() else []:
                relative = stray.relative_to(root).as_posix()
                if relative not in entries:
                    problems.append(f"{relative}: sobra en disco, no está en el manifiesto")
    stored = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    total = sum(size for path, size in sizes.items() if path.startswith(f"{SAMPLES_DIR}/"))
    if stored.get("summary", {}).get("samples_bytes") != total:
        problems.append(f"{MANIFEST}: samples_bytes no es la suma de los PDF en disco")
    return problems


def _pdf_problems(on_disk: Path, item: RenderedDocument) -> list[str]:
    """Liga el PDF de disco con el regenerado, sin depender de zlib ni de libjpeg."""
    data = on_disk.read_bytes()
    try:
        fingerprint = content_fingerprint(data)
    except PdfStructureError as error:
        return [f"estructura de PDF no admitida: {error}"]
    problems = []
    if fingerprint != content_fingerprint(item.pdf):
        problems.append("el contenido del PDF en disco no es el regenerado")
    if not item.spec.scanned:
        return problems
    if (metadata := scan_metadata(data)) != (expected := scan_metadata(item.pdf)):
        changed = sorted(
            k for k in metadata.keys() | expected.keys() if metadata.get(k) != expected.get(k)
        )
        problems.append(f"metadatos distintos de los regenerados: {', '.join(changed)}")
    if scan_source(data) != content_fingerprint(item.source_pdf):
        problems.append("el escaneado no declara como fuente el PDF vectorial regenerado")
    return problems + scan_differences(item.pdf, data)
