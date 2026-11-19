"""Repositorios de negocio: todos trabajan en la cuenta fijada en la unidad de trabajo.

Cada método actúa solo sobre la cuenta fijada con ``UnitOfWork.set_tenant``
(ADR-024): el código filtra por cuenta y, además, RLS lo hace en la base de
datos. Llamarlos sin cuenta fijada es un error de programación. Un id de otra
cuenta se comporta como uno que no existe (``None``): la API responde 404.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from kapataz.domain.billing.billing_record import BillingRecord
from kapataz.domain.billing.ids import InvoiceId, QuoteId, QuoteVersionId
from kapataz.domain.billing.invoice import Invoice
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.payment import Payment
from kapataz.domain.billing.quote import Quote, QuoteVersion
from kapataz.domain.catalog.model import CatalogItem, CatalogItemId
from kapataz.domain.customers.model import Customer, CustomerId
from kapataz.domain.settings.professional import Professional


class TenantNotSetError(RuntimeError):
    """Se usó un repositorio de negocio sin fijar la cuenta en la transacción."""


class TenantMismatchError(RuntimeError):
    """Se intentó escribir una entidad de otra cuenta. Es un error de programación."""


@dataclass(frozen=True, slots=True)
class SeriesCounter:
    """Contador de una serie en un año (RN-F-01): último número y su fecha de expedición.

    ``last_number`` es None mientras no se ha emitido ninguna factura de la
    serie en ese año.
    """

    series: Series
    year: int
    last_number: DocumentNumber | None
    last_issue_date: date | None


class ProfessionalRepository(Protocol):
    async def get(self) -> Professional | None:
        """Datos del profesional de la cuenta, o None si aún no los ha dado."""
        ...

    async def save(self, professional: Professional) -> None:
        """Crea o sustituye la única fila de la cuenta."""
        ...


class CustomerRepository(Protocol):
    async def add(self, customer: Customer) -> None:
        """Lanza ``DuplicateCustomerTaxIdError`` si el NIF ya está en la cuenta."""
        ...

    async def get(self, customer_id: CustomerId) -> Customer | None: ...


class CatalogRepository(Protocol):
    async def add(self, item: CatalogItem) -> None: ...

    async def get(self, item_id: CatalogItemId) -> CatalogItem | None: ...


class QuoteRepository(Protocol):
    async def add(self, quote: Quote) -> None: ...

    async def get(self, quote_id: QuoteId) -> Quote | None: ...

    async def get_version(self, version_id: QuoteVersionId) -> QuoteVersion | None:
        """Una versión con sus líneas, sin el resto del presupuesto.

        La emisión de una factura que sale de un presupuesto la usa para copiar
        el tipo de destinatario y la vivienda (RN-F-13).
        """
        ...

    async def save(self, quote: Quote) -> None:
        """Guarda el estado y las versiones nuevas o la versión en borrador sustituida.

        Las versiones anteriores no cambian: solo la actual de un borrador se
        reescribe (``Quote.revise``).
        """
        ...


class InvoiceRepository(Protocol):
    async def add_draft(self, invoice: Invoice) -> None:
        """Una factura nace como borrador (RF-FA-02): solo admite borradores."""
        ...

    async def get(self, invoice_id: InvoiceId) -> Invoice | None:
        """Borrador o emitida, con sus líneas y, si es rectificativa, lo que rectifica."""
        ...

    async def get_for_update(self, invoice_id: InvoiceId) -> Invoice | None:
        """Como ``get``, bloqueando la fila hasta el final de la transacción.

        La emisión la usa para que nadie cambie las líneas del borrador mientras
        se numera y para que dos emisiones del mismo borrador no lo numeren dos
        veces.
        """
        ...

    async def save_draft(self, invoice: Invoice) -> None:
        """Sustituye un borrador. Una factura emitida no se toca (RN-F-02)."""
        ...

    async def delete_draft(self, invoice_id: InvoiceId) -> None:
        """Borra un borrador. Una emitida no se borra: se rectifica (RN-F-02)."""
        ...

    async def mark_issued(self, invoice: Invoice) -> None:
        """Pasa a emitida un borrador guardado: número, fechas, partes e importes."""
        ...


class PaymentRepository(Protocol):
    async def add(self, payment: Payment) -> None: ...

    async def list_for_invoice(self, invoice_id: InvoiceId) -> tuple[Payment, ...]: ...


class SeriesCounterRepository(Protocol):
    async def lock(self, series: Series, year: int) -> SeriesCounter:
        """Bloquea el contador de la serie y el año, y lo crea si no existe (RN-F-01).

        Lo crea sin carreras: dos emisiones simultáneas no crean dos contadores.
        Se llama después de bloquear la cabeza de la cadena (RN-F-07).
        """
        ...

    async def last_issue_date(self, series: Series) -> date | None:
        """Fecha de la última factura emitida de la serie, de cualquier año (RN-F-04).

        Solo es fiable con la cabeza de la cadena bloqueada, que impide
        cualquier otra emisión de la cuenta mientras tanto.
        """
        ...

    async def save(self, counter: SeriesCounter) -> None:
        """Guarda el contador bloqueado con ``lock`` en la misma transacción."""
        ...


class BillingChainRepository(Protocol):
    """La cadena única de registros de facturación de la cuenta (RN-F-07)."""

    async def lock_head(self) -> BillingRecord | None:
        """Bloquea la cabeza de la cadena y devuelve el último registro (None si está vacía).

        Crea la cabeza si no existe, sin carreras. Toda operación que añade un
        registro la llama antes que nada más y antes de bloquear el contador.
        """
        ...

    async def append(self, record: BillingRecord) -> None:
        """Añade el registro detrás del último y mueve la cabeza a él.

        Exige la cabeza bloqueada con ``lock_head`` en la misma transacción.
        Guarda el contenido canónico y la huella tal como vienen del dominio.
        """
        ...

    async def list_chain(self) -> tuple[BillingRecord, ...]:
        """La cadena completa de la cuenta, del primer registro al último."""
        ...
