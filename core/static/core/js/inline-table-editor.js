(function (global) {
  const GROUP_VALUE = '__group__';
  const HOST_ID = 'inline-table-editor-host';

  let activeSession = null;
  let host = null;
  let selectEl = null;
  let ownersEl = null;
  let listenersBound = false;
  let selectedCell = null;
  let selectedCells = new Set();
  let numberDragAnchor = null;
  let numberDragBase = new Set();
  let numberDragAdditive = false;
  let numberDragMoved = false;
  let numberAlreadySelected = false;
  let numberSpinnerPointer = false;
  let syncingBulkNumber = false;
  let suppressNumberSelect = false;
  let bulkNumberOriginals = [];
  let textEdit = null;
  let richEdit = null;
  let richPointerStartedInEditor = false;
  let overlayKind = '';
  let overlayCell = null;
  let overlaySpecialtyIndex = null;
  let suppressSelectChange = false;

  function normalizeValue(value) {
    if (Array.isArray(value)) return value.map(function (item) { return String(item); });
    if (value == null) return '';
    return String(value);
  }

  function cloneValue(value) {
    return Array.isArray(value) ? value.slice() : value;
  }

  function valuesEqual(left, right) {
    const a = normalizeValue(left);
    const b = normalizeValue(right);
    if (Array.isArray(a) || Array.isArray(b)) {
      const aa = Array.isArray(a) ? a : (a === '' ? [] : [String(a)]);
      const bb = Array.isArray(b) ? b : (b === '' ? [] : [String(b)]);
      if (aa.length !== bb.length) return false;
      return aa.every(function (item, index) { return item === bb[index]; });
    }
    return a === b;
  }

  function parseJson(raw, fallback) {
    try {
      return JSON.parse(raw || '');
    } catch (err) {
      return fallback;
    }
  }

  function cellRef(cell) {
    if (!cell) return null;
    const section = cell.closest('[data-policy-table-key]');
    const row = cell.closest('tr[data-inline-row-id]');
    const field = cell.dataset.inlineField;
    if (!section || !row || !field) return null;
    return {
      cell: cell,
      section: section,
      tableKey: section.dataset.policyTableKey,
      rowId: row.dataset.inlineRowId,
      field: field,
      type: cell.dataset.inlineType || '',
    };
  }

  function editableCells(section) {
    return Array.from(section.querySelectorAll('td[data-inline-field][data-inline-type]')).filter(function (cell) {
      return cell.offsetParent !== null;
    });
  }

  function isCheckedValue(value) {
    if (value === true || value === 1) return true;
    const raw = String(value == null ? '' : value).trim().toLowerCase();
    return raw === 'true' || raw === '1' || raw === 'on' || raw === 'yes';
  }

  function normalizeSpecialtyIds(value) {
    let items = value;
    if (typeof value === 'string') {
      const parsed = parseJson(value, null);
      items = Array.isArray(parsed) ? parsed : (value ? [value] : []);
    } else if (value == null || value === '') {
      items = [];
    } else if (!Array.isArray(value)) {
      items = [value];
    }
    const ids = [];
    const seen = {};
    items.forEach(function (item) {
      const id = String(item == null ? '' : item).trim();
      if (id === '—') return;
      if (id) {
        if (seen[id]) return;
        seen[id] = true;
      }
      ids.push(id);
    });
    return ids;
  }

  function specialtyOptionsFor(cell) {
    const ref = cellRef(cell);
    const adapter = ref ? sessionAdapter(ref.tableKey) : null;
    if (adapter && typeof adapter.getSpecialtyOptions === 'function') {
      return adapter.getSpecialtyOptions() || [];
    }
    return [];
  }

  function renderSpecialtiesCell(cell, ids) {
    const options = specialtyOptionsFor(cell);
    const list = normalizeSpecialtyIds(ids);
    const display = list.length ? list : [''];
    let html = '<div class="inline-specialties" data-count="' + list.length + '">';
    display.forEach(function (id, index) {
      const item = options.find(function (entry) { return String(entry.id) === String(id); });
      const label = item ? item.label : (id || '—');
      html += '<div class="inline-specialty-row" data-index="' + index + '" data-id="' + escapeHtml(id) + '">';
      html += '<span class="inline-specialty-label">' + escapeHtml(label) + '</span>';
      html += '<span class="inline-specialty-icons">';
      html += '<span class="inline-specialty-actions">';
      html += '<button type="button" class="inline-specialty-btn" data-specialty-action="move" data-dir="-1" title="Выше" aria-label="Выше"' + (index === 0 ? ' disabled' : '') + '><i class="bi bi-arrow-up"></i></button>';
      html += '<button type="button" class="inline-specialty-btn" data-specialty-action="move" data-dir="1" title="Ниже" aria-label="Ниже"' + (index === display.length - 1 ? ' disabled' : '') + '><i class="bi bi-arrow-down"></i></button>';
      html += '<button type="button" class="inline-specialty-btn" data-specialty-action="remove" title="Удалить" aria-label="Удалить"><i class="bi bi-x-lg"></i></button>';
      html += '</span>';
      html += '<span class="inline-specialty-chevron" aria-hidden="true"></span>';
      html += '<button type="button" class="inline-specialty-add" data-specialty-action="add" title="Добавить специальность" aria-label="Добавить специальность"><i class="bi bi-plus-circle"></i></button>';
      html += '</span></div>';
    });
    html += '</div>';
    cell.innerHTML = html;
  }

  function applySpecialtyIds(cell, mutator) {
    applyCellValue(cell, mutator(normalizeSpecialtyIds(readCellValue(cell))));
  }

  function handleSpecialtyAction(cell, button, rowEl) {
    const action = button.getAttribute('data-specialty-action');
    const index = rowEl ? Number(rowEl.dataset.index || 0) : 0;
    if (action === 'add') {
      applySpecialtyIds(cell, function (current) {
        const next = current.slice();
        if (!next.length) next.push('');
        next.splice(index + 1, 0, '');
        return next;
      });
      return;
    }
    if (action === 'remove') {
      applySpecialtyIds(cell, function (current) {
        const next = current.slice();
        next.splice(index, 1);
        return next;
      });
      return;
    }
    if (action === 'move') {
      const dir = Number(button.getAttribute('data-dir') || 0);
      applySpecialtyIds(cell, function (current) {
        const next = current.slice();
        const to = index + dir;
        if (to < 0 || to >= next.length) return next;
        const tmp = next[index];
        next[index] = next[to];
        next[to] = tmp;
        return next;
      });
    }
  }

  function readCellValue(cell) {
    const type = cell.dataset.inlineType;
    if (type === 'checkbox') {
      const input = cell.querySelector('input[type="checkbox"]');
      if (input) return input.checked;
      return isCheckedValue(cell.getAttribute('data-inline-value'));
    }
    if (type === 'specialties') {
      return normalizeSpecialtyIds(cell.getAttribute('data-inline-value'));
    }
    if (type === 'owners') {
      const parsed = parseJson(cell.getAttribute('data-inline-value'), []);
      return Array.isArray(parsed) ? parsed.map(String) : [];
    }
    if (type === 'select') return cell.getAttribute('data-inline-value') || '';
    if (Object.prototype.hasOwnProperty.call(cell.dataset, 'inlineValue')) {
      return cell.getAttribute('data-inline-value') || '';
    }
    return (cell.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function parseRichValue(raw) {
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      return {
        html: String(raw.html || ''),
        plain_text: String(raw.plain_text || ''),
      };
    }
    const text = raw == null ? '' : String(raw);
    const trimmed = text.trim();
    if (trimmed.charAt(0) === '{') {
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed && typeof parsed === 'object') {
          return {
            html: String(parsed.html || ''),
            plain_text: String(parsed.plain_text || ''),
          };
        }
      } catch (err) {}
    }
    return { html: '', plain_text: text };
  }

  function serializeRichValue(value) {
    const parsed = parseRichValue(value);
    return JSON.stringify({
      html: parsed.html,
      plain_text: parsed.plain_text,
    });
  }

  function setRichCellDisplay(cell, value) {
    const parsed = parseRichValue(value);
    let html = parsed.html;
    if (!html && parsed.plain_text && window.ServiceCompositionEditor && window.ServiceCompositionEditor.normalizeTextToHtml) {
      html = window.ServiceCompositionEditor.normalizeTextToHtml(parsed.plain_text);
    } else if (!html) {
      html = parsed.plain_text || '';
    }
    let content = cell.querySelector('.policy-service-composition-content');
    if (!content) {
      content = document.createElement('div');
      content.className = 'policy-service-composition-content policy-service-composition-content--rich ql-editor';
      cell.innerHTML = '';
      cell.appendChild(content);
    }
    content.innerHTML = html;
  }

  function compositionHeader(cell) {
    const section = cell && cell.closest('#policy-typical-service-compositions-section');
    return section ? section.querySelector('.policy-service-composition-header') : null;
  }

  function compositionTable(cell) {
    return cell && cell.closest('#typical-service-compositions-table');
  }

  function lockCompositionTableColumns(table) {
    if (!table || table.dataset.inlineColsLocked === '1') return;
    table.querySelectorAll('thead th').forEach(function (th) {
      const width = Math.round(th.getBoundingClientRect().width);
      th.style.width = width + 'px';
      th.style.minWidth = width + 'px';
      th.style.maxWidth = width + 'px';
    });
    table.dataset.inlineColsLocked = '1';
  }

  function unlockCompositionTableColumns(table) {
    if (!table || table.dataset.inlineColsLocked !== '1') return;
    table.querySelectorAll('thead th').forEach(function (th) {
      th.style.width = '';
      th.style.minWidth = '';
      th.style.maxWidth = '';
    });
    delete table.dataset.inlineColsLocked;
  }

  function setCompositionToolbarVisible(cell, visible) {
    const header = compositionHeader(cell);
    if (!header) return null;
    const table = compositionTable(cell);
    if (visible) lockCompositionTableColumns(table);
    header.classList.toggle('is-rich-editing', !!visible);
    if (!visible) unlockCompositionTableColumns(table);
    const slot = header.querySelector('.policy-service-composition-inline-toolbar');
    return slot ? slot.querySelector('.proposal-service-text-toolbar') : null;
  }

  function expandTypicalServiceCompositionRows() {
    const table = document.getElementById('typical-service-compositions-table');
    if (!table || !table.classList.contains('clf-truncated')) return;
    table.classList.remove('clf-truncated');
    const toggle = document.getElementById('typical-service-compositions-wrap-toggle');
    if (toggle) toggle.classList.remove('active');
    window.__policyTypicalServiceCompositionWrapActive = false;
  }

  function setCellDisplay(cell, text) {
    const next = text == null ? '' : String(text);
    if (cell.childNodes.length === 1 && cell.firstChild.nodeType === 3) {
      if (cell.firstChild.nodeValue !== next) cell.firstChild.nodeValue = next;
      return;
    }
    cell.textContent = next;
  }

  function ensureHost() {
    if (host && document.body.contains(host)) return host;
    host = document.getElementById(HOST_ID);
    if (!host) {
      host = document.createElement('div');
      host.id = HOST_ID;
      document.body.appendChild(host);
    }
    if (!selectEl) {
      selectEl = document.createElement('select');
      selectEl.className = 'form-select form-select-sm inline-table-select-editor d-none';
      selectEl.setAttribute('aria-label', 'Выбор значения');
      host.appendChild(selectEl);
    }
    if (!ownersEl) {
      ownersEl = document.createElement('div');
      ownersEl.className = 'inline-table-owners-editor d-none';
      ownersEl.setAttribute('role', 'dialog');
      ownersEl.setAttribute('aria-label', 'Владелец');
      host.appendChild(ownersEl);
    }
    return host;
  }

  function closeTextEditor(commit) {
    if (!textEdit) return;
    const cell = textEdit.cell;
    const textarea = textEdit.textarea;
    const value = textarea.value;
    const originalHtml = textEdit.originalHtml;
    textEdit = null;
    overlayKind = '';
    overlayCell = null;
    const wrap = cell.querySelector('.inline-table-text-wrap');
    if (wrap) wrap.remove();
    const sizer = cell.querySelector('.inline-table-layout-sizer');
    if (sizer) sizer.remove();
    cell.classList.remove('inline-cell-editing');
    cell.style.height = '';
    cell.style.minHeight = '';
    cell.style.width = '';
    cell.style.minWidth = '';
    cell.style.maxWidth = '';
    cell.style.boxSizing = '';
    const tr = cell.closest('tr');
    if (tr) {
      tr.style.height = '';
      tr.classList.remove('inline-editing-row');
    }
    if (commit) {
      applyCellValue(cell, value);
      applyBulkNumberValue(cell, value);
    } else {
      restoreBulkNumberOriginals(cell);
      if (originalHtml != null) cell.innerHTML = originalHtml;
      else setCellDisplay(cell, readCellValue(cell));
    }
    bulkNumberOriginals = [];
  }

  function closeSelectEditor() {
    if (!selectEl || selectEl.classList.contains('d-none')) return;
    const cell = overlayCell;
    if (document.activeElement === selectEl) selectEl.blur();
    selectEl.classList.add('d-none');
    delete selectEl.dataset.inlineOpen;
    overlayKind = '';
    overlayCell = null;
    overlaySpecialtyIndex = null;
    if (cell) delete cell.dataset.inlineActiveIndex;
  }

  function closeOwnersEditor(commit) {
    if (!ownersEl || ownersEl.classList.contains('d-none')) return;
    if (commit && overlayCell) {
      const selected = Array.from(ownersEl.querySelectorAll('input[type="checkbox"]:checked')).map(function (input) {
        return input.value;
      });
      applyCellValue(overlayCell, selected.length ? selected : [GROUP_VALUE]);
    }
    ownersEl.classList.add('d-none');
    ownersEl.innerHTML = '';
    overlayKind = '';
    overlayCell = null;
  }

  function richContentsChanged(value, editState, hadUserChange) {
    if (!editState) return !!hadUserChange;
    if (!editState.baselineCaptured) return false;
    const html = value && value.html != null ? String(value.html) : '';
    const plain = value && value.plain_text != null ? String(value.plain_text) : '';
    return html !== String(editState.baselineHtml || '')
      || plain !== String(editState.baselinePlain || '');
  }

  function closeRichEditor(commit) {
    if (!richEdit) return;
    const cell = richEdit.cell;
    const originalHtml = richEdit.originalHtml;
    const editor = richEdit.editor;
    const originalValue = richEdit.originalValue;
    const hadUserChange = !!(richEdit.editState && richEdit.editState.hadUserChange);
    const value = editor && typeof editor.getState === 'function'
      ? editor.getState()
      : parseRichValue(readCellValue(cell));
    const contentsChanged = richContentsChanged(value, richEdit.editState, hadUserChange);
    if (editor && typeof editor.destroy === 'function') editor.destroy();
    richEdit = null;
    richPointerStartedInEditor = false;
    overlayKind = '';
    overlayCell = null;
    setCompositionToolbarVisible(cell, false);
    const wrap = cell.querySelector('.inline-table-text-wrap');
    if (wrap) wrap.remove();
    const sizer = cell.querySelector('.inline-table-layout-sizer');
    if (sizer) sizer.remove();
    cell.classList.remove('inline-cell-editing');
    cell.style.height = '';
    cell.style.minHeight = '';
    cell.style.width = '';
    cell.style.minWidth = '';
    cell.style.maxWidth = '';
    const tr = cell.closest('tr');
    if (tr) {
      tr.style.height = '';
      tr.classList.remove('inline-editing-row');
    }
    if (commit && contentsChanged) {
      applyCellValue(cell, value);
    } else if (originalHtml != null) {
      cell.innerHTML = originalHtml;
      if (originalValue != null) cell.setAttribute('data-inline-value', originalValue);
      syncCellChrome(cell);
    } else {
      setRichCellDisplay(cell, readCellValue(cell));
      syncCellChrome(cell);
    }
  }

  function closeEditors(options) {
    options = options || {};
    closeTextEditor(!!options.commitText);
    closeRichEditor(!!options.commitText);
    closeSelectEditor();
    closeOwnersEditor(!!options.commitOwners);
  }

  function positionOverlay(el, cell, options) {
    options = options || {};
    const rect = cell.getBoundingClientRect();
    const margin = 8;
    const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
    let width = options.minWidth ? Math.max(rect.width, options.minWidth) : rect.width;

    el.style.position = 'fixed';
    el.style.boxSizing = 'border-box';
    el.style.top = Math.max(margin, rect.top) + 'px';
    el.style.minHeight = rect.height + 'px';
    el.style.height = options.fitContent ? '' : rect.height + 'px';
    el.style.zIndex = '1080';
    el.style.maxWidth = '';

    if (options.fitContent) {
      el.style.width = 'max-content';
      el.style.maxWidth = Math.max(width, viewportWidth - margin * 2) + 'px';
      el.style.left = margin + 'px';
      el.classList.remove('d-none');
      width = Math.max(width, Math.ceil(el.getBoundingClientRect().width));
    }

    let left = options.expand === 'left' ? (rect.right - width) : rect.left;
    if (left + width > viewportWidth - margin) {
      left = viewportWidth - margin - width;
    }
    if (left < margin) {
      left = margin;
      width = Math.min(width, viewportWidth - margin * 2);
    }
    el.style.setProperty('left', left + 'px');
    el.style.setProperty('width', width + 'px');
    el.style.maxWidth = '';
  }

  function canPaintSelection(cell) {
    const type = cell && cell.dataset.inlineType;
    return type && type !== 'select' && type !== 'owners' && type !== 'checkbox' && type !== 'specialties';
  }

  function clearSelectionPaint(cell) {
    if (!cell) return;
    cell.classList.remove(
      'inline-cell-selected',
      'inline-cell-sel-t',
      'inline-cell-sel-r',
      'inline-cell-sel-b',
      'inline-cell-sel-l'
    );
  }

  function selectionNeighbor(cell, dir) {
    if (!cell || !cell.parentElement) return null;
    if (dir === 'left') return cell.previousElementSibling;
    if (dir === 'right') return cell.nextElementSibling;
    const row = dir === 'top' ? cell.parentElement.previousElementSibling : cell.parentElement.nextElementSibling;
    if (!row || !row.cells) return null;
    return row.cells[cell.cellIndex] || null;
  }

  function shouldDrawSelectionEdge(cell, dir) {
    const neighbor = selectionNeighbor(cell, dir);
    if (dir === 'top' || dir === 'left') return true;
    return !selectedCells.has(neighbor);
  }

  function syncSelectionEdges() {
    selectedCells.forEach(function (cell) {
      if (!cell.classList.contains('inline-cell-selected')) {
        cell.classList.remove('inline-cell-sel-t', 'inline-cell-sel-r', 'inline-cell-sel-b', 'inline-cell-sel-l');
        return;
      }
      cell.classList.toggle('inline-cell-sel-t', shouldDrawSelectionEdge(cell, 'top'));
      cell.classList.toggle('inline-cell-sel-r', shouldDrawSelectionEdge(cell, 'right'));
      cell.classList.toggle('inline-cell-sel-b', shouldDrawSelectionEdge(cell, 'bottom'));
      cell.classList.toggle('inline-cell-sel-l', shouldDrawSelectionEdge(cell, 'left'));
    });
  }

  function setSelectedCells(cells, anchor) {
    const next = new Set((cells || []).filter(Boolean));
    selectedCells.forEach(function (cell) {
      if (!next.has(cell)) clearSelectionPaint(cell);
    });
    next.forEach(function (cell) {
      if (canPaintSelection(cell)) cell.classList.add('inline-cell-selected');
    });
    selectedCells = next;
    if (anchor && next.has(anchor)) selectedCell = anchor;
    else selectedCell = next.size ? next.values().next().value : null;
    syncSelectionEdges();
  }

  function selectCell(cell) {
    if (!cell) {
      setSelectedCells([], null);
      return;
    }
    setSelectedCells([cell], cell);
  }

  function clearSelection() {
    setSelectedCells([], null);
  }

  function getNumberCell(target) {
    if (!target || !target.closest) return null;
    const cell = target.closest('td[data-inline-type="number"]');
    if (!cell || !activeSession || !activeSession.hasSection(cell.closest('[data-policy-table-key]'))) {
      return null;
    }
    return cell;
  }

  function getNumberGrid(section) {
    if (!section) return [];
    return Array.from(section.querySelectorAll('tr[data-inline-row-id]')).map(function (row) {
      return Array.from(row.querySelectorAll('td[data-inline-type="number"]'));
    }).filter(function (cells) { return cells.length; });
  }

  function getNumberCellRange(startCell, endCell) {
    if (!startCell || !endCell) return startCell ? [startCell] : [];
    const section = startCell.closest('[data-policy-table-key]');
    if (!section || endCell.closest('[data-policy-table-key]') !== section) return [endCell];
    const grid = getNumberGrid(section);
    let startRow = -1;
    let startColumn = -1;
    let endRow = -1;
    let endColumn = -1;
    grid.forEach(function (rowCells, rowIndex) {
      const startIndex = rowCells.indexOf(startCell);
      const endIndex = rowCells.indexOf(endCell);
      if (startIndex !== -1) {
        startRow = rowIndex;
        startColumn = startIndex;
      }
      if (endIndex !== -1) {
        endRow = rowIndex;
        endColumn = endIndex;
      }
    });
    if (startRow === -1 || endRow === -1) return [endCell];
    const firstRow = Math.min(startRow, endRow);
    const lastRow = Math.max(startRow, endRow);
    const firstColumn = Math.min(startColumn, endColumn);
    const lastColumn = Math.max(startColumn, endColumn);
    const range = [];
    for (let rowIndex = firstRow; rowIndex <= lastRow; rowIndex += 1) {
      for (let columnIndex = firstColumn; columnIndex <= lastColumn; columnIndex += 1) {
        const cell = grid[rowIndex] && grid[rowIndex][columnIndex];
        if (cell) range.push(cell);
      }
    }
    return range;
  }

  function applyBulkNumberValue(sourceCell, value, options) {
    if (syncingBulkNumber || selectedCells.size < 2 || !selectedCells.has(sourceCell)) return false;
    syncingBulkNumber = true;
    selectedCells.forEach(function (cell) {
      if (cell === sourceCell) return;
      applyCellValue(cell, value, options);
    });
    syncingBulkNumber = false;
    return true;
  }

  function snapshotBulkNumberOriginals() {
    bulkNumberOriginals = [];
    selectedCells.forEach(function (cell) {
      const ref = cellRef(cell);
      if (!ref || !activeSession) return;
      bulkNumberOriginals.push({
        tableKey: ref.tableKey,
        rowId: ref.rowId,
        field: ref.field,
        cell: cell,
        value: activeSession.getValue(ref.tableKey, ref.rowId, ref.field),
      });
    });
  }

  function restoreBulkNumberOriginals(sourceCell) {
    bulkNumberOriginals.forEach(function (item) {
      if (!item.cell || item.cell === sourceCell) return;
      applyCellValue(item.cell, item.value);
    });
  }

  function placeNumberCaretAtEnd(input) {
    if (!input) return;
    try {
      const len = String(input.value || '').length;
      input.setSelectionRange(len, len);
    } catch (err) {}
  }

  function restoreNumberSelectionPaint(cell) {
    if (cell && selectedCells.has(cell) && canPaintSelection(cell)) {
      cell.classList.add('inline-cell-selected');
    }
    syncSelectionEdges();
  }

  function isNumberSpinnerEvent(event, cell) {
    if (!textEdit || textEdit.cell !== cell) return false;
    const input = textEdit.textarea;
    if (!input || input.type !== 'number') return false;
    if (event.shiftKey || event.ctrlKey || event.metaKey) return false;
    const rect = input.getBoundingClientRect();
    return event.clientX >= rect.right - 24;
  }

  function sessionAdapter(tableKey) {
    return activeSession && activeSession.getAdapter(tableKey);
  }

  function applyCellValue(cell, value, options) {
    options = options || {};
    const paint = !options.skipDisplay;
    const ref = cellRef(cell);
    if (!ref || !activeSession) return;
    const adapter = sessionAdapter(ref.tableKey);
    let nextValue = value;
    let label = value;
    if (adapter && typeof adapter.normalizeValue === 'function') {
      const normalized = adapter.normalizeValue(ref, value, activeSession);
      if (normalized && typeof normalized === 'object') {
        nextValue = normalized.value;
        if (normalized.label != null) label = normalized.label;
      }
    }
    if (ref.type === 'checkbox') {
      const checked = isCheckedValue(nextValue);
      nextValue = checked;
      cell.setAttribute('data-inline-value', checked ? 'true' : 'false');
      const input = cell.querySelector('input[type="checkbox"]');
      if (input) input.checked = checked;
    } else if (ref.type === 'specialties') {
      nextValue = normalizeSpecialtyIds(nextValue);
      cell.setAttribute('data-inline-value', JSON.stringify(nextValue));
      if (paint) renderSpecialtiesCell(cell, nextValue);
    } else if (ref.type === 'owners') {
      cell.setAttribute('data-inline-value', JSON.stringify(normalizeValue(nextValue)));
      if (paint) setCellDisplay(cell, label);
    } else if (ref.type === 'select' || ref.type === 'number') {
      cell.setAttribute('data-inline-value', nextValue == null ? '' : String(nextValue));
      if (paint) setCellDisplay(cell, label);
    } else if (ref.type === 'rich') {
      nextValue = serializeRichValue(nextValue);
      cell.setAttribute('data-inline-value', nextValue);
      if (paint) setRichCellDisplay(cell, nextValue);
    } else {
      cell.setAttribute('data-inline-value', nextValue == null ? '' : String(nextValue));
      if (paint) setCellDisplay(cell, nextValue == null ? '' : String(nextValue));
    }
    activeSession.setValue(ref.tableKey, ref.rowId, ref.field, nextValue);
    activeSession.clearFieldError(ref.tableKey, ref.rowId, ref.field);
    if (paint) {
      syncCellChrome(cell);
      if (adapter && typeof adapter.afterChange === 'function') {
        adapter.afterChange(ref, nextValue, activeSession);
      }
    }
  }

  function syncCellChrome(cell) {
    const ref = cellRef(cell);
    if (!ref || !activeSession) return;
    const dirty = activeSession.isFieldDirty(ref.tableKey, ref.rowId, ref.field);
    const error = activeSession.getFieldError(ref.tableKey, ref.rowId, ref.field);
    cell.classList.toggle('inline-cell-dirty', dirty);
    cell.classList.toggle('inline-cell-error', !!error);
    if (error) cell.setAttribute('title', error);
    else cell.removeAttribute('title');
  }

  function syncSectionChrome(section) {
    editableCells(section).forEach(syncCellChrome);
  }

  function openTextEditor(cell, options) {
    options = options || {};
    const seed = options.seed == null ? null : String(options.seed);
    if (textEdit && textEdit.cell === cell && seed == null) return;
    const keepMulti = cell.dataset.inlineType === 'number'
      && selectedCells.size > 1
      && selectedCells.has(cell);
    closeEditors();
    if (!keepMulti) selectCell(cell);
    else selectedCell = cell;
    suppressNumberSelect = seed != null;
    let lockCaretAtEnd = seed != null;
    if (keepMulti) snapshotBulkNumberOriginals();
    const value = readCellValue(cell);
    const cs = getComputedStyle(cell);
    const pt = parseFloat(cs.paddingTop) || 0;
    const pr = parseFloat(cs.paddingRight) || 0;
    const pb = parseFloat(cs.paddingBottom) || 0;
    const pl = parseFloat(cs.paddingLeft) || 0;
    const bt = parseFloat(cs.borderTopWidth) || 0;
    const bb = parseFloat(cs.borderBottomWidth) || 0;
    const cellH = cell.getBoundingClientRect().height;
    const cellW = cell.getBoundingClientRect().width;
    const whiteSpace = cs.whiteSpace;
    const layoutHtml = cell.innerHTML;
    const tr = cell.closest('tr');
    const isNumber = cell.dataset.inlineType === 'number';
    if (tr && !isNumber) tr.classList.add('inline-editing-row');
    if (!isNumber) {
      cell.classList.remove('inline-cell-selected', 'inline-cell-sel-t', 'inline-cell-sel-r', 'inline-cell-sel-b', 'inline-cell-sel-l');
    }
    syncSelectionEdges();
    cell.style.height = cellH + 'px';
    cell.style.minHeight = cellH + 'px';
    if (isNumber) {
      cell.style.width = cellW + 'px';
      cell.style.minWidth = cellW + 'px';
      cell.style.maxWidth = cellW + 'px';
      cell.style.boxSizing = 'border-box';
    }

    const sizer = document.createElement('span');
    sizer.className = 'inline-table-layout-sizer';
    sizer.setAttribute('aria-hidden', 'true');
    sizer.style.setProperty('white-space', whiteSpace, 'important');
    sizer.innerHTML = layoutHtml;
    cell.innerHTML = '';
    cell.appendChild(sizer);
    cell.classList.add('inline-cell-editing');
    const wrap = document.createElement('div');
    wrap.className = 'inline-table-text-wrap' + (isNumber ? ' inline-table-number-wrap' : '');
    wrap.style.padding = pt + 'px ' + (pr + (isNumber ? 3 : 0)) + 'px ' + pb + 'px ' + pl + 'px';
    wrap.style.boxSizing = 'border-box';

    const textarea = isNumber ? document.createElement('input') : document.createElement('textarea');
    if (isNumber) {
      textarea.type = 'number';
      textarea.className = 'inline-table-number-input';
      textarea.min = cell.getAttribute('data-inline-min') || '0';
      textarea.step = cell.getAttribute('data-inline-step') || '1';
      textarea.inputMode = textarea.step === '1' ? 'numeric' : 'decimal';
      textarea.lang = document.documentElement.getAttribute('lang') || 'ru';
    } else {
      textarea.className = 'inline-table-text-input';
      textarea.rows = 1;
    }
    textarea.value = seed != null ? seed : value;
    textarea.setAttribute('spellcheck', 'false');
    textarea.style.font = cs.font;
    textarea.style.lineHeight = cs.lineHeight;
    textarea.style.letterSpacing = cs.letterSpacing;
    textarea.style.color = cs.color;
    wrap.appendChild(textarea);
    wrap.addEventListener('click', function (event) {
      if (isNumber) event.stopPropagation();
    });
    wrap.addEventListener('dblclick', function (event) {
      if (!isNumber) return;
      event.preventDefault();
      event.stopPropagation();
    });
    cell.appendChild(wrap);
    textEdit = { cell: cell, textarea: textarea, originalHtml: layoutHtml };
    overlayKind = 'text';
    overlayCell = cell;
    syncSelectionEdges();
    if (seed != null) {
      applyBulkNumberValue(cell, textarea.value);
      placeNumberCaretAtEnd(textarea);
    }

    function contentHeight() {
      return Math.max(0, cell.getBoundingClientRect().height - pt - pb - bt - bb);
    }

    function measureScrollHeight() {
      textarea.style.height = '0px';
      return textarea.scrollHeight;
    }

    function resizeWrap(allowGrow) {
      if (isNumber) {
        cell.style.minHeight = cellH + 'px';
        cell.style.height = cellH + 'px';
        textarea.style.height = '';
        return;
      }
      const sh = measureScrollHeight();
      if (allowGrow) {
        const next = Math.max(cellH, sh + pt + pb + bt + bb);
        cell.style.minHeight = next + 'px';
        cell.style.height = next + 'px';
        textarea.style.height = sh + 'px';
        return;
      }
      cell.style.minHeight = cellH + 'px';
      cell.style.height = cellH + 'px';
      textarea.style.height = contentHeight() + 'px';
    }
    textarea.addEventListener('input', function () {
      suppressNumberSelect = true;
      if (!isNumber) {
        resizeWrap(true);
        return;
      }
      applyBulkNumberValue(cell, textarea.value);
      if (keepMulti) placeNumberCaretAtEnd(textarea);
    });
    textarea.addEventListener('mousedown', function () {
      lockCaretAtEnd = false;
    });
    textarea.addEventListener('focus', function () {
      if (lockCaretAtEnd) placeNumberCaretAtEnd(textarea);
    });
    textarea.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeTextEditor(false);
        if (selectedCells.has(cell)) restoreNumberSelectionPaint(cell);
        else selectCell(cell);
        return;
      }
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        closeTextEditor(true);
        moveSelection(cell, event.shiftKey ? -1 : 1);
        return;
      }
      if (event.key === 'Tab') {
        event.preventDefault();
        closeTextEditor(true);
        moveSelection(cell, event.shiftKey ? -1 : 1);
      }
    });
    window.requestAnimationFrame(function () {
      resizeWrap(false);
      textarea.focus();
      if (lockCaretAtEnd) placeNumberCaretAtEnd(textarea);
      else if (!suppressNumberSelect) textarea.select();
    });
  }

  function openRichEditor(cell) {
    if (richEdit && richEdit.cell === cell) return;
    expandTypicalServiceCompositionRows();
    closeEditors();
    selectCell(cell);
    lockCompositionTableColumns(compositionTable(cell));
    const displayContent = cell.querySelector('.policy-service-composition-content--rich');
    const displayCs = getComputedStyle(displayContent || cell);
    const displayFontSize = displayCs.fontSize;
    const displayLineHeight = displayCs.lineHeight;
    const value = parseRichValue(readCellValue(cell));
    const originalValue = cell.getAttribute('data-inline-value');
    const cs = getComputedStyle(cell);
    const pt = parseFloat(cs.paddingTop) || 0;
    const pr = parseFloat(cs.paddingRight) || 0;
    const pb = parseFloat(cs.paddingBottom) || 0;
    const pl = parseFloat(cs.paddingLeft) || 0;
    const bt = parseFloat(cs.borderTopWidth) || 0;
    const bb = parseFloat(cs.borderBottomWidth) || 0;
    const cellH = cell.getBoundingClientRect().height;
    const cellW = cell.getBoundingClientRect().width;
    const layoutHtml = cell.innerHTML;
    const tr = cell.closest('tr');
    if (tr) tr.classList.add('inline-editing-row');
    cell.classList.remove('inline-cell-selected', 'inline-cell-sel-t', 'inline-cell-sel-r', 'inline-cell-sel-b', 'inline-cell-sel-l');
    syncSelectionEdges();
    cell.style.height = cellH + 'px';
    cell.style.minHeight = cellH + 'px';
    cell.style.width = cellW + 'px';
    cell.style.minWidth = cellW + 'px';
    cell.style.maxWidth = cellW + 'px';

    const sizer = document.createElement('span');
    sizer.className = 'inline-table-layout-sizer';
    sizer.setAttribute('aria-hidden', 'true');
    sizer.innerHTML = layoutHtml;
    cell.innerHTML = '';
    cell.appendChild(sizer);
    cell.classList.add('inline-cell-editing');

    const wrap = document.createElement('div');
    wrap.className = 'inline-table-text-wrap inline-table-rich-wrap';
    wrap.style.padding = pt + 'px ' + pr + 'px ' + pb + 'px ' + pl + 'px';
    wrap.style.boxSizing = 'border-box';
    wrap.style.fontSize = displayFontSize;
    wrap.style.lineHeight = displayLineHeight;
    wrap.style.userSelect = 'text';

    const editorEl = document.createElement('div');
    editorEl.className = 'inline-table-rich-editor';
    editorEl.innerHTML = displayContent ? displayContent.innerHTML : (value.html || '');
    wrap.appendChild(editorEl);
    wrap.addEventListener('click', function (event) {
      event.stopPropagation();
    });
    wrap.addEventListener('dblclick', function (event) {
      event.preventDefault();
      event.stopPropagation();
    });
    cell.appendChild(wrap);

    const toolbar = setCompositionToolbarVisible(cell, true);

    function resizeRichWrap() {
      const content = editorEl.querySelector('.ql-editor') || editorEl;
      const sh = Math.max(
        content.scrollHeight || 0,
        content.getBoundingClientRect().height || 0
      );
      const next = Math.max(cellH, sh + pt + pb + bt + bb);
      cell.style.minHeight = next + 'px';
      cell.style.height = next + 'px';
    }

    let editorApi = null;
    const editState = { hadUserChange: false };
    editorApi = window.ServiceCompositionEditor
      ? window.ServiceCompositionEditor.mount({
          toolbar: toolbar,
          editorEl: editorEl,
          html: value.html,
          plainText: value.plain_text,
          onChange: function (payload, source) {
            if (source === 'user') editState.hadUserChange = true;
            resizeRichWrap();
          },
          onReady: function () {
            resizeRichWrap();
            const quillRoot = editorEl.querySelector('.ql-editor');
            if (quillRoot) quillRoot.focus();
            else if (editorApi) editorApi.focus();
            window.requestAnimationFrame(function () {
              if (!richEdit || richEdit.editState !== editState || !editorApi) return;
              const baseline = editorApi.getState();
              editState.baselineHtml = baseline.html || '';
              editState.baselinePlain = baseline.plain_text || '';
              editState.baselineCaptured = true;
            });
          }
        })
      : null;

    richEdit = {
      cell: cell,
      editor: editorApi,
      originalHtml: layoutHtml,
      originalValue: originalValue,
      editState: editState
    };
    overlayKind = 'rich';
    overlayCell = cell;
    resizeRichWrap();
  }

  function fillSelectOptions(select, options, current) {
    select.innerHTML = '';
    (options || []).forEach(function (item) {
      const option = document.createElement('option');
      option.value = item.value;
      option.textContent = item.label;
      select.appendChild(option);
    });
    suppressSelectChange = true;
    select.value = current == null ? '' : String(current);
    if (select.value !== String(current || '') && current) {
      const extra = document.createElement('option');
      extra.value = String(current);
      extra.textContent = String(current);
      select.appendChild(extra);
      select.value = String(current);
    }
    suppressSelectChange = false;
  }

  function openSelectEditor(cell, extra) {
    extra = extra || {};
    closeEditors();
    clearSelection();
    ensureHost();
    const ref = cellRef(cell);
    overlaySpecialtyIndex = extra.index != null ? extra.index : null;
    if (overlaySpecialtyIndex != null) cell.dataset.inlineActiveIndex = String(overlaySpecialtyIndex);
    const adapter = ref ? sessionAdapter(ref.tableKey) : null;
    const options = adapter && typeof adapter.getSelectOptions === 'function'
      ? adapter.getSelectOptions(ref, activeSession)
      : [];
    const current = extra.current != null ? extra.current : readCellValue(cell);
    fillSelectOptions(selectEl, options, current);
    overlayKind = 'select';
    overlayCell = cell;
    const anchor = extra.anchor || cell;
    positionOverlay(selectEl, anchor);
    selectEl.classList.remove('d-none');
    selectEl.dataset.inlineOpen = '1';
    positionOverlay(selectEl, anchor);
    selectEl.focus();
    if (typeof selectEl.showPicker === 'function') {
      try { selectEl.showPicker(); } catch (err) { /* ignore */ }
    }
  }

  function renderOwnersEditor(values, ownerOptions) {
    const selected = new Set((values || []).map(String));
    const groupChecked = selected.has(GROUP_VALUE) || !selected.size;
    let html = '<div class="inline-table-owners-menu">';
    html += '<div class="form-check mb-2">';
    html += '<input class="form-check-input" type="checkbox" value="' + GROUP_VALUE + '" id="inline-owner-group"' + (groupChecked ? ' checked' : '') + '>';
    html += '<label class="form-check-label" for="inline-owner-group">Группа</label></div>';
    html += '<hr class="dropdown-divider">';
    (ownerOptions || []).forEach(function (item) {
      const id = 'inline-owner-' + item.pk;
      const checked = !groupChecked && selected.has(String(item.pk));
      html += '<div class="form-check">';
      html += '<input class="form-check-input" type="checkbox" value="' + String(item.pk) + '" id="' + id + '"' + (checked ? ' checked' : '') + '>';
      html += '<label class="form-check-label" for="' + id + '">' + escapeHtml(item.short_name || '') + '</label>';
      html += '</div>';
    });
    if (!(ownerOptions || []).length) {
      html += '<div class="text-muted small">Нет компаний</div>';
    }
    html += '</div>';
    return html;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function ownerLabel(values, ownerOptions) {
    const selected = (values || []).map(String);
    if (!selected.length || selected.indexOf(GROUP_VALUE) !== -1) return 'Группа';
    const names = (ownerOptions || []).filter(function (item) {
      return selected.indexOf(String(item.pk)) !== -1;
    }).map(function (item) { return item.short_name; });
    return names.join(', ') || selected.join(', ');
  }

  function openOwnersEditor(cell) {
    closeEditors();
    clearSelection();
    ensureHost();
    const ref = cellRef(cell);
    const adapter = ref ? sessionAdapter(ref.tableKey) : null;
    const ownerOptions = adapter && typeof adapter.getOwnerOptions === 'function'
      ? adapter.getOwnerOptions(ref, activeSession)
      : [];
    ownersEl.innerHTML = renderOwnersEditor(readCellValue(cell), ownerOptions);
    overlayKind = 'owners';
    overlayCell = cell;
    positionOverlay(ownersEl, cell, { expand: 'left', minWidth: 240, fitContent: true });
    ownersEl.classList.remove('d-none');
    ownersEl.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
      input.addEventListener('change', function () {
        const checks = Array.from(ownersEl.querySelectorAll('input[type="checkbox"]'));
        const groupCb = ownersEl.querySelector('input[value="' + GROUP_VALUE + '"]');
        if (input.value === GROUP_VALUE && input.checked) {
          checks.forEach(function (item) {
            if (item.value !== GROUP_VALUE) item.checked = false;
          });
        } else if (input.value !== GROUP_VALUE && input.checked && groupCb) {
          groupCb.checked = false;
        }
      });
    });
  }

  function moveSelection(fromCell, direction) {
    const section = fromCell.closest('[data-policy-table-key]');
    if (!section) return;
    const cells = editableCells(section).filter(function (cell) {
      return cell.dataset.inlineType === 'text'
        || cell.dataset.inlineType === 'number'
        || cell.dataset.inlineType === 'rich'
        || cell.dataset.inlineType === 'select'
        || cell.dataset.inlineType === 'owners'
        || cell.dataset.inlineType === 'checkbox'
        || cell.dataset.inlineType === 'specialties';
    });
    const index = cells.indexOf(fromCell);
    if (index < 0) return;
    const next = cells[index + direction];
    if (!next) {
      selectCell(fromCell);
      return;
    }
    selectCell(next);
    next.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  function isRichEditorEvent(event) {
    if (!richEdit || !event.target || typeof event.target.closest !== 'function') return false;
    if (richEdit.cell.contains(event.target)) return true;
    if (richEdit.editor && typeof richEdit.editor.contains === 'function' && richEdit.editor.contains(event.target)) {
      return true;
    }
    return !!(
      event.target.closest('.proposal-service-text-toolbar')
      || event.target.closest('.proposal-service-text-toolbar__list-menu')
      || event.target.closest('.proposal-service-text-toolbar__color-popover')
      || event.target.closest('.dropdown-menu')
      || event.target.closest('#typical-service-compositions-wrap-toggle')
      || event.target.closest('[data-rich-edit-action]')
      || event.target.closest('.policy-service-composition-header')
    );
  }

  function isEditorEvent(event) {
    if (textEdit && textEdit.textarea && (event.target === textEdit.textarea || textEdit.cell.contains(event.target))) {
      return true;
    }
    if (richEdit && isRichEditorEvent(event)) return true;
    if (selectEl && !selectEl.classList.contains('d-none') && (event.target === selectEl || selectEl.contains(event.target))) {
      return true;
    }
    if (ownersEl && !ownersEl.classList.contains('d-none') && ownersEl.contains(event.target)) {
      return true;
    }
    return false;
  }

  function dismissDropdownOverlays(event) {
    if (overlayKind === 'select') {
      if (selectEl && (event.target === selectEl || selectEl.contains(event.target))) return false;
      closeSelectEditor();
      clearSelection();
      return true;
    }
    if (overlayKind === 'owners') {
      if (ownersEl && ownersEl.contains(event.target)) return false;
      closeOwnersEditor(true);
      clearSelection();
      return true;
    }
    return false;
  }

  function handleNumberPointerDown(event) {
    if (event.button !== 0) return;
    const cell = getNumberCell(event.target);
    if (!cell) {
      numberDragAnchor = null;
      return false;
    }
    if (textEdit && textEdit.cell.contains(event.target) && isNumberSpinnerEvent(event, cell)) {
      numberSpinnerPointer = true;
      return true;
    }
    if (textEdit && textEdit.cell === cell) return true;
    event.preventDefault();
    closeEditors({ commitText: true });
    const section = cell.closest('[data-policy-table-key]');
    const additive = event.ctrlKey || event.metaKey;
    const before = new Set(
      Array.from(selectedCells).filter(function (item) {
        return item.closest('[data-policy-table-key]') === section;
      })
    );
    numberAlreadySelected = !additive && !event.shiftKey && selectedCells.size === 1 && selectedCells.has(cell);
    numberDragMoved = false;
    numberSpinnerPointer = false;
    if (
      event.shiftKey
      && selectedCell
      && selectedCell.dataset.inlineType === 'number'
      && selectedCell.closest('[data-policy-table-key]') === section
    ) {
      const range = getNumberCellRange(selectedCell, cell);
      setSelectedCells(additive ? Array.from(before).concat(range) : range, selectedCell);
      numberDragAnchor = null;
      numberAlreadySelected = false;
    } else if (additive) {
      const next = new Set(before);
      if (next.has(cell)) next.delete(cell);
      else next.add(cell);
      setSelectedCells(Array.from(next), cell);
      numberDragAnchor = cell;
      numberDragBase = before;
      numberDragAdditive = true;
      numberAlreadySelected = false;
    } else {
      setSelectedCells([cell], cell);
      numberDragAnchor = cell;
      numberDragBase = new Set();
      numberDragAdditive = false;
    }
    return true;
  }

  function handlePointerMove(event) {
    if (!activeSession || !numberDragAnchor) return;
    if ((event.buttons & 1) !== 1) {
      numberDragAnchor = null;
      return;
    }
    const cell = getNumberCell(event.target);
    if (!cell || cell === numberDragAnchor) return;
    if (cell.closest('[data-policy-table-key]') !== numberDragAnchor.closest('[data-policy-table-key]')) return;
    numberDragMoved = true;
    numberAlreadySelected = false;
    const range = getNumberCellRange(numberDragAnchor, cell);
    setSelectedCells(
      numberDragAdditive ? Array.from(numberDragBase).concat(range) : range,
      numberDragAnchor
    );
  }

  function handlePointerUp() {
    numberDragAnchor = null;
    numberDragBase = new Set();
    numberDragAdditive = false;
  }

  function handlePointerDown(event) {
    if (!activeSession) return;
    if (richEdit) {
      richPointerStartedInEditor = isRichEditorEvent(event);
      if (richPointerStartedInEditor) return;
    }
    if (overlayKind === 'select') return;
    dismissDropdownOverlays(event);
    handleNumberPointerDown(event);
  }

  function handleDocumentClick(event) {
    if (!activeSession) return;
    if (richEdit) {
      const richAction = event.target.closest && event.target.closest('[data-rich-edit-action]');
      if (richAction) {
        event.preventDefault();
        event.stopPropagation();
        richPointerStartedInEditor = false;
        closeRichEditor(richAction.getAttribute('data-rich-edit-action') === 'commit');
        return;
      }
      const startedInside = richPointerStartedInEditor;
      richPointerStartedInEditor = false;
      if (startedInside || isEditorEvent(event)) return;
    }
    if (overlayKind === 'select' || overlayKind === 'owners') {
      dismissDropdownOverlays(event);
    }
    if (isEditorEvent(event)) return;
    const cell = event.target.closest && event.target.closest('td[data-inline-type]');
    if (cell && activeSession.hasSection(cell.closest('[data-policy-table-key]'))) {
      const type = cell.dataset.inlineType;
      if (type === 'number') {
        if (textEdit && textEdit.cell === cell) return;
        if (numberSpinnerPointer) {
          numberSpinnerPointer = false;
          return;
        }
        const openEditor = numberAlreadySelected && selectedCell === cell && selectedCells.size === 1 && !numberDragMoved;
        numberAlreadySelected = false;
        numberDragMoved = false;
        if (event.shiftKey || event.ctrlKey || event.metaKey || selectedCells.size > 1) return;
        if (openEditor) {
          closeEditors({ commitText: true });
          openTextEditor(cell);
        }
        return;
      }
      if (type === 'text') {
        if (textEdit && textEdit.cell === cell) return;
        closeEditors({ commitText: true });
        if (selectedCell === cell) openTextEditor(cell);
        else selectCell(cell);
        return;
      }
      if (type === 'rich') {
        if (richEdit && richEdit.cell === cell) return;
        closeEditors({ commitText: true });
        selectCell(cell);
        return;
      }
      if (type === 'select') {
        closeEditors({ commitText: true });
        openSelectEditor(cell);
        return;
      }
      if (type === 'owners') {
        closeEditors({ commitText: true });
        openOwnersEditor(cell);
        return;
      }
      if (type === 'checkbox') {
        closeEditors({ commitText: true });
        const input = cell.querySelector('input[type="checkbox"]');
        if (!input || input.disabled) return;
        const clickedInput = event.target.closest && event.target.closest('input[type="checkbox"]');
        const checked = clickedInput ? input.checked : !input.checked;
        if (!clickedInput) input.checked = checked;
        applyCellValue(cell, checked);
        selectCell(cell);
        return;
      }
      if (type === 'specialties') {
        closeEditors({ commitText: true });
        const actionBtn = event.target.closest && event.target.closest('[data-specialty-action]');
        const rowEl = event.target.closest && event.target.closest('.inline-specialty-row');
        if (actionBtn) {
          event.preventDefault();
          event.stopPropagation();
          handleSpecialtyAction(cell, actionBtn, rowEl);
          selectCell(cell);
          return;
        }
        const index = rowEl ? Number(rowEl.dataset.index || 0) : 0;
        openSelectEditor(cell, {
          index: index,
          current: rowEl ? (rowEl.dataset.id || '') : '',
          anchor: rowEl || cell,
        });
        return;
      }
    }
    if (numberDragMoved) {
      numberDragMoved = false;
      numberAlreadySelected = false;
      return;
    }
    closeEditors({ commitText: true, commitOwners: true });
    clearSelection();
  }

  function handleDocumentDblClick(event) {
    if (!activeSession) return;
    const cell = event.target.closest && event.target.closest(
      'td[data-inline-type="text"], td[data-inline-type="number"], td[data-inline-type="rich"]'
    );
    if (!cell || !activeSession.hasSection(cell.closest('[data-policy-table-key]'))) return;
    if (textEdit && textEdit.cell === cell) {
      event.preventDefault();
      return;
    }
    if (richEdit && richEdit.cell === cell) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    if (cell.dataset.inlineType === 'rich') openRichEditor(cell);
    else openTextEditor(cell);
  }

  function handleDocumentKeydown(event) {
    if (!activeSession) return;
    if (overlayKind === 'select' && event.key === 'Escape') {
      closeSelectEditor();
      clearSelection();
      return;
    }
    if (overlayKind === 'owners' && event.key === 'Escape') {
      closeOwnersEditor(false);
      clearSelection();
      return;
    }
    if (richEdit) {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        if (richEdit.editor && typeof richEdit.editor.closePopovers === 'function' && richEdit.editor.closePopovers()) {
          return;
        }
        const cell = richEdit.cell;
        closeRichEditor(false);
        selectCell(cell);
      }
      return;
    }
    if (textEdit) return;
    if (!selectedCell) return;
    if (event.key === 'Escape') {
      clearSelection();
      return;
    }
    if (
      selectedCell.dataset.inlineType === 'number'
      && !event.ctrlKey
      && !event.metaKey
      && !event.altKey
      && (event.key === 'Backspace' || event.key === 'Delete')
      && selectedCells.size > 1
    ) {
      event.preventDefault();
      selectedCells.forEach(function (cell) {
        applyCellValue(cell, '');
      });
      return;
    }
    if (
      selectedCell.dataset.inlineType === 'number'
      && !event.ctrlKey
      && !event.metaKey
      && !event.altKey
      && event.key.length === 1
      && /[0-9.,]/.test(event.key)
    ) {
      event.preventDefault();
      openTextEditor(selectedCell, { seed: event.key === ',' ? '.' : event.key });
      return;
    }
    if (event.key === 'Enter' || event.key === 'F2' || event.key === ' ') {
      event.preventDefault();
      const type = selectedCell.dataset.inlineType;
      if (type === 'text' || type === 'number') openTextEditor(selectedCell);
      else if (type === 'rich') openRichEditor(selectedCell);
      else if (type === 'select') openSelectEditor(selectedCell);
      else if (type === 'owners') openOwnersEditor(selectedCell);
      else if (type === 'checkbox') {
        const input = selectedCell.querySelector('input[type="checkbox"]');
        if (!input || input.disabled) return;
        input.checked = !input.checked;
        applyCellValue(selectedCell, input.checked);
      } else if (type === 'specialties') {
        const rowEl = selectedCell.querySelector('.inline-specialty-row');
        openSelectEditor(selectedCell, {
          index: 0,
          current: rowEl ? (rowEl.dataset.id || '') : '',
          anchor: rowEl || selectedCell,
        });
      }
      return;
    }
    if (event.key === 'Tab') {
      event.preventDefault();
      moveSelection(selectedCell, event.shiftKey ? -1 : 1);
      return;
    }
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      event.preventDefault();
      moveSelection(selectedCell, 1);
      return;
    }
    if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      event.preventDefault();
      moveSelection(selectedCell, -1);
    }
  }

  function handleSelectChange() {
    if (suppressSelectChange || !overlayCell) return;
    const value = selectEl.value;
    const cell = overlayCell;
    const specialtyIndex = overlaySpecialtyIndex;
    closeSelectEditor();
    if (cell && cell.dataset.inlineType === 'specialties') {
      applySpecialtyIds(cell, function (ids) {
        const next = ids.slice();
        if (!next.length) next.push('');
        while (next.length <= specialtyIndex) next.push('');
        if (!value) next.splice(specialtyIndex, 1);
        else next[specialtyIndex] = value;
        return next;
      });
      clearSelection();
      return;
    }
    applyCellValue(cell, value);
    clearSelection();
  }

  function handleViewportChange() {
    if (overlayKind === 'select' || overlayKind === 'owners') closeEditors();
  }

  function bindGlobalListeners() {
    if (listenersBound) return;
    listenersBound = true;
    document.addEventListener('pointerdown', handlePointerDown, true);
    document.addEventListener('pointermove', handlePointerMove);
    document.addEventListener('pointerup', handlePointerUp);
    document.addEventListener('pointercancel', handlePointerUp);
    document.addEventListener('click', handleDocumentClick);
    document.addEventListener('dblclick', handleDocumentDblClick);
    document.addEventListener('keydown', handleDocumentKeydown, true);
    window.addEventListener('scroll', handleViewportChange, true);
    window.addEventListener('resize', handleViewportChange);
    ensureHost();
    selectEl.addEventListener('change', handleSelectChange);
    selectEl.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeSelectEditor();
        clearSelection();
      }
      if (event.key === 'Tab') {
        event.preventDefault();
        const cell = overlayCell;
        handleSelectChange();
        if (cell) moveSelection(cell, event.shiftKey ? -1 : 1);
      }
    });
  }

  function createSession() {
    const originals = {};
    const current = {};
    const errors = {};
    const adapters = {};
    const sections = new Set();
    const listeners = [];
    const newRows = {};
    const deletedRows = {};

    function bucket(store, tableKey) {
      if (!store[tableKey]) store[tableKey] = {};
      return store[tableKey];
    }

    function notify() {
      const payload = { dirty: api.isDirty(), saving: api.saving };
      listeners.forEach(function (fn) { fn(payload); });
    }

    const api = {
      saving: false,
      onChange: function (fn) {
        listeners.push(fn);
        return function () {
          const index = listeners.indexOf(fn);
          if (index >= 0) listeners.splice(index, 1);
        };
      },
      registerAdapter: function (tableKey, adapter) {
        adapters[tableKey] = adapter || {};
      },
      getAdapter: function (tableKey) {
        return adapters[tableKey] || null;
      },
      addSection: function (section) {
        if (section) sections.add(section);
      },
      hasSection: function (section) {
        return !!section && sections.has(section);
      },
      snapshotRow: function (tableKey, rowId, fields) {
        const orig = bucket(originals, tableKey)[rowId] = {};
        const cur = bucket(current, tableKey)[rowId] = {};
        Object.keys(fields || {}).forEach(function (field) {
          const value = cloneValue(normalizeValue(fields[field]));
          orig[field] = cloneValue(value);
          cur[field] = cloneValue(value);
        });
        notify();
      },
      markNewRow: function (tableKey, rowId, fields, meta) {
        bucket(newRows, tableKey)[String(rowId)] = {
          afterId: meta && meta.afterId != null ? String(meta.afterId) : '',
        };
        api.snapshotRow(tableKey, rowId, fields);
      },
      isNewRow: function (tableKey, rowId) {
        return !!(newRows[tableKey] && newRows[tableKey][String(rowId)]);
      },
      updateNewRowAfterId: function (tableKey, rowId, afterId) {
        const meta = newRows[tableKey] && newRows[tableKey][String(rowId)];
        if (!meta) return;
        meta.afterId = afterId != null ? String(afterId) : '';
      },
      removeRow: function (tableKey, rowId) {
        rowId = String(rowId);
        if (originals[tableKey]) delete originals[tableKey][rowId];
        if (current[tableKey]) delete current[tableKey][rowId];
        if (errors[tableKey]) delete errors[tableKey][rowId];
        if (newRows[tableKey]) delete newRows[tableKey][rowId];
        if (deletedRows[tableKey]) delete deletedRows[tableKey][rowId];
        notify();
      },
      markDeletedRow: function (tableKey, rowId) {
        rowId = String(rowId);
        if (!rowId) return;
        if (api.isNewRow(tableKey, rowId) || rowId.indexOf('new-') === 0) {
          api.removeRow(tableKey, rowId);
          return;
        }
        bucket(deletedRows, tableKey)[rowId] = true;
        if (originals[tableKey]) delete originals[tableKey][rowId];
        if (current[tableKey]) delete current[tableKey][rowId];
        if (errors[tableKey]) delete errors[tableKey][rowId];
        notify();
      },
      setValue: function (tableKey, rowId, field, value) {
        const cur = bucket(current, tableKey);
        if (!cur[rowId]) cur[rowId] = {};
        cur[rowId][field] = cloneValue(normalizeValue(value));
        notify();
      },
      getValue: function (tableKey, rowId, field) {
        const row = current[tableKey] && current[tableKey][rowId];
        if (!row) return '';
        return cloneValue(row[field]);
      },
      isFieldDirty: function (tableKey, rowId, field) {
        const origRow = originals[tableKey] && originals[tableKey][rowId];
        const curRow = current[tableKey] && current[tableKey][rowId];
        if (!origRow || !curRow) return false;
        return !valuesEqual(origRow[field], curRow[field]);
      },
      isDirty: function () {
        if (Object.keys(deletedRows).some(function (tableKey) {
          return Object.keys(deletedRows[tableKey] || {}).length > 0;
        })) return true;
        if (Object.keys(newRows).some(function (tableKey) {
          return Object.keys(newRows[tableKey] || {}).length > 0;
        })) return true;
        return Object.keys(current).some(function (tableKey) {
          return Object.keys(current[tableKey] || {}).some(function (rowId) {
            const fields = current[tableKey][rowId] || {};
            return Object.keys(fields).some(function (field) {
              return api.isFieldDirty(tableKey, rowId, field);
            });
          });
        });
      },
      collectTables: function () {
        const tables = {};
        Object.keys(current).forEach(function (tableKey) {
          const rows = [];
          Object.keys(current[tableKey] || {}).forEach(function (rowId) {
            const fields = current[tableKey][rowId] || {};
            const meta = newRows[tableKey] && newRows[tableKey][String(rowId)];
            const dirty = Object.keys(fields).some(function (field) {
              return api.isFieldDirty(tableKey, rowId, field);
            });
            if (!dirty && !meta) return;
            const payloadFields = {};
            Object.keys(fields).forEach(function (field) {
              payloadFields[field] = cloneValue(fields[field]);
            });
            const entry = { id: Number(rowId) || rowId, fields: payloadFields };
            if (meta) {
              entry.new = true;
              if (meta.afterId) entry.after_id = meta.afterId;
            }
            rows.push(entry);
          });
          if (rows.length) tables[tableKey] = rows;
        });
        Object.keys(deletedRows).forEach(function (tableKey) {
          const rows = tables[tableKey] || [];
          Object.keys(deletedRows[tableKey] || {}).forEach(function (rowId) {
            rows.push({ id: Number(rowId) || rowId, deleted: true });
          });
          if (rows.length) tables[tableKey] = rows;
        });
        return tables;
      },
      setSaving: function (value) {
        api.saving = !!value;
        notify();
      },
      setErrors: function (items) {
        Object.keys(errors).forEach(function (key) { delete errors[key]; });
        (items || []).forEach(function (item) {
          const tableKey = item.table || '';
          const rowId = String(item.id || '');
          const field = item.field || '';
          if (!tableKey || !rowId) return;
          bucket(errors, tableKey);
          if (!errors[tableKey][rowId]) errors[tableKey][rowId] = {};
          errors[tableKey][rowId][field || '__all__'] = item.message || 'Проверьте значение.';
        });
        notify();
      },
      getFieldError: function (tableKey, rowId, field) {
        const row = errors[tableKey] && errors[tableKey][rowId];
        if (!row) return '';
        return row[field] || row.__all__ || '';
      },
      clearFieldError: function (tableKey, rowId, field) {
        const row = errors[tableKey] && errors[tableKey][rowId];
        if (!row) return;
        delete row[field];
        delete row.__all__;
      },
      clearErrors: function () {
        Object.keys(errors).forEach(function (key) { delete errors[key]; });
        notify();
      },
      reset: function () {
        Object.keys(originals).forEach(function (key) { delete originals[key]; });
        Object.keys(current).forEach(function (key) { delete current[key]; });
        Object.keys(errors).forEach(function (key) { delete errors[key]; });
        Object.keys(newRows).forEach(function (key) { delete newRows[key]; });
        Object.keys(deletedRows).forEach(function (key) { delete deletedRows[key]; });
        sections.clear();
        notify();
      },
    };
    return api;
  }

  function snapshotSection(session, section) {
    const tableKey = section.dataset.policyTableKey;
    if (!tableKey) return;
    Array.from(section.querySelectorAll('tr[data-inline-row-id]')).forEach(function (row) {
      const fields = {};
      row.querySelectorAll('td[data-inline-field]').forEach(function (cell) {
        fields[cell.dataset.inlineField] = readCellValue(cell);
      });
      session.snapshotRow(tableKey, row.dataset.inlineRowId, fields);
    });
    session.addSection(section);
    syncSectionChrome(section);
  }

  function bindSection(session, section, adapter) {
    if (!session || !section) return;
    const tableKey = section.dataset.policyTableKey;
    if (adapter) session.registerAdapter(tableKey, adapter);
    snapshotSection(session, section);
  }

  function applyErrorsToDom(session, root) {
    (root || document).querySelectorAll('td[data-inline-field]').forEach(function (cell) {
      syncCellChrome(cell);
    });
  }

  function parseInlineOptions(section) {
    const node = section.querySelector('[data-policy-inline-options]');
    return parseJson(node && node.textContent, {});
  }

  function createPolicyProductsAdapter(section) {
    const options = parseInlineOptions(section);
    const catalog = options.catalog || {};
    const owners = options.owners || [];
    const types = catalog.consulting_types || [];
    const categories = catalog.service_categories || [];
    const subtypes = catalog.service_subtypes || [];

    function findCategory(id) {
      return categories.find(function (item) { return String(item.id) === String(id || ''); });
    }

    function findType(id) {
      return types.find(function (item) { return String(item.id) === String(id || ''); });
    }

    function findSubtype(id) {
      return subtypes.find(function (item) { return String(item.id) === String(id || ''); });
    }

    function updateCodeCell(row, categoryId) {
      const codeCell = row.querySelector('td[data-inline-field="service_code"]');
      if (!codeCell) return;
      const selected = findCategory(categoryId);
      const code = selected ? (selected.code || '') : '';
      codeCell.setAttribute('data-inline-value', code);
      setCellDisplay(codeCell, code);
      if (activeSession) {
        activeSession.setValue('products', row.dataset.inlineRowId, 'service_code', code);
        syncCellChrome(codeCell);
      }
    }

    function setSelectCell(row, field, value, label) {
      const cell = row.querySelector('td[data-inline-field="' + field + '"]');
      if (!cell) return;
      cell.setAttribute('data-inline-value', value == null ? '' : String(value));
      setCellDisplay(cell, label || '');
      if (activeSession) {
        activeSession.setValue('products', row.dataset.inlineRowId, field, value == null ? '' : String(value));
        activeSession.clearFieldError('products', row.dataset.inlineRowId, field);
        syncCellChrome(cell);
      }
    }

    return {
      getSelectOptions: function (ref) {
        const row = ref.cell.closest('tr');
        const consultingCell = row.querySelector('td[data-inline-field="consulting_type_ref"]');
        const categoryCell = row.querySelector('td[data-inline-field="service_category_ref"]');
        const consultingId = consultingCell ? consultingCell.getAttribute('data-inline-value') : '';
        const categoryId = categoryCell ? categoryCell.getAttribute('data-inline-value') : '';
        if (ref.field === 'consulting_type_ref') {
          return [{ value: '', label: '— выберите вид консалтинга —' }].concat(types.map(function (item) {
            return { value: String(item.id), label: item.label };
          }));
        }
        if (ref.field === 'service_category_ref') {
          const placeholder = consultingId ? '— выберите тип услуг —' : '— выберите вид консалтинга —';
          const filtered = categories.filter(function (item) {
            return String(item.consulting_type_id) === String(consultingId || '');
          });
          return [{ value: '', label: placeholder }].concat(filtered.map(function (item) {
            return { value: String(item.id), label: item.label };
          }));
        }
        if (ref.field === 'service_subtype_ref') {
          const placeholder = categoryId ? '— выберите подтип услуги —' : '— выберите тип услуг —';
          const filtered = subtypes.filter(function (item) {
            return String(item.service_category_id) === String(categoryId || '');
          });
          return [{ value: '', label: placeholder }].concat(filtered.map(function (item) {
            return { value: String(item.id), label: item.label };
          }));
        }
        return [];
      },
      getOwnerOptions: function () {
        return owners;
      },
      normalizeValue: function (ref, value) {
        if (ref.type === 'owners') {
          const selected = normalizeValue(value);
          return { value: selected, label: ownerLabel(selected, owners) };
        }
        if (ref.field === 'consulting_type_ref') {
          const item = findType(value);
          return { value: value ? String(value) : '', label: item ? item.label : '' };
        }
        if (ref.field === 'service_category_ref') {
          const item = findCategory(value);
          return { value: value ? String(value) : '', label: item ? item.label : '' };
        }
        if (ref.field === 'service_subtype_ref') {
          const item = findSubtype(value);
          return { value: value ? String(value) : '', label: item ? item.label : '' };
        }
        return { value: value, label: value };
      },
      afterChange: function (ref, value) {
        const row = ref.cell.closest('tr');
        if (!row) return;
        if (ref.field === 'consulting_type_ref') {
          setSelectCell(row, 'service_category_ref', '', '');
          setSelectCell(row, 'service_subtype_ref', '', '');
          updateCodeCell(row, '');
        }
        if (ref.field === 'service_category_ref') {
          setSelectCell(row, 'service_subtype_ref', '', '');
          updateCodeCell(row, value);
        }
      },
    };
  }

  function createPolicyServiceGoalReportsAdapter() {
    return {};
  }

  function createPolicyReportStructuresAdapter() {
    return {};
  }

  function createPolicyTypicalSectionsAdapter(section) {
    const options = parseInlineOptions(section);
    const accountingTypes = options.accounting_types || [];
    const expertiseDirs = options.expertise_dirs || [];
    const departments = options.departments || [];
    const specialties = options.specialties || [];

    function findById(items, id) {
      return items.find(function (item) { return String(item.id) === String(id || ''); });
    }

    return {
      getSelectOptions: function (ref) {
        if (ref.field === 'accounting_type') {
          return accountingTypes.map(function (item) {
            return { value: String(item.value), label: item.label };
          });
        }
        if (ref.field === 'expertise_dir') {
          return [{ value: '', label: '—' }].concat(expertiseDirs.map(function (item) {
            return { value: String(item.id), label: item.label };
          }));
        }
        if (ref.field === 'expertise_direction') {
          return [{ value: '', label: '—' }].concat(departments.map(function (item) {
            return { value: String(item.id), label: item.label };
          }));
        }
        if (ref.field === 'specialty_ids') {
          const selected = normalizeSpecialtyIds(readCellValue(ref.cell));
          const currentId = ref.cell.dataset.inlineActiveIndex != null
            ? selected[Number(ref.cell.dataset.inlineActiveIndex)] || ''
            : '';
          return [{ value: '', label: '—' }].concat(specialties.filter(function (item) {
            const id = String(item.id);
            return id === String(currentId || '') || selected.indexOf(id) === -1;
          }).map(function (item) {
            return { value: String(item.id), label: item.label };
          }));
        }
        return [];
      },
      getSpecialtyOptions: function () {
        return specialties;
      },
      normalizeValue: function (ref, value) {
        if (ref.field === 'accounting_type') {
          const item = accountingTypes.find(function (entry) {
            return String(entry.value) === String(value || '');
          });
          return { value: value ? String(value) : '', label: item ? item.label : (value || '') };
        }
        if (ref.field === 'expertise_dir') {
          const item = findById(expertiseDirs, value);
          return { value: value ? String(value) : '', label: item ? item.label : '' };
        }
        if (ref.field === 'expertise_direction') {
          const item = findById(departments, value);
          return { value: value ? String(value) : '', label: item ? item.label : '' };
        }
        if (ref.field === 'exclude_from_tkp_autofill') {
          const checked = isCheckedValue(value);
          return { value: checked, label: checked };
        }
        if (ref.field === 'specialty_ids') {
          return { value: normalizeSpecialtyIds(value), label: '' };
        }
        return { value: value, label: value };
      },
    };
  }

  function createPolicySectionStructuresAdapter(section) {
    function getSections() {
      return (parseInlineOptions(section).sections || []);
    }

    function findSection(id) {
      return getSections().find(function (item) { return String(item.id) === String(id || ''); });
    }

    function sectionOptionLabel(item) {
      const code = String((item && item.code) || '').trim();
      const display = String((item && item.displayLabel) || '').trim();
      const raw = String((item && item.label) || '').trim();
      if (code && display) return code + ' ' + display;
      if (code && raw) {
        if (raw === code || raw.indexOf(code + ' ') === 0) return raw;
        return code + ' ' + raw;
      }
      return raw || display || code;
    }

    function sectionDisplayLabel(item) {
      const display = String((item && item.displayLabel) || '').trim();
      if (display) return display;
      const code = String((item && item.code) || '').trim();
      const raw = String((item && item.label) || '').trim();
      if (code && raw.indexOf(code + ' ') === 0) return raw.slice(code.length).trim();
      return raw;
    }

    function updateCodeCell(row, sectionId) {
      if (!row) return;
      const span = row.querySelector('.typical-section-dsc-code');
      if (!span) return;
      const item = findSection(sectionId);
      span.textContent = item ? (item.code || '') : '';
    }

    return {
      getSelectOptions: function (ref) {
        if (ref.field === 'section') {
          return getSections().map(function (item) {
            return { value: String(item.id), label: sectionOptionLabel(item) };
          });
        }
        return [];
      },
      normalizeValue: function (ref, value) {
        if (ref.field === 'section') {
          const item = findSection(value);
          return {
            value: value ? String(value) : '',
            label: item ? sectionDisplayLabel(item) : '',
          };
        }
        return { value: value, label: value };
      },
      afterChange: function (ref, value) {
        if (ref.field === 'section') {
          updateCodeCell(ref.cell.closest('tr'), value);
        }
      },
    };
  }

  function parseInlineNumber(value) {
    if (value == null || value === '') return null;
    if (typeof value === 'number' && isFinite(value)) return value;
    const raw = String(value).replace(/\u00a0/g, '').replace(/\s/g, '').replace(',', '.');
    const num = Number(raw);
    return isFinite(num) ? num : null;
  }

  function formatInlineMoney(value) {
    const num = parseInlineNumber(value);
    if (num == null) return value == null ? '' : String(value);
    const sign = num < 0 ? '-' : '';
    const abs = Math.abs(num);
    const scaled = Math.round(abs * 100);
    const integerPart = Math.floor(scaled / 100);
    const decimalPart = scaled % 100;
    const intStr = String(integerPart).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
    return sign + intStr + ',' + String(decimalPart).padStart(2, '0');
  }

  function createPolicyTariffsAdapter(section) {
    const structures = createPolicySectionStructuresAdapter(section);
    function getOwners() {
      return (parseInlineOptions(section).owners || []);
    }
    function findOwner(id) {
      return getOwners().find(function (item) { return String(item.id) === String(id || ''); });
    }
    return {
      getSelectOptions: function (ref) {
        if (ref.field === 'owner') {
          return getOwners().map(function (item) {
            return { value: String(item.id), label: item.label || '' };
          });
        }
        return structures.getSelectOptions(ref);
      },
      normalizeValue: function (ref, value) {
        if (ref.field === 'owner') {
          const item = findOwner(value);
          return {
            value: value ? String(value) : '',
            label: item ? (item.label || '') : '',
          };
        }
        if (ref.field === 'section') return structures.normalizeValue(ref, value);
        if (ref.field === 'base_rate_vpm') {
          const num = parseInlineNumber(value);
          if (num == null) return { value: value, label: value };
          return { value: num.toFixed(2), label: formatInlineMoney(num) };
        }
        if (ref.field === 'service_hours' || ref.field === 'service_days_tkp') {
          const num = parseInlineNumber(value);
          if (num == null) return { value: value, label: value };
          const next = String(Math.round(num));
          return { value: next, label: next };
        }
        return { value: value, label: value };
      },
      afterChange: structures.afterChange,
    };
  }

  var TYPICAL_SERVICE_TERM_NUMBER_TO_UNIT = {
    source_data_weeks: 'source_data_term_unit',
    preliminary_report_months: 'preliminary_report_term_unit',
    final_report_weeks: 'final_report_term_unit',
  };
  var TYPICAL_SERVICE_TERM_UNIT_TO_NUMBER = {
    source_data_term_unit: 'source_data_weeks',
    preliminary_report_term_unit: 'preliminary_report_months',
    final_report_term_unit: 'final_report_weeks',
  };
  var TYPICAL_SERVICE_TERM_UNITS_FALLBACK = [
    { value: 'days', label: 'дн.' },
    { value: 'weeks', label: 'нед.' },
    { value: 'months', label: 'мес.' },
  ];

  function formatInlineTermValue(value, unit) {
    const num = parseInlineNumber(value);
    if (num == null) return value == null ? '' : String(value);
    if (unit === 'days') return String(Math.round(num));
    const scaled = Math.round(num * 10);
    const sign = num < 0 ? '-' : '';
    const abs = Math.abs(scaled);
    return sign + String(Math.floor(abs / 10)) + ',' + String(abs % 10);
  }

  function serializeInlineTermValue(value, unit) {
    const num = parseInlineNumber(value);
    if (num == null) return value;
    if (unit === 'days') return String(Math.round(num));
    return (Math.round(num * 10) / 10).toFixed(1);
  }

  function typicalServiceTermUnitForNumberCell(cell) {
    const field = cell && cell.getAttribute('data-inline-field');
    const unitField = TYPICAL_SERVICE_TERM_NUMBER_TO_UNIT[field];
    const row = cell && cell.closest('tr');
    if (!unitField || !row) return 'weeks';
    const unitCell = row.querySelector('td[data-inline-field="' + unitField + '"]');
    return unitCell ? (unitCell.getAttribute('data-inline-value') || 'weeks') : 'weeks';
  }

  function createPolicyTypicalServiceTermsAdapter(section) {
    function getUnits() {
      const parsed = parseInlineOptions(section).units;
      return (parsed && parsed.length) ? parsed : TYPICAL_SERVICE_TERM_UNITS_FALLBACK;
    }
    function findUnit(value) {
      return getUnits().find(function (item) {
        return String(item.value) === String(value || '');
      });
    }
    return {
      getSelectOptions: function (ref) {
        if (!TYPICAL_SERVICE_TERM_UNIT_TO_NUMBER[ref.field]) return [];
        return getUnits().map(function (item) {
          return { value: String(item.value), label: item.label || item.value };
        });
      },
      normalizeValue: function (ref, value) {
        if (TYPICAL_SERVICE_TERM_UNIT_TO_NUMBER[ref.field]) {
          const item = findUnit(value);
          return {
            value: value ? String(value) : '',
            label: item ? (item.label || '') : '',
          };
        }
        if (TYPICAL_SERVICE_TERM_NUMBER_TO_UNIT[ref.field]) {
          const unit = typicalServiceTermUnitForNumberCell(ref.cell);
          const num = parseInlineNumber(value);
          if (num == null) return { value: value, label: value };
          return {
            value: serializeInlineTermValue(num, unit),
            label: formatInlineTermValue(num, unit),
          };
        }
        return { value: value, label: value };
      },
      afterChange: function (ref, value) {
        const numberField = TYPICAL_SERVICE_TERM_UNIT_TO_NUMBER[ref.field];
        if (!numberField) return;
        const row = ref.cell && ref.cell.closest('tr');
        if (!row) return;
        const numCell = row.querySelector('td[data-inline-field="' + numberField + '"]');
        if (!numCell) return;
        numCell.setAttribute('data-inline-step', value === 'days' ? '1' : '0.1');
        applyCellValue(numCell, numCell.getAttribute('data-inline-value'));
      },
    };
  }

  function createPolicyTypicalServiceCompositionsAdapter(section) {
    const structures = createPolicySectionStructuresAdapter(section);
    return {
      getSelectOptions: structures.getSelectOptions,
      normalizeValue: function (ref, value) {
        if (ref.field === 'section') return structures.normalizeValue(ref, value);
        if (ref.field === 'service_composition_editor_state' || ref.type === 'rich') {
          const serialized = serializeRichValue(value);
          return { value: serialized, label: serialized };
        }
        return { value: value, label: value };
      },
      afterChange: structures.afterChange,
    };
  }

  function attach(session) {
    activeSession = session;
    bindGlobalListeners();
    ensureHost();
  }

  function detach(session) {
    if (session && activeSession !== session) return;
    closeEditors();
    clearSelection();
    activeSession = null;
  }

  global.WorkspaceInlineEditor = {
    GROUP_VALUE: GROUP_VALUE,
    createSession: createSession,
    attach: attach,
    detach: detach,
    bindSection: bindSection,
    closeEditors: closeEditors,
    applyErrorsToDom: applyErrorsToDom,
    createPolicyProductsAdapter: createPolicyProductsAdapter,
    createPolicyServiceGoalReportsAdapter: createPolicyServiceGoalReportsAdapter,
    createPolicyReportStructuresAdapter: createPolicyReportStructuresAdapter,
    createPolicyTypicalSectionsAdapter: createPolicyTypicalSectionsAdapter,
    createPolicySectionStructuresAdapter: createPolicySectionStructuresAdapter,
    createPolicyTariffsAdapter: createPolicyTariffsAdapter,
    createPolicyTypicalServiceTermsAdapter: createPolicyTypicalServiceTermsAdapter,
    createPolicyTypicalServiceCompositionsAdapter: createPolicyTypicalServiceCompositionsAdapter,
    readCellValue: readCellValue,
  };
})(window);
