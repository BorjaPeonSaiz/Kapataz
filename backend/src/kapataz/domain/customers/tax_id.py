"""Objeto de valor TaxId: NIF español de persona física (DNI), extranjero (NIE) o entidad (CIF).

La v1 solo admite NIF español (plan §1.4, RN-F-06). Los identificadores
extranjeros quedan preparados en la base de datos (``tax_id_type`` y
``tax_id_country``), pero no tienen objeto de valor hasta que se admitan.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Self

from kapataz.domain.aeat_limits import TAX_ID_LENGTH
from kapataz.domain.customers.errors import InvalidTaxIdError

# Letra de control del DNI y del NIE: resto de dividir el número entre 23.
_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
# El NIE sustituye su letra inicial por una cifra antes de calcular el control.
_NIE_PREFIX = {"X": "0", "Y": "1", "Z": "2"}
# K, L y M son NIF de personas físicas sin DNI (menores, extranjeros sin NIE):
# se calculan como un DNI con un cero delante.
_PERSON_SPECIAL_PREFIXES = "KLM"
# Letras de control del CIF, indexadas por el dígito calculado.
_CIF_CONTROL_LETTERS = "JABCDEFGHI"
_CIF_ENTITY_LETTERS = "ABCDEFGHJNPQRSUVW"
# Entidades cuyo control es siempre letra (no residentes, organismos públicos,
# entidades religiosas…) y siempre cifra (sociedades anónimas y limitadas…).
_CIF_LETTER_CONTROL = "NPQRSW"
_CIF_DIGIT_CONTROL = "ABEH"

_DNI_PATTERN = re.compile(r"^\d{8}[A-Z]$")
_NIE_PATTERN = re.compile(r"^[XYZ]\d{7}[A-Z]$")
_SPECIAL_PATTERN = re.compile(r"^[KLM]\d{7}[A-Z]$")
_CIF_PATTERN = re.compile(r"^[A-Z]\d{7}[A-Z0-9]$")
# Separadores que la gente escribe y que no forman parte del NIF.
_SEPARATORS = re.compile(r"[\s.\-]")


class TaxIdKind(StrEnum):
    DNI = "dni"
    NIE = "nie"
    CIF = "cif"


@dataclass(frozen=True, slots=True)
class TaxId:
    """NIF normalizado (mayúsculas, sin espacios ni guiones) y con el control correcto."""

    value: str
    # Se deduce del valor al validarlo; guardarlo evita repetir el cálculo y
    # que exista un TaxId sin tipo.
    kind: TaxIdKind = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        kind = _kind_of(self.value)
        if kind is None:
            raise InvalidTaxIdError("NIF no válido o sin normalizar.")
        object.__setattr__(self, "kind", kind)

    @classmethod
    def parse(cls, raw: str) -> Self:
        return cls(_SEPARATORS.sub("", raw).upper())

    def __str__(self) -> str:
        return self.value


def _kind_of(value: str) -> TaxIdKind | None:
    if len(value) != TAX_ID_LENGTH or not value.isascii():
        return None
    if _DNI_PATTERN.fullmatch(value):
        return TaxIdKind.DNI if _dni_letter(value[:8]) == value[8] else None
    if _SPECIAL_PATTERN.fullmatch(value):
        return TaxIdKind.DNI if _dni_letter("0" + value[1:8]) == value[8] else None
    if _NIE_PATTERN.fullmatch(value):
        digits = _NIE_PREFIX[value[0]] + value[1:8]
        return TaxIdKind.NIE if _dni_letter(digits) == value[8] else None
    if _CIF_PATTERN.fullmatch(value) and value[0] in _CIF_ENTITY_LETTERS:
        return TaxIdKind.CIF if _cif_control_matches(value) else None
    return None


def _dni_letter(digits: str) -> str:
    return _DNI_LETTERS[int(digits) % 23]


def _cif_control_matches(value: str) -> bool:
    entity, digits, control = value[0], value[1:8], value[8]
    even_sum = sum(int(d) for d in digits[1::2])
    odd_sum = sum(sum(divmod(int(d) * 2, 10)) for d in digits[0::2])
    check = (10 - (even_sum + odd_sum) % 10) % 10
    as_digit, as_letter = str(check), _CIF_CONTROL_LETTERS[check]
    # Los CIF de no residentes empiezan por «00» y llevan siempre letra.
    if entity in _CIF_LETTER_CONTROL or digits.startswith("00"):
        return control == as_letter
    if entity in _CIF_DIGIT_CONTROL:
        return control == as_digit
    return control in {as_digit, as_letter}
