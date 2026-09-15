"""Rate limiting por API key (ventana deslizante en memoria).

Antes no existía ningún límite: un único endpoint sin autenticación ni
límites de tasa es una factura abierta al proveedor del LLM y un vector
de DoS trivial (bucle simple de requests). Este limitador es intencional-
mente simple (in-memory, sin dependencia externa) porque cubre el caso de
un solo proceso/instancia.

LIMITACIÓN CONOCIDA: en un despliegue con más de una instancia detrás de
un load balancer, cada instancia lleva su propio conteo, así que el
límite real efectivo es ``rate_limit_por_minuto * n_instancias``. Si el
backend escala horizontalmente, este limitador debe reemplazarse por uno
respaldado en Redis (p. ej. `slowapi` con storage Redis, o
`redis-py` + script Lua de ventana deslizante) — se documenta aquí en vez
de ocultarlo para que la migración sea una decisión consciente, no un
descubrimiento en producción.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Protocol


class LimitadorTasaProtocolo(Protocol):
    """Contrato común a ``LimitadorTasa`` y ``LimitadorTasaRedis``: ambas
    implementan ``permitir(clave) -> bool`` con el mismo significado, pero
    no comparten jerarquía de clases (evitar herencia entre un backend en
    memoria y uno respaldado en Redis, que no comparten estado interno ni
    justifican una base común más allá de la firma). Este Protocol es lo
    que debe usarse como tipo en cualquier lugar que solo necesite llamar
    ``permitir`` sin importar cuál de las dos implementaciones recibe."""

    def permitir(self, clave: str) -> bool: ...


class LimitadorTasa:
    """Ventana deslizante de ``limite`` eventos por ``ventana_segundos``, por clave."""

    def __init__(self, limite: int, ventana_segundos: float = 60.0) -> None:
        self.limite = limite
        self.ventana_segundos = ventana_segundos
        self._eventos: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def permitir(self, clave: str) -> bool:
        """Registra un intento para ``clave`` y devuelve si está dentro del límite."""
        ahora = time.monotonic()
        with self._lock:
            eventos = self._eventos[clave]
            limite_inferior = ahora - self.ventana_segundos
            while eventos and eventos[0] < limite_inferior:
                eventos.popleft()
            if len(eventos) >= self.limite:
                return False
            eventos.append(ahora)
            return True


# Script Lua: hace ZREMRANGEBYSCORE (descarta eventos fuera de ventana) +
# ZCARD (cuenta los que quedan) + ZADD condicional + EXPIRE en una sola
# operación atómica del lado de Redis. Necesario porque, a diferencia de
# LimitadorTasa (protegido por un único threading.Lock en un solo
# proceso), aquí varias instancias del backend pueden llamar `permitir`
# para la misma clave al mismo tiempo: sin atomicidad, dos instancias
# podrían leer "9 de 10" simultáneamente y ambas insertar su evento 10,
# dejando pasar 11 en vez de 10 (race condition clásica de check-then-act
# distribuido).
_SCRIPT_VENTANA_DESLIZANTE = """
local clave = KEYS[1]
local ahora = tonumber(ARGV[1])
local ventana_ms = tonumber(ARGV[2])
local limite = tonumber(ARGV[3])
local limite_inferior = ahora - ventana_ms

redis.call('ZREMRANGEBYSCORE', clave, '-inf', limite_inferior)
local conteo = redis.call('ZCARD', clave)
if conteo >= limite then
    return 0
end
redis.call('ZADD', clave, ahora, ahora .. '-' .. redis.call('INCR', clave .. ':seq'))
redis.call('PEXPIRE', clave, ventana_ms)
redis.call('PEXPIRE', clave .. ':seq', ventana_ms)
return 1
"""


class LimitadorTasaRedis:
    """Igual contrato que ``LimitadorTasa`` (``permitir(clave) -> bool``),
    respaldado en Redis para que el límite sea correcto entre varias
    instancias del backend.

    Ver README "Escalar a múltiples instancias": ``LimitadorTasa`` (en
    memoria) es correcto con una sola instancia; con más de una, cada
    instancia cuenta por su cuenta y el límite real efectivo termina
    siendo ``limite * n_instancias``. Esta clase resuelve exactamente eso
    y solo eso — se activa con ``Settings.usar_redis_rate_limit``, apagada
    por defecto.

    ``redis`` se importa perezosamente en el constructor (no al nivel del
    módulo) para no forzar la dependencia cuando la funcionalidad está
    apagada, igual que ``PostgresConversationRepository`` con ``psycopg``.
    """

    def __init__(
        self,
        limite: int,
        ventana_segundos: float,
        redis_url: str,
        prefijo_clave: str = "ratelimit",
    ) -> None:
        try:
            import redis
        except ImportError as exc:
            raise ImportError(
                "LimitadorTasaRedis requiere el extra 'redis' (pip install -e '.[redis]')."
            ) from exc
        self.limite = limite
        self.ventana_segundos = ventana_segundos
        self._prefijo_clave = prefijo_clave
        self._cliente = redis.Redis.from_url(redis_url, decode_responses=True)
        self._script = self._cliente.register_script(_SCRIPT_VENTANA_DESLIZANTE)

    def permitir(self, clave: str) -> bool:
        ahora_ms = time.time() * 1000
        ventana_ms = self.ventana_segundos * 1000
        resultado = self._script(
            # prefijo_clave separa espacios de claves de limitadores
            # distintos (mensajes por device_id vs. registros por IP) para
            # que no puedan chocar entre sí en el mismo Redis.
            keys=[f"{self._prefijo_clave}:{clave}"],
            args=[ahora_ms, ventana_ms, self.limite],
        )
        return bool(resultado)
