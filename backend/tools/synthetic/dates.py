"""Fechas del generador: días laborables y fechas en letra."""

import random
from datetime import date, timedelta

_SATURDAY = 5

MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def business_day(rng: random.Random, low: date, high: date) -> date:
    """Día al azar entre dos fechas; sábado y domingo pasan al lunes siguiente."""
    when = low + timedelta(days=rng.randint(0, (high - low).days))
    while when.weekday() >= _SATURDAY:
        when += timedelta(days=1)
    return when


def long_date(when: date) -> str:
    """«14 de marzo de 2025»."""
    return f"{when.day} de {MONTHS[when.month - 1]} de {when.year}"
