# Patrón de Modales Accesibles

## Objetivo
Centralizar la gestión de diálogos modales en el cliente web con cumplimiento completo de WCAG 2.1 AA.

## Contexto
El proyecto Santa Muerte Conversacional requiere múltiples overlays modales:
- Consentimiento de privacidad (gate obligatorio)
- Errores de arranque del sistema
- Confirmaciones de acciones destructivas
- Futuros diálogos (configuración, ayuda, etc.)

Cada modal debe ser:
- **Operable por teclado** (WCAG 2.1.1)
- **Navegable con Tab cíclico** (WCAG 2.4.3)
- **Cerrable con Escape** (WCAG 2.1.1)
- **Enfocable programáticamente** (WCAG 2.4.3)
- **Semánticamente correcto** (ARIA dialog, aria-modal, etiquetas)
- **Compatible con lectores de pantalla**

## Implementación

### Servicio Centralizado: `ModalService`
Ubicación: `frontend/modal-service.js`

```javascript
// Uso básico
var closeModal = ModalService.show(elemento, {
  ariaLabelledby: 'titulo-del-dialogo',
  ariaDescribedby: 'descripcion-opcional',
  trapFocus: true,
  closeOnEscape: true,
  onClose: function() {
    // Lógica al cerrar con Escape
  }
});

// Para cerrar
closeModal();
```

### API Completa

| Método | Parámetros | Retorno | Descripción |
|--------|------------|---------|-------------|
| `show(element, options)` | `element`: HTMLElement<br>`options`: objeto de configuración | Función de cierre | Muestra un modal, configura ARIA, crea focus trap |
| `closeActive()` | Ninguno | `void` | Cierra el modal activo (top del stack) |
| `closeAll()` | Ninguno | `void` | Cierra todos los modales activos |
| `hasActiveModals()` | Ninguno | `boolean` | Verifica si hay modales activos |
| `activeCount()` | Ninguno | `number` | Número de modales en el stack |

### Opciones de Configuración

```javascript
{
  closeOnEscape: true,           // Cerrar con tecla Escape
  closeOnBackdropClick: false,  // Cerrar al hacer clic fuera
  ariaLabel: null,              // Etiqueta ARIA directa
  ariaLabelledby: null,         // Referencia a elemento que etiqueta
  ariaDescribedby: null,        // Referencia a descripción
  onClose: null,                // Callback al cerrar (Escape/backdrop)
  trapFocus: true               // Implementar focus trap
}
```

### Stack de Modales
El servicio gestiona un stack LIFO con las siguientes características:
- **Z-index automático**: cada nuevo modal recibe z-index incremental
- **Focus management**: guarda y restaura el elemento activo pre-modal
- **Escape global**: la tecla Escape cierra solo el modal superior
- **Cleanup automático**: elimina event listeners al cerrar

## Integración en Componentes Existentes

### 1. Consentimiento de Privacidad
```javascript
function mostrarPantallaConsentimiento(privacidad) {
  return new Promise(function (resolve) {
    var closeModal;
    
    closeModal = ModalService.show(consentOverlay, {
      ariaLabelledby: 'consent-title',
      onClose: function() {
        resolve(); // Continuar si el usuario presiona Escape
      },
      trapFocus: true,
      closeOnEscape: true
    });
    
    // Lógica específica del consentimiento...
  });
}
```

### 2. Error de Arranque
```javascript
function mostrarErrorArranque(mensaje, reintentar) {
  var closeModal;
  
  bootErrorMessage.textContent = mensaje;
  
  bootErrorRetryBtn.onclick = function () {
    if (closeModal) closeModal();
    reintentar();
  };

  closeModal = ModalService.show(bootErrorOverlay, {
    ariaLabelledby: 'boot-error-title',
    ariaDescribedby: 'boot-error-message',
    trapFocus: true,
    closeOnEscape: true,
    onClose: function() {
      reintentar(); // Reintentar también con Escape
    }
  });
}
```

## Atributos ARIA Obligatorios

Cada elemento modal debe incluir en el HTML:

```html
<div id="mi-modal" 
     role="dialog"
     aria-modal="true"
     aria-labelledby="titulo-modal"
     [aria-describedby="descripcion-modal"]>
  <h2 id="titulo-modal">Título del diálogo</h2>
  <p id="descripcion-modal">Descripción opcional</p>
  <!-- Contenido y acciones -->
</div>
```

### Explicación de Atributos
- `role="dialog"`: identifica el elemento como diálogo modal
- `aria-modal="true"`: indica que el contenido detrás es inerte
- `aria-labelledby`: referencia al título (obligatorio para diálogos)
- `aria-describedby`: referencia a descripción (opcional pero recomendado)
- `tabindex="-1"`: en el elemento dialog para recibir foco programático

## Focus Trap (Trampa de Foco)

El servicio implementa un focus trap que:
1. **Enfoca el primer elemento enfocable** al abrir
2. **Cicla el foco con Tab/Shift+Tab** dentro del diálogo
3. **Previene que el foco escape** al contenido inerte
4. **Restaura el foco original** al cerrar

Selector de elementos enfocables: `button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])`

## WCAG 2.1 Cumplido

| Criterio | Cumplimiento | Implementación |
|----------|--------------|----------------|
| **2.1.1 Keyboard** | ✅ | Teclado completo: Tab, Shift+Tab, Escape |
| **2.4.3 Focus Order** | ✅ | Focus trap cíclico, foco inicial al primer elemento |
| **2.4.7 Focus Visible** | ✅ | Estilos de foco nativos del navegador |
| **4.1.2 Name, Role, Value** | ✅ | Atributos ARIA: role, aria-labelledby, aria-modal |
| **1.3.1 Info and Relationships** | ✅ | HTML semántico, relaciones ARIA |
| **3.2.2 On Input** | ✅ | Escape cierra, no dispara acciones no esperadas |

## Tests Automatizados

El script `scripts/verificar_correcciones_ux.py` incluye verificaciones para:

1. **Existencia del servicio**: `ACC-MODAL-SERVICE`
2. **API completa**: `ACC-MODAL-SERVICE-API`, `ACC-MODAL-STACK`, `ACC-FOCUS-TRAP`
3. **Atributos ARIA**: `ACC-CONSENT-ARIA`, `ACC-ERROR-ARIA`
4. **Uso correcto**: `ACC-USE-MODALSERVICE-CONSENT`, `ACC-USE-MODALSERVICE-ERROR`
5. **Eliminación de código viejo**: `ACC-NO-CREARFOCUSTRAP`

## Integración en CI/CD

El workflow de GitHub Actions (`/.github/workflows/ci.yml`) incluye un job `accessibility` que ejecuta las verificaciones en cada push/PR.

## Extensión para Nuevos Diálogos

Para añadir un nuevo diálogo modal:

1. **Crear el HTML** con atributos ARIA obligatorios
2. **Obtener referencia** al elemento en JavaScript
3. **Usar `ModalService.show()`** con opciones apropiadas
4. **Manejar acciones** específicas del diálogo
5. **Probar** con teclado y lectores de pantalla

## Referencias

- [WCAG 2.1 Guideline 2.1 - Keyboard Accessible](https://www.w3.org/WAI/WCAG21/Understanding/keyboard-accessible)
- [ARIA Authoring Practices - Dialog Modal](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)
- [MDN - :focus-visible](https://developer.mozilla.org/en-US/docs/Web/CSS/:focus-visible)
- [A11Y Project - Modal Dialog](https://www.a11yproject.com/patterns/dialog-modal/)

---

**Versión**: 1.0.0  
**Última actualización**: 2026-09-17  
**Responsable**: Arquitectura Frontend