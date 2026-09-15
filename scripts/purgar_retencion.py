#!/usr/bin/env python3
"""Purga mensajes fuera de la ventana de retención configurada.

Implementa la política de minimización de datos descrita en
``docs/privacidad.md``: sin este job, ``SQLiteConversationRepository``
nunca borra nada por sí sola (``purgar_expirados`` existe como método,
pero nadie lo llamaba). Pensado para ejecutarse periódicamente —cron,
systemd timer, tarea programada del orquestador— no en el camino de cada
request.

Uso:
    python scripts/purgar_retencion.py
    python scripts/purgar_retencion.py --dias 30 --db-path otra.db

Ejemplo de cron (todos los días a las 03:00):
    0 3 * * * cd /ruta/al/proyecto && .venv/bin/python scripts/purgar_retencion.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from la_santisima_conversacional.config import get_settings  # noqa: E402
from la_santisima_conversacional.infrastructure.logging_config import (  # noqa: E402
    configurar_logging,
)
from la_santisima_conversacional.infrastructure.repositories import (  # noqa: E402
    SQLiteConversationRepository,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dias", type=int, default=None, help="Sobrescribe SANTISIMA_RETENCION_DIAS.")
    parser.add_argument("--db-path", default=None, help="Sobrescribe SANTISIMA_SQLITE_DB_PATH.")
    args = parser.parse_args()

    configurar_logging("INFO")
    settings = get_settings()
    repo = SQLiteConversationRepository(
        db_path=args.db_path or settings.sqlite_db_path,
        clave_cifrado=settings.clave_cifrado,
        retencion_dias=args.dias or settings.retencion_dias,
    )
    borradas = repo.purgar_expirados()
    print(f"Purgadas {borradas} filas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
