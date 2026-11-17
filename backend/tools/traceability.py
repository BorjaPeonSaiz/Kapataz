"""Matriz de trazabilidad entre la especificación y las pruebas de Kapataz.

Lee los identificadores de ``docs/01-especificacion.md`` y los cruza con los
marcadores de las pruebas. Solo usa la biblioteca estándar y no importa las
pruebas: las analiza con ``ast`` (backend) o con expresiones regulares
(frontend).

Uso, desde ``backend/``::

    uv run python tools/traceability.py                   # matriz breve
    uv run python tools/traceability.py --check           # falla si hay IDs inexistentes
    uv run python tools/traceability.py --check --strict  # falla también si falta alguna prueba
    uv run python tools/traceability.py --json            # resultado en JSON

Identificadores de la especificación
    Filas de tabla que empiezan por ``| HU-NN |``, ``| RF-XX-NN |``,
    ``| RN-NN |``, ``| RN-F-NN |`` o ``| RNF-NN |``. Las historias de usuario
    (HU) no llevan marcador de prueba: se verifican a través de sus RF, RN y
    escenarios (§2 de la especificación). Se informan aparte, no cuentan como
    requisitos sin prueba y citarlas en un marcador es un error.

Marcadores del backend (``backend/tests/**/*.py``)
    ``@pytest.mark.req("ID")``, con uno o varios identificadores, en una
    función, en una clase, en ``pytestmark`` de módulo o de clase, o en
    ``pytest.param(..., marks=...)``. También vale ``mark.req`` si se importa
    ``from pytest import mark``. El argumento tiene que ser una cadena literal.
    ``@pytest.mark.owasp("A01")`` o ``("LLM01")`` traza las categorías del
    OWASP Top 10 web y del OWASP Top 10 para LLM, edición 2025 (ADR-021).

Marcadores del frontend (``frontend/``, Vitest y Playwright)
    Convención: ``req("ID")`` u ``owasp("A01")`` en el título de la prueba,
    por ejemplo ``test('envía el mensaje req("RF-CO-01")', ...)``, o una
    anotación de Playwright ``{ type: 'req', description: 'RF-CO-01' }``.
    Se leen los ficheros ``*.spec.*`` y ``*.test.*`` con extensión js o ts,
    sin entrar en ``node_modules`` ni ``dist``. Si ``frontend/`` no existe, se
    ignora. La lectura es provisional: no detecta pruebas del frontend sin
    marcador; se completará cuando existan esas pruebas.

Qué hace fallar ``--check`` (código de salida 1)
    - Una prueba cita un ID que no existe en la especificación o una HU.
    - Una prueba cita una categoría OWASP que no existe. ADR-021 pide que esto
      falle desde el Bloque 1: es el mismo error de escritura que un ID
      inexistente.
    - Un marcador sin argumento literal, un fichero de prueba que no se puede
      analizar o un ID repetido en la especificación.

Qué solo hace fallar ``--check --strict``
    - Requisitos (RF, RN, RNF) sin prueba.
    - Categorías OWASP sin prueba (ADR-021).
    - Pruebas del backend sin marcador ``req``.

    En el Bloque 1 casi todos los requisitos están sin prueba, así que la CI
    usa ``--check``. El plan de verificación (Parte II) exige ``--strict``:
    ningún requisito ni categoría OWASP sin prueba.

Sin ``--check`` el código de salida es siempre 0. Un error de uso o una
especificación que no se puede leer devuelven 2.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import textwrap
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_SPEC: Final = REPO_ROOT / "docs" / "01-especificacion.md"
DEFAULT_TESTS: Final = REPO_ROOT / "backend" / "tests"
DEFAULT_FRONTEND: Final = REPO_ROOT / "frontend"

SPEC_ROW_RE: Final = re.compile(
    r"^\|\s*(HU-\d{2}|RF-[A-Z]{2}-\d{2}|RN-F-\d{2}|RN-\d{2}|RNF-\d{2})\s*\|"
)
OWASP_CATEGORIES: Final[tuple[str, ...]] = tuple(f"A{n:02d}" for n in range(1, 11)) + tuple(
    f"LLM{n:02d}" for n in range(1, 11)
)
MARKER_KINDS: Final = frozenset({"req", "owasp"})
FAMILIES: Final = ("RF", "RN", "RNF")

PYTEST_FILE_RE: Final = re.compile(r"^(test_.*|.*_test)\.py$")
FRONTEND_TEST_RE: Final = re.compile(r"\.(spec|test)\.[cm]?[jt]sx?$")
FRONTEND_SKIP_DIRS: Final = frozenset({"node_modules", "dist", ".git", "coverage"})
FRONTEND_INLINE_RE: Final = re.compile(r"""\b(req|owasp)\(\s*["'`]([^"'`]+)["'`]\s*\)""")
FRONTEND_ANNOTATION_RE: Final = re.compile(
    r"""\btype\s*:\s*["'`](req|owasp)["'`]\s*,\s*description\s*:\s*["'`]([^"'`]+)["'`]"""
)


def family(req_id: str) -> str:
    """Devuelve la familia de un identificador: HU, RF, RN (incluye RN-F) o RNF."""
    for prefix in ("HU", "RNF", "RF", "RN"):
        if req_id.startswith(f"{prefix}-"):
            return prefix
    msg = f"Identificador desconocido: {req_id}"
    raise ValueError(msg)


# --- Especificación -----------------------------------------------------------


@dataclass(frozen=True)
class Spec:
    """Identificadores de la especificación, en orden de aparición."""

    requirements: tuple[str, ...]
    user_stories: tuple[str, ...]
    duplicates: tuple[str, ...] = ()


def parse_spec(text: str) -> Spec:
    """Extrae los identificadores de las filas de tabla de la especificación."""
    seen: set[str] = set()
    requirements: list[str] = []
    user_stories: list[str] = []
    duplicates: list[str] = []
    for line in text.splitlines():
        match = SPEC_ROW_RE.match(line)
        if match is None:
            continue
        req_id = match.group(1)
        if req_id in seen:
            duplicates.append(req_id)
            continue
        seen.add(req_id)
        (user_stories if req_id.startswith("HU-") else requirements).append(req_id)
    return Spec(tuple(requirements), tuple(user_stories), tuple(duplicates))


# --- Pruebas ------------------------------------------------------------------


@dataclass(frozen=True)
class MarkerUse:
    """Un identificador citado por un marcador ``req`` u ``owasp``."""

    kind: str
    value: str
    test: str


@dataclass
class Scan:
    """Marcadores encontrados en las pruebas y problemas al leerlas."""

    markers: list[MarkerUse] = field(default_factory=list)
    untagged: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def extend(self, other: Scan) -> None:
        self.markers.extend(other.markers)
        self.untagged.extend(other.untagged)
        self.errors.extend(other.errors)


def _mark_kind(func: ast.expr) -> str | None:
    """Devuelve ``req`` u ``owasp`` si ``func`` es ``pytest.mark.X`` o ``mark.X``."""
    if not isinstance(func, ast.Attribute) or func.attr not in MARKER_KINDS:
        return None
    base = func.value
    if (isinstance(base, ast.Name) and base.id == "mark") or (
        isinstance(base, ast.Attribute) and base.attr == "mark"
    ):
        return func.attr
    return None


def _pytestmark_values(body: Sequence[ast.stmt]) -> list[ast.expr]:
    values: list[ast.expr] = []
    for stmt in body:
        if isinstance(stmt, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets):
                values.append(stmt.value)
        elif isinstance(stmt, ast.AnnAssign | ast.AugAssign):
            target = stmt.target
            if isinstance(target, ast.Name) and target.id == "pytestmark" and stmt.value:
                values.append(stmt.value)
    return values


class _PythonCollector:
    def __init__(self, rel: str, *, collect_tests: bool) -> None:
        self.rel = rel
        self.collect_tests = collect_tests
        self.scan = Scan()

    def marks_in(self, nodes: Iterable[ast.AST], test: str) -> bool:
        """Registra los marcadores de ``nodes`` y dice si alguno es ``req``."""
        has_req = False
        for node in nodes:
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                kind = _mark_kind(sub.func)
                if kind is None:
                    continue
                if not sub.args or sub.keywords:
                    self.scan.errors.append(
                        f"{self.rel}:{sub.lineno}: {kind}() necesita los identificadores "
                        "como argumentos posicionales"
                    )
                for arg in sub.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        self.scan.markers.append(MarkerUse(kind, arg.value, test))
                        has_req = has_req or kind == "req"
                    else:
                        self.scan.errors.append(
                            f"{self.rel}:{arg.lineno}: {kind}() con un argumento que no "
                            "es una cadena literal"
                        )
        return has_req

    def visit_body(
        self, body: Sequence[ast.stmt], prefix: str, *, inherited_req: bool, in_tests: bool
    ) -> None:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                name = f"{prefix}::{stmt.name}"
                has_req = self.marks_in(
                    [*stmt.decorator_list, *_pytestmark_values(stmt.body)], name
                )
                self.visit_body(
                    stmt.body,
                    name,
                    inherited_req=inherited_req or has_req,
                    in_tests=in_tests and stmt.name.startswith("Test"),
                )
            elif isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                name = f"{prefix}::{stmt.name}"
                has_req = self.marks_in(stmt.decorator_list, name)
                is_test = in_tests and self.collect_tests and stmt.name.startswith("test")
                if is_test and not (has_req or inherited_req):
                    self.scan.untagged.append(name)


def scan_python_source(source: str, rel: str, *, collect_tests: bool = True) -> Scan:
    """Analiza el código de un fichero de pruebas sin importarlo."""
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return Scan(errors=[f"{rel}:{exc.lineno}: no se puede analizar: {exc.msg}"])
    collector = _PythonCollector(rel, collect_tests=collect_tests)
    module_req = collector.marks_in(_pytestmark_values(tree.body), rel)
    collector.visit_body(tree.body, rel, inherited_req=module_req, in_tests=True)
    return collector.scan


def _read(path: Path, rel: str, scan: Scan) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        scan.errors.append(f"{rel}: no se puede leer: {exc}")
        return None


def scan_backend(tests_dir: Path) -> Scan:
    """Recorre ``tests_dir`` y analiza cada ``*.py``. Si no existe, no hay pruebas."""
    scan = Scan()
    if not tests_dir.is_dir():
        return scan
    base = tests_dir.parent
    for path in sorted(tests_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(base).as_posix()
        source = _read(path, rel, scan)
        if source is not None:
            collect = PYTEST_FILE_RE.match(path.name) is not None
            scan.extend(scan_python_source(source, rel, collect_tests=collect))
    return scan


def _frontend_files(frontend_dir: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(frontend_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in FRONTEND_SKIP_DIRS)
        for name in sorted(filenames):
            if FRONTEND_TEST_RE.search(name):
                yield Path(dirpath) / name


def scan_frontend_source(source: str, rel: str) -> Scan:
    """Lee los marcadores de una prueba de Vitest o Playwright (convención provisional)."""
    scan = Scan()
    for lineno, line in enumerate(source.splitlines(), start=1):
        for regex in (FRONTEND_INLINE_RE, FRONTEND_ANNOTATION_RE):
            for match in regex.finditer(line):
                scan.markers.append(MarkerUse(match.group(1), match.group(2), f"{rel}:{lineno}"))
    return scan


def scan_frontend(frontend_dir: Path) -> Scan:
    """Recorre las pruebas del frontend. Si ``frontend_dir`` no existe, se ignora."""
    scan = Scan()
    if not frontend_dir.is_dir():
        return scan
    base = frontend_dir.parent
    for path in _frontend_files(frontend_dir):
        rel = path.relative_to(base).as_posix()
        source = _read(path, rel, scan)
        if source is not None:
            scan.extend(scan_frontend_source(source, rel))
    return scan


# --- Matriz -------------------------------------------------------------------


@dataclass(frozen=True)
class UnknownMarker:
    """Un marcador que cita algo que no existe."""

    kind: str
    value: str
    test: str
    reason: str


@dataclass
class Report:
    """Resultado del cruce entre la especificación y las pruebas."""

    spec: str
    requirements: list[str]
    user_stories: list[str]
    covered: dict[str, list[str]]
    uncovered: list[str]
    unknown: list[UnknownMarker]
    owasp_covered: dict[str, list[str]]
    owasp_uncovered: list[str]
    untagged_tests: list[str]
    errors: list[str]

    def failures(self, *, strict: bool) -> list[str]:
        """Motivos por los que ``--check`` (o ``--check --strict``) falla."""
        reasons: list[str] = []
        if self.unknown:
            reasons.append(f"{len(self.unknown)} marcadores citan IDs o categorías inexistentes")
        if self.errors:
            reasons.append(f"{len(self.errors)} errores de análisis")
        if strict:
            if self.uncovered:
                reasons.append(f"{len(self.uncovered)} requisitos sin prueba")
            if self.owasp_uncovered:
                reasons.append(f"{len(self.owasp_uncovered)} categorías OWASP sin prueba")
            if self.untagged_tests:
                reasons.append(f"{len(self.untagged_tests)} pruebas sin marcador req")
        return reasons


def _append_unique(mapping: dict[str, list[str]], key: str, test: str) -> None:
    tests = mapping.setdefault(key, [])
    if test not in tests:
        tests.append(test)


def build_report(spec: Spec, scan: Scan, spec_label: str) -> Report:
    """Cruza los identificadores de la especificación con los marcadores."""
    requirements = set(spec.requirements)
    user_stories = set(spec.user_stories)
    covered: dict[str, list[str]] = {}
    owasp: dict[str, list[str]] = {}
    unknown: list[UnknownMarker] = []
    for marker in scan.markers:
        if marker.kind == "req":
            if marker.value in requirements:
                _append_unique(covered, marker.value, marker.test)
                continue
            reason = (
                "es una historia de usuario; las HU no llevan marcador"
                if marker.value in user_stories
                else "no existe en la especificación"
            )
        elif marker.value in OWASP_CATEGORIES:
            _append_unique(owasp, marker.value, marker.test)
            continue
        else:
            reason = "no es una categoría OWASP 2025 (A01-A10, LLM01-LLM10)"
        unknown.append(UnknownMarker(marker.kind, marker.value, marker.test, reason))
    errors = [f"ID repetido en la especificación: {d}" for d in spec.duplicates]
    return Report(
        spec=spec_label,
        requirements=list(spec.requirements),
        user_stories=list(spec.user_stories),
        covered={r: covered[r] for r in spec.requirements if r in covered},
        uncovered=[r for r in spec.requirements if r not in covered],
        unknown=unknown,
        owasp_covered={c: owasp[c] for c in OWASP_CATEGORIES if c in owasp},
        owasp_uncovered=[c for c in OWASP_CATEGORIES if c not in owasp],
        untagged_tests=list(scan.untagged),
        errors=[*errors, *scan.errors],
    )


# --- Salida -------------------------------------------------------------------


def _wrap(items: Sequence[str]) -> str:
    return textwrap.fill(
        ", ".join(items),
        width=100,
        initial_indent="    ",
        subsequent_indent="    ",
        break_on_hyphens=False,
    )


def render_text(report: Report, *, check: bool, strict: bool) -> str:
    counts = ", ".join(
        f"{fam} {sum(1 for r in report.requirements if family(r) == fam)}" for fam in FAMILIES
    )
    total = len(report.requirements)
    lines = [
        f"Trazabilidad: {report.spec}",
        (
            f"  Requisitos: {total} ({counts}). Historias de usuario: "
            f"{len(report.user_stories)}, se verifican a través de sus requisitos "
            "y no llevan marcador."
        ),
        "",
        f"Requisitos con prueba ({len(report.covered)} de {total}):",
    ]
    width = max((len(r) for r in report.covered), default=0)
    lines += [f"    {r:<{width}}  {', '.join(tests)}" for r, tests in report.covered.items()]
    lines.append(f"Requisitos sin prueba ({len(report.uncovered)}):")
    if report.uncovered:
        lines.append(_wrap(report.uncovered))
    lines.append(f"Pruebas que citan IDs o categorías inexistentes ({len(report.unknown)}):")
    lines += [f'    {u.kind}("{u.value}") en {u.test}: {u.reason}' for u in report.unknown]
    lines.append(f"Pruebas del backend sin marcador req ({len(report.untagged_tests)}):")
    lines += [f"    {t}" for t in report.untagged_tests]
    lines += [
        "",
        (
            f"OWASP (ADR-021): {len(report.owasp_covered)} de {len(OWASP_CATEGORIES)} "
            "categorías con prueba."
        ),
    ]
    lines += [f"    {c:<5}  {', '.join(tests)}" for c, tests in report.owasp_covered.items()]
    if report.owasp_uncovered:
        lines.append("  Sin prueba:")
        lines.append(_wrap(report.owasp_uncovered))
    if report.errors:
        lines += ["", f"Errores ({len(report.errors)}):"]
        lines += [f"    {e}" for e in report.errors]
    if check:
        mode = "--check --strict" if strict else "--check"
        reasons = report.failures(strict=strict)
        lines += ["", f"{mode}: " + ("falla: " + "; ".join(reasons) if reasons else "correcto")]
    return "\n".join(lines)


def render_json(report: Report, *, check: bool, strict: bool) -> str:
    data: dict[str, object] = asdict(report)
    if check:
        reasons = report.failures(strict=strict)
        data["check"] = {"strict": strict, "ok": not reasons, "failures": reasons}
    return json.dumps(data, ensure_ascii=False, indent=2)


# --- CLI ----------------------------------------------------------------------


def _label(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Matriz de trazabilidad entre docs/01-especificacion.md y las pruebas.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="sale con 1 si una prueba cita un ID o una categoría OWASP inexistente",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="con --check, falla también si falta prueba de un requisito o categoría OWASP",
    )
    parser.add_argument("--json", action="store_true", help="saca el resultado en JSON")
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC, help="especificación")
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS, help="pruebas del backend")
    parser.add_argument("--frontend", type=Path, default=DEFAULT_FRONTEND, help="raíz del frontend")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    check: bool = args.check
    strict: bool = args.strict
    spec_path: Path = args.spec
    tests_dir: Path = args.tests
    frontend_dir: Path = args.frontend
    if strict and not check:
        parser.error("--strict solo se usa junto con --check")
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"No se puede leer la especificación {spec_path}: {exc}", file=sys.stderr)
        return 2
    scan = scan_backend(tests_dir)
    scan.extend(scan_frontend(frontend_dir))
    report = build_report(parse_spec(spec_text), scan, _label(spec_path))
    render = render_json if args.json else render_text
    print(render(report, check=check, strict=strict))
    return 1 if check and report.failures(strict=strict) else 0


if __name__ == "__main__":
    sys.exit(main())
