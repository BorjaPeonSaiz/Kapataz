"""Tipo de IVA y tratamiento fiscal de una factura (RF-FA-05, RN-F-05, RN-F-13).

Una factura emitida por la app lleva un solo tratamiento de IVA (RN-F-13): un
``VatTreatment``, no uno por línea.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import ClassVar, Self

from kapataz.domain.billing.errors import InvalidTaxRateError


@dataclass(frozen=True, slots=True)
class TaxRate:
    """Tipo de IVA: general (21 %), reducido (10 %) o superreducido (4 %), RF-FA-05.

    Es una lista cerrada a propósito: un 18 % o un 7 % no son un tipo vigente y
    solo pueden venir de un error. Si cambian los tipos, se cambia esta lista.
    """

    percent: Decimal

    ALLOWED: ClassVar[frozenset[Decimal]] = frozenset(
        {Decimal(21), Decimal(10), Decimal(4)},
    )

    def __post_init__(self) -> None:
        if type(self.percent) is not Decimal:
            msg = f"TaxRate solo admite Decimal, no {type(self.percent).__name__} (RN-01)."
            raise TypeError(msg)
        if not self.percent.is_finite() or self.percent not in self.ALLOWED:
            raise InvalidTaxRateError("Tipo de IVA no admitido: solo 21 %, 10 % o 4 %.")
        # Normalizado sin decimales para que 21 y 21.00 se escriban igual.
        object.__setattr__(self, "percent", self.percent.quantize(Decimal(1)))

    @classmethod
    def general(cls) -> Self:
        return cls(Decimal(21))

    @classmethod
    def reduced(cls) -> Self:
        return cls(Decimal(10))

    @classmethod
    def super_reduced(cls) -> Self:
        return cls(Decimal(4))

    def as_fraction(self) -> Fraction:
        return Fraction(self.percent) / 100

    def __str__(self) -> str:
        return str(self.percent)


class OperationClass(StrEnum):
    """Calificación de la operación del registro de la AEAT (CalificacionOperacion).

    S1: sujeta y no exenta, sin inversión. S2: sujeta y no exenta, con inversión
    del sujeto pasivo. N1 y N2 (no sujetas) existen en la base de datos, pero la
    v1 no las emite: ``VatTreatment`` las rechaza.
    """

    S1 = "S1"
    S2 = "S2"
    N1 = "N1"
    N2 = "N2"


class RegimeKey(StrEnum):
    """Clave de régimen del registro de la AEAT (ClaveRegimen).

    La v1 solo emite en régimen general (01). Las demás claves se añadirán
    cuando haya un caso que las necesite.
    """

    GENERAL = "01"


# RD 1619/2012, art. 6.1.m: la factura lleva literalmente esta mención (RN-F-05).
REVERSE_CHARGE_MENTION = "Inversión del sujeto pasivo"


@dataclass(frozen=True, slots=True)
class VatTreatment:
    """Cómo tributa una factura: con IVA repercutido o con inversión del sujeto pasivo.

    Con inversión (S2) la cuota es cero (RN-F-05) y no hay tipo que aplicar, así
    que ``rate`` es None. Con S1 el tipo es obligatorio. N1 y N2 no se admiten
    en la v1. Así no puede existir un tratamiento sin tipo que cobre IVA, ni uno
    con inversión que lo cobre.
    """

    operation_class: OperationClass
    rate: TaxRate | None

    def __post_init__(self) -> None:
        match self.operation_class:
            case OperationClass.S1 if self.rate is None:
                raise InvalidTaxRateError("Una operación sujeta (S1) necesita su tipo de IVA.")
            case OperationClass.S2 if self.rate is not None:
                raise InvalidTaxRateError("Con inversión del sujeto pasivo no se aplica tipo.")
            case OperationClass.N1 | OperationClass.N2:
                raise InvalidTaxRateError("La v1 no emite operaciones no sujetas.")
            case _:
                pass

    @classmethod
    def taxed(cls, rate: TaxRate) -> Self:
        return cls(OperationClass.S1, rate)

    @classmethod
    def reverse_charge(cls) -> Self:
        return cls(OperationClass.S2, None)

    @property
    def is_reverse_charge(self) -> bool:
        return self.operation_class is OperationClass.S2

    @property
    def effective_rate(self) -> Fraction:
        """Fracción que se aplica a la base para obtener la cuota (0 con inversión)."""
        return Fraction(0) if self.rate is None else self.rate.as_fraction()

    @property
    def mention(self) -> str | None:
        """Mención legal obligatoria, si la hay (RN-F-05)."""
        return REVERSE_CHARGE_MENTION if self.is_reverse_charge else None
