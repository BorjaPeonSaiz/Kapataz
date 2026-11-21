"""La API no llega a otra cuenta por la puerta de atrás (RN-10, S3-R-03, S3-R-08).

``lint-imports`` no basta. Con ``from paquete.modulo import nombre``, grimp
registra el import de ``paquete.modulo`` y no el del módulo del que sale
``nombre``: si un módulo permitido reexporta un nombre prohibido, el contrato
queda en verde. Estas pruebas leen el código con ``ast`` (sin importarlo) y
cierran esa vía para lo que tiene que ver con elegir la cuenta:

- ``src/kapataz/api/`` no nombra el núcleo de carga del espacio de
  demostración (``demo_space_loader``, ``load_demo_space``), que crea el
  espacio de la cuenta que recibe, ni importa nombres privados de
  ``kapataz``, que es como entra hoy ese núcleo en ``LoadDemoSpace``, ni
  hace imports dinámicos (``importlib.import_module``, ``__import__``), que
  ninguna lectura estática sigue.
- Solo ``AuthenticateSession`` construye un ``AuthenticatedUser``, y nadie
  copia uno cambiándole la cuenta (``replace(..., tenant_id=...)``). Se
  revisa todo ``src/kapataz``, no solo la API: la API puede importar lo que
  construya la infraestructura o la aplicación.

Si una de estas pruebas falla con un cambio legítimo, el cambio se discute
antes de tocar la lista de permitidos.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

import kapataz

pytestmark = [pytest.mark.req("RN-10"), pytest.mark.owasp("A01")]

SRC = Path(kapataz.__file__).resolve().parent
API = SRC / "api"

# El núcleo y su función: crean el espacio de cualquier cuenta que reciban.
LOADER_MODULE = "demo_space_loader"
FORBIDDEN_IN_API = frozenset({LOADER_MODULE, "load_demo_space"})
DYNAMIC_IMPORTS = frozenset({"import_module", "__import__"})

# Quién construye legítimamente un AuthenticatedUser: la validación de la sesión.
AUTHENTICATED_USER = "AuthenticatedUser"
ALLOWED_BUILDERS = frozenset({"application/use_cases/authenticate_session.py"})


def _python_files(root: Path) -> Iterator[Path]:
    yield from sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _names_loader_module(dotted: str) -> bool:
    # Por segmentos: kapataz.application.use_cases.load_demo_space es el módulo
    # de LoadDemoSpace, permitido; lo prohibido es el núcleo.
    return LOADER_MODULE in dotted.split(".")


def forbidden_api_uses(tree: ast.AST) -> list[str]:
    """Usos del núcleo de carga o de nombres privados de kapataz en un módulo de la API."""
    found: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            found.extend(
                f"{line}: import {alias.name}"
                for alias in node.names
                if _names_loader_module(alias.name) or alias.asname in FORBIDDEN_IN_API
            )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _names_loader_module(module):
                found.append(f"{line}: from {module} import ...")
            for alias in node.names:
                if alias.name in FORBIDDEN_IN_API or (alias.asname or "") in FORBIDDEN_IN_API:
                    found.append(f"{line}: from {module} import {alias.name}")
                elif alias.name.startswith("_") and (module.startswith("kapataz") or node.level):
                    found.append(f"{line}: from {module} import {alias.name} (nombre privado)")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_IN_API:
            found.append(f"{line}: {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_IN_API:
            found.append(f"{line}: .{node.attr}")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and LOADER_MODULE in node.value
        ):
            # importlib.import_module("kapataz.application.use_cases.demo_space_loader").
            found.append(f"{line}: cadena {node.value!r}")
        elif isinstance(node, ast.Call):
            found.extend(_dynamic_access(node))
    return found


def _dynamic_access(call: ast.Call) -> list[str]:
    callee = _callee_name(call)
    if callee in DYNAMIC_IMPORTS:
        # Un import dinámico no lo ve ni grimp ni esta lectura: en la API no hay ninguno.
        return [f"{call.lineno}: {callee}(...)"]
    if callee == "getattr":
        # getattr(modulo, "_load_demo_space"): un nombre que no aparece como atributo.
        return [
            f"{call.lineno}: getattr(..., {arg.value!r})"
            for arg in call.args[1:2]
            if isinstance(arg, ast.Constant)
            and isinstance(arg.value, str)
            and (arg.value in FORBIDDEN_IN_API or arg.value.startswith("_"))
        ]
    return []


def _callee_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def authenticated_user_builds(tree: ast.AST) -> list[str]:
    """Construcciones de AuthenticatedUser y copias que le cambian la cuenta."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Con otro nombre, la búsqueda de AuthenticatedUser( no lo vería.
            found.extend(
                f"{node.lineno}: import {alias.name} as {alias.asname}"
                for alias in node.names
                if alias.name == AUTHENTICATED_USER and alias.asname not in (None, alias.name)
            )
        elif isinstance(node, ast.Call):
            callee = _callee_name(node)
            if callee == AUTHENTICATED_USER:
                found.append(f"{node.lineno}: {AUTHENTICATED_USER}(...)")
            elif callee in {"replace", "__replace__"} and any(
                keyword.arg == "tenant_id" for keyword in node.keywords
            ):
                found.append(f"{node.lineno}: {callee}(..., tenant_id=...)")
    return found


