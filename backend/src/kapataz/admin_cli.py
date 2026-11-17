"""CLI de administración ``kapataz-admin``.

``kapataz-admin create-user --email ana@ejemplo.es`` crea una cuenta de
cortesía ya verificada (RN-13) y pide la contraseña por la entrada estándar.
Sirve para probar en producción sin SMTP.
"""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence
from typing import TextIO

from kapataz.bootstrap import build_container
from kapataz.domain.errors import DomainError
from kapataz.infrastructure.logging.setup import configure_logging
from kapataz.infrastructure.settings import Settings

EXIT_OK = 0
EXIT_ERROR = 1


def _read_password(stdin: TextIO) -> str:
    if stdin.isatty():
        first = getpass.getpass("Contraseña: ")
        second = getpass.getpass("Repite la contraseña: ")
        if first != second:
            msg = "Las contraseñas no coinciden."
            raise ValueError(msg)
        return first
    # Sin terminal (por ejemplo, con una tubería): una línea, sin el salto final.
    return stdin.readline().rstrip("\r\n")


async def _create_user(settings: Settings, email: str, password: str) -> str:
    container = build_container(settings)
    try:
        user_id = await container.services.create_courtesy_account.execute(email, password)
    finally:
        await container.aclose()
    return str(user_id)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kapataz-admin", description="Administración de Kapataz")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser(
        "create-user", help="Crea una cuenta de cortesía ya verificada (RN-13)."
    )
    create.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    configure_logging()
    try:
        password = _read_password(sys.stdin)
        settings = Settings()
        user_id = asyncio.run(_create_user(settings, args.email, password))
    except (DomainError, ValueError) as error:
        sys.stderr.write(f"No se ha creado la cuenta: {error}\n")
        return EXIT_ERROR
    sys.stdout.write(f"Cuenta creada. user_id={user_id}\n")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
