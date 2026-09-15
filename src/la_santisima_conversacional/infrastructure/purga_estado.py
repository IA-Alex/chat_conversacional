"""Registro del último resultado de la purga de retención (scripts/purgar_retencion.py).

La purga corre fuera del proceso HTTP (systemd timer / cron, ver
scripts/systemd/), así que no puede simplemente incrementar una métrica
Prometheus en memoria del servidor web — esa memoria vive en otro
proceso. En vez de sumar un pushgateway (dependencia y pieza operativa
extra), la purga escribe su resultado en un archivo JSON pequeño, y
``GET /metrics/health`` (y ``GET /metrics``, vía
``infrastructure.metrics``) lo leen en cada scrape. Si la purga deja de
correr, el timestamp simplemente deja de avanzar — eso es lo que dispara
la alerta (ver docs/runbooks/INCIDENT_RESPONSE.md).
"""

import json
import os
import time
from pathlib import Path
from typing import Optional, TypedDict


class EstadoPurga(TypedDict):
    timestamp: float
    registros_borrados: int
    exitosa: bool


def registrar_resultado(ruta_estado: Path, registros_borrados: int, exitosa: bool = True) -> None:
    ruta_estado.parent.mkdir(parents=True, exist_ok=True)
    contenido = json.dumps(
        {
            "timestamp": time.time(),
            "registros_borrados": registros_borrados,
            "exitosa": exitosa,
        }
    )
    # Escritura atómica (temp + rename): ``GET /metrics/health`` lee este
    # archivo desde otro proceso en cada scrape de Prometheus; un
    # write_text() directo puede dejarlo leer a mitad de escritura.
    temporal = ruta_estado.with_suffix(ruta_estado.suffix + ".tmp")
    temporal.write_text(contenido, encoding="utf-8")
    os.replace(temporal, ruta_estado)


def leer_estado(ruta_estado: Path) -> Optional[EstadoPurga]:
    try:
        contenido = ruta_estado.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        datos = json.loads(contenido)
        return EstadoPurga(
            timestamp=float(datos["timestamp"]),
            registros_borrados=int(datos["registros_borrados"]),
            exitosa=bool(datos["exitosa"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