def test_la_api_no_usa_el_nucleo_que_carga_cualquier_cuenta():
    offenders = {
        path.relative_to(SRC).as_posix(): uses
        for path in _python_files(API)
        if (uses := forbidden_api_uses(_parse(path)))
    }
    assert offenders == {}, (
        "La API solo carga el espacio de demostración con LoadDemoSpace, que toma la "
        f"cuenta del usuario autenticado (S3-R-03, S3-R-08): {offenders}"
    )


def test_solo_la_validacion_de_sesion_construye_un_usuario_autenticado():
    offenders = {
        rel: builds
        for path in _python_files(SRC)
        if (rel := path.relative_to(SRC).as_posix()) not in ALLOWED_BUILDERS
        if (builds := authenticated_user_builds(_parse(path)))
    }
    assert offenders == {}, (
        "Un AuthenticatedUser solo sale de AuthenticateSession: la cuenta es la de la "
        f"sesión, nunca una elegida por quien llama (RN-10): {offenders}"
    )


def test_la_lista_de_permitidos_sigue_construyendo_el_usuario():
    # Si AuthenticateSession se mueve o cambia de forma, la prueba anterior
    # pasaría sin comprobar nada útil: la lista de permitidos tiene que estar viva.
    for rel in ALLOWED_BUILDERS:
        assert authenticated_user_builds(_parse(SRC / rel)), rel


@pytest.mark.parametrize(
    "source",
    [
        "from kapataz.application.use_cases.load_demo_space import load_demo_space",
        "from kapataz.application.use_cases.load_demo_space import _load_demo_space",
        "from kapataz.application.use_cases import demo_space_loader",
        "from kapataz.application.use_cases.demo_space_loader import load_demo_space as f",
        "import kapataz.application.use_cases.demo_space_loader",
        "import kapataz.application.use_cases as uc\nuc.demo_space_loader.load_demo_space()",
        "importlib.import_module('kapataz.application.use_cases.demo_space_loader')",
        "importlib.import_module('kapataz.application.use_cases.demo_space_' + suffix)",
        "__import__(name)",
        "from kapataz.application.use_cases.load_demo_space import _anything",
        "from .use_cases import _anything",
        "import kapataz.application.use_cases.load_demo_space as m\ngetattr(m, '_load_demo_space')",
        "import kapataz.application.use_cases.load_demo_space as m\nm.load_demo_space()",
    ],
)
def test_el_detector_de_la_api_ve_cada_puerta_de_atras(source):
    assert forbidden_api_uses(ast.parse(source))


@pytest.mark.parametrize(
    "source",
    [
        "AuthenticatedUser(user_id=u, tenant_id=t, email=e, session_id=s)",
        "model.AuthenticatedUser(user_id=u, tenant_id=t, email=e, session_id=s)",
        "from kapataz.domain.accounts.model import AuthenticatedUser as AU",
        "dataclasses.replace(user, tenant_id=other)",
        "replace(user, tenant_id=other)",
        "user.__replace__(tenant_id=other)",
    ],
)
def test_el_detector_ve_cada_forma_de_fabricar_un_usuario(source):
    assert authenticated_user_builds(ast.parse(source))


@pytest.mark.parametrize(
    "source",
    [
        "from kapataz.application.use_cases.load_demo_space import LoadDemoSpace",
        "from kapataz.domain.accounts.model import AuthenticatedUser",
        "def f(user: AuthenticatedUser) -> TenantId:\n    return user.tenant_id",
        "text.replace('a', 'b')",
        "import kapataz.application.use_cases.load_demo_space as m\nm.LoadDemoSpace",
        "log.info('demo_space_loaded', use_case='load_demo_space')",
    ],
)
def test_los_detectores_dejan_pasar_el_uso_legitimo(source):
    tree = ast.parse(source)
    assert forbidden_api_uses(tree) == []
    assert authenticated_user_builds(tree) == []
