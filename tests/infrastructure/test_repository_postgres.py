"""Tests de integración para PostgresConversationRepository.

Requieren un Postgres real y alcanzable (no se mockea psycopg): a
diferencia de SQLite, el valor de este repositorio está en su
comportamiento bajo un servidor de verdad (tipos TIMESTAMPTZ, %s como
placeholder, etc.), así que un mock de la conexión daría falsa confianza.

Se saltan automáticamente si no hay Postgres disponible en
``TEST_POSTGRES_DSN`` (o el default de desarrollo local) — no rompen CI en
entornos sin Postgres, consistente con que esta funcionalidad está apagada
por defecto (ver Settings.usar_postgres).

Levantar un Postgres local para correr estos tests:
    initdb -D /tmp/pgdata -U testuser -A trust
    pg_ctl -D /tmp/pgdata -l /tmp/pg.log -o "-p 5432 -k /tmp" start
    createdb -h /tmp -p 5432 -U testuser la_santisima_test
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

psycopg = pytest.importorskip("psycopg", reason="requiere el extra 'postgres'")

from la_santisima_conversacional.domain import Message  # noqa: E402
from la_santisima_conversacional.infrastructure.repositories import (  # noqa: E402
    PostgresConversationRepository,
)

_DSN = os.environ.get(
    "TEST_POSTGRES_DSN", "postgresql://postgres:postgres@127.0.0.1:5432/la_santisima_test"
)


def _postgres_disponible() -> bool:
    try:
        with psycopg.connect(_DSN, connect_timeout=2):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_disponible(),
    reason=f"Postgres no disponible en {_DSN} (ver docstring del módulo).",
)


@pytest.fixture
def repo():
    """Cada test usa una tabla limpia: TRUNCATE en vez de crear una DB por test."""
    r = PostgresConversationRepository(dsn=_DSN)
    with psycopg.connect(_DSN, autocommit=True) as conn:
        conn.execute("TRUNCATE TABLE messages")
    return r


class TestPostgresConversationRepository:
    def test_get_history_empty(self, repo):
        assert repo.get_history("s1") == []

    def test_save_and_get_message_preserva_orden(self, repo):
        repo.save_message("s1", Message(role="user", content="uno"))
        repo.save_message("s1", Message(role="assistant", content="dos"))
        historial = repo.get_history("s1")
        assert [m.content for m in historial] == ["uno", "dos"]

    def test_sesiones_distintas_no_se_mezclan(self, repo):
        repo.save_message("s1", Message(role="user", content="de s1"))
        repo.save_message("s2", Message(role="user", content="de s2"))
        assert [m.content for m in repo.get_history("s1")] == ["de s1"]
        assert [m.content for m in repo.get_history("s2")] == ["de s2"]

    def test_clear_history(self, repo):
        repo.save_message("s1", Message(role="user", content="hola"))
        repo.clear_history("s1")
        assert repo.get_history("s1") == []

    def test_save_and_get_resumen_upsert(self, repo):
        repo.save_resumen("s1", "version 1")
        repo.save_resumen("s1", "version 2")
        assert repo.get_resumen("s1") == "version 2"
        systems = [m for m in repo.get_history("s1") if m.role == "system"]
        assert len(systems) == 1

    def test_get_resumen_vacio_si_no_existe(self, repo):
        assert repo.get_resumen("no-existe") == ""

    def test_cifrado_en_reposo(self):
        """El contenido debe ser ilegible directamente en la tabla cuando
        se configura clave_cifrado, y descifrarse correctamente al leer
        vía el repositorio."""
        from cryptography.fernet import Fernet

        clave_cifrado = Fernet.generate_key().decode()
        repo_cifrado = PostgresConversationRepository(dsn=_DSN, clave_cifrado=clave_cifrado)
        with psycopg.connect(_DSN, autocommit=True) as conn:
            conn.execute("TRUNCATE TABLE messages")

        session_id = f"s-{uuid.uuid4()}"
        repo_cifrado.save_message(session_id, Message(role="user", content="secreto devocional"))

        with psycopg.connect(_DSN) as conn:
            cursor = conn.execute(
                "SELECT content FROM messages WHERE session_id = %s", (session_id,)
            )
            contenido_crudo = cursor.fetchone()[0]
        assert "secreto devocional" not in contenido_crudo

        assert repo_cifrado.get_history(session_id)[0].content == "secreto devocional"

    def test_purgar_expirados_borra_solo_mensajes_viejos(self, repo):
        session_id = f"s-{uuid.uuid4()}"
        with psycopg.connect(_DSN, autocommit=True) as conn:
            viejo = datetime.now(timezone.utc) - timedelta(days=100)
            reciente = datetime.now(timezone.utc)
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) "
                "VALUES (%s, 'user', 'viejo', %s), (%s, 'user', 'reciente', %s)",
                (session_id, viejo, session_id, reciente),
            )

        borradas = repo.purgar_expirados(retencion_dias=90)
        assert borradas == 1
        restante = [m.content for m in repo.get_history(session_id)]
        assert restante == ["reciente"]
