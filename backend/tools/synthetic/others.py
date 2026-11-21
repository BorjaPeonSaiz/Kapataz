"""Documentos «otro» para la clasificación (RF-IN-02).

Ni facturas emitidas ni presupuestos del profesional: albaranes y facturas de
proveedores (una factura recibida también es «otro»), cartas de la comunidad,
hojas de pedido de una constructora y partes de trabajo del propio oficio.
"""

import random
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from kapataz.domain.billing.codes import RecipientType
from synthetic import fiscal
from synthetic.dates import business_day, long_date
from synthetic.formats import es_amount
from synthetic.model import (
    CatalogEntryData,
    CustomerData,
    LineData,
    OtherDocumentData,
    OtherKind,
    PartyData,
    ProfessionalData,
    Trade,
)
from synthetic.people import Identities, email

_CENT = Decimal("0.01")
# Precio de coste del material para el profesional, frente a su precio de venta.
_COST_FACTOR = Decimal("0.7")


def _plain_line(
    description: str,
    quantity: Decimal,
    unit: str,
    price: Decimal,
    vat_rate: Decimal | None,
) -> LineData:
    return LineData(
        description=description,
        quantity=quantity,
        unit=unit,
        unit_price=price,
        discount=None,
        is_material=False,
        outside_works=False,
        catalog_key=None,
        vat_rate=vat_rate,
    )


