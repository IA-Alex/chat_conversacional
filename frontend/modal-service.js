/**
 * Servicio centralizado de gestión de modales accesibles
 * 
 * Proporciona:
 * - Gestión de stack de modales (z-index automático)
 * - Focus trap (WCAG 2.1.1, 2.4.3)
 * - Manejo de tecla Escape
 * - Atributos ARIA automáticos
 * - Compatibilidad con overlays existentes
 * 
 * @version 1.0.0
 * @license MIT
 */

(function () {
  'use strict';

  /**
   * Servicio singleton de modales
   * @type {Object}
   */
  var ModalService = window.ModalService || {};

  /**
   * Stack de modales activos (LIFO)
   * @type {Array<{element: HTMLElement, cleanup: Function}>}
   */
  var modalStack = [];

  /**
   * Z-index base para modales
   * @constant {number}
   */
  var BASE_Z_INDEX = 1000;

  /**
   * Elemento activo antes de abrir cualquier modal
   * @type {HTMLElement|null}
   */
  var previouslyActiveElement = null;

  /**
   * Selector de elementos enfocables
   * @constant {string}
   */
  var FOCUSABLE_SELECTOR = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

  /**
   * Crea un focus trap para un diálogo modal
   * @param {HTMLElement} dialog - Elemento del diálogo
   * @param {Function} [onClose] - Callback al cerrar con Escape
   * @returns {Function} Función de limpieza
   */
  function createFocusTrap(dialog, onClose) {
    var focusable = Array.from(dialog.querySelectorAll(FOCUSABLE_SELECTOR));
    var firstFocusable = focusable[0] || dialog;
    var lastFocusable = focusable[focusable.length - 1] || dialog;

    // Enfocar el primer elemento enfocable
    if (firstFocusable) {
      setTimeout(function () { firstFocusable.focus(); }, 0);
    }

    /**
     * Maneja eventos de teclado dentro del modal
     * @param {KeyboardEvent} e 
     */
    function handleKeydown(e) {
      if (e.key === 'Tab') {
        if (e.shiftKey) {
          // Shift+Tab: si estamos en el primer elemento, mover al último
          if (document.activeElement === firstFocusable) {
            e.preventDefault();
            lastFocusable.focus();
          }
        } else {
          // Tab: si estamos en el último elemento, mover al primero
          if (document.activeElement === lastFocusable) {
            e.preventDefault();
            firstFocusable.focus();
          }
        }
      } else if (e.key === 'Escape' && onClose) {
        onClose();
      }
    }

    dialog.addEventListener('keydown', handleKeydown);

    // Devolver función de limpieza
    return function cleanupFocusTrap() {
      dialog.removeEventListener('keydown', handleKeydown);
    };
  }

  /**
   * Configura atributos ARIA para un diálogo modal
   * @param {HTMLElement} dialog - Elemento del diálogo
   * @param {Object} options - Opciones del diálogo
   */
  function setupAriaAttributes(dialog, options) {
    if (!dialog.hasAttribute('role')) {
      dialog.setAttribute('role', 'dialog');
    }
    if (!dialog.hasAttribute('aria-modal')) {
      dialog.setAttribute('aria-modal', 'true');
    }
    if (options.ariaLabel) {
      dialog.setAttribute('aria-label', options.ariaLabel);
    } else if (options.ariaLabelledby) {
      dialog.setAttribute('aria-labelledby', options.ariaLabelledby);
    }
    if (options.ariaDescribedby) {
      dialog.setAttribute('aria-describedby', options.ariaDescribedby);
    }
  }

  /**
   * Muestra un modal/overlay
   * @param {HTMLElement} element - Elemento del modal
   * @param {Object} options - Opciones de configuración
   * @returns {Function} Función para cerrar el modal
   */
  ModalService.show = function (element, options) {
    options = Object.assign({
      closeOnEscape: true,
      closeOnBackdropClick: false,
      ariaLabel: null,
      ariaLabelledby: null,
      ariaDescribedby: null,
      onClose: null,
      trapFocus: true
    }, options || {});

    // Guardar elemento activo si es el primer modal
    if (modalStack.length === 0) {
      previouslyActiveElement = document.activeElement;
    }

    // Configurar atributos ARIA
    setupAriaAttributes(element, options);

    // Configurar z-index basado en posición en el stack
    var zIndex = BASE_Z_INDEX + modalStack.length * 10;
    element.style.zIndex = zIndex.toString();

    // Mostrar elemento
    element.hidden = false;
    element.removeAttribute('aria-hidden');

    // Crear focus trap si está habilitado
    var cleanupFocusTrap = null;
    if (options.trapFocus) {
      var closeHandler = options.closeOnEscape && options.onClose ? options.onClose : null;
      cleanupFocusTrap = createFocusTrap(element, closeHandler);
    }

    // Manejar clic en backdrop
    var backdropClickHandler = null;
    if (options.closeOnBackdropClick && options.onClose) {
      backdropClickHandler = function (e) {
        if (e.target === element) {
          options.onClose();
        }
      };
      element.addEventListener('click', backdropClickHandler);
    }

    // Agregar al stack
    var modalData = {
      element: element,
      cleanup: function () {
        if (cleanupFocusTrap) cleanupFocusTrap();
        if (backdropClickHandler) {
          element.removeEventListener('click', backdropClickHandler);
        }
        element.hidden = true;
        element.setAttribute('aria-hidden', 'true');
      }
    };
    modalStack.push(modalData);

    // Devolver función para cerrar este modal específico
    return function closeModal() {
      var index = modalStack.findIndex(function (item) {
        return item.element === element;
      });
      
      if (index !== -1) {
        // Cerrar este modal y todos los que estén arriba
        for (var i = modalStack.length - 1; i >= index; i--) {
          modalStack[i].cleanup();
          modalStack.pop();
        }

        // Si no quedan modales, restaurar foco
        if (modalStack.length === 0 && previouslyActiveElement) {
          setTimeout(function () {
            if (previouslyActiveElement && previouslyActiveElement.focus) {
              previouslyActiveElement.focus();
            }
          }, 0);
        }
      }
    };
  };

  /**
   * Cierra el modal activo (top del stack)
   */
  ModalService.closeActive = function () {
    if (modalStack.length === 0) return;
    
    var modalData = modalStack.pop();
    modalData.cleanup();

    // Si no quedan modales, restaurar foco
    if (modalStack.length === 0 && previouslyActiveElement) {
      setTimeout(function () {
        if (previouslyActiveElement && previouslyActiveElement.focus) {
          previouslyActiveElement.focus();
        }
      }, 0);
    }
  };

  /**
   * Cierra todos los modales
   */
  ModalService.closeAll = function () {
    while (modalStack.length > 0) {
      ModalService.closeActive();
    }
  };

  /**
   * Verifica si hay modales activos
   * @returns {boolean}
   */
  ModalService.hasActiveModals = function () {
    return modalStack.length > 0;
  };

  /**
   * Número de modales activos
   * @returns {number}
   */
  ModalService.activeCount = function () {
    return modalStack.length;
  };

  // Exponer servicio globalmente
  window.ModalService = ModalService;

  // Inicializar manejo global de Escape (para cerrar modal superior)
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modalStack.length > 0) {
      e.preventDefault();
      e.stopPropagation();
      ModalService.closeActive();
    }
  }, true);

  console.log('ModalService v1.0.0 inicializado');
})();