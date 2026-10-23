(function () {
  'use strict';

  // Общий механизм снятия выделения строк таблицы после закрытия модалки.
  //
  // Сценарий: пользователь отметил строки чек-боксом, нажал «Редактировать»,
  // панель загрузила форму в свою Bootstrap-модалку. Обработчик панели помечает
  // модалку через `clearOnModalHide(modalEl, name, rootId)`; когда модалка
  // закрывается любым способом (крестик, «Отмена», «Сохранить»), срабатывает
  // `hidden.bs.modal`, и выделение строк с `name` снимается: чек-боксы строк,
  // мастер-чекбокс, подсветка `table-active` и панель действий `#<actions-id>`.
  //
  // Перемещение строк («вверх»/«вниз») модалку не открывает и этим механизмом
  // не затрагивается.
  //
  // После очистки на document всплывает `table-selection:cleared`
  // с `detail: { name, root }` — панели могут досинхронизировать свой UI
  // (например, состояние отдельных кнопок редактирования).

  var DATA_NAME = 'clearSelectionName';
  var DATA_ROOT = 'clearSelectionRoot';

  function escapeAttr(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value);
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function resolveElement(elOrId) {
    if (!elOrId) return null;
    if (elOrId instanceof Element) return elOrId;
    var id = String(elOrId).replace(/^#/, '');
    // Некоторые панели (например, #policy-pane) могут присутствовать в DOM
    // в нескольких экземплярах; актуальным считается последний — как в панелях.
    var all = document.querySelectorAll('#' + escapeAttr(id));
    return all.length ? all[all.length - 1] : null;
  }

  function resolveRoot(rootOrId) {
    var root = resolveElement(rootOrId);
    return root && root.isConnected ? root : document;
  }

  function clearOnModalHide(modalElOrId, name, rootOrId) {
    var modalEl = resolveElement(modalElOrId);
    if (!modalEl || !name) return false;
    modalEl.dataset[DATA_NAME] = String(name);
    var root = resolveElement(rootOrId);
    if (root && root.id) {
      modalEl.dataset[DATA_ROOT] = root.id;
    } else if (typeof rootOrId === 'string' && rootOrId) {
      modalEl.dataset[DATA_ROOT] = rootOrId.replace(/^#/, '');
    } else {
      delete modalEl.dataset[DATA_ROOT];
    }
    return true;
  }

  function cancelClearOnModalHide(modalElOrId) {
    var modalEl = resolveElement(modalElOrId);
    if (!modalEl) return;
    delete modalEl.dataset[DATA_NAME];
    delete modalEl.dataset[DATA_ROOT];
  }

  function clearByName(name, rootOrId) {
    if (!name) return;
    var root = resolveRoot(rootOrId);
    var selectorName = escapeAttr(name);

    var rows = Array.prototype.slice.call(
      root.querySelectorAll('input.form-check-input[name="' + selectorName + '"]')
    );
    var firstChecked = null;
    rows.forEach(function (box) {
      if (box.checked && !firstChecked) firstChecked = box;
      box.checked = false;
      box.indeterminate = false;
      var tr = box.closest('tr');
      if (tr) tr.classList.remove('table-active');
    });

    Array.prototype.forEach.call(
      root.querySelectorAll('input.form-check-input[data-target-name="' + selectorName + '"]'),
      function (master) {
        master.checked = false;
        master.indeterminate = false;
        var actionsId = master.getAttribute('data-actions-id');
        if (!actionsId) return;
        var actions = root.querySelector('#' + escapeAttr(actionsId)) || document.getElementById(actionsId);
        if (actions) actions.classList.add('d-none');
      }
    );

    // Штатные обработчики панелей слушают всплывающий `change` на чекбоксе строки
    // и сами пересчитывают мастер/подсветку/панель действий/состояние кнопок.
    if (firstChecked) {
      try {
        firstChecked.dispatchEvent(new Event('change', { bubbles: true }));
      } catch (_) {}
    }

    try {
      document.dispatchEvent(new CustomEvent('table-selection:cleared', {
        bubbles: false,
        detail: { name: String(name), root: root === document ? null : root },
      }));
    } catch (_) {}
  }

  document.addEventListener('hidden.bs.modal', function (e) {
    var modalEl = e.target;
    if (!(modalEl instanceof Element)) return;
    var name = modalEl.dataset[DATA_NAME];
    if (!name) return;
    var rootId = modalEl.dataset[DATA_ROOT] || null;
    delete modalEl.dataset[DATA_NAME];
    delete modalEl.dataset[DATA_ROOT];
    clearByName(name, rootId);
  });

  window.TableSelection = {
    clearOnModalHide: clearOnModalHide,
    cancelClearOnModalHide: cancelClearOnModalHide,
    clearByName: clearByName,
  };
})();
