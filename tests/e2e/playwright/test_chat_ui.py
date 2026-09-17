"""
Test de UI con Playwright para el frontend de La Santísima Muerte.
"""
import pytest


@pytest.mark.playwright
def test_playwright_functional(page):
    """Test de humo para verificar que Playwright funciona correctamente."""
    # Navegar a una página en blanco
    page.goto("about:blank")
    assert page.url == "about:blank"
    # Verificar que podemos ejecutar JavaScript y obtener el título
    title = page.title()
    assert title == ""
    # Asegurar que page.locator funciona
    assert page.locator("body").count() == 1
    # Podemos también probar interacción básica: establecer contenido y leerlo
    page.set_content("<h1>Test La Santísima Muerte</h1>")
    assert page.locator("h1").text_content() == "Test La Santísima Muerte"
    # Esto confirma que Playwright está operativo y listo para tests más complejos