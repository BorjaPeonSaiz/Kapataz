"""Pruebas de ``tools/traceability.py`` con especificaciones y suites de ejemplo.

Ningún RF, RN ni RNF de la especificación trata de la trazabilidad de las
pruebas, así que estas pruebas no llevan marcador ``req``: aparecen en la
matriz como pruebas sin marcador hasta que se decida cómo trazar las
herramientas de calidad.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

TOOL = Path(__file__).resolve().parents[3] / "tools" / "traceability.py"


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("kapataz_traceability", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tr = _load_tool()

SPEC = """\
# Especificación de ejemplo

| ID | Historia | Requisitos |
|---|---|---|
| HU-01 | Como autónomo, quiero importar mis PDF. | RF-IN-01 |

| ID | Requisito |
|---|---|
| RF-IN-01 | Importar PDF. |
| RF-CO-01 | Consultar. |
| RN-01 | Importes en Decimal. |
| RN-F-01 | Numeración correlativa. |
| RNF-01 | Privacidad. |

Texto que menciona RF-XX-99 fuera de una tabla.

| Término | Referencia |
|---|---|
| Cuenta | RF-IN-01 en la segunda columna |
"""

ALL_OWASP = ", ".join(f'"{c}"' for c in tr.OWASP_CATEGORIES)


def _write_suite(tmp_path: Path, tests: dict[str, str], spec: str = SPEC) -> list[str]:
    """Escribe la especificación y las pruebas y devuelve los argumentos de la CLI."""
    spec_path = tmp_path / "docs" / "01-especificacion.md"
    spec_path.parent.mkdir(parents=True)
    spec_path.write_text(spec, encoding="utf-8")
    tests_dir = tmp_path / "backend" / "tests"
    for name, source in tests.items():
        path = tests_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return [
        "--spec",
        str(spec_path),
        "--tests",
        str(tests_dir),
        "--frontend",
        str(tmp_path / "frontend"),
    ]


def _markers(source: str) -> set[tuple[str, str, str]]:
    scan = tr.scan_python_source(source, "tests/test_x.py")
    assert scan.errors == []
    return {(m.kind, m.value, m.test) for m in scan.markers}


def test_lee_los_ids_de_las_filas_de_tabla() -> None:
    spec = tr.parse_spec(SPEC)

    assert spec.requirements == ("RF-IN-01", "RF-CO-01", "RN-01", "RN-F-01", "RNF-01")
    assert spec.user_stories == ("HU-01",)
    assert spec.duplicates == ()


def test_detecta_ids_repetidos_en_la_especificacion() -> None:
    spec = tr.parse_spec(SPEC + "| RN-01 | Otra vez. |\n")

    assert spec.duplicates == ("RN-01",)
    report = tr.build_report(spec, tr.Scan(), "spec")
    assert report.failures(strict=False) == ["1 errores de análisis"]


def test_la_especificacion_real_no_tiene_filas_sin_leer() -> None:
    text = tr.DEFAULT_SPEC.read_text(encoding="utf-8")
    id_like_rows = re.findall(r"^\|\s*(?:HU|RF|RN|RNF)-\S*\s*\|", text, flags=re.MULTILINE)

    spec = tr.parse_spec(text)

    assert spec.duplicates == ()
    assert len(spec.requirements) + len(spec.user_stories) == len(id_like_rows)
    assert {tr.family(r) for r in spec.requirements} == {"RF", "RN", "RNF"}


def test_marcadores_en_funcion_con_varios_ids() -> None:
    source = """
import pytest

@pytest.mark.req("RF-IN-01", "RN-F-01")
@pytest.mark.owasp("A01")
def test_importa() -> None: ...
"""
    assert _markers(source) == {
        ("req", "RF-IN-01", "tests/test_x.py::test_importa"),
        ("req", "RN-F-01", "tests/test_x.py::test_importa"),
        ("owasp", "A01", "tests/test_x.py::test_importa"),
    }


def test_marcadores_en_clase_y_pytestmark_de_clase() -> None:
    source = """
from pytest import mark

@mark.req("RF-CO-01")
class TestConsulta:
    pytestmark = [mark.owasp("LLM01")]

    def test_responde(self) -> None: ...

    @mark.req("RN-01")
    async def test_importes(self) -> None: ...
