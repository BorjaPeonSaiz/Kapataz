"""Lectura de facturas emitidas: estructura sí, reglas de emisión vigentes no (RN-F-02).

Una factura emitida no cambia. Si una regla de emisión se endurece después
(un límite nuevo, un dato obligatorio más, otro criterio del 40 %), lo emitido
antes tiene que seguir leyéndose para consultarlo, exportarlo y rectificarlo.
El repositorio la reconstruye con ``issued_amounts``: el dominio comprueba la
estructura y que los importes guardados cuadran, y nada más. El camino de
creación y emisión sigue aplicando todas las reglas.
"""

import dataclasses
from datetime import date

import pytest

from kapataz.domain.billing import invoice as invoice_module
from kapataz.domain.billing.calculation import InvoiceTotals
from kapataz.domain.billing.codes import InvoiceStatus, RecipientType
from kapataz.domain.billing.errors import (
    InvalidDocumentNumberError,
    InvalidInvoiceError,
    IssuedAmountsMismatchError,
)
from kapataz.domain.billing.invoice import (
    CorrectiveInvoice,
    Guarantee,
    Invoice,
    IssuedAmounts,
    RectifiedInvoice,
)
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.quantity import Percentage
from tests.unit.domain.billing_factories import (
    ISSUER,
    NOW,
    RECIPIENT,
    REDUCED,
    TODAY,
    corrective,
    draft,
    issue,
    line,
    money,
    quote_version,
)


def _amounts(totals: InvoiceTotals) -> IssuedAmounts:
    return IssuedAmounts(
        base=totals.base,
        tax=totals.tax,
        total_amount=totals.total_amount,
        withholding=totals.withholding,
        guarantee=totals.guarantee,
        amount_due=totals.amount_due,
    )


def _fields(invoice: Invoice) -> dict[str, object]:
    return {field.name: getattr(invoice, field.name) for field in dataclasses.fields(invoice)}


def _reload[T: Invoice](
    invoice: T, *, issued_amounts: IssuedAmounts | None = None, **changes: object
) -> T:
    """Lo que hace el repositorio al leer una emitida: sus campos y sus importes guardados."""
    stored = issued_amounts or _amounts(invoice.totals)
    return type(invoice)(**(_fields(invoice) | changes), issued_amounts=stored)


def _issued_corrective() -> CorrectiveInvoice:
    rectified = issue(draft(line("100.00")))
    assert rectified.number is not None
    assert rectified.issue_date is not None
    draft_corrective = corrective(
        line("-10.00"),
        rectified=(
            RectifiedInvoice(
                invoice_id=rectified.id,
                number=rectified.number,
                issue_date=rectified.issue_date,
            ),
        ),
    )
    return issue(draft_corrective)


@pytest.mark.req("RN-F-02")
@pytest.mark.parametrize(
    "build",
    [lambda: issue(draft(line("45.00", "3"))), _issued_corrective],
    ids=["factura", "rectificativa"],
)
def test_una_emitida_se_sigue_leyendo_si_despues_se_endurece_una_regla(build, monkeypatch):
    issued = build()
    # Después de emitirla, la AEAT baja el límite de la descripción general y
    # del motivo: los de la factura ya emitida pasan del nuevo.
    monkeypatch.setattr(invoice_module, "MAX_DESCRIPTION_LENGTH", 5)

    reloaded = _reload(issued)

    assert reloaded == issued
    assert reloaded.totals == issued.totals
    # El camino de creación no se ha relajado: el mismo borrador hoy no se crea.
    with pytest.raises(InvalidInvoiceError, match="descripción general"):
        draft(line("45.00", "3"), description="Reforma de baño")


@pytest.mark.req("RN-F-02")
@pytest.mark.req("RN-F-13")
def test_una_emitida_al_10_con_mas_del_40_de_material_se_lee_pero_no_se_crea():
    # Así quedaría una factura emitida si el criterio provisional del 40 % se
    # endureciera después: hoy no pasa la regla, pero ya está emitida.
    issued = issue(
        draft(
            line("1000.00"),
            treatment=REDUCED,
            recipient_type=RecipientType.PRIVATE,
            dwelling_over_two_years=True,
        )
    )
    lines = (line("700.00", is_material=True), line("300.00"))
    fields = _fields(issued) | {"lines": lines}
    with pytest.raises(InvalidInvoiceError, match=r"^Con más del 40 %"):
        Invoice(**fields)

    # La base es la misma (1.000 €), así que los importes guardados también.
    stored = Invoice(**fields, issued_amounts=_amounts(issued.totals))

    assert stored.is_issued
    assert stored.lines == lines
    assert stored.totals.tax == money("100.00")


@pytest.mark.req("RN-F-02")
def test_al_emitir_se_aplican_las_reglas_vigentes(monkeypatch):
    invoice = draft(line("45.00", "3"))
    monkeypatch.setattr(invoice_module, "MAX_DESCRIPTION_LENGTH", 5)

    with pytest.raises(InvalidInvoiceError, match="descripción general"):
        issue(invoice)


