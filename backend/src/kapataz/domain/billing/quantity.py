"""Objetos de valor Quantity y Percentage."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Self

from kapataz.domain.billing.errors import InvalidAmountError

# Tres decimales bastan para metros, kilos y horas de oficio (2,125 m) y dejan
# fuera cantidades absurdas que solo pueden venir de un error.
MAX_QUANTITY_DECIMALS = 3
MAX_QUANTITY = Decimal("999999.999")
MAX_PERCENTAGE_DECIMALS = 2


def _decimals(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    # Solo se llama con valores finitos, cuyo exponente es siempre un entero.
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def _require_decimal(value: object, what: str) -> Decimal:
    if type(value) is not Decimal:
        msg = f"{what} solo admite Decimal, no {type(value).__name__} (RN-01)."
        raise TypeError(msg)
    if not value.is_finite():
        msg = f"{what} tiene que ser un número finito."
        raise InvalidAmountError(msg)
    return value


@dataclass(frozen=True, slots=True)
class Quantity:
    """Cantidad de una línea: siempre positiva.

    Lo que resta (una factura anterior, un trabajo quitado en una rectificativa)
    se expresa con precio negativo, no con cantidad negativa: así una cantidad
    nunca cambia el signo de una línea por sorpresa.
    """

    value: Decimal

    def __post_init__(self) -> None:
        value = _require_decimal(self.value, "Una cantidad")
        if not 0 < value <= MAX_QUANTITY:
            msg = f"La cantidad tiene que ser mayor que cero y como mucho {MAX_QUANTITY}."
            raise InvalidAmountError(msg)
        if _decimals(value) > MAX_QUANTITY_DECIMALS:
            msg = f"La cantidad admite como mucho {MAX_QUANTITY_DECIMALS} decimales."
            raise InvalidAmountError(msg)

    @classmethod
    def of(cls, value: str | int) -> Self:
        return cls(Decimal(value))

    @classmethod
    def one(cls) -> Self:
        return cls(Decimal(1))

    def as_fraction(self) -> Fraction:
        return Fraction(self.value)

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Percentage:
    """Porcentaje entre 0 y 100, con dos decimales como mucho.

    Sirve para el descuento de una línea, la retención de IRPF y la garantía.
    Cada uso añade sus propios límites (una retención del 0 % no tiene sentido).
    """

    value: Decimal

    def __post_init__(self) -> None:
        value = _require_decimal(self.value, "Un porcentaje")
        if not 0 <= value <= 100:  # noqa: PLR2004
            raise InvalidAmountError("Un porcentaje tiene que estar entre 0 y 100.")
        if _decimals(value) > MAX_PERCENTAGE_DECIMALS:
            msg = f"Un porcentaje admite como mucho {MAX_PERCENTAGE_DECIMALS} decimales."
            raise InvalidAmountError(msg)

    @classmethod
    def of(cls, value: str | int) -> Self:
        return cls(Decimal(value))

    def as_fraction(self) -> Fraction:
        """El porcentaje como fracción de la unidad: 21 % es 21/100."""
        return Fraction(self.value) / 100

    def is_zero(self) -> bool:
        return self.value == 0

    def __str__(self) -> str:
        return str(self.value)
