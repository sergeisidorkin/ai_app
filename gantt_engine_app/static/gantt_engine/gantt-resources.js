(function (window) {
  'use strict';

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, function (char) {
      return ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;',
      })[char];
    });
  }

  function normalizeText(value) {
    return String(value || '').trim();
  }

  function uniqueId(prefix) {
    return (prefix || 'gantt-resource') + '-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  }

  function normalizeList(items, getLabel) {
    var seen = {};
    return (Array.isArray(items) ? items : [])
      .map(function (item) {
        return normalizeText(getLabel ? getLabel(item) : item);
      })
      .filter(function (label) {
        if (!label || seen[label]) return false;
        seen[label] = true;
        return true;
      });
  }

  function normalizeExecutors(items) {
    var byLabel = {};
    (Array.isArray(items) ? items : []).forEach(function (item) {
      var label = normalizeText(typeof item === 'string' ? item : (item && (item.label || item.name || item.value)));
      if (!label) return;
      var current = byLabel[label] || { label: label, specialties: [] };
      var specialtySeen = {};
      current.specialties.forEach(function (value) { specialtySeen[value] = true; });
      normalizeList(item && item.specialties).forEach(function (specialty) {
        if (specialtySeen[specialty]) return;
        current.specialties.push(specialty);
        specialtySeen[specialty] = true;
      });
      byLabel[label] = current;
    });
    return Object.keys(byLabel).map(function (key) { return byLabel[key]; });
  }

  function createResources(rawOptions) {
    var options = rawOptions || {};
    var gantt = options.gantt || null;
    var root = options.root || null;
    var container = options.container || null;
    var toggleButton = options.toggleButton || null;
    var fields = Object.assign({
      specialty: 'specialty',
      executor: 'executor',
      resourceId: 'resource_id',
      resourceName: 'resource_name',
    }, options.fields || {});
    var catalogs = normalizeCatalogs(options.catalogs || {});
    var rows = [];
    var selectedRowIds = new Set();
    var boundEvents = [];
    var modal = null;
    var modalEl = null;
    var modalAssignments = [];
    var modalRowId = '';
    var isExpanded = false;
    var renderQueued = false;
    var syncActive = false;
    var instanceId = uniqueId('gantt-resources');

    function normalizeCatalogs(raw) {
      return {
        specialties: normalizeList(raw.specialties, function (item) {
          return typeof item === 'string' ? item : (item && (item.label || item.name || item.specialty));
        }),
        executors: normalizeExecutors(raw.executors),
      };
    }

    function getTaskId(task) {
      return task && task.id !== undefined && task.id !== null ? String(task.id) : '';
    }

    function getTaskField(task, key) {
      return normalizeText(task && task[fields[key]]);
    }

    function setTaskField(task, key, value) {
      if (!task) return;
      var field = fields[key];
      if (!field) return;
      var normalized = normalizeText(value);
      if (normalized) {
        task[field] = normalized;
      } else {
        task[field] = '';
        delete task[field];
      }
    }

    function eachTask(callback) {
      if (!gantt || typeof gantt.eachTask !== 'function') return;
      try {
        gantt.eachTask(function (task) {
          if (!task) return;
          if (!isTaskAssignable(task)) return;
          callback(task);
        });
      } catch (_) {
        // A disposed or mid-remount Gantt can throw while walking the store.
      }
    }

    function isTaskAssignable(task) {
      return !(typeof options.isAssignableTask === 'function' && !options.isAssignableTask(task, gantt));
    }

    function isTaskDisabled(task, context) {
      return !!(typeof options.isTaskDisabled === 'function' && options.isTaskDisabled(task, gantt, context || null));
    }

    function sanitizeTaskIds(taskIds, context) {
      return normalizeList(taskIds).filter(function (taskId) {
        var task = getTaskById(taskId);
        return task && isTaskAssignable(task) && !isTaskDisabled(task, context);
      });
    }

    function getTaskById(taskId) {
      if (!taskId || !gantt || typeof gantt.getTask !== 'function') return null;
      try {
        return gantt.getTask(taskId);
      } catch (_) {
        return null;
      }
    }

    function getTaskOptions(context) {
      var items = [];
      eachTask(function (task) {
        var id = getTaskId(task);
        if (!id) return;
        var number = typeof options.getTaskNumber === 'function' ? normalizeText(options.getTaskNumber(task, gantt)) : '';
        var label = typeof options.getTaskLabel === 'function'
          ? normalizeText(options.getTaskLabel(task, gantt))
          : normalizeText(task.text);
        items.push({
          id: id,
          number: number,
          label: (number ? number + ' ' : '') + (label || id),
          disabled: isTaskDisabled(task, context),
        });
      });
      return items;
    }

    function normalizeMetaRows(meta) {
      return (Array.isArray(meta && meta.resources) ? meta.resources : [])
        .map(function (item, index) {
          if (!item || typeof item !== 'object') return null;
          var id = normalizeText(item.id) || uniqueId('resource');
          return {
            id: id,
            specialty: normalizeText(item.specialty),
            executor: normalizeText(item.executor),
            resourceName: normalizeText(item.resource_name || item.resourceName || item.name),
            taskIds: normalizeList(item.task_ids || item.taskIds),
            position: Number.isFinite(Number(item.position)) ? Number(item.position) : index + 1,
          };
        })
        .filter(Boolean)
        .sort(function (left, right) {
          return (left.position - right.position) || left.id.localeCompare(right.id);
        });
    }

    function taskIdsEqual(left, right) {
      if (left.length !== right.length) return false;
      for (var i = 0; i < left.length; i += 1) {
        if (String(left[i]) !== String(right[i])) return false;
      }
      return true;
    }

    function findRowById(id) {
      var normalized = normalizeText(id);
      return rows.find(function (row) { return row.id === normalized; }) || null;
    }

    function findRowByExecutor(executor) {
      var normalized = normalizeText(executor);
      if (!normalized) return null;
      return rows.find(function (row) { return row.executor === normalized; }) || null;
    }

    function resourcePairKey(rowLike) {
      var specialty = normalizeText(rowLike && rowLike.specialty);
      var executor = normalizeText(rowLike && rowLike.executor);
      return specialty && executor ? specialty + '\u0000' + executor : '';
    }

    function findDuplicateResourcePair(rowLike) {
      var key = resourcePairKey(rowLike);
      var id = normalizeText(rowLike && rowLike.id);
      if (!key) return null;
      return rows.find(function (row) {
        return row.id !== id && resourcePairKey(row) === key;
      }) || null;
    }

    function showValidationError(message, control) {
      if (control && typeof control.setCustomValidity === 'function' && typeof control.reportValidity === 'function') {
        control.setCustomValidity(message);
        control.reportValidity();
        window.setTimeout(function () { control.setCustomValidity(''); }, 0);
        return;
      }
      if (window.alert) window.alert(message);
    }

    function showModalValidationWarning(message, control) {
      if (!modalEl) {
        showValidationError(message, control);
        return;
      }
      var warning = modalEl.querySelector('.gantt-resources-modal-warning');
      if (warning) {
        warning.textContent = message;
        warning.classList.remove('d-none');
      }
      if (control && typeof control.focus === 'function') control.focus();
    }

    function clearModalValidationWarning() {
      if (!modalEl) return;
      var warning = modalEl.querySelector('.gantt-resources-modal-warning');
      if (!warning) return;
      warning.textContent = '';
      warning.classList.add('d-none');
    }

    function findOrCreateRowForTask(task) {
      var executor = getTaskField(task, 'executor');
      if (!executor) return null;
      var resourceId = getTaskField(task, 'resourceId');
      var row = null;
      if (resourceId) {
        row = findRowById(resourceId);
        if (row && row.executor && row.executor !== executor) row = null;
      }
      if (!row) row = findRowByExecutor(executor);
      if (!row) {
        row = {
          id: resourceId || uniqueId('resource'),
          specialty: getTaskField(task, 'specialty'),
          executor: executor,
          resourceName: getTaskField(task, 'resourceName') || executor,
          taskIds: [],
          position: rows.length + 1,
        };
        rows.push(row);
      }
      if (!row.specialty) row.specialty = getTaskField(task, 'specialty');
      if (!row.resourceName) row.resourceName = getTaskField(task, 'resourceName') || row.executor;
      return row;
    }

    function rebuildRowsFromGantt() {
      var metaRows = normalizeMetaRows(options.meta || {});
      rows = metaRows.map(function (row) {
        return Object.assign({}, row, { taskIds: [] });
      });

      eachTask(function (task) {
        if (isTaskDisabled(task)) {
          setTaskField(task, 'specialty', '');
          setTaskField(task, 'executor', '');
          setTaskField(task, 'resourceId', '');
          setTaskField(task, 'resourceName', '');
          return;
        }
        var row = findOrCreateRowForTask(task);
        if (!row) return;
        var taskId = getTaskId(task);
        if (taskId && row.taskIds.indexOf(taskId) === -1) row.taskIds.push(taskId);
        setTaskField(task, 'resourceId', row.id);
        if (row.resourceName) setTaskField(task, 'resourceName', row.resourceName);
      });

      rows = rows.filter(function (row) {
        return row.executor || row.specialty || row.resourceName || row.taskIds.length;
      });
      rows.forEach(function (row, index) { row.position = index + 1; });
      applyCalculatedResourceNames();
      selectedRowIds.forEach(function (id) {
        if (!findRowById(id)) selectedRowIds.delete(id);
      });
    }

    function queueRender() {
      if (renderQueued) return;
      renderQueued = true;
      window.requestAnimationFrame(function () {
        renderQueued = false;
        render();
      });
    }

    function notifyChange() {
      options.meta = serializeMeta(Object.assign({}, options.meta || {}));
      if (typeof options.onChange === 'function') {
        options.onChange(api);
      }
    }

    function getExecutorsForSpecialty(specialty) {
      var normalized = normalizeText(specialty);
      if (!normalized) return [];
      return catalogs.executors
        .filter(function (executor) {
          return executor.specialties.indexOf(normalized) !== -1;
        })
        .map(function (executor) { return executor.label; });
    }

    function optionHtml(values, selectedValue) {
      var selected = normalizeText(selectedValue);
      return '<option value=""></option>' + normalizeList(values).map(function (value) {
        return '<option value="' + escapeHtml(value) + '"' + (value === selected ? ' selected' : '') + '>' +
          escapeHtml(value) + '</option>';
      }).join('');
    }

    function resourceNumberKey(row) {
      var executor = normalizeText(row && row.executor);
      if (executor) return 'executor:' + executor;
      return 'resource:' + normalizeText(row && row.id);
    }

    function calculatedResourceName(rowLike) {
      var previewId = normalizeText(rowLike && rowLike.id);
      var targetKey = resourceNumberKey(rowLike);
      var numbersByKey = {};
      var nextNumber = 1;
      var includedPreview = false;
      rows.forEach(function (row) {
        var current = previewId && row.id === previewId ? Object.assign({}, row, rowLike) : row;
        var key = resourceNumberKey(current);
        if (!numbersByKey[key]) {
          numbersByKey[key] = nextNumber;
          nextNumber += 1;
        }
        if (previewId && row.id === previewId) includedPreview = true;
      });
      if (rowLike && !includedPreview) {
        if (!numbersByKey[targetKey]) numbersByKey[targetKey] = nextNumber;
      }
      return 'Сотрудник ' + (numbersByKey[targetKey] || 1);
    }

    function applyCalculatedResourceNames() {
      var numbersByKey = {};
      var nextNumber = 1;
      rows.forEach(function (row) {
        var key = resourceNumberKey(row);
        if (!numbersByKey[key]) {
          numbersByKey[key] = nextNumber;
          nextNumber += 1;
        }
        row.resourceName = 'Сотрудник ' + numbersByKey[key];
      });
    }

    function syncCalculatedResourceNamesToTasks() {
      var wasSyncActive = syncActive;
      syncActive = true;
      try {
        rows.forEach(function (row) {
          normalizeList(row.taskIds).forEach(function (taskId) {
            updateTask(taskId, { resourceName: row.resourceName });
          });
        });
      } finally {
        syncActive = wasSyncActive;
      }
    }

    function updateTask(taskId, changes) {
      var task = getTaskById(taskId);
      if (!task) return;
      if ('specialty' in changes) setTaskField(task, 'specialty', changes.specialty);
      if ('executor' in changes) setTaskField(task, 'executor', changes.executor);
      if ('resourceId' in changes) setTaskField(task, 'resourceId', changes.resourceId);
      if ('resourceName' in changes) setTaskField(task, 'resourceName', changes.resourceName);
      if (typeof gantt.updateTask === 'function') {
        try { gantt.updateTask(task.id); } catch (_) { /* task can disappear during remount */ }
      }
    }

    function applyRowToTasks(row, oldTaskIds) {
      if (!row) return;
      var wasSyncActive = syncActive;
      syncActive = true;
      try {
        applyCalculatedResourceNames();
        var nextTaskIds = sanitizeTaskIds(row.taskIds, row);
        row.taskIds = nextTaskIds;
        normalizeList(oldTaskIds || []).forEach(function (taskId) {
          if (nextTaskIds.indexOf(taskId) !== -1) return;
          var task = getTaskById(taskId);
          if (!task || getTaskField(task, 'resourceId') !== row.id) return;
          updateTask(taskId, { specialty: '', executor: '', resourceId: '', resourceName: '' });
        });
        nextTaskIds.forEach(function (taskId) {
          rows.forEach(function (other) {
            if (other.id === row.id) return;
            other.taskIds = other.taskIds.filter(function (id) { return id !== taskId; });
          });
          updateTask(taskId, {
            specialty: row.specialty,
            executor: row.executor,
            resourceId: row.id,
            resourceName: row.resourceName || row.executor,
          });
        });
        syncCalculatedResourceNamesToTasks();
      } finally {
        syncActive = wasSyncActive;
      }
    }

    function clearRowTasks(row) {
      if (!row) return;
      var wasSyncActive = syncActive;
      syncActive = true;
      try {
        row.taskIds.forEach(function (taskId) {
          var task = getTaskById(taskId);
          if (!task || getTaskField(task, 'resourceId') !== row.id) return;
          updateTask(taskId, { specialty: '', executor: '', resourceId: '', resourceName: '' });
        });
      } finally {
        syncActive = wasSyncActive;
      }
    }

    function getTaskNumber(task) {
      return typeof options.getTaskNumber === 'function' ? normalizeText(options.getTaskNumber(task, gantt)) : '';
    }

    function getTaskDuration(task) {
      if (typeof options.getTaskDuration === 'function') {
        var custom = Number(options.getTaskDuration(task, gantt));
        return Number.isFinite(custom) ? custom : 0;
      }
      var duration = Number(task && task.duration);
      return Number.isFinite(duration) ? duration : 0;
    }

    function rowTaskObjects(row) {
      return sanitizeTaskIds(row && row.taskIds, row).map(getTaskById).filter(Boolean);
    }

    function formatTaskNumbers(row) {
      return rowTaskObjects(row)
        .map(function (task) { return getTaskNumber(task); })
        .filter(Boolean)
        .join('; ');
    }

    function formatWorkload(row) {
      var total = rowTaskObjects(row).reduce(function (sum, task) {
        return sum + getTaskDuration(task);
      }, 0);
      return Number.isFinite(total) ? String(Math.round(total * 100) / 100).replace('.', ',') : '';
    }

    function parseDate(value) {
      if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
      var raw = normalizeText(value);
      if (!raw) return null;
      var iso = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
      if (iso) return new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
      var parsed = new Date(raw);
      return Number.isNaN(parsed.getTime()) ? null : parsed;
    }

    function dayKey(date) {
      return date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
    }

    function eachTaskDay(task, callback) {
      var start = parseDate(task && task.start_date);
      var end = parseDate(task && task.end_date);
      if (!start) return;
      if (!end || end < start) end = new Date(start);
      var cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate());
      var finalDate = new Date(end.getFullYear(), end.getMonth(), end.getDate());
      var duration = getTaskDuration(task);
      if (duration <= 0 || cursor.valueOf() === finalDate.valueOf()) {
        callback(dayKey(cursor));
        return;
      }
      while (cursor < finalDate) {
        callback(dayKey(cursor));
        cursor.setDate(cursor.getDate() + 1);
      }
    }

    function formatConflicts(row) {
      var tasks = rowTaskObjects(row);
      var byDay = {};
      tasks.forEach(function (task) {
        eachTaskDay(task, function (key) {
          byDay[key] = byDay[key] || [];
          byDay[key].push(getTaskId(task));
        });
      });
      var conflictIds = {};
      Object.keys(byDay).forEach(function (key) {
        if (byDay[key].length < 2) return;
        byDay[key].forEach(function (taskId) { conflictIds[taskId] = true; });
      });
      return tasks
        .filter(function (task) { return conflictIds[getTaskId(task)]; })
        .map(function (task) { return getTaskNumber(task); })
        .filter(Boolean)
        .join('; ');
    }

    function syncActions() {
      if (!container) return;
      var actions = container.querySelector('.gantt-resources-row-actions');
      var checkedRows = rows.filter(function (row) { return selectedRowIds.has(row.id); });
      var single = checkedRows.length === 1 ? checkedRows[0] : null;
      if (actions) actions.classList.toggle('d-none', !checkedRows.length);
      var up = container.querySelector('.gantt-resources-up-btn');
      var down = container.querySelector('.gantt-resources-down-btn');
      var edit = container.querySelector('.gantt-resources-edit-btn');
      var del = container.querySelector('.gantt-resources-delete-btn');
      var singleIndex = single ? rows.findIndex(function (row) { return row.id === single.id; }) : -1;
      if (up) up.disabled = !single || singleIndex <= 0;
      if (down) down.disabled = !single || singleIndex < 0 || singleIndex >= rows.length - 1;
      if (edit) edit.disabled = !single;
      if (del) del.disabled = !checkedRows.length;
      var master = container.querySelector('.gantt-resources-master-check');
      var rowChecks = Array.from(container.querySelectorAll('.gantt-resources-row-check'));
      if (master) {
        master.checked = rowChecks.length > 0 && rowChecks.every(function (box) { return box.checked; });
        master.indeterminate = rowChecks.some(function (box) { return box.checked; }) && !master.checked;
      }
    }

    function renderRows() {
      if (!container) return;
      var tbody = container.querySelector('.gantt-resources-tbody');
      if (!tbody) return;
      applyCalculatedResourceNames();
      tbody.innerHTML = '';
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-muted">Пока нет данных.</td></tr>';
        syncActions();
        return;
      }
      rows.forEach(function (row) {
        var tr = document.createElement('tr');
        tr.className = selectedRowIds.has(row.id) ? 'table-active' : '';
        tr.dataset.resourceId = row.id;
        var executorOptions = getExecutorsForSpecialty(row.specialty);
        tr.innerHTML =
          '<td class="text-nowrap">' +
          '<div class="form-check"><input type="checkbox" class="form-check-input gantt-resources-row-check" aria-label="Выделить ресурс"></div>' +
          '</td>' +
          '<td><select class="form-select form-select-sm gantt-resources-specialty" aria-label="Специальность">' +
          optionHtml(catalogs.specialties, row.specialty) +
          '</select></td>' +
          '<td><select class="form-select form-select-sm gantt-resources-executor" aria-label="ФИО">' +
          optionHtml(executorOptions, row.executor) +
          '</select></td>' +
          '<td><input type="text" class="form-control form-control-sm readonly-field gantt-resources-name" aria-label="Название ресурса" value="' + escapeHtml(row.resourceName || '') + '" readonly tabindex="-1"></td>' +
          '<td class="gantt-resources-task-list">' + escapeHtml(formatTaskNumbers(row)) + '</td>' +
          '<td><input type="text" class="form-control form-control-sm readonly-field gantt-resources-workload" readonly tabindex="-1" value="' + escapeHtml(formatWorkload(row)) + '"></td>' +
          '<td><input type="text" class="form-control form-control-sm readonly-field gantt-resources-conflicts" readonly tabindex="-1" value="' + escapeHtml(formatConflicts(row)) + '"></td>';
        var check = tr.querySelector('.gantt-resources-row-check');
        check.checked = selectedRowIds.has(row.id);
        check.addEventListener('change', function () {
          if (check.checked) selectedRowIds.add(row.id);
          else selectedRowIds.delete(row.id);
          tr.classList.toggle('table-active', check.checked);
          syncActions();
        });
        tr.querySelector('.gantt-resources-specialty').addEventListener('change', function (event) {
          var oldTaskIds = row.taskIds.slice();
          var oldSpecialty = row.specialty;
          var oldExecutor = row.executor;
          row.specialty = normalizeText(event.target.value);
          if (getExecutorsForSpecialty(row.specialty).indexOf(row.executor) === -1) row.executor = '';
          if (findDuplicateResourcePair(row)) {
            row.specialty = oldSpecialty;
            row.executor = oldExecutor;
            showValidationError('Ресурс с такой специальностью и ФИО уже есть в таблице.', event.target);
            renderRows();
            return;
          }
          applyRowToTasks(row, oldTaskIds);
          notifyChange();
          renderRows();
        });
        tr.querySelector('.gantt-resources-executor').addEventListener('change', function (event) {
          var oldTaskIds = row.taskIds.slice();
          var oldExecutor = row.executor;
          row.executor = normalizeText(event.target.value);
          if (findDuplicateResourcePair(row)) {
            row.executor = oldExecutor;
            showValidationError('Ресурс с такой специальностью и ФИО уже есть в таблице.', event.target);
            renderRows();
            return;
          }
          applyRowToTasks(row, oldTaskIds);
          notifyChange();
          renderRows();
        });
        tbody.appendChild(tr);
      });
      syncActions();
    }

    function render() {
      if (!container) return;
      container.innerHTML =
        '<div class="gantt-resources-panel-inner">' +
        '<div class="d-flex justify-content-between align-items-center mb-3 table-section-header">' +
        '<h5 class="table-section-title mb-0"><i class="bi bi-table me-2"></i>Ресурсы проекта</h5>' +
        '</div>' +
        '<div class="table-responsive">' +
        '<table class="table table-sm align-top gantt-resources-table">' +
        '<thead><tr>' +
        '<th style="width:1%"><div class="form-check m-0"><input type="checkbox" class="form-check-input gantt-resources-master-check" aria-label="Выделить все строки ресурсов"></div></th>' +
        '<th>Специальность</th><th>ФИО</th><th>Название ресурса</th><th>Задачи</th><th>Трудозатраты, раб. дн.</th><th>Конфликты</th>' +
        '</tr></thead>' +
        '<tbody class="gantt-resources-tbody"></tbody>' +
        '</table>' +
        '<div class="d-flex align-items-stretch gap-2 products-actions-row gantt-resources-actions-row">' +
        '<button type="button" class="btn btn-primary btn-sm d-flex align-items-center gantt-resources-add-btn">' +
        '<i class="bi bi-plus-circle me-2"></i>Добавить строку' +
        '</button>' +
        '<div class="gantt-resources-row-actions d-none d-flex"><div class="btn-group">' +
        '<button type="button" class="btn btn-outline-primary btn-sm h-100 py-0 gantt-resources-up-btn" title="Переместить вверх" aria-label="Переместить вверх"><i class="bi bi-arrow-up-square"></i></button>' +
        '<button type="button" class="btn btn-outline-primary btn-sm h-100 py-0 gantt-resources-down-btn" title="Переместить вниз" aria-label="Переместить вниз"><i class="bi bi-arrow-down-square"></i></button>' +
        '<button type="button" class="btn btn-outline-primary btn-sm h-100 py-0 gantt-resources-edit-btn" title="Изменить" aria-label="Изменить"><i class="bi bi-pencil-square"></i></button>' +
        '<button type="button" class="btn btn-outline-danger btn-sm h-100 py-0 gantt-resources-delete-btn" title="Удалить" aria-label="Удалить"><i class="bi bi-x-square"></i></button>' +
        '</div></div>' +
        '</div>' +
        '</div>' +
        '</div>';
      container.classList.toggle('d-none', !isExpanded);
      bindTableEvents();
      renderRows();
    }

    function bindTableEvents() {
      if (!container) return;
      var master = container.querySelector('.gantt-resources-master-check');
      if (master) {
        master.addEventListener('change', function () {
          selectedRowIds.clear();
          if (master.checked) rows.forEach(function (row) { selectedRowIds.add(row.id); });
          renderRows();
        });
      }
      container.querySelector('.gantt-resources-add-btn').addEventListener('click', function () {
        openResourceModal(null);
      });
      container.querySelector('.gantt-resources-up-btn').addEventListener('click', function () {
        moveSelectedRow(-1);
      });
      container.querySelector('.gantt-resources-down-btn').addEventListener('click', function () {
        moveSelectedRow(1);
      });
      container.querySelector('.gantt-resources-edit-btn').addEventListener('click', function () {
        var row = getSingleSelectedRow();
        if (row) openResourceModal(row);
      });
      container.querySelector('.gantt-resources-delete-btn').addEventListener('click', function () {
        deleteSelectedRows();
      });
    }

    function getSingleSelectedRow() {
      if (selectedRowIds.size !== 1) return null;
      return findRowById(Array.from(selectedRowIds)[0]);
    }

    function moveSelectedRow(delta) {
      var row = getSingleSelectedRow();
      if (!row) return;
      var index = rows.findIndex(function (item) { return item.id === row.id; });
      var next = index + delta;
      if (index < 0 || next < 0 || next >= rows.length) return;
      var tmp = rows[index];
      rows[index] = rows[next];
      rows[next] = tmp;
      rows.forEach(function (item, idx) { item.position = idx + 1; });
      applyCalculatedResourceNames();
      syncCalculatedResourceNamesToTasks();
      notifyChange();
      renderRows();
    }

    function deleteSelectedRows() {
      if (!selectedRowIds.size) return;
      Array.from(selectedRowIds).forEach(function (id) {
        clearRowTasks(findRowById(id));
      });
      rows = rows.filter(function (row) { return !selectedRowIds.has(row.id); });
      selectedRowIds.clear();
      rows.forEach(function (row, index) { row.position = index + 1; });
      applyCalculatedResourceNames();
      syncCalculatedResourceNamesToTasks();
      notifyChange();
      renderRows();
    }

    function ensureModal() {
      if (modalEl) return modalEl;
      modalEl = document.createElement('div');
      modalEl.className = 'modal fade gantt-resources-modal';
      modalEl.tabIndex = -1;
      modalEl.setAttribute('aria-hidden', 'true');
      modalEl.id = instanceId + '-modal';
      modalEl.innerHTML =
        '<div class="modal-dialog modal-lg modal-dialog-scrollable">' +
        '<div class="modal-content">' +
        '<div class="modal-header">' +
        '<h5 class="modal-title"><i class="bi bi-person-vcard me-2"></i>Ресурс проекта</h5>' +
        '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Закрыть"></button>' +
        '</div>' +
        '<div class="modal-body"></div>' +
        '<div class="modal-footer">' +
        '<button type="button" class="btn btn-secondary btn-sm gantt-resources-modal-cancel" data-bs-dismiss="modal">Отмена</button>' +
        '<button type="button" class="btn btn-primary btn-sm gantt-resources-modal-save"><i class="bi bi-check2-circle me-2"></i>Сохранить</button>' +
        '</div>' +
        '</div>' +
        '</div>';
      document.body.appendChild(modalEl);
      modalEl.querySelector('.gantt-resources-modal-save').addEventListener('click', saveModal);
      if (window.bootstrap && window.bootstrap.Modal) {
        modal = window.bootstrap.Modal.getOrCreateInstance(modalEl);
      }
      return modalEl;
    }

    function openResourceModal(row) {
      ensureModal();
      modalRowId = row ? row.id : '';
      modalAssignments = normalizeList(row ? row.taskIds : []);
      renderModalBody(row || {
        id: '',
        specialty: '',
        executor: '',
        resourceName: '',
        taskIds: [],
      });
      if (modal) {
        modal.show();
      } else {
        modalEl.classList.add('show');
        modalEl.style.display = 'block';
        modalEl.removeAttribute('aria-hidden');
      }
    }

    function renderModalBody(row) {
      var body = modalEl.querySelector('.modal-body');
      var executorOptions = getExecutorsForSpecialty(row.specialty);
      row.resourceName = calculatedResourceName(row);
      body.innerHTML =
        '<div class="alert alert-warning d-none gantt-resources-modal-warning" role="alert"></div>' +
        '<div class="gantt-resources-modal-grid">' +
        '<div class="mb-3">' +
        '<label class="form-label" for="' + instanceId + '-specialty">Специальность</label>' +
        '<select id="' + instanceId + '-specialty" class="form-select form-select-sm gantt-resources-modal-specialty">' +
        optionHtml(catalogs.specialties, row.specialty) +
        '</select>' +
        '</div>' +
        '<div class="mb-3">' +
        '<label class="form-label" for="' + instanceId + '-executor">ФИО</label>' +
        '<select id="' + instanceId + '-executor" class="form-select form-select-sm gantt-resources-modal-executor">' +
        optionHtml(executorOptions, row.executor) +
        '</select>' +
        '</div>' +
        '<div class="mb-3">' +
        '<label class="form-label" for="' + instanceId + '-name">Название ресурса</label>' +
        '<input id="' + instanceId + '-name" type="text" class="form-control form-control-sm readonly-field gantt-resources-modal-name" readonly tabindex="-1" value="' + escapeHtml(row.resourceName || '') + '">' +
        '</div>' +
        '<div class="mb-3">' +
        '<label class="form-label">Трудозатраты, раб. дн.</label>' +
        '<input type="text" class="form-control form-control-sm readonly-field gantt-resources-modal-workload" readonly tabindex="-1" value="' + escapeHtml(formatWorkload({ taskIds: modalAssignments })) + '">' +
        '</div>' +
        '<div class="mb-3 gantt-resources-modal-conflicts-field">' +
        '<label class="form-label">Конфликты</label>' +
        '<input type="text" class="form-control form-control-sm readonly-field gantt-resources-modal-conflicts" readonly tabindex="-1" value="' + escapeHtml(formatConflicts({ taskIds: modalAssignments })) + '">' +
        '</div>' +
        '</div>' +
        '<div class="gantt-resources-assignments policy-gantt-links">' +
        '<div class="policy-gantt-links-title">Назначения</div>' +
        '<div class="policy-gantt-links-editor">' +
        '<div class="table-responsive"><table class="table table-sm align-middle policy-gantt-links-table gantt-resources-assignments-table">' +
        '<thead><tr><th class="policy-gantt-links-check-col"></th><th>Название задачи</th></tr></thead>' +
        '<tbody class="gantt-resources-assignments-tbody"></tbody>' +
        '</table></div>' +
        '<div class="d-flex align-items-stretch gap-2 policy-gantt-links-actions-row">' +
        '<button type="button" class="btn btn-sm policy-gantt-links-add-btn gantt-resources-assignment-add-btn"><i class="bi bi-plus-circle me-2"></i>Добавить назначение</button>' +
        '<div class="policy-gantt-links-row-actions gantt-resources-assignment-actions d-none d-flex"><div class="btn-group">' +
        '<button type="button" class="btn btn-outline-primary btn-sm policy-gantt-links-up-btn gantt-resources-assignment-up-btn" title="Переместить вверх" aria-label="Переместить вверх"><i class="bi bi-arrow-up-square"></i></button>' +
        '<button type="button" class="btn btn-outline-primary btn-sm policy-gantt-links-down-btn gantt-resources-assignment-down-btn" title="Переместить вниз" aria-label="Переместить вниз"><i class="bi bi-arrow-down-square"></i></button>' +
        '<button type="button" class="btn btn-outline-danger btn-sm policy-gantt-links-delete-btn gantt-resources-assignment-delete-btn" title="Удалить" aria-label="Удалить"><i class="bi bi-x-square"></i></button>' +
        '</div></div>' +
        '</div></div></div>';

      body.querySelector('.gantt-resources-modal-specialty').addEventListener('change', function (event) {
        var specialty = normalizeText(event.target.value);
        var executorSelect = body.querySelector('.gantt-resources-modal-executor');
        executorSelect.innerHTML = optionHtml(getExecutorsForSpecialty(specialty), '');
        updateModalResourceName();
        renderAssignmentRows();
      });
      body.querySelector('.gantt-resources-modal-executor').addEventListener('change', function () {
        updateModalResourceName();
      });
      body.querySelector('.gantt-resources-assignment-add-btn').addEventListener('click', function () {
        var taskOptions = getTaskOptions(getModalResourceContext());
        var firstFree = taskOptions.find(function (item) {
          return !item.disabled && modalAssignments.indexOf(item.id) === -1;
        });
        if (!firstFree) return;
        modalAssignments.push(firstFree.id);
        renderAssignmentRows();
      });
      body.querySelector('.gantt-resources-assignment-up-btn').addEventListener('click', function () { moveAssignment(-1); });
      body.querySelector('.gantt-resources-assignment-down-btn').addEventListener('click', function () { moveAssignment(1); });
      body.querySelector('.gantt-resources-assignment-delete-btn').addEventListener('click', deleteCheckedAssignments);
      renderAssignmentRows();
    }

    function getModalResourceContext() {
      if (!modalEl) return {};
      var body = modalEl.querySelector('.modal-body');
      if (!body) return {};
      return {
        id: modalRowId || '',
        specialty: normalizeText(body.querySelector('.gantt-resources-modal-specialty') && body.querySelector('.gantt-resources-modal-specialty').value),
        executor: normalizeText(body.querySelector('.gantt-resources-modal-executor') && body.querySelector('.gantt-resources-modal-executor').value),
      };
    }

    function updateModalResourceName() {
      if (!modalEl) return;
      var body = modalEl.querySelector('.modal-body');
      if (!body) return;
      var nameInput = body.querySelector('.gantt-resources-modal-name');
      if (!nameInput) return;
      nameInput.value = calculatedResourceName({
        id: modalRowId || '',
        executor: normalizeText(body.querySelector('.gantt-resources-modal-executor') && body.querySelector('.gantt-resources-modal-executor').value),
      });
    }

    function renderAssignmentRows() {
      var tbody = modalEl.querySelector('.gantt-resources-assignments-tbody');
      if (!tbody) return;
      var taskOptions = getTaskOptions(getModalResourceContext());
      tbody.innerHTML = '';
      modalAssignments = normalizeList(modalAssignments);
      modalAssignments.forEach(function (taskId, index) {
        var tr = document.createElement('tr');
        tr.className = 'gantt-resources-assignment-row';
        tr.dataset.index = String(index);
        tr.innerHTML =
          '<td class="policy-gantt-links-check-cell"><div class="form-check policy-gantt-links-check-wrap">' +
          '<input type="checkbox" class="form-check-input gantt-resources-assignment-check" aria-label="Выделить назначение">' +
          '</div></td>' +
          '<td><select class="form-select gantt-resources-assignment-task" aria-label="Название задачи">' +
          taskOptions.map(function (item) {
            return '<option value="' + escapeHtml(item.id) + '"' +
              (item.id === taskId ? ' selected' : '') +
              (item.disabled ? ' disabled' : '') + '>' +
              escapeHtml(item.label) + '</option>';
          }).join('') +
          '</select></td>';
        tr.querySelector('.gantt-resources-assignment-check').addEventListener('change', syncAssignmentActions);
        tr.querySelector('.gantt-resources-assignment-task').addEventListener('change', function (event) {
          modalAssignments[index] = normalizeText(event.target.value);
          refreshModalComputedFields();
        });
        tbody.appendChild(tr);
      });
      refreshModalComputedFields();
      syncAssignmentActions();
    }

    function checkedAssignmentIndexes() {
      return Array.from(modalEl.querySelectorAll('.gantt-resources-assignment-row'))
        .filter(function (row) { return row.querySelector('.gantt-resources-assignment-check').checked; })
        .map(function (row) { return Number(row.dataset.index); })
        .filter(function (index) { return Number.isFinite(index); });
    }

    function syncAssignmentActions() {
      var indexes = checkedAssignmentIndexes();
      var actions = modalEl.querySelector('.gantt-resources-assignment-actions');
      if (actions) actions.classList.toggle('d-none', !indexes.length);
      var single = indexes.length === 1 ? indexes[0] : -1;
      var up = modalEl.querySelector('.gantt-resources-assignment-up-btn');
      var down = modalEl.querySelector('.gantt-resources-assignment-down-btn');
      var del = modalEl.querySelector('.gantt-resources-assignment-delete-btn');
      if (up) up.disabled = single <= 0;
      if (down) down.disabled = single < 0 || single >= modalAssignments.length - 1;
      if (del) del.disabled = !indexes.length;
    }

    function moveAssignment(delta) {
      var indexes = checkedAssignmentIndexes();
      if (indexes.length !== 1) return;
      var index = indexes[0];
      var next = index + delta;
      if (next < 0 || next >= modalAssignments.length) return;
      var tmp = modalAssignments[index];
      modalAssignments[index] = modalAssignments[next];
      modalAssignments[next] = tmp;
      renderAssignmentRows();
      var row = modalEl.querySelector('.gantt-resources-assignment-row[data-index="' + next + '"]');
      var check = row && row.querySelector('.gantt-resources-assignment-check');
      if (check) {
        check.checked = true;
        syncAssignmentActions();
      }
    }

    function deleteCheckedAssignments() {
      var indexes = new Set(checkedAssignmentIndexes());
      modalAssignments = modalAssignments.filter(function (_, index) { return !indexes.has(index); });
      renderAssignmentRows();
    }

    function refreshModalComputedFields() {
      if (!modalEl) return;
      var workload = modalEl.querySelector('.gantt-resources-modal-workload');
      var conflicts = modalEl.querySelector('.gantt-resources-modal-conflicts');
      var temp = Object.assign(getModalResourceContext(), { taskIds: sanitizeTaskIds(modalAssignments, getModalResourceContext()) });
      if (workload) workload.value = formatWorkload(temp);
      if (conflicts) conflicts.value = formatConflicts(temp);
    }

    function saveModal() {
      var body = modalEl.querySelector('.modal-body');
      var specialty = normalizeText(body.querySelector('.gantt-resources-modal-specialty').value);
      var executor = normalizeText(body.querySelector('.gantt-resources-modal-executor').value);
      var specialtySelect = body.querySelector('.gantt-resources-modal-specialty');
      var executorSelect = body.querySelector('.gantt-resources-modal-executor');
      clearModalValidationWarning();
      if (executor && getExecutorsForSpecialty(specialty).indexOf(executor) === -1) {
        showModalValidationWarning('Выберите исполнителя, связанного с выбранной специальностью.', executorSelect);
        return;
      }
      if (findDuplicateResourcePair({ id: modalRowId || '', specialty: specialty, executor: executor })) {
        showModalValidationWarning('Ресурс с такой специальностью и ФИО уже есть в таблице. Измените специальность или ФИО либо отредактируйте существующую строку.', executorSelect || specialtySelect);
        return;
      }
      var row = modalRowId ? findRowById(modalRowId) : null;
      var oldTaskIds = row ? row.taskIds.slice() : [];
      if (!row) {
        row = {
          id: uniqueId('resource'),
          specialty: specialty,
          executor: executor,
          resourceName: '',
          taskIds: [],
          position: rows.length + 1,
        };
        rows.push(row);
      }
      row.specialty = specialty;
      row.executor = executor;
      row.taskIds = sanitizeTaskIds(modalAssignments, row);
      applyRowToTasks(row, oldTaskIds);
      rows.forEach(function (item, index) { item.position = index + 1; });
      notifyChange();
      renderRows();
      if (modal) {
        modal.hide();
      } else {
        modalEl.classList.remove('show');
        modalEl.style.display = 'none';
        modalEl.setAttribute('aria-hidden', 'true');
      }
    }

    function bindToggle() {
      if (!toggleButton) return;
      var handler = function () {
        isExpanded = !isExpanded;
        toggleButton.classList.toggle('active', isExpanded);
        toggleButton.setAttribute('aria-pressed', isExpanded ? 'true' : 'false');
        toggleButton.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
        if (container) container.classList.toggle('d-none', !isExpanded);
        if (isExpanded) refreshFromGantt();
        if (typeof options.onToggle === 'function') {
          options.onToggle(api, isExpanded);
        }
      };
      toggleButton.addEventListener('click', handler);
      boundEvents.push({ target: toggleButton, type: 'click', handler: handler });
    }

    function bindGanttEvents() {
      if (!gantt || typeof gantt.attachEvent !== 'function') return;
      ['onAfterTaskAdd', 'onAfterTaskUpdate', 'onAfterTaskDelete', 'onAfterTaskMove', 'onRowDragEnd', 'onParse'].forEach(function (eventName) {
        try {
          var id = gantt.attachEvent(eventName, function () {
            if (syncActive) return true;
            refreshFromGantt({ preserveMeta: true });
            return true;
          });
          boundEvents.push({ gantt: gantt, eventId: id });
        } catch (_) {
          // Some Gantt builds do not expose all event names.
        }
      });
    }

    function refreshFromGantt() {
      syncActive = true;
      try {
        rebuildRowsFromGantt();
        queueRender();
      } finally {
        syncActive = false;
      }
    }

    function serializeMeta(meta) {
      var target = meta && typeof meta === 'object' ? meta : {};
      applyCalculatedResourceNames();
      target.resources = rows.map(function (row, index) {
        return {
          id: row.id,
          specialty: row.specialty,
          executor: row.executor,
          resource_name: row.resourceName || row.executor,
          task_ids: sanitizeTaskIds(row.taskIds, row),
          position: index + 1,
        };
      });
      return target;
    }

    function dispose() {
      boundEvents.forEach(function (entry) {
        if (entry.gantt && entry.eventId && typeof entry.gantt.detachEvent === 'function') {
          try { entry.gantt.detachEvent(entry.eventId); } catch (_) { /* noop */ }
        } else if (entry.target && entry.type && entry.handler) {
          entry.target.removeEventListener(entry.type, entry.handler);
        }
      });
      boundEvents = [];
      if (modal) {
        try { modal.hide(); } catch (_) { /* noop */ }
      }
      if (modalEl && modalEl.parentNode) modalEl.parentNode.removeChild(modalEl);
      modalEl = null;
      modal = null;
      if (container) container.innerHTML = '';
    }

    function attach(nextOptions) {
      nextOptions = nextOptions || {};
      gantt = nextOptions.gantt || gantt;
      root = nextOptions.root || root;
      container = nextOptions.container || container;
      toggleButton = nextOptions.toggleButton || toggleButton;
      options = Object.assign({}, options, nextOptions);
      fields = Object.assign(fields, nextOptions.fields || {});
      catalogs = normalizeCatalogs(options.catalogs || {});
      refreshFromGantt();
    }

    var api = {
      attach: attach,
      dispose: dispose,
      refreshFromGantt: refreshFromGantt,
      serializeMeta: serializeMeta,
      setExpanded: function (expanded) {
        isExpanded = !!expanded;
        if (toggleButton) {
          toggleButton.classList.toggle('active', isExpanded);
          toggleButton.setAttribute('aria-pressed', isExpanded ? 'true' : 'false');
          toggleButton.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
        }
        if (container) container.classList.toggle('d-none', !isExpanded);
        if (isExpanded) refreshFromGantt();
        if (typeof options.onToggle === 'function') {
          options.onToggle(api, isExpanded);
        }
      },
      getRows: function () {
        return rows.map(function (row) {
          return Object.assign({}, row, { taskIds: row.taskIds.slice() });
        });
      },
    };

    bindToggle();
    bindGanttEvents();
    rebuildRowsFromGantt();
    render();

    return api;
  }

  window.GanttEngine = window.GanttEngine || {};
  window.GanttEngine.createResources = createResources;
})(window);
