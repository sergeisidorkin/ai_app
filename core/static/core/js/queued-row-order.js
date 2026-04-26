(function () {
  if (window.__queuedRowOrder) return;

  var STORAGE_KEY = 'queuedRowOrder.pending.v1';
  var SAVE_DELAY_MS = 1200;
  var states = [];

  function qa(selector, root) {
    return Array.from((root || document).querySelectorAll(selector));
  }

  function getCookie(name) {
    var cookies = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < cookies.length; i += 1) {
      var cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        return decodeURIComponent(cookie.substring(name.length + 1));
      }
    }
    return '';
  }

  function readStorage() {
    try {
      return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}') || {};
    } catch (error) {
      return {};
    }
  }

  function writeStorage(records) {
    try {
      var keys = Object.keys(records || {});
      if (!keys.length) {
        window.localStorage.removeItem(STORAGE_KEY);
        return;
      }
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(records));
    } catch (error) {
      // localStorage can be unavailable in private contexts.
    }
  }

  function storageKeyForTable(table) {
    if (!table || !table.dataset) return '';
    return table.dataset.rowOrderContext || table.dataset.rowOrderSaveUrl || '';
  }

  function collectOrderIds(table) {
    return qa('tbody tr[data-row-order-id]', table).map(function (row) {
      return String(row.dataset.rowOrderId || '');
    }).filter(Boolean);
  }

  function isMovableRow(row) {
    return row && row.hasAttribute('data-row-order-id') && !row.classList.contains('d-none');
  }

  function getStatusEl(table) {
    var panel = table && table.closest ? table.closest('[data-worktime-panel]') : null;
    return (panel || document).querySelector('[data-row-order-status]');
  }

  function setStatus(table, message, kind) {
    var el = getStatusEl(table);
    if (!el) return;
    el.classList.toggle('d-none', !message);
    el.classList.toggle('row-order-status-saving', !!message && kind !== 'error');
    el.classList.toggle('row-order-status-error', !!message && kind === 'error');
    el.classList.toggle('text-danger', kind === 'error');
    el.classList.toggle('text-muted', !kind || kind === 'muted' || kind === 'success');
    if (!message) {
      el.textContent = '';
      el.removeAttribute('aria-label');
      return;
    }
    if (kind === 'error') {
      el.textContent = message;
      el.removeAttribute('aria-label');
      return;
    }
    el.setAttribute('aria-label', message);
    el.innerHTML = '<span class="row-order-status-spinner" role="status" aria-hidden="true"></span>';
  }

  function getState(table) {
    if (!table) return null;
    if (table._queuedRowOrderState) return table._queuedRowOrderState;
    var state = {
      table: table,
      key: storageKeyForTable(table),
      url: table.dataset.rowOrderSaveUrl || '',
      baseSignature: table.dataset.rowOrderSignature || '',
      timerId: null,
      dirty: false,
      saving: null,
      lastPayload: null
    };
    table._queuedRowOrderState = state;
    states.push(state);
    return state;
  }

  function buildPayload(state) {
    var table = state.table;
    var payload = {
      week: table && table.dataset ? (table.dataset.rowOrderWeek || '') : '',
      ordered_assignment_ids: table ? collectOrderIds(table) : (state.lastPayload && state.lastPayload.ordered_assignment_ids) || [],
      base_order_signature: state.baseSignature || ''
    };
    state.lastPayload = payload;
    return payload;
  }

  function storePending(state, payload) {
    if (!state || !state.key) return;
    var records = readStorage();
    records[state.key] = {
      key: state.key,
      url: state.url,
      payload: payload,
      updated_at: Date.now()
    };
    writeStorage(records);
  }

  function removePending(key) {
    if (!key) return;
    var records = readStorage();
    if (!records[key]) return;
    delete records[key];
    writeStorage(records);
  }

  function dispatchTableEvent(name, state, detail) {
    var table = state && state.table;
    var panel = table && table.closest ? table.closest('[data-worktime-panel]') : null;
    document.body.dispatchEvent(new CustomEvent(name, {
      bubbles: true,
      detail: Object.assign({ table: table || null, panel: panel || null }, detail || {})
    }));
  }

  function postPayload(state, payload, options) {
    return window.fetch(state.url, {
      method: 'POST',
      credentials: 'same-origin',
      keepalive: !!(options && options.keepalive),
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.text().then(function (text) {
        var data = {};
        if (text) {
          try {
            data = JSON.parse(text);
          } catch (error) {
            data = {};
          }
        }
        return { response: response, data: data };
      });
    });
  }

  function flushState(state, options) {
    if (!state || !state.url) return Promise.resolve(true);
    if (state.timerId) {
      window.clearTimeout(state.timerId);
      state.timerId = null;
    }
    if (state.saving) {
      return state.saving.then(function () {
        return state.dirty ? flushState(state, options) : true;
      });
    }
    if (!state.dirty && !state.lastPayload) return Promise.resolve(true);

    var payload = state.dirty ? buildPayload(state) : state.lastPayload;
    storePending(state, payload);
    state.dirty = false;
    setStatus(state.table, 'Сохраняем порядок...', 'muted');

    state.saving = postPayload(state, payload, options).then(function (result) {
      var response = result.response;
      var data = result.data || {};
      if (response.status === 409) {
        state.lastPayload = null;
        removePending(state.key);
        setStatus(state.table, data.error || 'Порядок изменился на сервере.', 'error');
        dispatchTableEvent('queued-row-order:conflict', state, { response: response, data: data });
        return false;
      }
      if (!response.ok || !data.ok) {
        throw new Error(data.error || ('Row order save failed with status ' + response.status));
      }
      state.lastPayload = null;
      state.baseSignature = data.order_signature || state.baseSignature;
      if (state.table && state.table.dataset) {
        state.table.dataset.rowOrderSignature = state.baseSignature;
        state.table.dataset.worktimeOrderSignature = state.baseSignature;
      }
      removePending(state.key);
      setStatus(state.table, 'Порядок сохранен', 'success');
      window.setTimeout(function () {
        setStatus(state.table, '', 'muted');
      }, 1600);
      dispatchTableEvent('queued-row-order:saved', state, { response: response, data: data });
      return true;
    }).catch(function (error) {
      state.dirty = true;
      storePending(state, payload);
      setStatus(state.table, 'Не удалось сохранить порядок. Повторим автоматически.', 'error');
      dispatchTableEvent('queued-row-order:error', state, { error: error });
      return false;
    }).then(function (result) {
      state.saving = null;
      if (state.dirty && !(options && options.keepalive)) {
        scheduleStateSave(state, SAVE_DELAY_MS);
      }
      return result;
    });
    return state.saving;
  }

  function scheduleStateSave(state, delayMs) {
    if (!state) return;
    if (state.timerId) {
      window.clearTimeout(state.timerId);
    }
    state.timerId = window.setTimeout(function () {
      state.timerId = null;
      flushState(state);
    }, typeof delayMs === 'number' ? delayMs : SAVE_DELAY_MS);
  }

  function queueSave(table) {
    var state = getState(table);
    if (!state || !state.url) return false;
    if (!state.baseSignature && table.dataset) {
      state.baseSignature = table.dataset.rowOrderSignature || '';
    }
    state.dirty = true;
    storePending(state, buildPayload(state));
    setStatus(table, 'Порядок будет сохранен автоматически...', 'muted');
    scheduleStateSave(state, SAVE_DELAY_MS);
    return true;
  }

  function moveSelection(panel, direction, options) {
    var table = panel && panel.querySelector ? panel.querySelector('table[data-queued-row-order]') : null;
    if (!table || direction !== 'up' && direction !== 'down') return false;
    var selectionName = options && options.selectionName;
    if (!selectionName) {
      var master = panel.querySelector('input[data-worktime-target-name]');
      selectionName = master ? master.getAttribute('data-worktime-target-name') : '';
    }
    if (!selectionName) return false;

    var rows = qa('tbody tr[data-row-order-id]', table);
    var movableRows = rows.filter(isMovableRow);
    var selectedIds = options && Array.isArray(options.selectedIds)
      ? new Set(options.selectedIds.map(String))
      : null;
    var selectedRows = movableRows.filter(function (row) {
      if (selectedIds) return selectedIds.has(String(row.dataset.rowOrderId || ''));
      var box = row.querySelector('input.form-check-input[name="' + selectionName + '"]');
      return box && box.checked;
    });
    if (!selectedRows.length) return false;

    var selectedSet = new Set(selectedRows);
    var moved = false;
    if (direction === 'up') {
      movableRows.forEach(function (row) {
        if (!selectedSet.has(row)) return;
        var prev = row.previousElementSibling;
        while (prev && !isMovableRow(prev)) {
          prev = prev.previousElementSibling;
        }
        if (prev && !selectedSet.has(prev)) {
          row.parentNode.insertBefore(row, prev);
          moved = true;
        }
      });
    } else {
      movableRows.slice().reverse().forEach(function (row) {
        if (!selectedSet.has(row)) return;
        var next = row.nextElementSibling;
        while (next && !isMovableRow(next)) {
          next = next.nextElementSibling;
        }
        if (next && !selectedSet.has(next)) {
          row.parentNode.insertBefore(next, row);
          moved = true;
        }
      });
    }
    if (!moved) return false;

    if (options && typeof options.onAfterMove === 'function') {
      options.onAfterMove(table);
    }
    return queueSave(table);
  }

  function flushPanel(panel, options) {
    var table = panel && panel.querySelector ? panel.querySelector('table[data-queued-row-order]') : null;
    var state = table ? getState(table) : null;
    return flushState(state, options);
  }

  function flushAll(options) {
    var currentTables = qa('table[data-queued-row-order]');
    currentTables.forEach(getState);
    return Promise.all(states.map(function (state) {
      return flushState(state, options);
    })).then(function (results) {
      return results.every(Boolean);
    });
  }

  function applyStoredOrder(table, record) {
    var payload = record && record.payload;
    var ids = payload && payload.ordered_assignment_ids;
    if (!Array.isArray(ids) || !ids.length) return;
    var tbody = table.querySelector('tbody');
    if (!tbody) return;
    var rowsById = {};
    qa('tr[data-row-order-id]', tbody).forEach(function (row) {
      rowsById[String(row.dataset.rowOrderId)] = row;
    });
    var currentIds = Object.keys(rowsById).sort();
    var storedIds = ids.map(String).sort();
    if (currentIds.join('|') !== storedIds.join('|')) return;
    ids.map(String).forEach(function (id) {
      if (rowsById[id]) {
        tbody.insertBefore(rowsById[id], tbody.querySelector('tr:not([data-row-order-id])'));
      }
    });
  }

  function restoreStoredPending(root) {
    var records = readStorage();
    qa('table[data-queued-row-order]', root || document).forEach(function (table) {
      var key = storageKeyForTable(table);
      var record = key ? records[key] : null;
      if (!record || !record.payload) return;
      var state = getState(table);
      state.baseSignature = record.payload.base_order_signature || state.baseSignature;
      state.lastPayload = record.payload;
      state.dirty = true;
      applyStoredOrder(table, record);
      scheduleStateSave(state, 250);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    restoreStoredPending(document);
  });
  document.body.addEventListener('htmx:afterSettle', function (event) {
    restoreStoredPending(event.target || document);
  });
  document.addEventListener('click', function (event) {
    var tab = event.target && event.target.closest ? event.target.closest('[data-bs-toggle="tab"], [data-bs-toggle="pill"]') : null;
    if (tab) flushAll({ keepalive: true });
  }, true);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flushAll({ keepalive: true });
  });
  window.addEventListener('pagehide', function () {
    flushAll({ keepalive: true });
  });

  window.__queuedRowOrder = {
    moveSelection: moveSelection,
    queueSave: queueSave,
    flushPanel: flushPanel,
    flushAll: flushAll,
    flushVisible: flushAll,
    restoreStoredPending: restoreStoredPending
  };
})();
