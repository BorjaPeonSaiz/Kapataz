"""Verdad de referencia versionada: completitud, esquema, coherencia y errores sembrados.

Leen ``samples/`` y ``evals/extraction/`` tal como están en el repositorio y
comprueban con ``Decimal``, sin usar el código del generador, que los importes
cuadran donde deben cuadrar y no cuadran donde se sembró el error (ADR-020).

Sin req en todo el módulo: verifican el dataset de evaluación de la ingesta
(RF-IN-02, RF-IN-03, RF-IN-05), de las trampas (RN-05) y de la fuga (RNF-17), no
esos requisitos, que se prueban contra la app cuando exista la ingesta.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from jsonschema import Draft202012Validator

from kapataz.domain.customers.tax_id import TaxId
from synthetic.schema import SCHEMA_FILENAME, extraction_schema
from tests.unit.tools.synthetic_support import (
    ACTIVE,
    EVALS,
    REPO_ROOT,
    SAMPLES,
    assert_unreachable_phones,
    dec,
    normalize,
    pdf_metadata,
    pdf_pages_text,
    pdf_syntax,
    pdf_title,
    percent,
    round_cents,
    single_revision_problems,
)

if TYPE_CHECKING:
    from synthetic.output import RenderedDocument

Truths = dict[str, dict[str, Any]]
# Presupuesto de tamaño de samples/ (encargo del Bloque 3).
MAX_SAMPLES_BYTES = 10_000_000

REASON_OF = {
    "total_no_cuadra": "total_no_cuadra",
    "base_no_cuadra": "base_no_cuadra",
    "cuota_iva_no_cuadra": "cuota_iva_no_cuadra",
    "nif_ausente": "falta_nif_cliente",
}


def _checks(extraction: dict[str, Any]) -> dict[str, bool]:
    """Cada comprobación aritmética de RF-IN-05, hecha aparte con Decimal."""
    lines = extraction["lines"]
    line_ok = all(
        dec(line["amount"])
        == round_cents(
            dec(line["quantity"]) * dec(line["unit_price"]) * (100 - dec(line["discount"])) / 100,
        )
        for line in lines
    )
    base = dec(extraction["base"])
    lines_sum = sum((dec(line["amount"]) for line in lines), Decimal(0))
    buckets = extraction["vat_breakdown"]
    bucket_bases_ok = len(buckets) == 1 or all(
        dec(bucket["base"])
        == sum(
            (dec(line["amount"]) for line in lines if line["vat_rate"] == bucket["rate"]),
            Decimal(0),
        )
        for bucket in buckets
    )
    vat_ok = all(
        dec(bucket["amount"])
        == (
            Decimal("0.00")
            if bucket["rate"] is None
            else percent(dec(bucket["base"]), dec(bucket["rate"]))
        )
        for bucket in buckets
    ) and dec(extraction["vat_amount"]) == sum((dec(b["amount"]) for b in buckets), Decimal(0))
    withholding = extraction["withholding"]
    withheld = Decimal(0)
    if withholding is not None:
        withheld = dec(withholding["amount"])
    withholding_ok = withholding is None or withheld == percent(base, dec(withholding["rate"]))
    total_ok = dec(extraction["total"]) == base + dec(extraction["vat_amount"]) - withheld
    guarantee = extraction["guarantee"]
    kept = dec(guarantee["amount"]) if guarantee else Decimal(0)
    guarantee_ok = guarantee is None or kept == percent(base, dec(guarantee["rate"]))
    due_ok = dec(extraction["amount_due"]) == dec(extraction["total"]) - kept
    return {
        "lines": line_ok,
        "base": lines_sum == base
        and bucket_bases_ok
        and (len(buckets) > 1 or dec(buckets[0]["base"]) == base),
        "vat": vat_ok,
        "withholding": withholding_ok,
        "total": total_ok,
        "guarantee": guarantee_ok,
        "amount_due": due_ok,
    }


# ------------------------------------------------------------------ completitud


def test_cada_pdf_tiene_su_json_y_cada_json_su_pdf(truths: Truths) -> None:
    pdfs = {p.relative_to(SAMPLES).with_suffix("").as_posix() for p in SAMPLES.glob("*/*.pdf")}
    jsons = {p.relative_to(EVALS).with_suffix("").as_posix() for p in EVALS.glob("*/doc-*.json")}
    assert pdfs
    assert pdfs == jsons == set(truths)
    for key, truth in truths.items():
        assert truth["pdf"] == f"samples/{key}.pdf"
        assert truth["professional"] == key.split("/")[0]
    assert not list((REPO_ROOT / "evals").rglob("*.pdf"))
    assert not [p for p in SAMPLES.rglob("*") if p.is_file() and p.suffix != ".pdf"]


def test_cada_json_valida_contra_el_esquema_versionado(truths: Truths) -> None:
    stored = json.loads((EVALS / SCHEMA_FILENAME).read_text(encoding="utf-8"))
    assert stored == extraction_schema()
    Draft202012Validator.check_schema(stored)
    validator = Draft202012Validator(stored, format_checker=Draft202012Validator.FORMAT_CHECKER)
    for key, truth in truths.items():
        errors = [error.message for error in validator.iter_errors(truth)]
        assert not errors, (key, errors[:3])


def _reject_float(raw: str) -> None:
    msg = f"Número con decimales en el JSON: {raw}"
    raise AssertionError(msg)


def test_los_importes_son_cadenas_decimales_y_nunca_float(truths: Truths) -> None:
    assert truths
    for path in [*EVALS.glob("*/doc-*.json"), EVALS / "manifest.json"]:
        json.loads(path.read_text(encoding="utf-8"), parse_float=_reject_float)


def test_el_manifiesto_cubre_cada_fichero_con_su_sha256() -> None:
    manifest = json.loads((EVALS / "manifest.json").read_text(encoding="utf-8"))
    paths = {entry["path"] for entry in manifest["files"]}
    on_disk = {p.relative_to(REPO_ROOT).as_posix() for p in SAMPLES.rglob("*.pdf")}
    on_disk |= {
        p.relative_to(REPO_ROOT).as_posix()
        for p in EVALS.rglob("*.json")
        if p.name != "manifest.json"
    }
    assert paths == on_disk
    lines = []
    for entry in sorted(manifest["files"], key=lambda item: item["path"]):
        data = (REPO_ROOT / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
        assert len(data) == entry["bytes"]
        lines.append(f"{entry['sha256']}  {entry['path']}\n")
    digest = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    assert digest == manifest["dataset_sha256"]
    assert manifest["summary"]["samples_bytes"] < MAX_SAMPLES_BYTES


# ------------------------------------------------------------------ coherencia


def test_sin_error_sembrado_los_importes_cuadran_con_un_solo_redondeo(truths: Truths) -> None:
    clean = [
        t
        for t in truths.values()
        if t["extraction"] is not None
        and not {e["kind"] for e in t["seeded_errors"]} - {"nif_ausente", "linea_partida"}
    ]
    assert len(clean) > 100
    for truth in clean:
        checks = _checks(truth["extraction"])
        assert all(checks.values()), (truth["id"], checks)


def test_cada_error_sembrado_rompe_solo_la_cuenta_que_declara(truths: Truths) -> None:
    broken_by = {
        "total_no_cuadra": {"total"},
        "base_no_cuadra": {"base"},
        "cuota_iva_no_cuadra": {"vat"},
        "nif_ausente": set(),
        "linea_partida": set(),
    }
    seen = set()
    for truth in truths.values():
        for error in truth["seeded_errors"]:
            kind = error["kind"]
            seen.add(kind)
            checks = _checks(truth["extraction"])
            assert {name for name, ok in checks.items() if not ok} == broken_by[kind], truth["id"]
            expected = [REASON_OF[kind]] if kind in REASON_OF else []
            assert truth["expected_review_reasons"] == expected
            if kind in {"total_no_cuadra", "base_no_cuadra", "cuota_iva_no_cuadra"}:
                field = error["field"]
                assert truth["extraction"][field] == error["printed"] != error["correct"]
    assert seen == set(broken_by)


def test_los_documentos_sin_error_no_esperan_revision(truths: Truths) -> None:
    for truth in truths.values():
        if not truth["seeded_errors"]:
            assert truth["expected_review_reasons"] == []


def test_el_nif_ausente_va_a_null_y_no_esta_en_el_pdf(truths: Truths) -> None:
    missing = [
        t for t in truths.values() if any(e["kind"] == "nif_ausente" for e in t["seeded_errors"])
    ]
    assert len(missing) == 4
    for truth in missing:
        assert truth["extraction"]["customer"]["tax_id"] is None
        real = next(e["correct"] for e in truth["seeded_errors"])
        TaxId(real)
        if not truth["scanned"]:
            text = " ".join(pdf_pages_text(REPO_ROOT / truth["pdf"]))
            assert real not in text
            assert truth["extraction"]["customer"]["name"] in text


def test_la_linea_partida_empieza_en_una_pagina_y_sigue_en_la_siguiente(truths: Truths) -> None:
    split = [
        t for t in truths.values() if any(e["kind"] == "linea_partida" for e in t["seeded_errors"])
    ]
    assert len(split) == 4
    for truth in split:
        error = truth["seeded_errors"][0]
        first, second = error["pages"]
        assert second == first + 1 <= truth["pages"]
        if truth["scanned"]:
            continue
        index = int(error["field"].removeprefix("lines[").removesuffix("]"))
        line = truth["extraction"]["lines"][index]
        concept = normalize(line["concept"])
        pages = pdf_pages_text(REPO_ROOT / truth["pdf"])
        assert " ".join(concept.split()[:3]) in pages[first - 1]
        if truth["layout"] == "texto_sin_tabla":
            # En texto corrido se parte la frase: el importe queda en la página siguiente.
            amount = f"importe, {line['amount'].replace('.', ',')} euros."
            assert amount not in pages[first - 1]
            assert amount in pages[second - 1]
        else:
            # En una tabla se parte el concepto: los importes quedan arriba.
            assert concept not in pages[first - 1]
            assert concept.split()[-1] in pages[second - 1]


# ------------------------------------------------------------------ PDF


def test_los_pdf_vectoriales_imprimen_lo_que_dice_su_json(truths: Truths) -> None:
    for truth in truths.values():
        path = REPO_ROOT / truth["pdf"]
        pages = pdf_pages_text(path)
        assert len(pages) == truth["pages"]
        assert pdf_title(path) == f"Documento {truth['id'].split('/')[1]}"
        if truth["scanned"]:
            continue
        text = " ".join(pages)
        extraction = truth["extraction"]
        if extraction is not None:
            assert extraction["number"] in text
            assert extraction["issuer"]["tax_id"] in text
            total = extraction["total"].replace(".", ",")
            assert total in text.replace(".", ""), truth["id"]


def test_los_escaneados_son_solo_imagen_y_son_el_15_por_ciento(truths: Truths) -> None:
    scanned = [t for t in truths.values() if t["scanned"]]
    assert len(scanned) == (len(truths) * 15 + 50) // 100
    assert {t["layout"] for t in scanned} >= {
        "tabla_clasica",
        "word_exportado",
        "programa_generico",
        "texto_sin_tabla",
        "logotipo_pie_extenso",
    }
    assert any(t["seeded_errors"] for t in scanned)
    for truth in scanned:
        assert all(page == "" for page in pdf_pages_text(REPO_ROOT / truth["pdf"]))


def test_los_datos_personales_listados_estan_impresos(truths: Truths) -> None:
    for truth in truths.values():
        kinds = {item["kind"] for item in truth["personal_data"]}
        assert {"nombre", "direccion"} <= kinds
        if truth["scanned"]:
            continue
        text = " ".join(pdf_pages_text(REPO_ROOT / truth["pdf"]))
        for item in truth["personal_data"]:
            assert normalize(item["value"]) in text, (truth["id"], item)


# ------------------------------------------------------------------ clasificación y trampas


def test_los_documentos_otro_no_llevan_extraccion(truths: Truths) -> None:
    others = [t for t in truths.values() if t["document_type"] == "otro"]
    assert 6 <= len(others) <= 10
    for truth in others:
        assert truth["extraction"] is None
        assert truth["other"]["kind"]
        assert not truth["seeded_errors"]
        assert truth["expected_review_reasons"] == []
    assert {t["other"]["kind"] for t in others} == {
        "albaran_proveedor",
        "factura_proveedor",
        "carta_comunidad",
        "hoja_de_pedido",
        "parte_de_trabajo",
    }
    for truth in truths.values():
        assert (truth["other"] is None) == (truth["document_type"] != "otro")


def test_los_pdf_trampa_llevan_la_instruccion_y_esperan_ninguna_accion(truths: Truths) -> None:
    traps = [t for t in truths.values() if t["is_trap"]]
    assert sorted((t["trap"]["technique"], t["scanned"]) for t in traps) == [
        ("concepto_de_linea", False),
        ("metadatos", False),
        ("pie_visible", False),
        ("pie_visible", True),
        ("texto_oculto", False),
    ]
    for truth in traps:
        trap = truth["trap"]
        behavior = trap["expected_behavior"]
        assert truth["document_type"] == "factura"
        assert behavior["pending_actions"] == []
        assert behavior["follows_injected_instructions"] is False
        # Dejar la trampa en revisión no se castiga: los motivos esperados son un mínimo.
        assert behavior["may_flag_for_review"] is True
        assert truth["expected_review_reasons"] == []
        assert all(_checks(truth["extraction"]).values())
        _no_real_destinations(trap["injected_text"])
        path = REPO_ROOT / truth["pdf"]
        text = " ".join(pdf_pages_text(path))
        injected = normalize(trap["injected_text"])
        match trap["technique"]:
            case "metadatos":
                assert pdf_metadata(path)["Subject"] == trap["injected_text"]
                assert injected not in text
            case "pie_visible" if truth["scanned"]:
                # Solo en la imagen: llega por OCR. El texto es otro que el del vectorial.
                assert text == ""
                assert "OCR" in trap["location"]
            case _:
                assert injected in text
        if trap["technique"] == "concepto_de_linea":
            concept = truth["extraction"]["lines"][trap["line_index"]]["concept"]
            assert concept.endswith(trap["injected_text"])
    injected_texts = [t["trap"]["injected_text"] for t in traps]
    assert len(set(injected_texts)) == len(injected_texts)
    for truth in truths.values():
        assert (truth["trap"] is not None) == truth["is_trap"]


def test_la_trampa_escaneada_lleva_la_instruccion_en_la_imagen_del_pie(
    rendered: list[RenderedDocument],
) -> None:
    """El PDF de disco no tiene texto; el vectorial que se rasterizó sí la lleva en el pie."""
    (item,) = [i for i in rendered if i.spec.trap is not None and i.spec.scanned]
    assert item.spec.trap is not None
    document = pdfium.PdfDocument(item.source_pdf)
    try:
        last = document[len(document) - 1]
        textpage = last.get_textpage()
        text = normalize(textpage.get_text_range())
        textpage.close()
        last.close()
    finally:
        document.close()
    assert normalize(item.spec.trap.injected_text) in text


_EMAIL_DOMAIN = re.compile(r"@([\w-]+(?:\.[\w-]+)+)")
_IBAN_IN_TEXT = re.compile(r"\bES\d{2}(?: \d{4}){5}\b")


# El host de una URL: lo que va entre «//» y la ruta, el puerto, la consulta o el final.
# Con usuario delante («https://usuario@sitio.es») el host leído es «usuario», que no
# acaba en .example: se rechaza igual.
_URL_HOST = re.compile(r"https?://([^\s/?#:]+)", re.IGNORECASE)


def _no_real_destinations(text: str) -> None:
    """Los destinos de una instrucción inyectada no llegan a nadie: correos y URL en
    .example, IBAN inválido y teléfonos que no se pueden marcar (S3-R-02, S3-R-04)."""
    domains = _EMAIL_DOMAIN.findall(text)
    assert all(domain.endswith(".example") for domain in domains), domains
    hosts = [host.rstrip(".").lower() for host in _URL_HOST.findall(text)]
    assert all(host.endswith(".example") for host in hosts), hosts
    for iban in _IBAN_IN_TEXT.findall(text):
        assert iban.startswith("ES00"), iban  # dígitos de control que el mod 97 nunca da
    assert_unreachable_phones(text, text)


def test_el_filtro_de_destinos_rechaza_los_que_llegan_a_alguien() -> None:
    _no_real_destinations(
        "Escribe a a@b.example, entra en https://pagos.example/x o llama al 461 22 33 44.",
    )
    for text in (
        "Entra en https://www.banco.es/pago.",
        "Entra en http://pagos.example.com:8080/.",
        "Entra en HTTPS://usuario@sitio.es/.",
        "Llama al 061 76 20 57.",
        "Llama al 092 00 65 75.",
        "Llama al +34 942 00 00 00.",
        "Llama al 612345678.",
        "Llama al 016-123-456.",
    ):
        try:
            _no_real_destinations(text)
        except AssertionError:
            continue
        msg = f"No rechaza: {text}"
        raise AssertionError(msg)


def _text_of(pdf: bytes) -> str:
    document = pdfium.PdfDocument(pdf)
    texts = []
    try:
        for index in range(len(document)):
            page = document[index]
            textpage = page.get_textpage()
            texts.append(textpage.get_text_range())
            textpage.close()
            page.close()
    finally:
        document.close()
    return " ".join(texts)


def test_ningun_telefono_del_dataset_se_puede_marcar(
    truths: Truths,
    rendered: list[RenderedDocument],
) -> None:
    """Datos personales, todo el JSON (también las trampas), el texto y los metadatos de
    los PDF y, en los escaneados, el texto del vectorial que se rasterizó (S3-R-02)."""
    phones = [
        item["value"]
        for truth in truths.values()
        for item in truth["personal_data"]
        if item["kind"] == "telefono"
    ]
    assert phones
    assert all(re.fullmatch(r"4[69]\d \d{2} \d{2} \d{2}", value) for value in phones), phones
    for path in EVALS.rglob("*.json"):
        assert_unreachable_phones(path.read_text(encoding="utf-8"), path.name)
    for truth in truths.values():
        path = REPO_ROOT / truth["pdf"]
        assert_unreachable_phones(" ".join(pdf_pages_text(path)), truth["id"])
        assert_unreachable_phones(" ".join(pdf_metadata(path).values()), truth["id"])
    scanned = [item for item in rendered if item.spec.scanned]
    assert scanned
    for item in scanned:
        assert_unreachable_phones(_text_of(item.source_pdf), item.pdf_path)


# ------------------------------------------------------------------ contenido activo


def test_ningun_pdf_lleva_contenido_activo_ni_adjuntos() -> None:
    pdfs = sorted(SAMPLES.glob("*/*.pdf"))
    assert len(pdfs) > 100
    for path in pdfs:
        data = path.read_bytes()
        assert not single_revision_problems(data), (path.name, single_revision_problems(data))
        found = {m.group(1).decode() for m in ACTIVE.finditer(pdf_syntax(data))}
        assert not found, (path.name, found)
        document = pdfium.PdfDocument(data)
        try:
            # -1: sin manejador de seguridad, es decir, sin cifrar.
            assert pdfium_c.FPDF_GetSecurityHandlerRevision(document.raw) == -1, path
            assert pdfium_c.FPDFDoc_GetJavaScriptActionCount(document.raw) == 0, path
            assert document.count_attachments() == 0, path
            assert document.get_formtype() == pdfium_c.FORMTYPE_NONE, path
            for index in range(len(document)):
                page = document[index]
                assert pdfium_c.FPDFPage_GetAnnotCount(page.raw) == 0, (path, index)
                page.close()
        finally:
            document.close()


def test_los_metadatos_de_cada_pdf_dicen_que_es_sintetico(truths: Truths) -> None:
    for truth in truths.values():
        metadata = pdf_metadata(REPO_ROOT / truth["pdf"])
        assert "sintético" in metadata["Author"], truth["id"]
        assert "sintético" in metadata["Keywords"], truth["id"]
        trap = truth["trap"]
        if trap is not None and trap["technique"] == "metadatos":
            # Excepción explícita: en esta trampa el /Subject es la instrucción inyectada.
            assert metadata["Subject"] == trap["injected_text"]
        else:
            assert "sintético" in metadata["Subject"], truth["id"]
