"""Determinismo del render y ``--check``: lo regenerado coincide con lo versionado (ADR-020).

Qué se compara y por qué:

- JSON y esquema, byte a byte: son texto y no dependen de ninguna biblioteca nativa.
- Cada PDF, por ``content_sha256`` de los bytes de disco: la huella del fichero
  entero con los flujos Flate descomprimidos y los JPEG sustituidos por un marcador.
  Los bytes comprimidos dependen de la zlib de la máquina (zlib, zlib-ng…) y de
  libjpeg-turbo; la huella, no (``test_synthetic_fingerprint``).
- Escaneados, además, por sus metadatos, por la fuente que declaran (el
  ``content_sha256`` del PDF vectorial que se rasterizó) y por la imagen de cada
  página: dimensiones y tinta. Dentro de una misma máquina se comprueba que sus
  bytes son idénticos entre dos ejecuciones.

Sin req en todo el módulo: verifican el dataset de evaluación de ``samples/`` y
``evals/``, no un requisito de la app.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from typing import TYPE_CHECKING, Any

from synthetic.build import DEFAULT_SEED, build_dataset
from synthetic.fingerprint import content_fingerprint
from synthetic.model import DocumentSpec, Layout, SeededErrorKind
from synthetic.output import (
    MANIFEST,
    check,
    files_to_write,
    render_all,
    write,
)
from synthetic.scan import scan_pdf
from tests.unit.tools.synthetic_support import REPO_ROOT, replace_on_disk

if TYPE_CHECKING:
    from pathlib import Path

    from synthetic.model import SyntheticDataset
    from synthetic.output import RenderedDocument

TRADES = ["electricista", "albanil"]


def _representative(rendered: list[RenderedDocument]) -> set[tuple[str, str]]:
    """Un documento por maquetación, más escaneados, trampas y líneas partidas."""
    chosen: set[tuple[str, str]] = set()
    layouts: set[Layout] = set()
    for item in rendered:
        spec = item.spec
        key = (spec.trade.value, spec.doc_id)
        if spec.layout not in layouts:
            layouts.add(spec.layout)
            chosen.add(key)
        if spec.trap or spec.seeded_error is SeededErrorKind.SPLIT_LINE:
            chosen.add(key)
    scanned = [(i.spec.trade.value, i.spec.doc_id) for i in rendered if i.spec.scanned]
    return chosen | set(scanned[:3])


def _written(root: Path, dataset: SyntheticDataset, rendered: list[RenderedDocument]) -> None:
    write(root, files_to_write(dataset, rendered), TRADES)


def _stable(manifest: dict[str, Any]) -> dict[str, Any]:
    """El manifiesto sin lo que depende de la zlib y del JPEG de la máquina.

    Quedan la cabecera, el resumen sin tamaños, el conjunto de rutas y, por fichero,
    el ``content_sha256`` de los PDF y el ``sha256`` de los JSON.
    """
    files = {}
    for entry in manifest["files"]:
        key = "content_sha256" if "content_sha256" in entry else "sha256"
        files[entry["path"]] = entry[key]
    summary = {
        trade: {k: v for k, v in figures.items() if k != "bytes"}
        for trade, figures in manifest["summary"]["professionals"].items()
    }
    header = {k: v for k, v in manifest.items() if k not in {"files", "summary", "dataset_sha256"}}
    return {"header": header, "summary": summary, "files": files}


def test_lo_regenerado_coincide_con_lo_versionado(
    dataset: SyntheticDataset,
    rendered: list[RenderedDocument],
) -> None:
    assert check(REPO_ROOT, dataset, rendered) == []
    for item in rendered:
        assert (REPO_ROOT / item.json_path).read_bytes() == item.json_bytes, item.json_path


def test_dos_ejecuciones_dan_los_mismos_bytes_tambien_escaneados(
    rendered: list[RenderedDocument],
) -> None:
    chosen = _representative(rendered)
    assert len(chosen) >= 9

    def wanted(spec: DocumentSpec) -> bool:
        return (spec.trade.value, spec.doc_id) in chosen

    again = {
        (i.spec.trade.value, i.spec.doc_id): i for i in render_all(build_dataset(), select=wanted)
    }
    assert any(item.spec.scanned for item in again.values())
    for item in rendered:
        key = (item.spec.trade.value, item.spec.doc_id)
        if key in again:
            assert again[key].pdf == item.pdf, key
            assert again[key].json_bytes == item.json_bytes, key


def test_otra_semilla_genera_otros_documentos(rendered: list[RenderedDocument]) -> None:
    other = build_dataset(DEFAULT_SEED + 1)
    first = other.professionals[0].documents[0]
    fresh = render_all(other, select=lambda spec: spec == first)[0]
    original = next(
        i for i in rendered if i.spec.trade is first.trade and i.spec.doc_id == first.doc_id
    )
    assert fresh.json_bytes != original.json_bytes


def test_escribir_y_comprobar_en_otra_carpeta(
    tmp_path: Path,
    dataset: SyntheticDataset,
    rendered: list[RenderedDocument],
) -> None:
    stale = tmp_path / "samples" / "albanil" / "doc-999.pdf"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"sobrante")
    keep = tmp_path / "samples" / "albanil" / "LEEME.txt"
    keep.write_text("no es un documento generado", encoding="utf-8")
    _written(tmp_path, dataset, rendered)
    assert not stale.exists()
    assert keep.exists()
    assert check(tmp_path, dataset, rendered) == []
    manifest = json.loads((tmp_path / MANIFEST).read_text(encoding="utf-8"))
    assert _stable(manifest) == _stable(
        json.loads((REPO_ROOT / MANIFEST).read_text(encoding="utf-8")),
    )
    target = rendered[0]
    (tmp_path / target.json_path).write_bytes(target.json_bytes + b" ")
    problems = check(tmp_path, dataset, rendered)
    assert problems == [
        f"{target.json_path}: el fichero no coincide con su sha256 del manifiesto",
        f"{target.json_path}: no coincide con el JSON regenerado",
    ]
    shutil.rmtree(tmp_path / "samples")
    assert len(check(tmp_path, dataset, rendered)) > len(rendered) // 2


def test_check_falla_si_falta_un_documento_en_lo_regenerado(
    tmp_path: Path,
    dataset: SyntheticDataset,
    rendered: list[RenderedDocument],
) -> None:
    _written(tmp_path, dataset, rendered)
    missing = rendered[0]
    problems = check(tmp_path, dataset, rendered[1:])
    assert f"{missing.pdf_path}: está en el manifiesto pero no se regenera" in problems
    assert f"{missing.json_path}: está en el manifiesto pero no se regenera" in problems
    assert f"{MANIFEST}: summary distinto del regenerado" in problems


def test_check_falla_si_la_semilla_o_el_periodo_no_son_los_del_dataset(
    tmp_path: Path,
    dataset: SyntheticDataset,
    rendered: list[RenderedDocument],
) -> None:
    _written(tmp_path, dataset, rendered)
    other_seed = dataclasses.replace(dataset, seed=dataset.seed + 1)
    assert f"{MANIFEST}: seed distinto del regenerado" in check(tmp_path, other_seed, rendered)
    shifted = dataclasses.replace(dataset, period_start=dataset.period_end)
    assert f"{MANIFEST}: period distinto del regenerado" in check(tmp_path, shifted, rendered)


def test_check_falla_si_se_sustituye_un_pdf_vectorial_y_se_actualiza_el_manifiesto(
    tmp_path: Path,
    dataset: SyntheticDataset,
    rendered: list[RenderedDocument],
) -> None:
    _written(tmp_path, dataset, rendered)
    vector = [item for item in rendered if not item.spec.scanned]
    target, intruder = vector[0], vector[1]
    # El manifiesto conserva el content_sha256 legítimo: solo cuadran sha256 y bytes.
    replace_on_disk(tmp_path, target.pdf_path, intruder.pdf)
    problems = check(tmp_path, dataset, rendered)
    assert problems == [f"{target.pdf_path}: el contenido del PDF en disco no es el regenerado"]
    # Y con el content_sha256 del intruso también: no coincide con el regenerado.
    replace_on_disk(
        tmp_path, target.pdf_path, intruder.pdf, content=content_fingerprint(intruder.pdf)
    )
    problems = check(tmp_path, dataset, rendered)
    assert f"{target.pdf_path}: content_sha256 distinto del versionado" in problems
    assert f"{target.pdf_path}: el contenido del PDF en disco no es el regenerado" in problems


def test_check_liga_cada_escaneado_con_su_fuente_y_su_imagen(
    tmp_path: Path,
    dataset: SyntheticDataset,
    rendered: list[RenderedDocument],
) -> None:
    _written(tmp_path, dataset, rendered)
    scanned = [item for item in rendered if item.spec.scanned]
    target, intruder = scanned[0], scanned[1]
    # Otro escaneado: otra huella, otros metadatos, otra fuente declarada y otra imagen.
    replace_on_disk(tmp_path, target.pdf_path, intruder.pdf)
    problems = check(tmp_path, dataset, rendered)
    assert problems[:3] == [
        f"{target.pdf_path}: el contenido del PDF en disco no es el regenerado",
        f"{target.pdf_path}: metadatos distintos de los regenerados: Keywords, Title",
        f"{target.pdf_path}: el escaneado no declara como fuente el PDF vectorial regenerado",
    ]
    assert all(": página " in p for p in problems[3:]), problems
    # El mismo vectorial escaneado con otro ruido: la estructura, los metadatos y la fuente
    # declarada son los regenerados (la huella no mira los datos del JPEG), pero la imagen
    # no es la regenerada.
    source = content_fingerprint(target.source_pdf)
    forged = scan_pdf(
        target.source_pdf,
        seed=target.spec.scan_seed + 1,
        title=f"Documento {target.spec.doc_id}",
        source_fingerprint=source,
    )
    replace_on_disk(tmp_path, target.pdf_path, forged)
    problems = check(tmp_path, dataset, rendered)
    assert problems
    assert all(p.startswith(f"{target.pdf_path}: página ") for p in problems), problems
    assert any("la imagen no coincide" in p for p in problems)
