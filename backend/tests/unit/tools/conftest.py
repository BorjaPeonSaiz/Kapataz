"""Fixtures del generador de datos sintéticos (ADR-020).

El dataset se construye una vez por sesión, y el render completo, que tarda
unos 5 s, también: lo comparten las pruebas de determinismo y de regeneración.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from synthetic.build import build_dataset
from synthetic.output import render_all
from tests.unit.tools.synthetic_support import EVALS

if TYPE_CHECKING:
    from synthetic.model import SyntheticDataset
    from synthetic.output import RenderedDocument


@pytest.fixture(scope="session")
def dataset() -> SyntheticDataset:
    return build_dataset()


@pytest.fixture(scope="session")
def rendered(dataset: SyntheticDataset) -> list[RenderedDocument]:
    return render_all(dataset)


@pytest.fixture(scope="session")
def truths() -> dict[str, dict[str, Any]]:
    """Verdad de referencia versionada, por id (``electricista/doc-001``)."""
    found = {}
    for path in sorted(EVALS.glob("*/doc-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        found[data["id"]] = data
    return found