@pytest.mark.req("RN-F-02")
def test_una_emitida_con_importes_guardados_que_no_cuadran_no_se_lee():
    issued = issue(draft(line("45.00", "3")))
    totals = issued.totals
    altered = dataclasses.replace(
        _amounts(totals),
        base=totals.base + money("0.01"),
        total_amount=totals.total_amount + money("0.01"),
        amount_due=totals.amount_due + money("0.01"),
    )

    with pytest.raises(
        IssuedAmountsMismatchError,
        match=r"^Los importes guardados .*: base, total_amount, amount_due$",
    ):
        _reload(issued, issued_amounts=altered)


@pytest.mark.req("RN-F-02")
def test_la_lectura_de_una_emitida_sigue_comprobando_la_estructura():
    issued = issue(draft(line("45.00", "3")))

    with pytest.raises(
        InvalidDocumentNumberError, match=r"^El número no es de la serie de la factura"
    ):
        _reload(issued, number=DocumentNumber(Series.correctives(), 2026, 1))
    with pytest.raises(InvalidInvoiceError, match=r"^Una emitida tiene"):
        _reload(issued, recipient=dataclasses.replace(RECIPIENT, address=None))
    with pytest.raises(InvalidInvoiceError, match=r"^El vencimiento no puede"):
        _reload(issued, due_date=date(2026, 1, 1))


@pytest.mark.req("RF-FA-01")
def test_un_borrador_no_se_lee_con_importes_guardados():
    invoice = draft(line("45.00", "3"))

    with pytest.raises(InvalidInvoiceError, match=r"^Solo una factura emitida se lee"):
        Invoice(**_fields(invoice), issued_amounts=_amounts(invoice.totals))


@pytest.mark.req("RN-F-02")
def test_la_emitida_leida_conserva_partes_fechas_y_estado():
    issued = issue(draft(line("45.00", "3")))

    reloaded = _reload(issued)

    assert reloaded.status is InvoiceStatus.ISSUED
    assert reloaded.issuer == ISSUER
    assert reloaded.recipient == RECIPIENT
    assert reloaded.issued_at == NOW
    assert reloaded.issue_date == TODAY


@pytest.mark.req("RN-F-13")
@pytest.mark.req("RN-F-02")
def test_una_emitida_sin_destinatario_o_sin_vivienda_no_se_lee():
    # Sin ellos no se sabría si su tipo de IVA era correcto: es estructura.
    issued = issue(
        draft(
            line("1000.00"),
            treatment=REDUCED,
            recipient_type=RecipientType.PRIVATE,
            dwelling_over_two_years=True,
        )
    )

    with pytest.raises(InvalidInvoiceError, match=r"^Una emitida guarda el tipo"):
        _reload(issued, recipient_type=None, dwelling_over_two_years=None)
    with pytest.raises(InvalidInvoiceError, match=r"^Una emitida guarda el tipo"):
        _reload(issued, dwelling_over_two_years=None)


@pytest.mark.req("RN-F-13")
@pytest.mark.req("RN-F-02")
def test_una_emitida_desde_presupuesto_se_lee_con_los_datos_copiados():
    version = quote_version(recipient_type=RecipientType.PRIVATE, dwelling_over_two_years=True)
    issued = issue(
        draft(line("1000.00"), treatment=REDUCED, quote_version_id=version.id), version=version
    )

    reloaded = _reload(issued)

    assert reloaded == issued
    assert reloaded.recipient_type is RecipientType.PRIVATE
    assert reloaded.dwelling_over_two_years is True


@pytest.mark.req("RN-F-13")
@pytest.mark.req("RN-F-02")
def test_la_lectura_solo_exige_la_presencia_no_la_regla_del_tipo():
    # Una emitida al 10 % se sigue leyendo aunque la regla del destinatario
    # cambiara después: la lectura no vuelve a aplicar las reglas de emisión.
    issued = issue(
        draft(
            line("1000.00"),
            treatment=REDUCED,
            recipient_type=RecipientType.PRIVATE,
            dwelling_over_two_years=True,
        )
    )
    fields = _fields(issued) | {"recipient_type": RecipientType.BUSINESS}
    with pytest.raises(InvalidInvoiceError, match=r"^El 10 % exige"):
        Invoice(**fields)

    stored = Invoice(**fields, issued_amounts=_amounts(issued.totals))

    assert stored.recipient_type is RecipientType.BUSINESS
    assert stored.totals.tax == money("100.00")


@pytest.mark.req("RN-F-02")
def test_cada_importe_guardado_que_no_cuadra_se_nombra():
    issued = issue(
        draft(line("1000.00"))
        .with_withholding(Percentage.of("15"))
        .with_guarantee(Guarantee(rate=Percentage.of("5"), due_date=TODAY))
    )
    stored = _amounts(issued.totals)
    cent = money("0.01")
    assert stored.differences(issued.totals) == ()
    for name in ("base", "tax", "total_amount", "withholding", "guarantee", "amount_due"):
        altered = dataclasses.replace(stored, **{name: getattr(stored, name) + cent})
        assert altered.differences(issued.totals) == (name,)
