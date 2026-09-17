"""
Capa de aplicación - Casos de uso y servicios

Contiene la lógica de aplicación que coordina el flujo entre:
- La presentación (entrada/salida)
- El dominio (lógica de negocio)
- La infraestructura (implementaciones concretas)
"""

from .casos_de_uso import CasoDeUsoResponderMensaje

__all__ = ["CasoDeUsoResponderMensaje"]
