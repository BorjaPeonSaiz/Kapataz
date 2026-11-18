"""Objeto de valor Money y único punto de redondeo de importes (ADR-009, RN-01, RN-03).

Todo importe del dominio es un ``Money`` con exactamente dos decimales. Los
cálculos intermedios (cantidad por precio, porcentajes, la división del
anticipo) se hacen con ``Fraction``, que es exacta, y solo se redondean una vez
al convertirlos en ``Money`` con ``Money.round``. Con ``Decimal`` a secas, una
división como 6.000 / 1,10 se trunca a la precisión del contexto antes del
redondeo final, y ese doble redondeo podría mover un céntimo.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Self

from kapataz.domain.billing.errors import InvalidAmountError

CENT = Decimal("0.01")
_DECIMALS = 2
# ADR-009: la base de datos guarda céntimos en INTEGER, así que ningún importe
# puede pasar de 2.147.483.647 céntimos. Se rechaza aquí, al calcularlo, y no
# al guardarlo, cuando ya no se sabe de dónde salió. Si la columna pasa a
# BIGINT, se sube este tope.
MAX_ABS_AMOUNT = Decimal("21474836.47")
_HALF = Fraction(1, 2)


@dataclass(frozen=True, slots=True, order=True)
class Money:
    """Importe en euros con dos decimales.

    Solo admite ``Decimal``: un ``float`` es un error de programación (RN-01) y
    se rechaza también en tiempo de ejecución, por si llega desde código sin
    tipar. Un ``Decimal`` con más de dos decimales se rechaza en vez de
    redondearse en silencio: quien necesite redondear usa ``Money.round``.
    Admite importes negativos, que aparecen en las rectificativas por
    diferencias y en las líneas que restan facturas anteriores.
    """

    amount: Decimal

    def __post_init__(self) -> None:
        if type(self.amount) is not Decimal:
            msg = f"Money solo admite Decimal, no {type(self.amount).__name__} (RN-01)."
            raise TypeError(msg)
        if not self.amount.is_finite():
            raise InvalidAmountError("Un importe tiene que ser un número finito.")
        exponent = self.amount.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -_DECIMALS:
            raise InvalidAmountError("Un importe tiene como mucho dos decimales.")
        if abs(self.amount) > MAX_ABS_AMOUNT:
            raise InvalidAmountError("El importe supera el máximo admitido.")
        # Se normaliza a dos decimales para que 10 y 10.00 sean el mismo valor
        # también al serializarlos (contenido canónico del registro, RN-F-07).
        normalized = self.amount.quantize(CENT) + Decimal("0.00")
        object.__setattr__(self, "amount", normalized)

    @classmethod
    def of(cls, amount: str) -> Self:
        """Atajo para literales: ``Money.of("45.00")``. Nunca recibe un float."""
        return cls(Decimal(amount))

    @classmethod
    def zero(cls) -> Self:
        return cls(Decimal("0.00"))

    @classmethod
    def round(cls, value: Fraction | Decimal) -> Self:
        """Redondea a céntimos con ROUND_HALF_UP (mitad hacia fuera del cero, RN-03).

        Es el único redondeo de importes del dominio. Simétrico respecto al
        cero: -0,005 da -0,01, así una rectificativa por diferencias es
        exactamente la opuesta de lo que rectifica.
        """
        if isinstance(value, Decimal) and not value.is_finite():
            raise InvalidAmountError("Un importe tiene que ser un número finito.")
        exact = Fraction(value)
        cents = int(abs(exact) * 100 + _HALF)
        signed = -cents if exact < 0 else cents
        return cls(Decimal(signed).scaleb(-2))

    def as_fraction(self) -> Fraction:
        return Fraction(self.amount)

    def is_zero(self) -> bool:
        return self.amount == 0

    def is_negative(self) -> bool:
        return self.amount < 0

    def is_positive(self) -> bool:
        return self.amount > 0

    def __add__(self, other: "Money") -> "Money":
        return Money(self.amount + other.amount)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self.amount - other.amount)

    def __neg__(self) -> "Money":
        return Money(-self.amount)

    def __abs__(self) -> "Money":
        return Money(abs(self.amount))

    def __str__(self) -> str:
        """Formato con punto decimal y dos decimales, el del registro de la AEAT."""
        return f"{self.amount:.2f}"


def sum_money(amounts: Iterable[Money]) -> Money:
    """Suma exacta de importes; la suma vacía es cero."""
    total = Money.zero()
    for amount in amounts:
        total += amount
    return total
