"""Caso de uso IssueInvoice con la unidad de trabajo en memoria (arquitectura §7)."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from kapataz.application.ports.repositories import SeriesCounter
from kapataz.application.use_cases.issue_invoice import IssuedInvoice, IssueInvoice, fiscal_date
from kapataz.domain.billing.billing_record import RecordType, verify_chain
from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.errors import (
    InvalidInvoiceError,
    InvoiceAlreadyIssuedError,
    InvoiceNotFoundError,
    IssueDateBeforeLastError,
    MissingIssueDataError,
)
from kapataz.domain.billing.ids import InvoiceId
from kapataz.domain.billing.invoice import Invoice
from kapataz.domain.billing.money import Money
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.tax import TaxRate, VatTreatment
from kapataz.infrastructure.clock import FrozenClock
from kapataz.infrastructure.fiscal.null_submission import NullBillingRecordSubmission
from tests.billing_support import (
    ISSUER_TAX_ID,
    RECIPIENT_TAX_ID,
    SYSTEM,
    add_accepted_quote,
    add_customer,
    add_draft,
    add_draft_from_quote,
    create_account,
    issuable_drafts,
)
from tests.fakes.fiscal import FakeBillingRecordSubmission
from tests.fakes.memory_uow import MemoryUnitOfWorkFactory

NOW = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
REDUCED = VatTreatment.taxed(TaxRate.reduced())


class Scenario:
    def __init__(self, *, at: datetime = NOW) -> None:
        self.factory = MemoryUnitOfWorkFactory()
        self.clock = FrozenClock(at)
        self.submission = FakeBillingRecordSubmission()
        self.use_case = IssueInvoice(self.factory, self.clock, self.submission, SYSTEM)

    def issue(self, tenant_id, invoice_id) -> IssuedInvoice:
        return asyncio.run(self.use_case.execute(tenant_id, invoice_id))

    def run(self, coroutine):
        return asyncio.run(coroutine)

    def stored_invoice(self, tenant_id, invoice_id) -> Invoice | None:
        async def read():
            async with self.factory() as uow:
                await uow.set_tenant(tenant_id)
                return await uow.invoices.get(invoice_id)

        return asyncio.run(read())

    def chain(self, tenant_id):
        async def read():
            async with self.factory() as uow:
                await uow.set_tenant(tenant_id)
                return await uow.billing_chain.list_chain()

        return asyncio.run(read())

    def counters(self) -> dict:
        return dict(self.factory.state.counters)


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RF-FA-02")
def test_la_primera_emision_numera_f_2026_0001_y_la_deja_emitida():
    s = Scenario()
    tenant_id, [draft_id] = s.run(issuable_drafts(s.factory, 1))

    result = s.issue(tenant_id, draft_id)

    assert str(result.invoice.number) == "F-2026-0001"
    assert result.invoice.is_issued
    assert result.invoice.issue_date == date(2026, 11, 18)
    assert result.invoice.issued_at == NOW
    assert result.invoice.issuer is not None
    assert result.invoice.issuer.tax_id == ISSUER_TAX_ID
    assert result.invoice.recipient is not None
    assert result.invoice.recipient.tax_id == RECIPIENT_TAX_ID
    assert s.stored_invoice(tenant_id, draft_id) == result.invoice
    assert s.counters()[(tenant_id, "F", 2026)] == SeriesCounter(
        Series.invoices(), 2026, result.invoice.number, date(2026, 11, 18)
    )


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RF-FA-02")
def test_numeracion_correlativa_por_serie_y_por_ano():
    s = Scenario()
    tenant_id, drafts = s.run(issuable_drafts(s.factory, 3))

    numbers = [str(s.issue(tenant_id, draft_id).invoice.number) for draft_id in drafts[:2]]
    s.clock.advance(timedelta(days=60))  # 17/01/2027
    numbers.append(str(s.issue(tenant_id, drafts[2]).invoice.number))

    assert numbers == ["F-2026-0001", "F-2026-0002", "F-2027-0001"]


@pytest.mark.req("RN-F-01")
def test_cada_serie_tiene_su_contador():
    s = Scenario()
    tenant_id = s.run(create_account(s.factory))
    customer_id = s.run(add_customer(s.factory, tenant_id))
    invoice_draft = s.run(add_draft(s.factory, tenant_id, customer_id))
    other_series = s.run(add_draft(s.factory, tenant_id, customer_id, series=Series("OBRA")))

    assert str(s.issue(tenant_id, other_series).invoice.number) == "OBRA-2026-0001"
    assert str(s.issue(tenant_id, invoice_draft).invoice.number) == "F-2026-0001"


@pytest.mark.req("RN-F-01")
@pytest.mark.req("RN-10")
def test_cada_cuenta_numera_por_separado():
    s = Scenario()
    first_tenant, [first_draft] = s.run(issuable_drafts(s.factory, 1))
    second_tenant, [second_draft] = s.run(issuable_drafts(s.factory, 1))

    first = s.issue(first_tenant, first_draft)
    second = s.issue(second_tenant, second_draft)

    assert str(first.invoice.number) == str(second.invoice.number) == "F-2026-0001"
    assert first.record.is_first
    assert second.record.is_first


@pytest.mark.req("RN-F-01")
def test_la_fecha_de_expedicion_es_la_del_calendario_espanol():
    # 31/12/2026 a las 23:30 UTC ya es 1 de enero en Madrid: número del año 2027.
    s = Scenario(at=datetime(2026, 12, 31, 23, 30, tzinfo=UTC))
    tenant_id, [draft_id] = s.run(issuable_drafts(s.factory, 1))

    result = s.issue(tenant_id, draft_id)

    assert result.invoice.issue_date == date(2027, 1, 1)
    assert str(result.invoice.number) == "F-2027-0001"
    assert fiscal_date(datetime(2026, 7, 1, 22, 30, tzinfo=UTC)) == date(2026, 7, 2)


@pytest.mark.req("RN-F-04")
def test_fecha_anterior_a_la_ultima_de_la_serie_no_emite_ni_consume_numero():
    s = Scenario()
    tenant_id, [first, second] = s.run(issuable_drafts(s.factory, 2))
    s.issue(tenant_id, first)
    counters_before = s.counters()
    chain_before = s.chain(tenant_id)
    s.clock.advance(timedelta(days=-1))  # El reloj del servidor va hacia atrás.

    with pytest.raises(IssueDateBeforeLastError):
        s.issue(tenant_id, second)

    assert s.counters() == counters_before
    assert s.chain(tenant_id) == chain_before
    stored = s.stored_invoice(tenant_id, second)
    assert stored is not None
    assert not stored.is_issued
    assert s.submission.submitted == list(chain_before)


@pytest.mark.req("RN-F-04")
def test_rn_f_04_compara_con_la_ultima_de_la_serie_de_cualquier_ano():
    s = Scenario(at=datetime(2027, 1, 2, 10, 0, tzinfo=UTC))
    tenant_id, [first, second] = s.run(issuable_drafts(s.factory, 2))
    s.issue(tenant_id, first)
    s.clock.advance(timedelta(days=-3))  # 30/12/2026, contador de 2026 aún vacío.

    with pytest.raises(IssueDateBeforeLastError):
        s.issue(tenant_id, second)


@pytest.mark.req("RN-F-04")
def test_la_misma_fecha_que_la_ultima_si_se_admite():
    s = Scenario()
    tenant_id, [first, second] = s.run(issuable_drafts(s.factory, 2))
    s.issue(tenant_id, first)

    assert str(s.issue(tenant_id, second).invoice.number) == "F-2026-0002"


@pytest.mark.req("RN-F-06")
def test_faltan_datos_obligatorios_dice_todos_y_no_consume_numero():
    s = Scenario()
    tenant_id = s.run(create_account(s.factory, professional_address=None))
    customer_id = s.run(add_customer(s.factory, tenant_id, tax_id=None, address=None))
    draft_id = s.run(add_draft(s.factory, tenant_id, customer_id, description=None))

    with pytest.raises(MissingIssueDataError) as error:
        s.issue(tenant_id, draft_id)

    assert set(error.value.missing) == {
        "description",
        "issuer_address",
        "recipient_tax_id",
        "recipient_address",
    }
    assert s.counters() == {}
    assert s.chain(tenant_id) == ()
    assert s.submission.submitted == []


@pytest.mark.req("RN-F-06")
def test_sin_datos_del_profesional_no_se_emite():
    s = Scenario()
    tenant_id = s.run(create_account(s.factory, with_professional=False))
    customer_id = s.run(add_customer(s.factory, tenant_id))
    draft_id = s.run(add_draft(s.factory, tenant_id, customer_id))

    with pytest.raises(MissingIssueDataError) as error:
        s.issue(tenant_id, draft_id)

    assert error.value.missing == ("issuer_name", "issuer_tax_id", "issuer_address")


@pytest.mark.req("RN-F-07")
@pytest.mark.req("RF-VF-01")
def test_cada_emision_anade_un_registro_encadenado_a_la_cabeza():
    s = Scenario()
    tenant_id = s.run(create_account(s.factory))
    customer_id = s.run(add_customer(s.factory, tenant_id))
    invoice_draft = s.run(add_draft(s.factory, tenant_id, customer_id))
    other_series = s.run(add_draft(s.factory, tenant_id, customer_id, series=Series("OBRA")))

    first = s.issue(tenant_id, invoice_draft)
    s.clock.advance(timedelta(minutes=5))
    second = s.issue(tenant_id, other_series)

    chain = s.chain(tenant_id)
    assert chain == (first.record, second.record)
    verify_chain(chain)
    assert first.record.is_first
    assert second.record.previous == first.record.as_link()
    assert first.record.record_type is RecordType.REGISTRATION
    assert first.record.series_number == "F-2026-0001"
    assert first.record.invoice_id == invoice_draft
    assert s.factory.state.chain_heads[tenant_id] == second.record.id


@pytest.mark.req("RN-F-07")
def test_el_registro_lleva_los_importes_que_calcula_el_dominio():
    s = Scenario()
    tenant_id, [draft_id] = s.run(issuable_drafts(s.factory, 1))

    result = s.issue(tenant_id, draft_id)

    content = result.record.content()
    assert content["CuotaTotal"] == "262.50"
    assert content["ImporteTotal"] == "1512.50"
    assert result.invoice.totals.total_amount == Money.of("1512.50")


@pytest.mark.req("RN-F-07")
def test_bloquea_el_borrador_despues_la_cabeza_y_despues_el_contador():
    s = Scenario()
    tenant_id, [draft_id] = s.run(issuable_drafts(s.factory, 1))
    s.factory.lock_log.clear()

    s.issue(tenant_id, draft_id)

    assert s.factory.lock_log == [f"invoice:{draft_id}", "chain_head", "series_counter:F:2026"]


@pytest.mark.req("RF-VF-01")
def test_entrega_el_registro_al_puerto_de_envio():
    s = Scenario()
    tenant_id, [draft_id] = s.run(issuable_drafts(s.factory, 1))

    result = s.issue(tenant_id, draft_id)

    assert s.submission.submitted == [result.record]


@pytest.mark.req("RN-F-01")
def test_si_el_envio_falla_se_deshace_la_emision_entera():
    s = Scenario()
    tenant_id, [draft_id] = s.run(issuable_drafts(s.factory, 1))
    s.submission.error = RuntimeError("fallo simulado")

    with pytest.raises(RuntimeError, match="fallo simulado"):
        s.issue(tenant_id, draft_id)

    stored = s.stored_invoice(tenant_id, draft_id)
    assert stored is not None
    assert not stored.is_issued
    assert s.counters() == {}
    assert s.chain(tenant_id) == ()


@pytest.mark.req("RF-VF-01")
def test_con_el_adaptador_nulo_la_emision_funciona_igual():
    s = Scenario()
    use_case = IssueInvoice(s.factory, s.clock, NullBillingRecordSubmission(), SYSTEM)
    tenant_id, [draft_id] = s.run(issuable_drafts(s.factory, 1))

    result = asyncio.run(use_case.execute(tenant_id, draft_id))

    assert result.invoice.number == DocumentNumber(Series.invoices(), 2026, 1)
    assert s.chain(tenant_id) == (result.record,)


@pytest.mark.req("RN-10")
@pytest.mark.owasp("A01")
def test_un_borrador_de_otra_cuenta_no_existe():
    s = Scenario()
    _, [foreign_draft] = s.run(issuable_drafts(s.factory, 1))
    my_tenant = s.run(create_account(s.factory))

    with pytest.raises(InvoiceNotFoundError):
        s.issue(my_tenant, foreign_draft)

    assert s.counters() == {}


@pytest.mark.req("RN-F-02")
def test_una_factura_emitida_no_se_vuelve_a_emitir():
    s = Scenario()
    tenant_id, [draft_id] = s.run(issuable_drafts(s.factory, 1))
    s.issue(tenant_id, draft_id)

    with pytest.raises(InvoiceAlreadyIssuedError):
        s.issue(tenant_id, draft_id)

    assert len(s.chain(tenant_id)) == 1


@pytest.mark.req("RN-10")
def test_un_id_inexistente_no_existe():
    s = Scenario()
    tenant_id = s.run(create_account(s.factory))

    with pytest.raises(InvoiceNotFoundError):
        s.issue(tenant_id, InvoiceId(uuid4()))


# ------------------------------------------------- factura que sale de un presupuesto


def _from_quote(s: Scenario, treatment, recipient_type, dwelling):
    tenant_id = s.run(create_account(s.factory))
    customer_id = s.run(add_customer(s.factory, tenant_id))
    version = s.run(
        add_accepted_quote(
            s.factory,
            tenant_id,
            customer_id,
            recipient_type=recipient_type,
            dwelling_over_two_years=dwelling,
        )
    )
    draft_id = s.run(
        add_draft_from_quote(s.factory, tenant_id, customer_id, version, treatment=treatment)
    )
    return tenant_id, draft_id


@pytest.mark.req("RN-F-13")
@pytest.mark.req("RF-FA-02")
def test_desde_presupuesto_la_emitida_copia_destinatario_y_vivienda():
    s = Scenario()
    tenant_id, draft_id = _from_quote(s, REDUCED, RecipientType.PRIVATE, True)

    result = s.issue(tenant_id, draft_id)

    stored = s.stored_invoice(tenant_id, draft_id)
    assert stored == result.invoice
    assert stored is not None
    assert (stored.recipient_type, stored.dwelling_over_two_years) == (RecipientType.PRIVATE, True)
    assert stored.totals.tax == Money.of("100.00")


@pytest.mark.req("RN-F-13")
@pytest.mark.req("RN-F-01")
@pytest.mark.parametrize(
    ("treatment", "recipient_type", "dwelling", "message"),
    [
        (REDUCED, RecipientType.BUSINESS, None, "10 %"),
        (REDUCED, RecipientType.PRIVATE, False, "10 %"),
        (VatTreatment.reverse_charge(), RecipientType.PRIVATE, True, "inversión"),
    ],
)
def test_desde_presupuesto_un_tipo_que_no_admite_el_destinatario_no_se_emite(
    treatment, recipient_type, dwelling, message
):
    s = Scenario()
    tenant_id, draft_id = _from_quote(s, treatment, recipient_type, dwelling)

    with pytest.raises(InvalidInvoiceError, match=message):
        s.issue(tenant_id, draft_id)

    # Se deshace entero: ni número consumido ni registro (RN-F-01).
    stored = s.stored_invoice(tenant_id, draft_id)
    assert stored is not None
    assert not stored.is_issued
    assert s.counters() == {}
    assert s.chain(tenant_id) == ()
    assert s.submission.submitted == []
