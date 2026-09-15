"""Estado de observabilidad del proceso HTTP.

Módulo aparte y no variables sueltas en ``http_api.py`` por dos razones
concretas de calidad: (1) ``http_api.py`` ya está en el límite de tamaño del
proyecto y cada constante de estado que se le suma lo empuja más; (2) el
estado mutable necesita ``global`` para modificarse desde una función, y
``pylint`` marca cada ``global`` (``W0603``). Encapsularlo en una clase con
un método elimina el ``global`` y, de paso, deja el estado testeable sin
tocar el módulo.
"""

import logging
import threading
from typing import TYPE_CHECKING, Dict, Optional

from ..infrastructure import metrics

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

# Estados posibles de ``estado_redis``. Constantes y no literales sueltos:
# el valor se compara en tests y se documenta en HEALTH_CHECKS.md, así que
# un typo en uno de los tres sitios dejaría de coincidir en silencio.
REDIS_DISABLED = "disabled"
REDIS_OK = "ok"
REDIS_UNREACHABLE = "unreachable"

# Tope del mapa de sesiones. Sin esto es un ``dict`` que crece con cada
# sesión creada y nunca se vacía — exactamente el memory leak que el
# escenario de carga ``tests/load/`` está pensado para detectar. Las
# sesiones reiniciadas salen del mapa (ver ``cerrar``), pero una sesión que
# simplemente se abandona (el usuario cierra la app) no dispara ningún
# request que lo registre, así que sin cota el mapa solo crece. Al superar
# el tope se descartan las más antiguas (mismo criterio LRU-por-antigüedad
# que ``ConversationRepositoryMemory``): la métrica de sesiones activas
# pasa a ser una cota inferior en vez de un valor exacto, lo cual es
# aceptable para operar (un abandono no es un incidente) y a cambio
# garantiza memoria acotada. El tamaño real está en el historial de la BD
# (``santisima_db_historial_filas``).
MAX_SESIONES_SEGUIDAS = 10_000


class EstadoObservabilidad:
    """Estado del proceso que alimenta las métricas de ``/metrics/health``.

    Sustituye a tres variables globales sueltas (sesiones abiertas, último
    estado del LLM, conteo de filas) por un objeto con métodos, para que:
    - modificar el estado no requiera ``global`` (``pylint`` W0603);
    - el estado sea explícito y no se mezcle con constantes de módulo
      (``pylint`` C0103, que espera UPPER_CASE para todo lo de nivel módulo).
    """

    def __init__(self) -> None:
        # ``session_id -> momento de creación`` (``time.monotonic()``).
        self._sesiones: Dict[str, float] = {}
        # FastAPI corre los handlers ``def`` sync (crear/cerrar sesión) en un
        # threadpool: sin este lock, dos requests concurrentes pueden mutar
        # ``_sesiones`` mientras otra lo itera en ``sorted()`` de abajo y
        # lanzar ``RuntimeError: dictionary changed size during iteration``.
        self._lock = threading.Lock()
        # Último valor publicado en ``santisima_llm_degradado``. ``None`` =
        # todavía no se publicó nada, así que el primer scrape que vea
        # degradado cuenta como una entrada (correcto: el proceso puede
        # arrancar degradado).
        self._ultimo_degradado: Optional[bool] = None

    # --- Sesiones ---------------------------------------------------------

    @property
    def sesiones_activas(self) -> int:
        return len(self._sesiones)

    def registrar_sesion(self, session_id: str, ahora: float) -> None:
        """Marca una sesión como abierta y publica el gauge de activas.

        Se llama al crear un ``session_id`` (``POST /api/v1/sesiones``), que
        es el único punto donde una sesión conversacional realmente empieza.

        ``ahora`` es ``time.monotonic()`` — inyectado y no llamado aquí para
        que los tests puedan controlar el paso del tiempo sin ``sleep``.
        """
        with self._lock:
            if len(self._sesiones) >= MAX_SESIONES_SEGUIDAS:
                # Ver MAX_SESIONES_SEGUIDAS: descartar las más antiguas antes
                # de admitir una nueva mantiene la memoria acotada sin
                # necesitar un job de limpieza aparte.
                a_descartar = len(self._sesiones) - MAX_SESIONES_SEGUIDAS + 1
                for vieja in sorted(self._sesiones, key=self._sesiones.__getitem__)[:a_descartar]:
                    self._sesiones.pop(vieja, None)
            self._sesiones[session_id] = ahora
            total = len(self._sesiones)
        metrics.active_sessions.set(total)

    def cerrar_sesion(self, session_id: str, ahora: float) -> None:
        """Cierra una sesión, observando su duración.

        Se llama al reiniciar (``POST /api/v1/sesiones/{id}/reiniciar``), que
        es el final explícito de una sesión. Si la sesión no estaba en el
        mapa (creada antes de un reinicio del proceso, o ya descartada por
        el tope), NO se observa duración: registrar una duración inventada
        (p. ej. 0) sesgaría el p50/p95 hacia abajo y haría parecer que las
        sesiones duran segundos cuando el dato simplemente no existe.
        """
        with self._lock:
            inicio = self._sesiones.pop(session_id, None)
            total = len(self._sesiones)
        metrics.active_sessions.set(total)
        if inicio is not None:
            metrics.session_duration_seconds.observe(ahora - inicio)

    # --- Degradación del LLM ---------------------------------------------

    def actualizar_estado_llm(self, degradado: bool) -> None:
        """Publica el gauge de degradación y cuenta las entradas a degradado.

        ``santisima_llm_degradado`` (gauge) es el ESTADO actual;
        ``santisima_llm_degradation_events_total`` (counter) cuenta cada
        TRANSICIÓN a degradado. Un gauge no permite distinguir "lleva
        degradado desde el arranque" de "se degradó y se recuperó 40 veces
        en la última hora", y esa diferencia decide si hay que intervenir.
        """
        metrics.llm_degradado.set(1 if degradado else 0)
        if degradado and self._ultimo_degradado is not True:
            metrics.llm_degradation_events_total.inc()
            logger.error(
                "El motor de IA entró en modo degradado (fallback genérico). "
                "Ver docs/runbooks/TROUBLESHOOTING.md#llm-degraded."
            )
        elif not degradado and self._ultimo_degradado is True:
            logger.info("El motor de IA se recuperó de modo degradado.")
        self._ultimo_degradado = degradado


