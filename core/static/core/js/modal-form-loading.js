// Глобальный индикатор сохранения для форм в модальных окнах.
//
// Для любой формы внутри `.modal`, отправляемой через htmx (не-GET), на
// кнопке submit появляется спиннер и текст «Сохранение...», кнопка и кнопки
// закрытия (`[data-bs-dismiss="modal"]`) блокируются, а по завершении
// запроса (успех, ошибка, таймаут, abort) исходное состояние возвращается.
//
// Протокол совпадает с локальными реализациями (ТКП, договоры):
// `data-loading="1"` + `data-original-html`. Кнопки, уже помеченные
// `data-loading="1"` чужим кодом, не трогаем — конфликтов нет.
(function () {
  'use strict';

  const SPINNER_HTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>';
  const DEFAULT_SAVING_TEXT = 'Сохранение...';
  const OWN_FLAG = 'modalLoading';            // data-modal-loading
  const DISMISS_FLAG = 'modalLoadingDismiss'; // data-modal-loading-dismiss
  // Страховочный тайм-аут: htmx:afterRequest приходит во всех исходах, но
  // медленные ответы (внешние интеграции) могут идти десятки секунд.
  const RECORD_TTL_MS = 120000;

  // xhr → { submitBtn, dismissBtns, modalContent, timer }
  const records = new Map();

  function isSubmitControl(el) {
    if (!(el instanceof Element)) return false;
    if (el.tagName === 'BUTTON') return (el.getAttribute('type') || 'submit').toLowerCase() === 'submit';
    return el.tagName === 'INPUT' && (el.getAttribute('type') || '').toLowerCase() === 'submit';
  }

  function hasOwnRequestAttr(el) {
    return !!(el && (el.hasAttribute('hx-post') || el.hasAttribute('hx-put')
      || el.hasAttribute('hx-patch') || el.hasAttribute('hx-delete')));
  }

  function resolveSubmitButton(elt, requestConfig) {
    if (elt.tagName !== 'FORM') {
      // Кнопка с собственным hx-post (например, подтверждение удаления).
      return (elt.tagName === 'BUTTON' || elt.tagName === 'INPUT') ? elt : null;
    }
    const trigger = requestConfig && requestConfig.triggeringEvent;
    const submitter = trigger && trigger.submitter;
    if (submitter instanceof Element && elt.contains(submitter) && isSubmitControl(submitter)) {
      return submitter;
    }
    return elt.querySelector('.modal-footer button[type="submit"], .modal-footer input[type="submit"]')
      || elt.querySelector('button[type="submit"], input[type="submit"]');
  }

  function loadingLabel(button) {
    const custom = button.dataset.loadingText;
    if (custom) return custom;
    const text = (button.textContent || '').replace(/\s+/g, ' ').trim();
    if (!text || /^сохранить$/i.test(text)) return DEFAULT_SAVING_TEXT;
    return text;
  }

  function setButtonLoading(button) {
    if (!(button instanceof HTMLButtonElement) && !(button instanceof HTMLInputElement)) return false;
    if (button.dataset.loading === '1') return false; // уже под управлением локального кода
    button.dataset.loading = '1';
    button.dataset[OWN_FLAG] = '1';
    if (button instanceof HTMLInputElement) {
      button.dataset.originalHtml = button.value;
      button.value = loadingLabel(button) || button.value;
    } else {
      button.dataset.originalHtml = button.innerHTML;
      button.innerHTML = SPINNER_HTML + loadingLabel(button);
    }
    button.disabled = true;
    return true;
  }

  function resetButtonLoading(button) {
    if (!(button instanceof Element) || button.dataset[OWN_FLAG] !== '1') return;
    if (button.dataset.originalHtml !== undefined) {
      if (button instanceof HTMLInputElement) button.value = button.dataset.originalHtml;
      else button.innerHTML = button.dataset.originalHtml;
    }
    button.disabled = false;
    delete button.dataset.loading;
    delete button.dataset.originalHtml;
    delete button.dataset[OWN_FLAG];
  }

  function disableDismiss(modalContent) {
    const result = [];
    modalContent.querySelectorAll('[data-bs-dismiss="modal"]').forEach(function (el) {
      if (!('disabled' in el) || el.disabled) return;
      el.disabled = true;
      el.dataset[DISMISS_FLAG] = '1';
      result.push(el);
    });
    return result;
  }

  function enableDismiss(el) {
    if (!(el instanceof Element) || el.dataset[DISMISS_FLAG] !== '1') return;
    el.disabled = false;
    delete el.dataset[DISMISS_FLAG];
  }

  function finishRecord(xhr) {
    const record = records.get(xhr);
    if (!record) return;
    records.delete(xhr);
    if (record.timer) window.clearTimeout(record.timer);
    resetButtonLoading(record.submitBtn);
    record.dismissBtns.forEach(enableDismiss);
  }

  document.body.addEventListener('htmx:beforeSend', function (event) {
    const detail = event.detail || {};
    const elt = detail.elt;
    const xhr = detail.xhr;
    const requestConfig = detail.requestConfig || {};
    if (!(elt instanceof Element) || !xhr) return;
    if (String(requestConfig.verb || '').toLowerCase() === 'get') return;
    if (elt.tagName !== 'FORM' && !(isSubmitControl(elt) && hasOwnRequestAttr(elt))) return;
    const modalContent = elt.closest('.modal-content') || elt.closest('.modal');
    if (!modalContent) return;

    // Если кнопку уже перевёл в loading локальный код (ТКП, договоры) —
    // её не трогаем, но кнопки закрытия всё равно блокируем на время запроса.
    const submitBtn = resolveSubmitButton(elt, requestConfig);
    const ownsSubmit = !!submitBtn && setButtonLoading(submitBtn);
    const dismissBtns = disableDismiss(modalContent);
    if (!ownsSubmit && !dismissBtns.length) return;

    records.set(xhr, {
      submitBtn: ownsSubmit ? submitBtn : null,
      dismissBtns: dismissBtns,
      modalContent: modalContent,
      timer: window.setTimeout(function () { finishRecord(xhr); }, RECORD_TTL_MS),
    });
  });

  // htmx вызывает afterRequest во всех исходах (load / error / abort /
  // timeout); если форма уже выброшена swap'ом, событие приходит на ближайшего
  // оставшегося предка с тем же detail.xhr.
  document.body.addEventListener('htmx:afterRequest', function (event) {
    const xhr = event.detail && event.detail.xhr;
    if (xhr) finishRecord(xhr);
  });

  // Страховка: модалку закрыли (Esc / backdrop), пока запрос ещё шёл.
  document.addEventListener('hidden.bs.modal', function (event) {
    const modal = event.target;
    if (!(modal instanceof Element)) return;
    records.forEach(function (record, xhr) {
      if (modal.contains(record.modalContent)) finishRecord(xhr);
    });
  });
})();
