"""Personas, empresas, NIF y domicilios ficticios (ADR-020).

Los nombres y las calles salen de Faker ``es_ES`` (versión fijada); los
municipios y códigos postales de Cantabria, de una lista propia. Los NIF se
generan con el dígito o la letra de control correctos, para que pasen
``kapataz.domain.customers.tax_id``: DNI para las personas, CIF con letra B para
las sociedades limitadas y con letra H para las comunidades de propietarios.
Un NIF válido puede coincidir con el de alguien real; por eso solo se usa
junto a nombres ficticios y en espacios de demostración y pruebas.

Los datos de contacto no pueden ser de nadie: teléfonos en un segmento del plan
de numeración pendiente de atribución, IBAN de una entidad que no existe y correos
en el dominio reservado ``.example`` (RFC 2606).
"""

import random
from collections.abc import Callable
from dataclasses import dataclass

from faker import Faker

_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
# Código de provincia de Cantabria en los CIF.
_CANTABRIA_PROVINCE = "39"


@dataclass(frozen=True, slots=True)
class Town:
    name: str
    postal_code: str


TOWNS = (
    Town("Santander", "39001"),
    Town("Santander", "39005"),
    Town("Santander", "39008"),
    Town("Santander", "39011"),
    Town("Torrelavega", "39300"),
    Town("Castro Urdiales", "39700"),
    Town("Camargo", "39600"),
    Town("El Astillero", "39610"),
    Town("Piélagos", "39470"),
    Town("Santa Cruz de Bezana", "39100"),
    Town("Laredo", "39770"),
    Town("Santoña", "39740"),
    Town("Suances", "39340"),
    Town("Reinosa", "39200"),
    Town("Cabezón de la Sal", "39500"),
    Town("Los Corrales de Buelna", "39400"),
    Town("Colindres", "39750"),
    Town("Polanco", "39313"),
)

_FLOORS = ("bajo", "1.º A", "1.º B", "2.º A", "2.º C", "3.º D", "4.º izda.", "5.º dcha.")


def dni(rng: random.Random) -> str:
    number = rng.randint(10_000_000, 79_999_999)
    return f"{number}{_DNI_LETTERS[number % 23]}"


def cif(rng: random.Random, entity: str) -> str:
    """CIF de la provincia de Cantabria con control en cifra (letras A, B, E y H)."""
    digits = _CANTABRIA_PROVINCE + f"{rng.randint(0, 99_999):05d}"
    even_sum = sum(int(d) for d in digits[1::2])
    odd_sum = sum(sum(divmod(int(d) * 2, 10)) for d in digits[0::2])
    check = (10 - (even_sum + odd_sum) % 10) % 10
    return f"{entity}{digits}{check}"


def person_name(fake: Faker) -> str:
    return f"{fake.first_name()} {fake.last_name()} {fake.last_name()}"


def street(fake: Faker) -> str:
    return str(fake.street_name())


def address(
    rng: random.Random,
    *,
    street_name: str,
    number: int,
    town: Town,
    with_floor: bool,
) -> str:
    floor = f", {rng.choice(_FLOORS)}" if with_floor else ""
    return f"{street_name}, {number}{floor}, {town.postal_code} {town.name} (Cantabria)"


# Teléfonos que no se pueden marcar hacia nadie ni hacia ningún servicio (S3-R-02).
#
# Fuente: Plan nacional de numeración telefónica, aprobado por el Real Decreto
# 2296/2004 (BOE-A-2004-21841, texto consolidado), apartados 4.2, 4.4, 5.4 y 10.1 y
# su apéndice de atribuciones vigentes:
#
# - N=0 y N=1 son «servicios de numeración corta y prefijos» (4.4), y los números
#   cortos tienen el formato «0XY (X≠0)» o «1XYA» (10.1). Cualquier 0XY es un número
#   corto atribuido (010, 011, 012, 016, 017, 024, 060, 061, 062, 067, 080, 085,
#   088, 091, 092…) o atribuible, y 00 es el prefijo internacional. Además, el plan
#   evita que las redes esperen para distinguir secuencias (4.2): al marcar «061 …»
#   la llamada puede ir al 061 aunque sigan más cifras. Por eso ningún 0 ni 1 inicial.
# - N=2 está pendiente de atribución, pero los operadores lo usan dentro de su red
#   (5.4): 22XXX, 242… Descartado.
# - N=4 está «pendiente de atribución» (4.4) y el apéndice no le atribuye nada: un
#   número nacional que empieza por 4 no corresponde a nadie, no es un número corto
#   ni lo contiene como prefijo, y ningún número de emergencia que un móvil reconoce
#   por sí solo (3GPP TS 22.101: 112 y 911; sin SIM, 000, 08, 110, 118, 119 y 999)
#   empieza por 4.
#
# Forma: «4» + 8 cifras, nueve en total como cualquier número nacional. La segunda
# cifra recuerda el tipo: 46 móvil (como el 6), 49 fijo (como el 9). Si algún día se
# atribuye el segmento 4, hay que cambiar el prefijo y regenerar el dataset.
FAKE_MOBILE_PREFIX = "46"
FAKE_LANDLINE_PREFIX = "49"