def estado() -> EstadoObservabilidad:
    """Instancia única por proceso (``http_api._lifespan`` la reemplaza por app)."""
    return _ESTADO


_ESTADO = EstadoObservabilidad()


class ContenedorEstado:
    """Contenedor mutable de un ``EstadoObservabilidad``.

    Existe para poder cambiar el estado vigente del proceso sin usar
    ``global`` (que ``pylint`` marca como ``W0603`` y que este proyecto no
    usa en ningún módulo — ver el comentario de ``_lifespan`` en
    ``http_api.py``): en vez de reasignar una variable de módulo, se muta el
    contenido de este objeto, que sí es una variable de módulo constante.
    """

    def __init__(self) -> None:
        self._estado = EstadoObservabilidad()

    def get(self) -> EstadoObservabilidad:
        return self._estado

    def set(self, nuevo: EstadoObservabilidad) -> None:
        self._estado = nuevo


def estado_redis(settings: "Settings") -> str:
    """PING al Redis del rate limiter compartido. Devuelve un estado legible.

    Solo lo usa ``GET /metrics/health`` (bajo demanda, para un humano), nunca
    el camino de un request de mensajes: un PING por request agregaría una
    ida y vuelta de red al camino caliente solo para alimentar una métrica
    que se lee cada 15 s.

    - ``"disabled"``: ``usar_redis_rate_limit=False``. NO es un problema —
      es la configuración correcta en single-instance (el limitador en
      memoria no necesita Redis). No intentar "arreglarlo" habilitando
      Redis sin haber migrado también a Postgres (ver SCALING.md).
    - ``"ok"``: PING respondió. Rate limiter compartido operativo.
    - ``"unreachable"``: configurado pero no responde. **Estado peligroso**:
      con ``usar_redis_rate_limit=True``, cada request que toca el limitador
      depende de Redis; si está caído, el rate limit no se aplica de forma
      coordinada y el cupo del LLM queda expuesto. Ver INCIDENT_RESPONSE.md.
    """
    if not settings.usar_redis_rate_limit:
        return REDIS_DISABLED
    if not settings.redis_url:
        return REDIS_UNREACHABLE

    # Se instancia LimitadorTasaRedis (no un cliente redis suelto) para
    # reutilizar exactamente la misma config de conexión que usa el rate
    # limit real — un PING que responda en una conexión distinta a la del
    # limitador no probaría nada sobre el componente que importa.
    try:
        from ..infrastructure.rate_limit import LimitadorTasaRedis  # noqa: PLC0415

        limitador = LimitadorTasaRedis(
            1, ventana_segundos=60.0, redis_url=settings.redis_url, prefijo_clave="healthcheck"
        )
        cliente = getattr(limitador, "_cliente", None)
        if cliente is None:
            metrics.redis_up.set(0)
            return REDIS_UNREACHABLE
        cliente.ping()
        metrics.redis_up.set(1)
        return REDIS_OK
    except Exception:  # noqa: BLE001 — el endpoint de salud nunca debe fallar por esto
        logger.warning("Redis configurado pero no responde a PING.", exc_info=True)
        metrics.redis_up.set(0)
        return REDIS_UNREACHABLE