"""
    assert _markers(source) == {
        ("req", "RF-CO-01", "tests/test_x.py::TestConsulta"),
        ("owasp", "LLM01", "tests/test_x.py::TestConsulta"),
        ("req", "RN-01", "tests/test_x.py::TestConsulta::test_importes"),
    }
    assert tr.scan_python_source(source, "tests/test_x.py").untagged == []


def test_marcadores_en_pytestmark_de_modulo_y_en_param() -> None:
    source = """
import pytest

pytestmark = pytest.mark.req("RNF-01")
pytestmark += [pytest.mark.owasp("A02")]

@pytest.mark.parametrize("n", [pytest.param(1, marks=pytest.mark.req("RN-01"))])
def test_parametrizada(n: int) -> None: ...

def test_sin_marcador_propio() -> None: ...
"""
    scan = tr.scan_python_source(source, "tests/test_x.py")

    assert {(m.kind, m.value, m.test) for m in scan.markers} == {
        ("req", "RNF-01", "tests/test_x.py"),
        ("owasp", "A02", "tests/test_x.py"),
        ("req", "RN-01", "tests/test_x.py::test_parametrizada"),
    }
    assert scan.untagged == []


def test_informa_de_las_pruebas_sin_marcador_req() -> None:
    source = """
import pytest

@pytest.mark.owasp("A01")
def test_solo_owasp() -> None: ...

class TestSinMarcador:
    def test_metodo(self) -> None: ...

class Ayudante:
    def test_no_es_prueba(self) -> None: ...

def ayudante() -> None: ...
"""
    scan = tr.scan_python_source(source, "tests/test_x.py")

    assert scan.untagged == [
        "tests/test_x.py::test_solo_owasp",
        "tests/test_x.py::TestSinMarcador::test_metodo",
    ]


def test_argumento_no_literal_es_un_error() -> None:
    source = """
import pytest
ID = "RN-01"

@pytest.mark.req(ID)
def test_a() -> None: ...

