"""Único conversor entre ``Money`` y los céntimos en ``INTEGER`` de la base de datos (ADR-009).

Ningún otro sitio del código convierte importes: las tablas declaran sus
columnas de importe con ``Cents`` y los repositorios reciben y devuelven
``Money``. Nunca pasa por ``float``.
"""

from decimal import Decimal
from typing import override

from sqlalchemy import Dialect, Integer
from sqlalchemy.types import TypeDecorator

from kapataz.domain.billing.money import Money


def money_to_cents(money: Money) -> int:
    """Céntimos exactos: ``Money`` tiene siempre dos decimales, así que no hay redondeo."""
    cents = money.amount.scaleb(2)
    if cents != cents.to_integral_value():  # pragma: no cover - Money lo impide
        msg = "Un importe con más de dos decimales no se guarda."
        raise ValueError(msg)
    return int(cents)


def cents_to_money(cents: int) -> Money:
    if type(cents) is not int:
        msg = f"Los céntimos son un entero, no {type(cents).__name__}."
        raise TypeError(msg)
    return Money(Decimal(cents).scaleb(-2))


class Cents(TypeDecorator[Money]):
    """Columna ``INTEGER`` de céntimos que en Python es ``Money``."""

    impl = Integer
    cache_ok = True

    @override
    def process_bind_param(self, value: object, dialect: Dialect) -> int | None:
        del dialect
        if value is None:
            return None
        if not isinstance(value, Money):
            msg = f"Una columna de importe solo admite Money, no {type(value).__name__}."
            raise TypeError(msg)
        return money_to_cents(value)

    @override
    def process_result_value(self, value: int | None, dialect: Dialect) -> Money | None:
        del dialect
        return None if value is None else cents_to_money(value)