def phone(rng: random.Random, *, mobile: bool) -> str:
    """Teléfono ficticio en el segmento 4, sin atribuir: ``46X XX XX XX`` o ``49X XX XX XX``."""
    prefix = FAKE_MOBILE_PREFIX if mobile else FAKE_LANDLINE_PREFIX
    digits = f"{prefix}{rng.randint(0, 9_999_999):07d}"
    return f"{digits[:3]} {digits[3:5]} {digits[5:7]} {digits[7:]}"


# IBAN con una entidad que no existe. El código de entidad (las cuatro cifras tras los
# dígitos de control) lo asigna el Banco de España en su Registro de Entidades, y el
# 0000 no está asignado a ninguna: una transferencia a esta cuenta no llega a nadie.
# Los dígitos de control nacionales y los del IBAN (mod 97, ISO 13616) son correctos,
# para que la cuenta pase cualquier validación de formato como una real.
FAKE_BANK_CODE = "0000"
_CCC_WEIGHTS = (1, 2, 4, 8, 5, 10, 9, 7, 3, 6)
_IBAN_MODULUS = 97


def _ccc_digit(digits: str) -> str:
    """Dígito de control de la cuenta española (CCC) para diez cifras."""
    remainder = 11 - sum(int(d) * w for d, w in zip(digits, _CCC_WEIGHTS, strict=True)) % 11
    return {11: "0", 10: "1"}.get(remainder, str(remainder))


def iban_check_digits(country: str, bban: str) -> str:
    """Dígitos de control del IBAN: 98 menos el resto mod 97 de BBAN + país + 00."""
    numeric = "".join(str(int(ch, 36)) for ch in f"{bban}{country}00")
    return f"{98 - int(numeric) % _IBAN_MODULUS:02d}"


def iban_is_valid(value: str) -> bool:
    """Comprobación mod 97 de ISO 13616: el resto tiene que ser 1."""
    compact = value.replace(" ", "")
    numeric = "".join(str(int(ch, 36)) for ch in compact[4:] + compact[:4])
    return int(numeric) % _IBAN_MODULUS == 1


def iban(rng: random.Random) -> str:
    """IBAN español en la entidad inexistente 0000, con sus controles, en grupos de cuatro."""
    branch = f"{rng.randint(0, 9999):04d}"
    account = f"{rng.randint(0, 9_999_999_999):010d}"
    control = _ccc_digit(f"00{FAKE_BANK_CODE}{branch}") + _ccc_digit(account)
    bban = f"{FAKE_BANK_CODE}{branch}{control}{account}"
    raw = f"ES{iban_check_digits('ES', bban)}{bban}"
    return " ".join(raw[index : index + 4] for index in range(0, len(raw), 4))


def ascii_slug(text: str) -> str:
    """Parte local de un email: minúsculas sin tildes ni espacios."""
    table = str.maketrans("áéíóúüñ", "aeiouun")
    return "".join(ch for ch in text.lower().translate(table) if ch.isalnum())


def email(local: str) -> str:
    """Correo en el dominio reservado ``.example`` (RFC 2606): nunca llega a nadie."""
    return f"{ascii_slug(local)}@correo.example"


class Identities:
    """Fábrica de datos de personas y empresas con NIF únicos dentro de un profesional."""

    def __init__(self, rng: random.Random, fake: Faker) -> None:
        self.rng = rng
        self.fake = fake
        self._tax_ids: set[str] = set()

    def _unique(self, make: Callable[[], str]) -> str:
        while True:
            value = make()
            if value not in self._tax_ids:
                self._tax_ids.add(value)
                return value

    def dni(self) -> str:
        return self._unique(lambda: dni(self.rng))

    def cif(self, entity: str) -> str:
        return self._unique(lambda: cif(self.rng, entity))

    def person(self) -> str:
        return person_name(self.fake)

    def surname(self) -> str:
        return str(self.fake.last_name())

    def company(self, prefix: str) -> str:
        return f"{prefix} {self.surname()} S.L."

    def street(self) -> str:
        return street(self.fake)

    def town(self, index: int | None = None) -> Town:
        if index is not None:
            return TOWNS[index]
        return self.rng.choice(TOWNS)

    def address(self, town: Town | None = None, *, with_floor: bool = True) -> str:
        return address(
            self.rng,
            street_name=self.street(),
            number=self.rng.randint(1, 120),
            town=town or self.town(),
            with_floor=with_floor,
        )

    def phone(self, *, mobile: bool) -> str:
        return phone(self.rng, mobile=mobile)

    def iban(self) -> str:
        return iban(self.rng)
