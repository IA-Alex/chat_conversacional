from pathlib import Path

from src.la_santisima_conversacional.infrastructure.purga_estado import (
    leer_estado,
    registrar_resultado,
)


def test_leer_estado_sin_archivo_devuelve_none(tmp_path: Path) -> None:
    assert leer_estado(tmp_path / "no-existe.json") is None


def test_registrar_y_leer_estado(tmp_path: Path) -> None:
    ruta = tmp_path / "purga_estado.json"
    registrar_resultado(ruta, registros_borrados=42, exitosa=True)

    estado = leer_estado(ruta)

    assert estado is not None
    assert estado["registros_borrados"] == 42
    assert estado["exitosa"] is True
    assert estado["timestamp"] > 0


def test_registrar_resultado_crea_directorios_padre(tmp_path: Path) -> None:
    ruta = tmp_path / "anidado" / "purga_estado.json"
    registrar_resultado(ruta, registros_borrados=0, exitosa=False)
    assert leer_estado(ruta) == {
        "timestamp": leer_estado(ruta)["timestamp"],
        "registros_borrados": 0,
        "exitosa": False,
    }


def test_leer_estado_json_corrupto_devuelve_none(tmp_path: Path) -> None:
    ruta = tmp_path / "purga_estado.json"
    ruta.write_text("no es json", encoding="utf-8")
    assert leer_estado(ruta) is None
