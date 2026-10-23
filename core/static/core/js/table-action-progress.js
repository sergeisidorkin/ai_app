(function () {
  'use strict';

  // Глобальный индикатор длительных табличных операций (удаление строк и т.п.):
  // снимает выделение переданных строк и включает курсор `progress` на всё окно
  // (html.table-action-progress, см. site.css) до завершения операции.

  var ROOT_CLASS = 'table-action-progress';
  var SAFETY_TTL_MS = 120000;

  var activeCount = 0;
  var safetyTimer = null;

  function root() {
    return document.documentElement;
  }

  function clearSafetyTimer() {
    if (safetyTimer) {
      clearTimeout(safetyTimer);
      safetyTimer = null;
    }
  }

  function armSafetyTimer() {
    clearSafetyTimer();
    safetyTimer = setTimeout(function () {
      activeCount = 0;
      safetyTimer = null;
      root().classList.remove(ROOT_CLASS);
    }, SAFETY_TTL_MS);
  }

  function acquire() {
    activeCount += 1;
    if (activeCount === 1) root().classList.add(ROOT_CLASS);
    armSafetyTimer();
  }

  function release() {
    if (activeCount <= 0) return;
    activeCount -= 1;
    if (activeCount === 0) {
      clearSafetyTimer();
      root().classList.remove(ROOT_CLASS);
    }
  }

  function toCheckboxList(input) {
    if (!input) return [];
    if (input instanceof Element) return [input];
    var list = [];
    try {
      Array.prototype.forEach.call(input, function (item) {
        if (item instanceof Element) list.push(item);
      });
    } catch (_) {
      return [];
    }
    return list;
  }

  function hideActionsPanel(table, name) {
    if (!table) return;
    var master = table.querySelector('thead input[data-target-name="' + name + '"]');
    if (master) {
      master.checked = false;
      master.indeterminate = false;
      var actionsId = master.getAttribute('data-actions-id');
      if (actionsId) {
        var actions = document.getElementById(actionsId);
        if (actions && !table.querySelector('tbody input.form-check-input[name="' + name + '"]:checked')) {
          actions.classList.add('d-none');
        }
      }
    }
  }

  function clearSelection(checkboxes) {
    var tables = new Map();

    checkboxes.forEach(function (box) {
      if (!(box instanceof HTMLInputElement)) return;
      box.checked = false;
      var tr = box.closest('tr');
      if (tr) tr.classList.remove('table-active');
      var table = box.closest('table');
      var key = (table || document.body);
      if (!tables.has(key)) tables.set(key, { table: table, name: box.name || '', box: box });
    });

    tables.forEach(function (entry) {
      // Штатные обработчики панелей слушают всплывающий `change` на чекбоксе строки
      // и пересчитывают подсветку/мастер/видимость панели действий по имени таблицы.
      try {
        entry.box.dispatchEvent(new Event('change', { bubbles: true }));
      } catch (_) {}
      if (entry.name) hideActionsPanel(entry.table, entry.name);
    });
  }

  function begin(checkboxes, opts) {
    var options = opts || {};
    var boxes = toCheckboxList(checkboxes);
    if (options.clearSelection !== false && boxes.length) {
      try {
        clearSelection(boxes);
      } catch (_) {}
    }
    acquire();
    var ended = false;
    return {
      end: function () {
        if (ended) return;
        ended = true;
        release();
      },
    };
  }

  function run(checkboxes, fn, opts) {
    var handle = begin(checkboxes, opts);
    var result;
    try {
      result = typeof fn === 'function' ? fn() : undefined;
    } catch (err) {
      handle.end();
      throw err;
    }
    if (result && typeof result.then === 'function') {
      return Promise.resolve(result).finally(function () {
        handle.end();
      });
    }
    handle.end();
    return result;
  }

  window.TableActionProgress = {
    begin: begin,
    run: run,
    isActive: function () {
      return activeCount > 0;
    },
  };
})();
