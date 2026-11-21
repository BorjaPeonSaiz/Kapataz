"""API de datos del generador: ``build_dataset(seed)`` sin E/S (ADR-020, RF-CF-04).

El periodo es fijo (``PERIOD_START`` a ``PERIOD_END``, 18 meses) y todo el azar
sale de ``random.Random`` y de Faker sembrados con la semilla: la misma semilla
produce el mismo dataset en cualquier máquina con las mismas versiones fijadas.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from faker import Faker

from kapataz.domain.billing.codes import RecipientType
from kapataz.domain.billing.numbering import DocumentNumber, Series
from kapataz.domain.billing.quote import QuoteStatus
from synthetic import fiscal
from synthetic.catalogs import CATALOGS, ELECTRICIAN_OUTSIDE_WORKS, JOBS, JobTemplate, TemplateItem
from synthetic.dates import business_day
from synthetic.model import (
    CatalogEntryData,
    CustomerData,
    InvoiceData,
    LineData,
    OtherKind,
    ProfessionalData,
    ProfessionalDataset,
    QuoteData,
    SeededErrorKind,
    SyntheticDataset,
    Trade,
    TrapTechnique,
)
from synthetic.others import OtherDocumentMaker
from synthetic.people import Identities, email
from synthetic.planning import DocumentPlanner, PlanSettings, TrapPlan

DEFAULT_SEED = 20251120
PERIOD_START = date(2025, 1, 1)
PERIOD_END = date(2026, 6, 30)
QUOTE_VALIDITY_DAYS = 30

_CENT = Decimal("0.01")
_HALF = Decimal("0.5")
_SECOND_YEAR_RAISE = Decimal("1.03")
# Desde este precio de referencia, un servicio se cobra en múltiplos de 0,50 €.
_ROUND_SERVICE_FROM = Decimal(20)
_MIN_STANDALONE_INVOICES = 8
# ADR-020: de 40 a 60 facturas por profesional.
_MAX_INVOICES = 60
_SPARE_JOBS = 60
# Probabilidades en tanto por ciento.
_DWELLING_OVER_TWO_YEARS = 92
_DISCOUNT_CHANCE = 15
_ACCEPTED = 60
_REJECTED_UP_TO = 80
_ADDITIONAL_WORK = 30
_TWO_PARTS = 2
# Con menos de diez unidades, una línea va entera en la última certificación.
_MIN_SPLIT_QUANTITY = 10


@dataclass(frozen=True, slots=True, kw_only=True)
class _CustomerPlan:
    privates: int
    communities: int
    businesses: tuple[str, ...]
    contractors: tuple[str, ...]
    weights: dict[str, int]
    home_town: int


@dataclass(frozen=True, slots=True, kw_only=True)
class _TradeProfile:
    trade: Trade
    invoice_series: str
    quote_series: str
    quotes: tuple[int, int]
    invoices: tuple[int, int]
    customers: _CustomerPlan
    detailed_jobs: tuple[str, ...]
    others: tuple[OtherKind, ...]
    traps: tuple[TrapPlan, ...]
    outside_works_invoices: int


# Unos 9 documentos con imperfección de unos 80 por profesional (el 11 %).
_ERRORS = (
    (SeededErrorKind.SPLIT_LINE, 2),
    (SeededErrorKind.TOTAL_MISMATCH, 2),
    (SeededErrorKind.VAT_MISMATCH, 2),
    (SeededErrorKind.BASE_MISMATCH, 1),
    (SeededErrorKind.MISSING_TAX_ID, 2),
)

PROFILES = (
    _TradeProfile(
        trade=Trade.ELECTRICIAN,
        invoice_series="F",
        quote_series="P",
        quotes=(22, 28),
        invoices=(46, 56),
        customers=_CustomerPlan(
            privates=9,
            communities=4,
            businesses=("Cafetería", "Talleres", "Panadería", "Gestoría"),
            contractors=(),
            weights={"private": 50, "community": 25, "business": 25},
            home_town=0,
        ),
        detailed_jobs=(
            "Renovación completa de la instalación eléctrica de la vivienda",
            "Renovación completa de la instalación eléctrica de la vivienda",
            "Instalación eléctrica de local comercial",
        ),
        others=(
            OtherKind.SUPPLIER_DELIVERY_NOTE,
            OtherKind.SUPPLIER_INVOICE,
            OtherKind.COMMUNITY_LETTER,
            OtherKind.WORK_REPORT,
        ),
        traps=(TrapPlan(TrapTechnique.VISIBLE_FOOTER), TrapPlan(TrapTechnique.LINE_CONCEPT)),
        outside_works_invoices=3,
    ),
    _TradeProfile(
        trade=Trade.BRICKLAYER,
        invoice_series="FA",
        quote_series="PA",
        quotes=(22, 28),
        invoices=(46, 56),
        customers=_CustomerPlan(
            privates=3,
            communities=1,
            businesses=("Clínica Dental",),
            contractors=("Construcciones", "Promociones", "Edificaciones", "Obras y Proyectos"),
            weights={"contractor": 70, "private": 18, "community": 6, "business": 6},
            home_town=4,
        ),
        detailed_jobs=(
            "Obra de albañilería de edificio de viviendas",
            "Obra de albañilería de edificio de viviendas",
            "Reforma integral de vivienda",
        ),
        others=(
            OtherKind.SUPPLIER_DELIVERY_NOTE,
            OtherKind.SUPPLIER_INVOICE,
            OtherKind.PURCHASE_ORDER,
            OtherKind.WORK_REPORT,
        ),
        traps=(
            TrapPlan(TrapTechnique.HIDDEN_TEXT),
            # La instrucción en el pie de un escaneado: solo se lee por OCR.
            TrapPlan(TrapTechnique.VISIBLE_FOOTER, scanned=True),
            TrapPlan(TrapTechnique.METADATA),
        ),
        outside_works_invoices=0,
    ),
)


def build_dataset(seed: int = DEFAULT_SEED) -> SyntheticDataset:
    """Dataset completo de los dos profesionales. Puro: ni E/S ni reloj."""
    return SyntheticDataset(
        seed=seed,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        professionals=tuple(_Builder(seed, profile).build() for profile in PROFILES),
    )


def canonical_quantity(value: Decimal) -> Decimal:
    """Cantidad sin ceros sobrantes ni notación científica: 121.0 → 121, 2.50 → 2.5."""
    if value == value.to_integral_value():
        return value.quantize(Decimal(1))
    return value.normalize()


@dataclass(slots=True)
class _Job:
    """Trabajo planificado antes de numerar: un presupuesto o una factura suelta."""

    customer: CustomerData
    template: JobTemplate
    issue_date: date
    dwelling_over_two_years: bool | None
    lines: tuple[LineData, ...] = field(default=())


@dataclass(frozen=True, slots=True)
class _QuotedJob:
    job: _Job
    quote: QuoteData


class _Builder:
    """Construye la actividad de un profesional con su propio generador de azar."""

    def __init__(self, seed: int, profile: _TradeProfile) -> None:
        self.profile = profile
        self.trade = profile.trade
        self.rng = random.Random(f"kapataz-synthetic:{seed}:{profile.trade.value}")  # noqa: S311
        fake = Faker("es_ES")
        fake.seed_instance(self.rng.getrandbits(32))
        self.ids = Identities(self.rng, fake)
        self.catalog = {entry.key: entry for entry in CATALOGS[self.trade]}

    def build(self) -> ProfessionalDataset:
        professional = self._professional()
        customers = self._customers()
        quote_jobs, invoice_jobs, required = self._plan_jobs(customers)
        quoted = self._number_quotes(quote_jobs, professional)
        quotes, derived = self._resolve_quotes(quoted)
        standalone = self._standalone_invoices(invoice_jobs, len(derived), required)
        invoices = self._number_invoices([*derived, *standalone], professional)
        customers = self._with_since(customers, quotes, invoices)
        maker = OtherDocumentMaker(
            rng=self.rng,
            ids=self.ids,
            trade=self.trade,
            catalog=CATALOGS[self.trade],
            professional=professional,
            customers=customers,
            period=(PERIOD_START, PERIOD_END),
        )
        others = tuple(maker.make(kind) for kind in self.profile.others)
        settings = PlanSettings(trade=self.trade, traps=self.profile.traps, errors=_ERRORS)
        documents = DocumentPlanner(self.rng, settings).plan(quotes, invoices, others)
        return ProfessionalDataset(
            professional=professional,
            customers=customers,
            catalog=CATALOGS[self.trade],
            quotes=quotes,
            invoices=invoices,
            documents=documents,
        )

    # ------------------------------------------------------------ personas

    def _professional(self) -> ProfessionalData:
        name = self.ids.person()
        surname = name.split()[-2]
        if self.trade is Trade.ELECTRICIAN:
            trade_name = f"Electricidad {surname}"
            activity = "Instalaciones eléctricas de baja tensión"
        else:
            trade_name = f"Reformas y Albañilería {surname}"
            activity = "Albañilería y pequeños trabajos de construcción"
        return ProfessionalData(
            trade=self.trade,
            name=name,
            trade_name=trade_name,
            activity=activity,
            tax_id=self.ids.dni(),
            address=self.ids.address(self.ids.town(self.profile.customers.home_town)),
            phone=self.ids.phone(mobile=True),
            email=email(trade_name),
            iban=self.ids.iban(),
            invoice_series=self.profile.invoice_series,
            quote_series=self.profile.quote_series,
        )

    def _customers(self) -> tuple[CustomerData, ...]:
        plan = self.profile.customers
        found: list[CustomerData] = []

        def add(name: str, tax_id: str, address: str, kind: RecipientType, *, builds: bool) -> None:
            found.append(
                CustomerData(
                    key=f"{self.trade.value}-c{len(found) + 1:02d}",
                    name=name,
                    tax_id=tax_id,
                    address=address,
                    recipient_type=kind,
                    is_contractor=builds,
                    since=PERIOD_START,
                ),
            )

        business = RecipientType.BUSINESS
        for prefix in plan.contractors:
            add(
                self.ids.company(prefix),
                self.ids.cif("B"),
                self.ids.address(),
                business,
                builds=True,
            )
        if plan.contractors:
            # Dos constructoras de nombre casi igual (RF-CO-05).
            similar = f"Construcciones y Reformas {found[0].name.split()[1]} S.L."
            add(similar, self.ids.cif("B"), self.ids.address(), business, builds=True)
        private = RecipientType.PRIVATE
        for _ in range(plan.privates):
            add(self.ids.person(), self.ids.dni(), self.ids.address(), private, builds=False)
        # Dos particulares con el mismo nombre y distinto NIF (RF-CO-05).
        twin = next(item for item in found if item.recipient_type is private)
        add(twin.name, self.ids.dni(), self.ids.address(), private, builds=False)
        for name, address in self._communities(plan.communities):
            add(name, self.ids.cif("H"), address, RecipientType.COMMUNITY, builds=False)
        for prefix in plan.businesses:
            address = self.ids.address(with_floor=False)
            add(self.ids.company(prefix), self.ids.cif("B"), address, business, builds=False)
        return tuple(found)

    def _communities(self, count: int) -> list[tuple[str, str]]:
        """Nombre y domicilio; las dos primeras, en la misma calle con 14 y 41 (RF-CO-05)."""
        shared = self.ids.street()
        number = self.rng.randint(12, 39)
        # Ni 20 (daría 2) ni 22 (daría el mismo número): otra cifra.
        if number % 10 == 0 or number % 11 == 0:
            number += 1
        similar = [(shared, number), (shared, int(str(number)[::-1]))]
        found: list[tuple[str, str]] = []
        for index in range(count):
            if index < len(similar):
                street_name, street_number = similar[index]
                town = self.ids.town(0)
            else:
                street_name, street_number = self.ids.street(), self.rng.randint(1, 90)
                town = self.ids.town()
            address = f"{street_name}, {street_number}, {town.postal_code} {town.name} (Cantabria)"
            found.append((f"Comunidad de Propietarios {street_name} {street_number}", address))
        return found

    # ------------------------------------------------------------ trabajos

    def _plan_jobs(
        self,
        customers: Sequence[CustomerData],
    ) -> tuple[list[_Job], list[_Job], int]:
        """Presupuestos (primero los detallados) y trabajos sin presupuesto.

        Cada cliente sale al menos una vez: los trabajos que lo garantizan van
        delante en la lista de facturas sueltas, que se recorta por el final, y
        se devuelve cuántos son para no recortarlos.
        """
        n_quotes = self.rng.randint(*self.profile.quotes)
        detailed = [
            self._detailed_job(subject, customers) for subject in self.profile.detailed_jobs
        ]
        used = {job.customer.key for job in detailed}
        coverage = [self._job(c) for c in customers if c.key not in used]
        extra = [self._job(self._weighted_customer(customers)) for _ in range(_SPARE_JOBS)]
        mixed = coverage + extra
        self.rng.shuffle(mixed)
        n_plain_quotes = n_quotes - len(detailed)
        quote_jobs = detailed + mixed[:n_plain_quotes]
        rest = mixed[n_plain_quotes:]
        first = {id(job) for job in coverage}
        rest.sort(key=lambda job: id(job) not in first)
        return quote_jobs, rest, sum(id(job) in first for job in rest)

    def _group(self, customer: CustomerData) -> str:
        return "contractor" if customer.is_contractor else customer.recipient_type.value

    def _weighted_customer(self, customers: Sequence[CustomerData]) -> CustomerData:
        weights = self.profile.customers.weights
        groups = sorted(weights)
        group = self.rng.choices(groups, weights=[weights[g] for g in groups])[0]
        return self.rng.choice([c for c in customers if self._group(c) == group])

    def _detailed_job(self, subject: str, customers: Sequence[CustomerData]) -> _Job:
        template = next(t for t in JOBS[self.trade] if t.subject == subject)
        customer = self.rng.choice([c for c in customers if _fits(template, c)])
        # Los detallados empiezan pronto para que dé tiempo a certificarlos.
        when = business_day(self.rng, PERIOD_START, PERIOD_START + timedelta(days=300))
        return self._job(customer, template=template, when=when)

    def _job(
        self,
        customer: CustomerData,
        *,
        template: JobTemplate | None = None,
        when: date | None = None,
    ) -> _Job:
        if template is None:
            options = [t for t in JOBS[self.trade] if not t.detailed and _fits(t, customer)]
            template = self.rng.choice(options)
        dwelling = None
        if customer.recipient_type in {RecipientType.PRIVATE, RecipientType.COMMUNITY}:
            dwelling = self.rng.randint(1, 100) <= _DWELLING_OVER_TWO_YEARS
        issue = when or business_day(self.rng, PERIOD_START, PERIOD_END - timedelta(days=12))
        job = _Job(customer, template, issue, dwelling)
        job.lines = self._lines(job)
        return job

    def _lines(self, job: _Job) -> tuple[LineData, ...]:
        raw = [
            self._line(item, job)
            for item in job.template.items
            if self.rng.randint(1, 100) <= item.chance
        ]
        if not raw:
            raw.append(self._line(job.template.items[0], job))
        return self._with_rates(raw, job)

    def _with_rates(self, lines: Sequence[LineData], job: _Job) -> tuple[LineData, ...]:
        """Tipo de cada línea: el de la obra entera, decidido por el dominio (RN-F-13)."""
        reverse = fiscal.applies_reverse_charge(
            self.trade, is_contractor=job.customer.is_contractor
        )
        works = fiscal.works_rate(
            [line for line in lines if not line.outside_works],
            job.customer.recipient_type,
            dwelling_over_two_years=job.dwelling_over_two_years,
        )
        return tuple(
            replace(
                line,
                vat_rate=fiscal.line_rate(
                    outside_works=line.outside_works,
                    works=works,
                    reverse_charge=reverse,
                ),
            )
            for line in lines
        )

    def _line(self, item: TemplateItem, job: _Job) -> LineData:
        entry = self.catalog[item.key]
        description = entry.concept
        if job.template.detailed:
            description = f"{entry.concept}. {entry.detail}"
        return LineData(
            description=description,
            quantity=self._quantity(item),
            unit=entry.unit,
            unit_price=self._price(entry, job.issue_date),
            discount=self._discount(entry, job.customer),
            is_material=entry.is_material and not item.outside_works,
            outside_works=item.outside_works,
            catalog_key=entry.key,
            vat_rate=None,
        )

    def _quantity(self, item: TemplateItem) -> Decimal:
        low, high, step = Decimal(item.low), Decimal(item.high), Decimal(item.step)
        steps = int((high - low) / step)
        return canonical_quantity(low + step * self.rng.randint(0, steps))

    def _price(self, entry: CatalogEntryData, when: date) -> Decimal:
        """Precio de referencia con una variación de -8 % a +10 % y la subida del segundo año."""
        factor = Decimal(self.rng.randint(920, 1100)) / 1000
        if when.year > PERIOD_START.year:
            factor *= _SECOND_YEAR_RAISE
        raw = entry.reference_price * factor
        is_service = not entry.is_material and entry.reference_price >= _ROUND_SERVICE_FROM
        if entry.unit == "h" or is_service:
            # La mano de obra y los servicios se cobran en múltiplos de 0,50 €.
            return ((raw / _HALF).quantize(Decimal(1), ROUND_HALF_UP) * _HALF).quantize(_CENT)
        return raw.quantize(_CENT, ROUND_HALF_UP)

    def _discount(self, entry: CatalogEntryData, customer: CustomerData) -> Decimal | None:
        """Descuento en parte del material a empresas y comunidades."""
        if not entry.is_material or customer.recipient_type is RecipientType.PRIVATE:
            return None
        if self.rng.randint(1, 100) > _DISCOUNT_CHANCE:
            return None
        return Decimal(self.rng.choice((5, 10, 15)))

    # ------------------------------------------------------------ presupuestos

    def _number_quotes(self, jobs: list[_Job], professional: ProfessionalData) -> list[_QuotedJob]:
        jobs = sorted(jobs, key=lambda job: job.issue_date)
        numbers = _numbers(professional.quote_series, [job.issue_date for job in jobs])
        quoted: list[_QuotedJob] = []
        for job, number in zip(jobs, numbers, strict=True):
            quote = QuoteData(
                number=number,
                customer_key=job.customer.key,
                issue_date=job.issue_date,
                valid_until=job.issue_date + timedelta(days=QUOTE_VALIDITY_DAYS),
                status=QuoteStatus.SENT,
                recipient_type=job.customer.recipient_type,
                dwelling_over_two_years=job.dwelling_over_two_years,
                subject=job.template.subject,
                lines=job.lines,
                reverse_charge=fiscal.applies_reverse_charge(
                    self.trade,
                    is_contractor=job.customer.is_contractor,
                ),
                detailed=job.template.detailed,
            )
            quoted.append(_QuotedJob(job, quote))
        return quoted

    def _resolve_quotes(
        self,
        quoted: list[_QuotedJob],
    ) -> tuple[tuple[QuoteData, ...], list[InvoiceData]]:
        """Estado de cada presupuesto al final del periodo y las facturas que salen de él."""
        quotes: list[QuoteData] = []
        invoices: list[InvoiceData] = []
        for item in quoted:
            quote, derived = self._resolve(item)
            quotes.append(quote)
            invoices.extend(derived)
        return tuple(quotes), invoices

    def _resolve(self, item: _QuotedJob) -> tuple[QuoteData, list[InvoiceData]]:
        """Un 60 % se acepta (los detallados, siempre); del resto, la mitad se rechaza."""
        quote = item.quote
        roll = self.rng.randint(1, 100)
        if not quote.detailed and roll > _ACCEPTED:
            if roll <= _REJECTED_UP_TO:
                status = QuoteStatus.REJECTED
            elif quote.valid_until < PERIOD_END:
                status = QuoteStatus.EXPIRED
            else:
                status = QuoteStatus.SENT
            return replace(quote, status=status), []
        if item.job.customer.is_contractor:
            invoices, planned = self._certifications(item)
        else:
            invoices, planned = self._single_invoice(item), 1
        if not invoices:
            return replace(quote, status=QuoteStatus.ACCEPTED), []
        done = len(invoices) == planned
        status = QuoteStatus.INVOICED if done else QuoteStatus.PARTIALLY_INVOICED
        return replace(quote, status=status), invoices

    def _single_invoice(self, item: _QuotedJob) -> list[InvoiceData]:
        """La factura de un presupuesto aceptado; en el 30 %, con trabajo adicional."""
        when = business_day(
            self.rng,
            item.quote.issue_date + timedelta(days=10),
            item.quote.issue_date + timedelta(days=40),
        )
        if when > PERIOD_END:
            return []
        lines = item.quote.lines
        if self.rng.randint(1, 100) <= _ADDITIONAL_WORK:
            extra = self._line(TemplateItem("oficial", "1", "4", "0.5"), item.job)
            text = f"Trabajos adicionales no presupuestados: {extra.description.lower()}"
            lines = self._with_rates([*lines, replace(extra, description=text)], item.job)
        return [self._invoice(item.job, when, lines, quote_number=item.quote.number)]

    def _certifications(self, item: _QuotedJob) -> tuple[list[InvoiceData], int]:
        """Certificaciones mensuales de una obra para constructora, y cuántas se planearon."""
        parts = self.rng.randint(2, 3)
        shares = _shares(self.rng, parts)
        split = [_partition(line, shares) for line in item.quote.lines]
        guarantee = fiscal.GUARANTEE_RATE if self.rng.randint(1, 2) == 1 else None
        invoices: list[InvoiceData] = []
        start = item.quote.issue_date + timedelta(days=25)
        for index in range(parts):
            first = start + timedelta(days=30 * index)
            when = business_day(self.rng, first, first + timedelta(days=4))
            if when > PERIOD_END:
                break
            lines = tuple(chunk for chunks in split if (chunk := chunks[index]) is not None)
            invoices.append(
                self._invoice(
                    item.job,
                    when,
                    lines,
                    quote_number=item.quote.number,
                    subject=f"Certificación n.º {index + 1} de la obra «{item.quote.subject}»",
                    guarantee=guarantee,
                ),
            )
        return invoices, parts

    # ------------------------------------------------------------ facturas

    def _invoice(
        self,
        job: _Job,
        when: date,
        lines: Sequence[LineData],
        *,
        quote_number: str | None,
        subject: str | None = None,
        guarantee: Decimal | None = None,
    ) -> InvoiceData:
        customer = job.customer
        days = 60 if customer.recipient_type is RecipientType.BUSINESS else 15
        return InvoiceData(
            number="",
            customer_key=customer.key,
            issue_date=when,
            due_date=when + timedelta(days=days),
            subject=subject or job.template.subject,
            lines=tuple(lines),
            reverse_charge=fiscal.applies_reverse_charge(
                self.trade,
                is_contractor=customer.is_contractor,
            ),
            withholding_rate=fiscal.withholding_rate(self.trade, customer.recipient_type),
            guarantee_rate=guarantee,
            quote_number=quote_number,
            recipient_type=customer.recipient_type,
            dwelling_over_two_years=job.dwelling_over_two_years,
            detailed=job.template.detailed,
        )

    def _standalone_invoices(
        self,
        jobs: list[_Job],
        derived: int,
        required: int,
    ) -> list[InvoiceData]:
        """Facturas sin presupuesto hasta llegar al objetivo; algunas, con dos tipos."""
        target = self.rng.randint(*self.profile.invoices)
        # Si las certificaciones ya llenan el objetivo, se superan unas pocas.
        count = max(target - derived, _MIN_STANDALONE_INVOICES, required)
        if derived + count > _MAX_INVOICES or count > len(jobs):
            msg = f"Plan de facturas imposible: {derived} de presupuestos y objetivo {target}."
            raise ValueError(msg)
        invoices: list[InvoiceData] = []
        outside_left = self.profile.outside_works_invoices
        for job in jobs[:count]:
            lines = job.lines
            if outside_left and _takes_outside_line(job):
                outside_left -= 1
                extra = self._line(ELECTRICIAN_OUTSIDE_WORKS, job)
                lines = self._with_rates([*job.lines, extra], job)
            invoices.append(self._invoice(job, job.issue_date, lines, quote_number=None))
        return invoices

    def _number_invoices(
        self,
        invoices: list[InvoiceData],
        professional: ProfessionalData,
    ) -> tuple[InvoiceData, ...]:
        ordered = sorted(invoices, key=lambda invoice: invoice.issue_date)
        numbers = _numbers(professional.invoice_series, [i.issue_date for i in ordered])
        return tuple(replace(i, number=n) for i, n in zip(ordered, numbers, strict=True))

    def _with_since(
        self,
        customers: tuple[CustomerData, ...],
        quotes: Sequence[QuoteData],
        invoices: Sequence[InvoiceData],
    ) -> tuple[CustomerData, ...]:
        """Fecha de alta: unos días antes del primer documento del cliente."""
        first: dict[str, date] = {}
        issued = [(q.customer_key, q.issue_date) for q in quotes]
        issued += [(i.customer_key, i.issue_date) for i in invoices]
        for key, when in issued:
            if key not in first or when < first[key]:
                first[key] = when
        missing = [c.key for c in customers if c.key not in first]
        if missing:
            msg = f"Clientes sin documentos: {missing}"
            raise ValueError(msg)
        return tuple(
            replace(c, since=first[c.key] - timedelta(days=self.rng.randint(0, 20)))
            for c in customers
        )


def _fits(template: JobTemplate, customer: CustomerData) -> bool:
    return (
        customer.recipient_type in template.recipients
        and template.contractor == customer.is_contractor
    )


def _takes_outside_line(job: _Job) -> bool:
    """Particular con la obra al 10 %: se le vende algo al 21 % en la misma factura."""
    return job.customer.recipient_type is RecipientType.PRIVATE and all(
        line.vat_rate == fiscal.REDUCED_RATE for line in job.lines
    )


def _numbers(series: str, dates: Sequence[date]) -> list[str]:
    """Números correlativos por serie y año, en orden de fecha (RN-F-01)."""
    counters: dict[int, int] = {}
    numbers: list[str] = []
    for when in dates:
        counters[when.year] = counters.get(when.year, 0) + 1
        numbers.append(str(DocumentNumber(Series(series), when.year, counters[when.year])))
    return numbers


def _shares(rng: random.Random, parts: int) -> list[int]:
    """Porcentaje de la obra que mide cada certificación salvo la última."""
    if parts == _TWO_PARTS:
        return [rng.randint(40, 60)]
    return [rng.randint(25, 40), rng.randint(25, 40)]


_WHOLE_UNITS = frozenset({"pa", "ud", "semana"})


def _partition(line: LineData, shares: Sequence[int]) -> list[LineData | None]:
    """Reparte la cantidad de una línea entre las certificaciones; la última, el resto."""
    if line.unit in _WHOLE_UNITS or line.quantity < _MIN_SPLIT_QUANTITY:
        return [*([None] * len(shares)), line]
    chunks: list[LineData | None] = []
    used = Decimal(0)
    for share in shares:
        part = (line.quantity * share / 100).quantize(_CENT, ROUND_HALF_UP)
        used += part
        chunks.append(replace(line, quantity=canonical_quantity(part)))
    chunks.append(replace(line, quantity=canonical_quantity(line.quantity - used)))
    return chunks