@pytest.mark.req()
def test_b() -> None: ...
"""
    scan = tr.scan_python_source(source, "tests/test_x.py")

    assert len(scan.errors) == 2
    assert "no es una cadena literal" in scan.errors[0]


def test_fichero_que_no_se_puede_analizar_es_un_error() -> None:
    scan = tr.scan_python_source("def test_(:\n", "tests/test_x.py")

    assert len(scan.errors) == 1
    assert "no se puede analizar" in scan.errors[0]


def test_check_falla_si_una_prueba_cita_un_id_inexistente(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _write_suite(
        tmp_path,
        {
            "unit/test_a.py": (
                "import pytest\n\n"
                '@pytest.mark.req("RF-IN-01")\ndef test_ok() -> None: ...\n\n'
                '@pytest.mark.req("RF-XX-99")\ndef test_mal() -> None: ...\n'
            )
        },
    )

    assert tr.main(args) == 0
    assert tr.main([*args, "--check"]) == 1
    out = capsys.readouterr().out
    assert 'req("RF-XX-99") en tests/unit/test_a.py::test_mal' in out
    assert "--check: falla" in out


def test_check_falla_si_una_prueba_cita_una_historia_de_usuario(tmp_path: Path) -> None:
    args = _write_suite(
        tmp_path,
        {"test_a.py": 'import pytest\n\n@pytest.mark.req("HU-01")\ndef test_a() -> None: ...\n'},
    )

    assert tr.main([*args, "--check"]) == 1


def test_check_falla_si_una_categoria_owasp_no_existe(tmp_path: Path) -> None:
    args = _write_suite(
        tmp_path,
        {
            "test_a.py": (
                'import pytest\n\n@pytest.mark.req("RN-01")\n@pytest.mark.owasp("A11")\n'
                "def test_a() -> None: ...\n"
            )
        },
    )

    assert tr.main([*args, "--check"]) == 1


def test_check_sin_strict_tolera_requisitos_sin_prueba(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _write_suite(
        tmp_path,
        {"test_a.py": 'import pytest\n\n@pytest.mark.req("RN-01")\ndef test_a() -> None: ...\n'},
    )

    assert tr.main([*args, "--check"]) == 0
    out = capsys.readouterr().out
    assert "Requisitos con prueba (1 de 5)" in out
    assert "Requisitos sin prueba (4)" in out
    assert "--check: correcto" in out


def test_strict_falla_si_falta_prueba_de_un_requisito(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _write_suite(
        tmp_path,
        {
            "test_a.py": (
                'import pytest\n\n@pytest.mark.req("RF-IN-01", "RF-CO-01", "RN-01", "RN-F-01")\n'
                f"@pytest.mark.owasp({ALL_OWASP})\ndef test_a() -> None: ...\n"
            )
        },
    )

    assert tr.main([*args, "--check", "--strict"]) == 1
    assert "1 requisitos sin prueba" in capsys.readouterr().out


def test_strict_falla_si_falta_una_categoria_owasp(tmp_path: Path) -> None:
    sin_a05 = ", ".join(f'"{c}"' for c in tr.OWASP_CATEGORIES if c != "A05")
    args = _write_suite(
        tmp_path,
        {
            "test_a.py": (
                "import pytest\n\n"
                '@pytest.mark.req("RF-IN-01", "RF-CO-01", "RN-01", "RN-F-01", "RNF-01")\n'
                f"@pytest.mark.owasp({sin_a05})\ndef test_a() -> None: ...\n"
            )
        },
    )

    assert tr.main([*args, "--check"]) == 0
    assert tr.main([*args, "--check", "--strict"]) == 1


def test_strict_pasa_con_todo_cubierto(tmp_path: Path) -> None:
    args = _write_suite(
        tmp_path,
        {
            "test_a.py": (
                "import pytest\n\n"
                '@pytest.mark.req("RF-IN-01", "RF-CO-01", "RN-01", "RN-F-01", "RNF-01")\n'
                f"@pytest.mark.owasp({ALL_OWASP})\ndef test_a() -> None: ...\n"
            )
        },
    )

    assert tr.main([*args, "--check", "--strict"]) == 0


def test_strict_sin_check_es_un_error_de_uso(tmp_path: Path) -> None:
    args = _write_suite(tmp_path, {})

    with pytest.raises(SystemExit) as exc:
        tr.main([*args, "--strict"])

    assert exc.value.code == 2


def test_salida_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = _write_suite(
        tmp_path,
        {"test_a.py": 'import pytest\n\n@pytest.mark.req("RF-ZZ-01")\ndef test_a() -> None: ...\n'},
    )

    assert tr.main([*args, "--json", "--check"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["user_stories"] == ["HU-01"]
    assert len(data["uncovered"]) == 5
    assert data["unknown"][0]["value"] == "RF-ZZ-01"
    assert data["check"]["ok"] is False


def test_lee_la_convencion_del_frontend(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    (frontend / "e2e").mkdir(parents=True)
    (frontend / "src" / "api").mkdir(parents=True)
    (frontend / "node_modules" / "x").mkdir(parents=True)
    (frontend / "e2e" / "chat.spec.ts").write_text(
        "test('envía el mensaje req(\"RF-CO-01\")', async () => {})\n"
        "test('acceso', { annotation: { type: 'req', description: 'RN-01' } }, async () => {})\n",
        encoding="utf-8",
    )
    # Forma de las pruebas de Vitest: título entre comillas dobles e ID entre simples.
    (frontend / "src" / "api" / "client.test.ts").write_text(
        "it(\"envía el token req('RF-AC-01') owasp('A01')\", async () => {})\n"
        'it("sin marcador [RNF-10]", () => {})\n',
        encoding="utf-8",
    )
    (frontend / "node_modules" / "x" / "lib.spec.ts").write_text(
        "test('ajeno req(\"RF-XX-99\")', () => {})\n", encoding="utf-8"
    )

    scan = tr.scan_frontend(frontend)

    assert {(m.kind, m.value, m.test) for m in scan.markers} == {
        ("req", "RF-CO-01", "frontend/e2e/chat.spec.ts:1"),
        ("req", "RN-01", "frontend/e2e/chat.spec.ts:2"),
        ("req", "RF-AC-01", "frontend/src/api/client.test.ts:1"),
        ("owasp", "A01", "frontend/src/api/client.test.ts:1"),
    }
    assert tr.scan_frontend(tmp_path / "no-existe").markers == []
