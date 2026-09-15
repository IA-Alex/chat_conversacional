"""Configuración de logging estructurado para el proceso servidor.

Antes no había ningún ``logging.basicConfig``/``dictConfig`` en el
proyecto: los ``logger.exception``/``logger.warning`` ya sembrados en el
código (adapters, degradación) dependían de que quien lanzara el proceso
configurara logging por su cuenta, así que en la práctica podían no
imprimirse en ningún lado. Se llama una sola vez al arrancar la app HTTP.

Formato JSON por línea (no una librería de terceros: son ~15 líneas y evita
sumar una dependencia solo para esto) para que un colector de logs
(CloudWatch, Loki, Datadog) lo parsee sin reglas ad-hoc.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class _FormateadorJSON(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "nivel": record.levelname,
            "logger": record.name,
            "mensaje": record.getMessage(),
        }
        if record.exc_info:
            payload["excepcion"] = self.formatException(record.exc_info)
        # Campos extra pasados vía logger.info(..., extra={...}), p. ej.
        # session_id, ruta, latencia_ms — sin forzar un esquema fijo.
        for clave, valor in record.__dict__.items():
            if clave in _CAMPOS_ESTANDAR or clave.startswith("_"):
                continue
            payload[clave] = valor
        return json.dumps(payload, ensure_ascii=False, default=str)


_CAMPOS_ESTANDAR = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {"message"}


def configurar_logging(nivel: str = "INFO") -> None:
    """Configura el root logger una sola vez (idempotente)."""
    root = logging.getLogger()
    if getattr(root, "_la_santisima_configurado", False):
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_FormateadorJSON())
    root.handlers = [handler]
    root.setLevel(nivel)
    root._la_santisima_configurado = True  # type: ignore[attr-defined]