class OtherDocumentMaker:
    """Crea los documentos «otro» de un profesional con sus mismas fuentes de azar."""

    def __init__(
        self,
        *,
        rng: random.Random,
        ids: Identities,
        trade: Trade,
        catalog: Sequence[CatalogEntryData],
        professional: ProfessionalData,
        customers: Sequence[CustomerData],
        period: tuple[date, date],
    ) -> None:
        self.rng = rng
        self.ids = ids
        self.trade = trade
        self.catalog = {entry.key: entry for entry in catalog}
        self.professional = professional
        self.customers = customers
        self.period = period

    def make(self, kind: OtherKind) -> OtherDocumentData:
        start, end = self.period
        when = business_day(self.rng, start + timedelta(days=20), end - timedelta(days=5))
        match kind:
            case OtherKind.SUPPLIER_DELIVERY_NOTE:
                return self._delivery_note(when)
            case OtherKind.SUPPLIER_INVOICE:
                return self._supplier_invoice(when)
            case OtherKind.COMMUNITY_LETTER:
                return self._community_letter(when)
            case OtherKind.PURCHASE_ORDER:
                return self._purchase_order(when)
            case OtherKind.WORK_REPORT:
                return self._work_report(when)

    # ------------------------------------------------------------ partes

    def _me(self) -> PartyData:
        p = self.professional
        return PartyData(
            name=p.name,
            tax_id=p.tax_id,
            address=p.address,
            phone=p.phone,
            email=p.email,
        )

    def _supplier(self, prefix: str) -> PartyData:
        surname = self.ids.surname()
        return PartyData(
            name=f"{prefix} {surname} S.L.",
            tax_id=self.ids.cif("B"),
            address=self.ids.address(with_floor=False),
            phone=self.ids.phone(mobile=False),
            email=email(f"pedidos{surname}"),
        )

    def _material_lines(self, *, priced: bool) -> tuple[LineData, ...]:
        keys = [key for key, entry in self.catalog.items() if entry.is_material]
        lines: list[LineData] = []
        for key in self.rng.sample(keys, k=min(4, len(keys))):
            entry = self.catalog[key]
            per_pack = 50 if entry.unit == "m" else 1
            quantity = Decimal(self.rng.randint(2, 12) * per_pack)
            price = (entry.reference_price * _COST_FACTOR).quantize(_CENT, ROUND_HALF_UP)
            rate = fiscal.GENERAL_RATE if priced else None
            lines.append(_plain_line(entry.concept, quantity, entry.unit, price, rate))
        return tuple(lines)

    # ------------------------------------------------------------ documentos

    def _delivery_note(self, when: date) -> OtherDocumentData:
        prefix = (
            "Suministros Eléctricos"
            if self.trade is Trade.ELECTRICIAN
            else "Materiales de Construcción"
        )
        return OtherDocumentData(
            kind=OtherKind.SUPPLIER_DELIVERY_NOTE,
            title="ALBARÁN DE ENTREGA",
            reference=f"ALB-{when:%y}/{self.rng.randint(100, 9999):04d}",
            issue_date=when,
            issuer=self._supplier(prefix),
            recipient=self._me(),
            signatory=None,
            lines=self._material_lines(priced=False),
            priced=False,
            vat_rate=None,
            paragraphs=(
                "Mercancía entregada en obra. Revise el material antes de firmar.",
                "Recibí conforme: firma y DNI de quien recibe.",
            ),
        )

    def _supplier_invoice(self, when: date) -> OtherDocumentData:
        if self.trade is Trade.ELECTRICIAN:
            prefix = "Material Eléctrico"
            lines = self._material_lines(priced=True)
        else:
            prefix = "Contenedores"
            lines = (
                _plain_line(
                    "Alquiler de contenedor de 5 m³ con transporte y canon",
                    Decimal(self.rng.randint(2, 6)),
                    "ud",
                    Decimal("145.00"),
                    fiscal.GENERAL_RATE,
                ),
            )
        return OtherDocumentData(
            kind=OtherKind.SUPPLIER_INVOICE,
            title="FACTURA",
            reference=f"FV{when:%y}-{self.rng.randint(1000, 9999)}",
            issue_date=when,
            issuer=self._supplier(prefix),
            recipient=self._me(),
            signatory=None,
            lines=lines,
            priced=True,
            vat_rate=fiscal.GENERAL_RATE,
            paragraphs=("Forma de pago: recibo domiciliado a 30 días.",),
        )

    def _community_letter(self, when: date) -> OtherDocumentData:
        community = self.rng.choice(
            [c for c in self.customers if c.recipient_type is RecipientType.COMMUNITY],
        )
        admin = self.ids.person()
        office_name = f"Administración de Fincas {admin.split()[1]}"
        office = PartyData(
            name=office_name,
            tax_id=None,
            address=self.ids.address(),
            phone=self.ids.phone(mobile=False),
            email=email(f"administracion{admin.split()[1]}"),
        )
        visit = when + timedelta(days=self.rng.randint(7, 20))
        return OtherDocumentData(
            kind=OtherKind.COMMUNITY_LETTER,
            title="Comunicación a proveedores",
            reference=community.name,
            issue_date=when,
            issuer=office,
            recipient=self._me(),
            signatory=admin,
            lines=(),
            priced=False,
            vat_rate=None,
            paragraphs=(
                (
                    f"Le escribimos en nombre de la {community.name}, con domicilio en "
                    f"{community.address}."
                ),
                (
                    "En la última junta de propietarios se acordó revisar el alumbrado de "
                    "la escalera y del garaje, porque varios vecinos han avisado de que "
                    "algunos puntos de luz no encienden."
                ),
                (
                    f"Le rogamos que pase por el edificio el {long_date(visit)} por la "
                    "mañana; el presidente le abrirá el cuarto de contadores. Si no le "
                    "viene bien, llámenos para buscar otro día."
                ),
                (
                    "Le recordamos que cualquier trabajo que no sea la revisión necesita "
                    "un presupuesto aprobado por la junta antes de empezar."
                ),
            ),
        )

    def _purchase_order(self, when: date) -> OtherDocumentData:
        contractor = self.rng.choice([c for c in self.customers if c.is_contractor])
        lines = tuple(
            _plain_line(
                self.catalog[key].concept,
                Decimal(self.rng.randint(8, 40) * 10),
                self.catalog[key].unit,
                self.catalog[key].reference_price,
                None,
            )
            for key in ("tabique", "enfoscado", "recrecido")
        )
        total = sum((line.amount for line in lines), Decimal("0.00"))
        return OtherDocumentData(
            kind=OtherKind.PURCHASE_ORDER,
            title="HOJA DE PEDIDO DE SUBCONTRATACIÓN",
            reference=f"PED-{when:%Y}-{self.rng.randint(10, 400):03d}",
            issue_date=when,
            issuer=PartyData(
                name=contractor.name,
                tax_id=contractor.tax_id,
                address=contractor.address,
            ),
            recipient=self._me(),
            signatory=self.ids.person(),
            lines=lines,
            priced=True,
            vat_rate=None,
            paragraphs=(
                f"Importe máximo del pedido: {es_amount(total)} euros, IVA no incluido.",
                (
                    "Los trabajos se certificarán mensualmente según la medición real "
                    "aprobada por la jefatura de obra. Este pedido no es una factura."
                ),
            ),
        )

    def _work_report(self, when: date) -> OtherDocumentData:
        customer = self.rng.choice(list(self.customers))
        entry = self.catalog["oficial"]
        if self.trade is Trade.ELECTRICIAN:
            task, hours = "Localización de la avería y comprobación de circuitos", "2.5"
        else:
            task, hours = "Replanteo y ejecución de tabiquería en planta primera", "8"
        lines = (
            _plain_line(task, Decimal(hours), entry.unit, entry.reference_price, None),
            _plain_line(
                "Recogida y limpieza de la zona de trabajo",
                Decimal("0.5"),
                entry.unit,
                entry.reference_price,
                None,
            ),
        )
        return OtherDocumentData(
            kind=OtherKind.WORK_REPORT,
            title="PARTE DE TRABAJO",
            reference=f"PT-{self.rng.randint(10, 300):04d}",
            issue_date=when,
            issuer=self._me(),
            recipient=PartyData(
                name=customer.name,
                tax_id=customer.tax_id,
                address=customer.address,
            ),
            signatory=None,
            lines=lines,
            priced=False,
            vat_rate=None,
            paragraphs=(
                "Trabajo terminado. Las horas de este parte se facturarán a final de mes.",
                "Firma del cliente: conforme.",
            ),
        )
