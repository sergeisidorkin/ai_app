// Глобальная защита затемнения (backdrop) Bootstrap-модалок.
//
// Bootstrap 5 при show() сначала ~150 мс анимирует backdrop и только потом
// выставляет модалке display:block и класс .show. В этом окне модалка не
// отличима по DOM от закрытой, и любые «чистильщики зависшего backdrop»
// (htmx:afterSwap, hidden.bs.modal, watchdog'и) удаляли затемнение у
// открывающейся модалки — она появлялась без него.
//
// Модуль даёт единую проверку «есть ли активная модалка» (показана ИЛИ
// открывается) — ModalBackdropGuard.isAnyModalActive() — и страхует:
// если backdrop активной модалки всё же удалили, он возвращается в том же
// microtask, до отрисовки кадра.
//
// Подключается синхронно сразу после bootstrap.bundle — до любого кода,
// который чистит backdrop.
(function () {
  'use strict';

  if (window.ModalBackdropGuard) return;

  const OPENING_ATTR = 'data-modal-opening';
  const FALLBACK_ATTR = 'data-modal-backdrop-fallback';
  // Локальные флаги «модалка открыта», выставляемые на show.bs.modal
  // (договоры, шаблоны, реквизиты) — учитываем для совместимости.
  const LEGACY_BODY_CLASSES = [
    'contracts-modal-open',
    'contract-templates-modal-open',
    'contract-requisites-modal-open',
  ];

  function getInstance(modalEl) {
    try {
      return (window.bootstrap && window.bootstrap.Modal && window.bootstrap.Modal.getInstance(modalEl)) || null;
    } catch (_) {
      return null;
    }
  }

  function isModalActive(modalEl) {
    if (!(modalEl instanceof Element) || !modalEl.isConnected) return false;
    if (modalEl.classList.contains('show') || modalEl.hasAttribute(OPENING_ATTR)) return true;
    if (modalEl.style.display === 'block') return true;
    const instance = getInstance(modalEl);
    return !!(instance && instance._isShown === true);
  }

  function isAnyModalActive() {
    const body = document.body;
    if (body && LEGACY_BODY_CLASSES.some(function (cls) { return body.classList.contains(cls); })) return true;
    return Array.prototype.some.call(document.querySelectorAll('.modal'), isModalActive);
  }

  function getBackdrop(modalEl) {
    const instance = getInstance(modalEl);
    return (instance && instance._backdrop) || null;
  }

  function needsBackdrop(modalEl) {
    const backdrop = getBackdrop(modalEl);
    if (backdrop && backdrop._config && typeof backdrop._config.isVisible === 'boolean') {
      return backdrop._config.isVisible;
    }
    return modalEl.getAttribute('data-bs-backdrop') !== 'false';
  }

  function removeFallback(modalEl) {
    const fallback = modalEl && modalEl.__backdropFallback;
    if (!fallback) return;
    modalEl.__backdropFallback = null;
    fallback.remove();
  }

  function ensureBackdrop(modalEl) {
    if (!isModalActive(modalEl) || !needsBackdrop(modalEl)) return false;
    const instance = getInstance(modalEl);
    if (instance && instance._isShown === false) return false; // уже закрывается
    const body = document.body;
    if (!body) return false;
    body.classList.add('modal-open');
    if (document.querySelector('.modal-backdrop.show')) return false;

    // Предпочтительно вернуть собственный элемент Bootstrap: тогда hide()
    // штатно погасит и удалит его, без «осиротевших» слоёв.
    const backdrop = getBackdrop(modalEl);
    const own = backdrop && backdrop._isAppended ? backdrop._element : null;
    if (own instanceof Element && !own.isConnected) {
      own.classList.add('show');
      const root = backdrop._config && backdrop._config.rootElement instanceof Element
        ? backdrop._config.rootElement
        : body;
      root.append(own);
      return true;
    }

    removeFallback(modalEl);
    const fallback = document.createElement('div');
    fallback.className = 'modal-backdrop fade';
    fallback.setAttribute(FALLBACK_ATTR, modalEl.id || '1');
    body.append(fallback);
    void fallback.offsetHeight;
    fallback.classList.add('show');
    modalEl.__backdropFallback = fallback;
    return true;
  }

  function ensureAllBackdrops() {
    document.querySelectorAll('.modal').forEach(function (modalEl) {
      if (isModalActive(modalEl)) ensureBackdrop(modalEl);
    });
  }

  function modalFromEvent(event) {
    const target = event && event.target;
    return target instanceof Element && target.classList.contains('modal') ? target : null;
  }

  document.addEventListener('show.bs.modal', function (event) {
    const modalEl = modalFromEvent(event);
    if (!modalEl) return;
    modalEl.setAttribute(OPENING_ATTR, '1');
    // Bootstrap проверяет defaultPrevented сразу после dispatch; если показ
    // отменили — снимаем маркер, иначе он заблокировал бы очистку навсегда.
    queueMicrotask(function () {
      if (event.defaultPrevented) modalEl.removeAttribute(OPENING_ATTR);
    });
  });

  document.addEventListener('shown.bs.modal', function (event) {
    const modalEl = modalFromEvent(event);
    if (!modalEl) return;
    modalEl.removeAttribute(OPENING_ATTR);
    ensureBackdrop(modalEl);
  });

  document.addEventListener('hide.bs.modal', function (event) {
    const modalEl = modalFromEvent(event);
    if (!modalEl) return;
    queueMicrotask(function () {
      if (event.defaultPrevented) return;
      modalEl.removeAttribute(OPENING_ATTR);
      if (modalEl.__backdropFallback) modalEl.__backdropFallback.classList.remove('show');
    });
  });

  document.addEventListener('hidden.bs.modal', function (event) {
    const modalEl = modalFromEvent(event);
    if (!modalEl) return;
    modalEl.removeAttribute(OPENING_ATTR);
    removeFallback(modalEl);
  });

  function observeBackdropRemoval() {
    if (!document.body || typeof MutationObserver !== 'function') return;
    new MutationObserver(function (mutations) {
      const backdropRemoved = mutations.some(function (mutation) {
        return Array.prototype.some.call(mutation.removedNodes, function (node) {
          return node instanceof Element && node.classList.contains('modal-backdrop');
        });
      });
      if (backdropRemoved) ensureAllBackdrops();
    }).observe(document.body, { childList: true });
  }

  if (document.body) observeBackdropRemoval();
  else document.addEventListener('DOMContentLoaded', observeBackdropRemoval);

  window.ModalBackdropGuard = {
    isModalActive: isModalActive,
    isAnyModalActive: isAnyModalActive,
    ensureBackdrop: ensureBackdrop,
  };
})();
