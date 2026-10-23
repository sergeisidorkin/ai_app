(function () {
  if (window.__queuedRowOrder) return;

  // Shared "move rows up/down" engine for every selectable table.
  //
  // Two persistence modes share the same optimistic UI (rows are reordered in the DOM
  // immediately, the order is saved once after a short debounce, pending saves survive
  // reloads through localStorage):
  //
  //  * legacy mode  – table has data-row-order-save-url (+ data-row-order-signature /
  //                   data-row-order-payload-field); used by the dedicated bulk endpoints
  //                   (proposals registry, contract drafts, performers, personal worktime).
  //  * generic mode – table has data-row-order-key; the order is posted to
  //                   /core/row-order/<key>/ as {ordered_ids, base_order_ids}; the server
  //                   applies a partial permutation inside each ordering scope
  //                   (see core/row_order.py).
  //
  // Row-level attributes understood in both modes:
  //  data-row-order-id       – row id (falls back to the selection checkbox value)
  //  data-row-order-scope    – rows may only move inside their scope value
  //  data-row-order-locked   – "1": the row cannot be moved and cannot be crossed

  var STORAGE_KEY = 'queuedRowOrder.pending.v1';
  var SAVE_DELAY_MS = 1200;
  var GENERIC_URL_PREFIX = '/core/row-order/';
  var GLOBAL_STATUS_ID = 'row-order-global-status';
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

  // ---------------------------------------------------------------------------
  // Table / row helpers
  // ---------------------------------------------------------------------------

  function genericKey(table) {
    return (table && table.dataset && table.dataset.rowOrderKey) || '';
  }

  function isGenericTable(table) {
    return !!genericKey(table) && !(table.dataset && table.dataset.rowOrderSaveUrl);
  }

  function saveUrlForTable(table) {
    if (!table || !table.dataset) return '';
    if (table.dataset.rowOrderSaveUrl) return table.dataset.rowOrderSaveUrl;
    var key = genericKey(table);
    return key ? GENERIC_URL_PREFIX + encodeURIComponent(key) + '/' : '';
  }

  function storageKeyForTable(table) {
    if (!table || !table.dataset) return '';
    return table.dataset.rowOrderContext
      || table.dataset.rowOrderSaveUrl
      || (genericKey(table) ? 'row-order:' + genericKey(table) : '');
  }

  function selectionNameForTable(table) {
    if (!table) return '';
    if (table._rowOrderSelectionName) return table._rowOrderSelectionName;
    var master = table.querySelector('thead input[data-target-name], thead input[data-worktime-target-name]');
    var name = master
      ? (master.getAttribute('data-target-name') || master.getAttribute('data-worktime-target-name') || '')
      : '';
    if (!name) {
      var box = table.querySelector('tbody input.form-check-input[type="checkbox"][name]');
      name = box ? box.getAttribute('name') : '';
    }
    table._rowOrderSelectionName = name || '';
    return table._rowOrderSelectionName;
  }

  function rowSelectionBox(row, selectionName) {
    if (!row || !row.querySelector) return null;
    if (selectionName) {
      var named = row.querySelector('input.form-check-input[type="checkbox"][name="' + cssEscape(selectionName) + '"]');
      if (named) return named;
    }
    return row.querySelector('td input.form-check-input[type="checkbox"]');
  }

  function cssEscape(value) {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value);
    return String(value).replace(/["\\]/g, '\\$&');
  }

  function rowIdOf(row, selectionName) {
    if (!row || !row.dataset) return '';
    // Unsaved inline rows have no server id yet and never take part in the saved order.
    if (row.dataset.inlineNew === '1') return '';
    if (row.dataset.rowOrderId) return String(row.dataset.rowOrderId);
    var box = rowSelectionBox(row, selectionName);
    var value = box && box.value ? String(box.value) : '';
    return /^\d+$/.test(value) ? value : '';
  }

  function tableRows(table) {
    if (!table || !table.tBodies) return [];
    var selectionName = selectionNameForTable(table);
    var rows = [];
    Array.from(table.tBodies).forEach(function (tbody) {
      Array.from(tbody.rows).forEach(function (row) {
        if (rowIdOf(row, selectionName)) rows.push(row);
      });
    });
    return rows;
  }

  function collectOrderIds(table) {
    var selectionName = selectionNameForTable(table);
    return tableRows(table).map(function (row) {
      return rowIdOf(row, selectionName);
    }).filter(Boolean);
  }

  function isHiddenRow(row) {
    return !row || row.classList.contains('d-none') || row.hidden;
  }

  function isLockedRow(row) {
    return !!(row && row.dataset && row.dataset.rowOrderLocked === '1');
  }

  function isMovableRow(row, selectionName) {
    return !!row && !!rowIdOf(row, selectionName) && !isHiddenRow(row);
  }

  function matchesRowScope(candidate, row, options) {
    var key = options && options.rowScopeDataKey;
    if (key) {
      if (!candidate || !row || !candidate.dataset || !row.dataset) return false;
      var candidateValue = candidate.dataset[key];
      var rowValue = row.dataset[key];
      return candidateValue !== undefined
        && rowValue !== undefined
        && String(candidateValue) === String(rowValue);
    }
    var a = candidate && candidate.dataset ? candidate.dataset.rowOrderScope : undefined;
    var b = row && row.dataset ? row.dataset.rowOrderScope : undefined;
    if (a === undefined && b === undefined) return true;
    return String(a) === String(b);
  }

  // ---------------------------------------------------------------------------
  // Status indicator
  // ---------------------------------------------------------------------------

  function ensureGlobalStatusEl() {
    var el = document.getElementById(GLOBAL_STATUS_ID);
    if (el) return el;
    el = document.createElement('div');
    el.id = GLOBAL_STATUS_ID;
    el.className = 'row-order-global-status d-none';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    document.body.appendChild(el);
    return el;
  }

  function getStatusEl(table) {
    var container = table && table.closest
      ? table.closest('[data-worktime-panel], #proposals-pane, #performers-pane, #contracts-development-pane, [hx-get], .tab-pane')
      : null;
    var local = container ? container.querySelector('[data-row-order-status]') : null;
    if (local) return local;
    return ensureGlobalStatusEl();
  }

  function setStatus(table, message, kind) {
    var el = getStatusEl(table);
    if (!el) return;
    var isGlobal = el.id === GLOBAL_STATUS_ID;
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
    if (isGlobal) {
      el.innerHTML = '<span class="row-order-status-spinner" aria-hidden="true"></span>'
        + '<span class="row-order-global-status-text">' + message + '</span>';
      return;
    }
    el.innerHTML = '<span class="row-order-status-spinner" role="status" aria-hidden="true"></span>';
  }

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  function orderPayloadField(table) {
    if (table && table.dataset && table.dataset.rowOrderPayloadField) return table.dataset.rowOrderPayloadField;
    return isGenericTable(table) ? 'ordered_ids' : 'ordered_assignment_ids';
  }

  function payloadOrderIds(table, payload) {
    var field = orderPayloadField(table);
    return (payload && Array.isArray(payload[field]) && payload[field])
      || (payload && Array.isArray(payload.ordered_ids) && payload.ordered_ids)
      || (payload && Array.isArray(payload.ordered_assignment_ids) && payload.ordered_assignment_ids)
      || [];
  }

  function getState(table) {
    if (!table) return null;
    if (table._queuedRowOrderState) return table._queuedRowOrderState;
    var state = {
      table: table,
      key: storageKeyForTable(table),
      url: saveUrlForTable(table),
      generic: isGenericTable(table),
      baseSignature: table.dataset.rowOrderSignature || '',
      baseOrderIds: null,
      options: null,
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
    var payload;
    if (state.generic) {
      payload = {
        ordered_ids: table ? collectOrderIds(table) : payloadOrderIds(table, state.lastPayload),
        base_order_ids: Array.isArray(state.baseOrderIds) ? state.baseOrderIds.slice() : [],
        scope: (table && table.dataset && table.dataset.rowOrderScopeContext)
          ? safeJsonParse(table.dataset.rowOrderScopeContext)
          : {}
      };
    } else {
      payload = {
        week: table && table.dataset ? (table.dataset.rowOrderWeek || '') : '',
        base_order_signature: state.baseSignature || ''
      };
      payload[orderPayloadField(table)] = table ? collectOrderIds(table) : payloadOrderIds(table, state.lastPayload);
    }
    state.lastPayload = payload;
    return payload;
  }

  function safeJsonParse(text) {
    try {
      return JSON.parse(text) || {};
    } catch (error) {
      return {};
    }
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
      detail: Object.assign({ table: table || null, panel: panel || null, generic: !!(state && state.generic) }, detail || {})
    }));
  }

  function triggerBodyEvents(events) {
    if (!events || typeof events !== 'object') return;
    Object.keys(events).forEach(function (name) {
      var detail = events[name];
      if (detail === true || detail === null || detail === undefined) detail = {};
      if (window.htmx && typeof window.htmx.trigger === 'function') {
        window.htmx.trigger(document.body, name, detail);
      } else {
        document.body.dispatchEvent(new CustomEvent(name, { bubbles: true, detail: detail }));
      }
    });
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

  // ---------------------------------------------------------------------------
  // Refresh helpers (conflict / derived columns)
  // ---------------------------------------------------------------------------

  function defaultRefresh(table) {
    if (!table || !window.htmx) return false;
    var pane = table.closest('[hx-get]');
    if (!pane) return false;
    var url = pane.getAttribute('hx-get');
    if (!url) return false;
    var swap = pane.getAttribute('hx-swap') || 'outerHTML';
    window.htmx.ajax('GET', url, { target: pane, swap: swap });
    return true;
  }

  function refreshTable(state) {
    var options = state && state.options;
    if (options && typeof options.refresh === 'function') {
      try {
        options.refresh(state.table);
        return true;
      } catch (error) {
        // fall through to the generic refresh
      }
    }
    return defaultRefresh(state && state.table);
  }

  // ---------------------------------------------------------------------------
  // Save pipeline
  // ---------------------------------------------------------------------------

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
        state.baseOrderIds = null;
        removePending(state.key);
        setStatus(state.table, data.error || 'Порядок изменился на сервере.', 'error');
        dispatchTableEvent('queued-row-order:conflict', state, { response: response, data: data });
        if (state.generic) {
          window.setTimeout(function () { setStatus(state.table, '', 'muted'); }, 2400);
          refreshTable(state);
        }
        return false;
      }
      if (response.status >= 400 && response.status < 500) {
        // Permission / validation problems will not fix themselves: stop retrying.
        state.lastPayload = null;
        state.baseOrderIds = null;
        removePending(state.key);
        setStatus(state.table, data.error || 'Не удалось сохранить порядок строк.', 'error');
        dispatchTableEvent('queued-row-order:error', state, { response: response, data: data, fatal: true });
        if (state.generic) {
          window.setTimeout(function () { setStatus(state.table, '', 'muted'); }, 3200);
          refreshTable(state);
        }
        return false;
      }
      if (!response.ok || !data.ok) {
        throw new Error(data.error || ('Row order save failed with status ' + response.status));
      }
      state.lastPayload = null;
      if (state.generic) {
        state.baseOrderIds = Array.isArray(data.order_ids)
          ? data.order_ids.map(String)
          : payloadOrderIds(state.table, payload).map(String);
      } else {
        state.baseSignature = data.order_signature || state.baseSignature;
        if (state.table && state.table.dataset) {
          state.table.dataset.rowOrderSignature = state.baseSignature;
          state.table.dataset.worktimeOrderSignature = state.baseSignature;
        }
      }
      removePending(state.key);
      setStatus(state.table, 'Порядок сохранен', 'success');
      window.setTimeout(function () {
        setStatus(state.table, '', 'muted');
      }, 1600);
      var saveOptions = state.options || {};
      if (typeof saveOptions.onSaved === 'function') {
        try {
          saveOptions.onSaved(data, state.table);
        } catch (error) {
          // adapter errors must not break the save pipeline
        }
      }
      if (!saveOptions.suppressEvents) triggerBodyEvents(data.events);
      dispatchTableEvent('queued-row-order:saved', state, { response: response, data: data });
      if (saveOptions.refreshAfterSave && !state.dirty) {
        refreshTable(state);
      }
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

  function queueSave(table, options) {
    var state = getState(table);
    if (!state || !state.url) return false;
    if (options) state.options = options;
    if (!state.generic && !state.baseSignature && table.dataset) {
      state.baseSignature = table.dataset.rowOrderSignature || '';
    }
    state.dirty = true;
    storePending(state, buildPayload(state));
    setStatus(table, 'Порядок будет сохранен автоматически...', 'muted');
    scheduleStateSave(state, SAVE_DELAY_MS);
    return true;
  }

  // ---------------------------------------------------------------------------
  // Optimistic DOM reorder
  // ---------------------------------------------------------------------------

  function canCrossRow(crossingRow, direction, movingRow, options) {
    if (isLockedRow(crossingRow)) return false;
    if (options && typeof options.canCross === 'function') {
      return !!options.canCross(crossingRow, direction, movingRow);
    }
    return true;
  }

  function groupKey(row) {
    if (!row || !row.dataset) return '';
    return row.dataset.rowGroup || row.dataset.expdirGroup || '';
  }

  function isGroupContinuation(row) {
    if (!row || !row.dataset) return false;
    return row.dataset.rowGroupContinuation === '1' || row.dataset.expdirGroupContinuation === '1';
  }

  function takeGroupBlock(row) {
    var block = [row];
    var key = groupKey(row);
    if (!key) return block;
    var sibling = row.nextElementSibling;
    while (sibling && groupKey(sibling) === key && isGroupContinuation(sibling)) {
      block.push(sibling);
      sibling = sibling.nextElementSibling;
    }
    return block;
  }

  function insertBlockBefore(block, reference) {
    var parent = (reference && reference.parentNode) || block[0].parentNode;
    block.forEach(function (node) {
      parent.insertBefore(node, reference);
    });
  }

  function reorderRows(table, direction, selectedRows, options) {
    var selectionName = selectionNameForTable(table);
    var movableRows = tableRows(table).filter(function (row) {
      return isMovableRow(row, selectionName);
    });
    var selectedSet = new Set(selectedRows);
    var moved = false;

    function findNeighbour(row, step) {
      var candidate = step === 'up' ? row.previousElementSibling : row.nextElementSibling;
      while (candidate) {
        if (candidate.tagName === 'TR' && isMovableRow(candidate, selectionName)) {
          if (matchesRowScope(candidate, row, options)) return candidate;
          if (options && options.rowScopeDataKey) {
            candidate = step === 'up' ? candidate.previousElementSibling : candidate.nextElementSibling;
            continue;
          }
          return null;
        }
        candidate = step === 'up' ? candidate.previousElementSibling : candidate.nextElementSibling;
      }
      return null;
    }

    if (direction === 'up') {
      movableRows.forEach(function (row) {
        if (!selectedSet.has(row) || isLockedRow(row)) return;
        var prev = findNeighbour(row, 'up');
        if (prev && !selectedSet.has(prev) && canCrossRow(prev, direction, row, options)) {
          insertBlockBefore(takeGroupBlock(row), prev);
          moved = true;
        }
      });
    } else {
      movableRows.slice().reverse().forEach(function (row) {
        if (!selectedSet.has(row) || isLockedRow(row)) return;
        var next = findNeighbour(row, 'down');
        if (next && !selectedSet.has(next) && canCrossRow(next, direction, row, options)) {
          insertBlockBefore(takeGroupBlock(next), row);
          moved = true;
        }
      });
    }
    return moved;
  }

  function isManagedTable(table) {
    return !!table && table.hasAttribute('data-queued-row-order') && !!saveUrlForTable(table);
  }

  function findManagedTable(panel, selectionName) {
    if (!panel || !panel.querySelector) return null;
    var tables = qa('table[data-queued-row-order]', panel);
    if (!tables.length) return null;
    if (selectionName) {
      var byName = tables.find(function (table) {
        return !!table.querySelector('input.form-check-input[name="' + cssEscape(selectionName) + '"]');
      });
      if (byName) return byName;
    }
    return tables[0];
  }

  function moveRowsInTable(table, direction, selectedRows, options) {
    if (!isManagedTable(table) || (direction !== 'up' && direction !== 'down')) return false;
    if (!selectedRows.length) return false;
    var state = getState(table);
    if (state.generic && !Array.isArray(state.baseOrderIds)) {
      state.baseOrderIds = collectOrderIds(table);
    }
    var moved = reorderRows(table, direction, selectedRows, options);
    if (!moved) return false;
    if (options && typeof options.onAfterMove === 'function') {
      options.onAfterMove(table);
    }
    return queueSave(table, options);
  }

  // Legacy entry point: panel + direction (+ selectionName / selectedIds).
  function moveSelection(panel, direction, options) {
    var selectionName = options && options.selectionName;
    if (!selectionName && panel && panel.querySelector) {
      var master = panel.querySelector('input[data-worktime-target-name]');
      selectionName = master ? master.getAttribute('data-worktime-target-name') : '';
    }
    var table = findManagedTable(panel, selectionName);
    if (!table || !selectionName) return false;

    var rows = tableRows(table);
    var selectedIds = options && Array.isArray(options.selectedIds)
      ? new Set(options.selectedIds.map(String))
      : null;
    var selectedRows = rows.filter(function (row) {
      if (isHiddenRow(row)) return false;
      if (selectedIds) return selectedIds.has(rowIdOf(row, selectionName));
      var box = rowSelectionBox(row, selectionName);
      return box && box.checked;
    });
    return moveRowsInTable(table, direction, selectedRows, options);
  }

  // Generic entry point: checked checkboxes + direction.
  // Returns true when the table is managed by this module (even if nothing could move),
  // so callers can skip their legacy per-row request fallback.
  function handleMoveAction(options) {
    options = options || {};
    var checked = Array.isArray(options.checked) ? options.checked : [];
    var direction = options.action || options.direction;
    if (!checked.length || (direction !== 'up' && direction !== 'down')) return false;
    var table = checked[0].closest ? checked[0].closest('table') : null;
    if (!isManagedTable(table)) return false;
    var selectedRows = [];
    checked.forEach(function (box) {
      var row = box.closest ? box.closest('tr') : null;
      if (row && row.closest('table') === table && selectedRows.indexOf(row) === -1 && !isHiddenRow(row)) {
        selectedRows.push(row);
      }
    });
    moveRowsInTable(table, direction, selectedRows, options);
    return true;
  }

  function flushPanel(panel, options) {
    var tables = panel && panel.querySelector ? qa('table[data-queued-row-order]', panel) : [];
    return Promise.all(tables.map(function (table) {
      return flushState(getState(table), options);
    })).then(function (results) {
      return results.every(Boolean);
    });
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

  // ---------------------------------------------------------------------------
  // Pending (localStorage) restore
  // ---------------------------------------------------------------------------

  function applyStoredOrder(table, record) {
    var payload = record && record.payload;
    var ids = payloadOrderIds(table, payload);
    if (!Array.isArray(ids) || !ids.length) return false;
    var tbody = table.querySelector('tbody');
    if (!tbody) return false;
    var selectionName = selectionNameForTable(table);
    var rowsById = {};
    tableRows(table).forEach(function (row) {
      rowsById[rowIdOf(row, selectionName)] = row;
    });
    var currentIds = Object.keys(rowsById).sort();
    var storedIds = ids.map(String).sort();
    if (currentIds.join('|') !== storedIds.join('|')) return false;
    var hasGroups = !!tbody.querySelector('tr[data-row-group], tr[data-expdir-group]');
    if (hasGroups) {
      ids.map(String).forEach(function (id) {
        if (rowsById[id]) insertBlockBefore(takeGroupBlock(rowsById[id]), null);
      });
      return true;
    }
    var firstForeign = qa('tr', tbody).find(function (row) {
      return row.parentNode === tbody && !rowIdOf(row, selectionName);
    }) || null;
    ids.map(String).forEach(function (id) {
      if (rowsById[id]) {
        tbody.insertBefore(rowsById[id], firstForeign);
      }
    });
    return true;
  }

  function restoreStoredPending(root) {
    var records = readStorage();
    if (!Object.keys(records).length) return;
    qa('table[data-queued-row-order]', root || document).forEach(function (table) {
      var key = storageKeyForTable(table);
      var record = key ? records[key] : null;
      if (!record || !record.payload) return;
      var state = getState(table);
      if (state.saving || state.dirty) return;
      var applied = applyStoredOrder(table, record);
      if (state.generic) {
        state.baseOrderIds = Array.isArray(record.payload.base_order_ids)
          ? record.payload.base_order_ids.map(String)
          : null;
      } else {
        state.baseSignature = record.payload.base_order_signature || state.baseSignature;
      }
      state.lastPayload = record.payload;
      // When the stored order matches the current rows we rebuild the payload from the DOM;
      // otherwise (table shows another scope) the stored payload is re-sent verbatim.
      state.dirty = applied;
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
    handleMoveAction: handleMoveAction,
    isManagedTable: isManagedTable,
    queueSave: queueSave,
    flushPanel: flushPanel,
    flushAll: flushAll,
    flushVisible: flushAll,
    restoreStoredPending: restoreStoredPending,
    collectOrderIds: collectOrderIds
  };
})();
