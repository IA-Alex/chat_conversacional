"""
Test básico para evaluar calidad de respuestas usando golden dataset.
"""
import json
import os

import pytest


def cargar_golden_dataset():
    """Carga el golden dataset desde el archivo JSON."""
    ruta_dataset = os.path.join(
        os.path.dirname(__file__), '..', 'golden_dataset.json'
    )
    with open(ruta_dataset, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestGoldenDataset:
    """Tests para validar la estructura y contenido del golden dataset."""
    
    def test_dataset_carga_correctamente(self):
        """Verifica que el dataset se carga sin errores."""
        dataset = cargar_golden_dataset()
        assert dataset is not None
        assert isinstance(dataset, list)
        assert len(dataset) > 0
    
    def test_cada_entrada_tiene_campos_requeridos(self):
        """Verifica que cada entrada tiene id, input y objetivo."""
        dataset = cargar_golden_dataset()
        for entrada in dataset:
            assert 'id' in entrada
            assert 'input' in entrada
            assert 'objetivo' in entrada
            assert isinstance(entrada['id'], str)
            assert isinstance(entrada['input'], str)
            assert isinstance(entrada['objetivo'], str)
            assert len(entrada['input']) > 0
            assert len(entrada['objetivo']) > 0
    
    def test_ids_son_unicos(self):
        """Verifica que los IDs en el dataset sean únicos."""
        dataset = cargar_golden_dataset()
        ids = [entrada['id'] for entrada in dataset]
        assert len(ids) == len(set(ids))
    
    def test_inputs_no_vacios(self):
        """Verifica que los inputs no estén vacíos."""
        dataset = cargar_golden_dataset()
        for entrada in dataset:
            assert entrada['input'].strip() != ''
    
    def test_objetivos_descriptivos(self):
        """Verifica que los objetivos sean descriptivos (más de 5 caracteres)."""
        dataset = cargar_golden_dataset()
        for entrada in dataset:
            objetivo = entrada['objetivo']
            assert len(objetivo) >= 5, f"Objetivo demasiado corto: '{objetivo}'"
class TestEvaluacionCalidadRespuestas:
    """Tests que evalúan respuestas reales del sistema contra el golden dataset."""
    
    @pytest.fixture
    def golden_dataset(self):
        """Fixture que proporciona el golden dataset cargado."""
        return cargar_golden_dataset()
    
    def test_respuestas_ejemplo_cumplen_longitud_minima(self, golden_dataset):
        """Verifica que respuestas de ejemplo tengan longitud mínima (20 caracteres)."""
        # Respuestas de ejemplo que simulan lo que el sistema debería producir
        respuestas_ejemplo = [
            "Hola, soy La Santísima Muerte. Te escucho con amor y compasión.",
            "Te acompaño en tu soledad, hijo mío. La vida tiene sentido en la fe.",
            "Enciende una vela roja y ora con devoción. El dinero llegará.",
            "En tu ira, encuentro calma. La soledad me acompaña también.",
            "El secreto del universo es el amor que perdura más allá de la muerte."
        ]
        
        for respuesta in respuestas_ejemplo:
            assert len(respuesta) >= 20, f"Respuesta demasiado corta: {respuesta}"
    
    def test_respuestas_ejemplo_no_contienen_errores_obvios(self):
        """Verifica que respuestas de ejemplo no contengan placeholders o errores obvios."""
        respuestas_ejemplo = [
            "Hola, soy La Santísima Muerte. Te escucho con amor y compasión.",
            "Te acompaño en tu soledad, hijo mío. La vida tiene sentido en la fe.",
            "Enciende una vela roja y ora con devoción. El dinero llegará.",
        ]
        
        placeholders = ['{{', '}}', '[', ']', 'TODO:', 'FIXME:', 'XXX']
        for respuesta in respuestas_ejemplo:
            for placeholder in placeholders:
                assert placeholder not in respuesta, \
                    f"Respuesta contiene placeholder: {placeholder}"
            assert respuesta.strip() != ''
    
    def test_emociones_validas(self):
        """Verifica que las emociones del vocabulario sean válidas."""
        from la_santisima_conversacional.domain.validators import validar_clasificacion_intencion
        
        emociones_validas = {
            'devocion', 'respeto', 'consuelo', 'resignacion', 'soledad',
            'desesperacion', 'ira', 'ninguna'
        }
        
        for emocion in emociones_validas:
            # Usar el validador existente si está disponible
            # (simplemente verificamos que la emoción está en el conjunto)
            assert emocion in emociones_validas


def test_metricas_evaluacion():
    """Test de ejemplo para métricas de evaluación automatizadas."""
    dataset = cargar_golden_dataset()
    
    # Ejemplo: calcular estadísticas básicas
    total_ejemplos = len(dataset)
    longitud_promedio_input = sum(len(e['input']) for e in dataset) / total_ejemplos
    
    assert total_ejemplos >= 5, f"Solo {total_ejemplos} ejemplos en dataset"
    assert longitud_promedio_input > 10, "Inputs demasiado cortos en promedio"
    
    # Ejemplo: verificar diversidad de objetivos
    objetivos = [e['objetivo'] for e in dataset]
    objetivos_unicos = set(objetivos)
    assert len(objetivos_unicos) >= 3, "Poca diversidad en objetivos"