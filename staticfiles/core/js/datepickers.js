(function () {
  function initDatepickers(root) {
    const scope = root || document;
    const inputs = scope.querySelectorAll('input.js-date:not([data-has-picker])');
    if (!inputs.length) return;

    inputs.forEach(function (el) {
      // 1) flatpickr
      if (window.flatpickr) {
        window.flatpickr(el, {
          dateFormat: 'd.m.Y',     // как пользователь видит
          allowInput: true,
          disableMobile: false,
        });
        el.dataset.hasPicker = '1';
        return;
      }

      // 2) bootstrap-datepicker (jQuery)
      if (window.$ && $.fn && $.fn.datepicker) {
        $(el).datepicker({
          format: 'dd.mm.yyyy',
          autoclose: true,
          todayHighlight: true,
          language: 'ru'
        });
        el.dataset.hasPicker = '1';
        return;
      }

      // 3) Fallback — нативный
      el.setAttribute('type', 'date'); // покажет родной календарь браузера
      el.dataset.hasPicker = '1';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initDatepickers(document);
  });

  // после подгрузки формы HTMX в модалку
  document.body.addEventListener('htmx:afterSwap', function (e) {
    if (!e.target) return;
    // Если прилетело содержимое модалки или панель проектов — инициализируем в её пределах
    if (e.target.closest && (e.target.closest('#projects-modal') || e.target.id === 'projects-pane')) {
      initDatepickers(e.target);
    }
  });
})();