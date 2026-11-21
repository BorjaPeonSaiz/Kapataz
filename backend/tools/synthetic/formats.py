"""Formatos de números y fechas tal como los imprimen los documentos."""

from datetime import date
from decimal import Decimal

from synthetic.dates import long_date


def es_amount(value: Decimal) -> str:
    """Importe con punto de miles y coma decimal: 1.234,56."""
    text = f"{value:,.2f}"
    return text.replace(",", " ").replace(".", ",").replace(" ", ".")


def es_plain_amount(value: Decimal) -> str:
    """Importe sin separador de miles: 1234,56."""
    return f"{value:.2f}".replace(".", ",")


def es_quantity(value: Decimal, *, decimals: int | None = None) -> str:
    """Cantidad con coma decimal; con ``decimals``, siempre con esos decimales."""
    if decimals is not None:
        text = f"{value:,.{decimals}f}"
        return text.replace(",", " ").replace(".", ",").replace(" ", ".")
    return str(value).replace(".", ",")


def es_percent(value: Decimal) -> str:
    """Porcentaje sin decimales sobrantes: 21, 10, 5."""
    return str(value.quantize(Decimal(1)) if value == value.to_integral_value() else value)


def date_slash(when: date) -> str:
    return f"{when.day:02d}/{when.month:02d}/{when.year}"


def date_dash(when: date) -> str:
    return f"{when.day:02d}-{when.month:02d}-{when.year}"


def date_dot(when: date) -> str:
    return f"{when.day:02d}.{when.month:02d}.{when.year}"


def date_long(when: date) -> str:
    return long_date(when)
