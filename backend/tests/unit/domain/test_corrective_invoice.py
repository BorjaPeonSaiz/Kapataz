"""Rectificativas: clase, tipo y facturas rectificadas (RF-FA-04, RN-F-03)."""

import dataclasses
from datetime import date
from uuid import uuid4

import pytest

from kapataz.domain.billing.codes import CorrectionType, InvoiceType, PhaseType
from kapataz.domain.billing.errors import InvalidInvoiceError, NegativeInvoiceBaseError
from kapataz.domain.billing.ids import InvoiceId
from kapataz.domain.billing.invoice import CorrectiveInvoice, Guarantee, Invoice, RectifiedInvoice
from kapataz.domain.billing.numbering import DocumentNumber
from kapataz.domain.billing.quantity import Percentage
from tests.unit.domain.billing_factories import TODAY, corrective, issue, line, money


def rectified(
    number: str = "F-2026-0001",
    base: str | None = None,
    tax: str | None = None,
) -> RectifiedInvoice:
    return RectifiedInvoice(
        invoice_id=InvoiceId(uuid4()),
        number=DocumentNumber.parse(number),
        issue_date=date(2026, 3, 1),
        rectified_base=None if base is None else money(base),
        rectified_tax=None if tax is None else money(tax),
    )


@pytest.mark.req("RN-F-03")
@pytest.mark.req("RF-FA-04")
def test_rectificativa_por_diferencias_de_varias_facturas():
    first, second = rectified("F-2026-0001"), rectified("F-2026-0002")
    invoice = corrective(line("-1000.00"), rectified=(first, second))
    assert isinstance(invoice, Invoice)
    assert invoice.rectified == (first, second)
    assert invoice.invoice_type is InvoiceType.R1
    assert invoice.correction_type is CorrectionType.DIFFERENCE
    assert invoice.rectified_base_total is None
    issued = issue(invoice)
    assert str(issued.number) == "R-2026-0001"
    assert issued.totals.base == money("-1000.00")
    assert issued.totals.tax == money("-210.00")


@pytest.mark.req("RN-F-03")
def test_rectificativa_por_sustitucion_guarda_lo_rectificado():
    invoice = corrective(
        line("900.00"),
        rectified=(
            rectified(base="1000.00", tax="210.00"),
            rectified("F-2026-0002", "50", "10.50"),
        ),
        correction_type=CorrectionType.SUBSTITUTION,
        invoice_type=InvoiceType.R4,
    )
    assert invoice.rectified_base_total == money("1050.00")
    assert invoice.rectified_tax_total == money("220.50")
    assert issue(invoice).totals.base == money("900.00")


@pytest.mark.req("RN-F-03")
def test_por_sustitucion_no_admite_base_negativa():
    invoice = corrective(
        line("-1.00"),
        rectified=(rectified(base="1.00", tax="0.21"),),
        correction_type=CorrectionType.SUBSTITUTION,
    )
    with pytest.raises(NegativeInvoiceBaseError):
        issue(invoice)


@pytest.mark.req("RN-F-03")
@pytest.mark.parametrize("invoice_type", [InvoiceType.R1, InvoiceType.R2, InvoiceType.R3])
def test_clases_r1_a_r4(invoice_type):
    assert corrective(rectified=(rectified(),), invoice_type=invoice_type)


@pytest.mark.req("RN-F-03")
@pytest.mark.parametrize("invoice_type", [InvoiceType.F1, InvoiceType.R5, InvoiceType.F3])
def test_clases_no_admitidas(invoice_type):
    with pytest.raises(InvalidInvoiceError):
        corrective(rectified=(rectified(),), invoice_type=invoice_type)


@pytest.mark.req("RN-F-03")
def test_rectificativas_no_validas():
    same = rectified()
    with pytest.raises(InvalidInvoiceError):
        corrective(rectified=())
    with pytest.raises(InvalidInvoiceError):
        corrective(rectified=(same, same))
    with pytest.raises(InvalidInvoiceError):
        corrective(rectified=(rectified(),), reason="  ")
    with pytest.raises(InvalidInvoiceError):
        corrective(rectified=(rectified(),), reason="x" * 501)
    with pytest.raises(InvalidInvoiceError):
        corrective(rectified=(rectified(base="1.00", tax="0.21"),))
    with pytest.raises(InvalidInvoiceError):
        corrective(rectified=(rectified(),), correction_type=CorrectionType.SUBSTITUTION)
    with pytest.raises(InvalidInvoiceError):
        rectified(base="1.00")


@pytest.mark.req("RN-F-03")
def test_una_rectificativa_no_es_una_fase_ni_lleva_garantia():
    invoice = corrective(rectified=(rectified(),))
    assert invoice.phase_type is None
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(invoice, phase_type=PhaseType.FULL)
    with pytest.raises(InvalidInvoiceError):
        invoice.with_guarantee(Guarantee(rate=Percentage.of("5"), due_date=TODAY))
    with pytest.raises(InvalidInvoiceError):
        dataclasses.replace(invoice, gross_amount=money("1.00"))


@pytest.mark.req("RN-F-03")
def test_una_rectificativa_es_inmutable_al_emitirla():
    issued = issue(corrective(line("-1.00"), rectified=(rectified(),)))
    assert isinstance(issued, CorrectiveInvoice)
    with pytest.raises(Exception, match="rectificativa"):
        issued.add_line(line("1.00"))
