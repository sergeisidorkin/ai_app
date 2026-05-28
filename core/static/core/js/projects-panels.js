(function () {
  if (window.__projectsPanelBound) return;
  window.__projectsPanelBound = true;

  // ТОЧНО как в policy-panels.js — общий кеш выбора
  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;

  function pane() { return document.getElementById('projects-pane'); }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  const csrftoken = getCookie('csrftoken');
  const REGISTRATION_INLINE_EDITOR_FRAME_OFFSET = 0.25;
  const PROJECT_REGISTRY_COLPICKER = {
    prefKey: 'projects:registrationHiddenCols',
    wrapId: 'registration-colpicker-wrap',
    btnId: 'registration-colpicker-btn',
    menuId: 'registration-colpicker-menu',
    allId: 'registration-col-all',
    tableId: 'registration-registry-table',
    hidden: null,
  };

  function getMasterForPanel(panel) {
    const id = panel?.id;
    if (!id) return null;
    return pane()?.querySelector(`input.form-check-input[data-actions-id="${CSS.escape(id)}"]`) || null;
  }
  function getNameForPanel(panel) {
    if (panel?.dataset?.targetName) return panel.dataset.targetName;
    const master = getMasterForPanel(panel);
    return master?.dataset?.targetName || null;
  }
  function getRowChecksByName(name) {
    const root = pane();
    return qa(`tbody input.form-check-input[name="${CSS.escape(name)}"]`, root);
  }
  function isVisibleRowCheckbox(box) {
    const row = box?.closest('tr');
    return !!row && !row.classList.contains('d-none');
  }
  function getVisibleRowChecksByName(name) {
    return getRowChecksByName(name).filter(isVisibleRowCheckbox);
  }
  function getCheckedByName(name) {
    return getVisibleRowChecksByName(name).filter(b => b.checked);
  }
  function updateRowHighlightFor(name) {
    getRowChecksByName(name).forEach(b => {
      const tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateMasterStateFor(name) {
    const boxes = getVisibleRowChecksByName(name);
    const root = pane();
    const master = root?.querySelector(`input.form-check-input[data-target-name="${CSS.escape(name)}"]`);
    if (!master) return;
    const checkedCount = boxes.filter(b => b.checked).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function findActionsByName(name) {
    const root = pane();
    if (!root) return null;
    const master = root.querySelector(`input.form-check-input[data-target-name="${CSS.escape(name)}"]`);
    if (!master) return null;
    const actionsId = master.getAttribute('data-actions-id') || '';
    if (!actionsId) return null;
    return root.querySelector('#' + actionsId);
  }
  function ensureActionsVisibility(name) {
    const panel = findActionsByName(name);
    if (!panel) return;
    const anyChecked = getCheckedByName(name).length > 0;
    panel.classList.toggle('d-none', !anyChecked);
    panel.classList.toggle('d-flex', anyChecked);
  }
  function clearHiddenSelections(name) {
    getRowChecksByName(name).forEach((box) => {
      if (!isVisibleRowCheckbox(box)) box.checked = false;
    });
  }
  function syncSelectionToVisible(name) {
    clearHiddenSelections(name);
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
    if (name === 'contract-select') updateContractEditBtn();
    if (name === 'registration-select') updateRegWorkspaceBtn();
    if (name === 'project-schedule-select') scheduleProjectScheduleScrollGapsUpdate();
  }
  window.__refreshProjectsSelectionState = function() {
    ['registration-select', 'contract-select', 'project-schedule-select', 'work-select', 'legal-select'].forEach(syncSelectionToVisible);
  };
  document.addEventListener('DOMContentLoaded', initProjectRegistryColPicker);
  document.addEventListener('DOMContentLoaded', function() {
    bindProjectScheduleScrollGaps();
    scheduleProjectScheduleScrollGapsUpdate();
  });
  window.addEventListener('resize', scheduleProjectScheduleScrollGapsUpdate);
  window.addEventListener('load', scheduleProjectScheduleScrollGapsUpdate);

  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const viewInput = e.target.closest('.js-project-schedule-view');
    if (viewInput && root.contains(viewInput)) scheduleProjectScheduleScrollGapsUpdate();
  });

  function getDeleteConfirmationMessage(name, count) {
    if (name === 'work-select') {
      return `Удалить ${count} строк(у/и) из "Объем услуг"? Будут также удалены связанные строки в "Юридические лица" и "Исполнители".`;
    }
    return `Удалить ${count} строк(у/и)?`;
  }

  function getProjectScheduleFilterValue() {
    const root = pane();
    const selected = root?.querySelector('.js-project-schedule-filter:checked');
    const value = selected?.value || (window.__projectScheduleFilter && window.__projectScheduleFilter[0]) || '';
    return value === '__all__' ? '' : value;
  }

  function updateProjectScheduleScrollGaps() {
    const root = pane();
    if (!root) return;
    qa(
      '#projects-content-launch .registration-table-wrap, .project-schedule-scroll-wrap, .work-table-wrap, .legal-table-wrap',
      root
    ).forEach((wrap) => {
      wrap.classList.toggle('has-horizontal-scroll', wrap.scrollWidth > wrap.clientWidth + 1);
    });
  }

  function scheduleProjectScheduleScrollGapsUpdate() {
    window.requestAnimationFrame(updateProjectScheduleScrollGaps);
  }

  function bindProjectScheduleScrollGaps(root = pane()) {
    if (!root || root.dataset.projectScheduleScrollGapsBound === '1') return;
    root.dataset.projectScheduleScrollGapsBound = '1';
    root.addEventListener('project-schedule-filter-changed', scheduleProjectScheduleScrollGapsUpdate);
    root.addEventListener('work-filter-changed', scheduleProjectScheduleScrollGapsUpdate);
    root.addEventListener('legal-filter-changed', scheduleProjectScheduleScrollGapsUpdate);
    root.addEventListener('reg-filter-changed', scheduleProjectScheduleScrollGapsUpdate);
  }

  window.addEventListener('projects:section-shown', function(e) {
    if (e.detail && (e.detail.section === 'launch' || e.detail.section === 'scope')) {
      scheduleProjectScheduleScrollGapsUpdate();
    }
  });

  function prepareProjectScheduleWrap(wrap, selectedIds) {
    const projectId = getProjectScheduleFilterValue();
    const selectedSet = new Set((selectedIds || []).map(String));
    wrap.querySelectorAll('table.project-schedule-table tbody tr').forEach((row) => {
      const visible = !!projectId && (row.dataset.projectId || '') === projectId;
      row.classList.toggle('d-none', !visible);
      const checkbox = row.querySelector('input[name="project-schedule-select"]');
      if (checkbox) checkbox.checked = visible && selectedSet.has(String(checkbox.value));
      row.classList.toggle('table-active', !!(checkbox && checkbox.checked));
    });
  }

  async function replaceProjectScheduleWrapFromResponse(url, selectedIds) {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrftoken,
        'X-Requested-With': 'XMLHttpRequest',
      },
    });
    if (!response.ok) throw new Error('Не удалось обновить график проекта.');
    const html = await response.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const nextWrap = doc.querySelector('.project-schedule-table-wrap');
    const currentWrap = pane()?.querySelector('.project-schedule-table-wrap');
    if (!nextWrap || !currentWrap) throw new Error('Не удалось обновить график проекта.');
    prepareProjectScheduleWrap(nextWrap, selectedIds);
    currentWrap.replaceWith(nextWrap);
    syncSelectionToVisible('project-schedule-select');
    scheduleProjectScheduleScrollGapsUpdate();
  }

  function updateRegWorkspaceBtn() {
    const root = pane();
    if (!root) return;
    const btn = root.querySelector('#reg-create-workspace-btn');
    const checkedCount = getCheckedByName('registration-select').length;
    if (btn) btn.disabled = checkedCount !== 1;
  }

  function clearRegistrationSelection() {
    const boxes = getRowChecksByName('registration-select');
    boxes.forEach(b => { b.checked = false; });
    updateMasterStateFor('registration-select');
    updateRowHighlightFor('registration-select');
    ensureActionsVisibility('registration-select');
    updateRegWorkspaceBtn();
  }

  function getProjectRegistryDefaultHiddenColumns() {
    const menu = document.getElementById(PROJECT_REGISTRY_COLPICKER.menuId);
    const hidden = {};
    if (!menu) return hidden;
    menu.querySelectorAll('input.form-check-input[data-default-hidden="true"]:not([value="all"])').forEach((cb) => {
      hidden[cb.value] = true;
    });
    return hidden;
  }

  function getProjectRegistryHiddenColumns() {
    if (!PROJECT_REGISTRY_COLPICKER.hidden) {
      const saved = window.UIPref ? UIPref.get(PROJECT_REGISTRY_COLPICKER.prefKey, null) : null;
      PROJECT_REGISTRY_COLPICKER.hidden = saved && typeof saved === 'object' && !Array.isArray(saved)
        ? saved
        : getProjectRegistryDefaultHiddenColumns();
    }
    return PROJECT_REGISTRY_COLPICKER.hidden || {};
  }

  function saveProjectRegistryHiddenColumns() {
    if (window.UIPref) UIPref.set(PROJECT_REGISTRY_COLPICKER.prefKey, getProjectRegistryHiddenColumns());
  }

  function updateProjectRegistryColPickerLabel(btn, menu) {
    const cbs = qa('input.form-check-input:not([value="all"])', menu);
    const checked = cbs.filter((cb) => cb.checked).length;
    btn.textContent = checked === cbs.length ? 'Все поля' : checked + ' из ' + cbs.length;
  }

  function applyProjectRegistryColumnVisibility() {
    const table = document.getElementById(PROJECT_REGISTRY_COLPICKER.tableId);
    if (!table) return;
    const hidden = Object.keys(getProjectRegistryHiddenColumns());
    table.querySelectorAll('[data-col]').forEach((cell) => {
      cell.style.display = hidden.includes(cell.getAttribute('data-col')) ? 'none' : '';
    });
    table.querySelectorAll('col[data-col]').forEach((col) => {
      col.style.display = hidden.includes(col.getAttribute('data-col')) ? 'none' : '';
    });
    scheduleProjectScheduleScrollGapsUpdate();
  }

  function initProjectRegistryColPicker() {
    const cfg = PROJECT_REGISTRY_COLPICKER;
    const wrap = document.getElementById(cfg.wrapId);
    const btn = document.getElementById(cfg.btnId);
    const menu = document.getElementById(cfg.menuId);
    if (!wrap || !btn || !menu) return;

    btn.onclick = (event) => {
      event.stopPropagation();
      menu.classList.toggle('show');
    };

    const cbs = qa('input.form-check-input:not([value="all"])', menu);
    const hiddenState = getProjectRegistryHiddenColumns();
    cbs.forEach((cb) => {
      cb.checked = !hiddenState[cb.value];
    });

    const allCb = document.getElementById(cfg.allId);
    if (allCb) {
      allCb.checked = cbs.every((cb) => cb.checked);
    }

    updateProjectRegistryColPickerLabel(btn, menu);
    applyProjectRegistryColumnVisibility();

    menu.onchange = (event) => {
      const cb = event.target;
      if (!cb.classList.contains('form-check-input')) return;
      const items = qa('input.form-check-input:not([value="all"])', menu);
      if (cb.value === 'all') {
        items.forEach((item) => { item.checked = cb.checked; });
      } else {
        const ac = document.getElementById(cfg.allId);
        if (ac) ac.checked = items.every((item) => item.checked);
      }
      cfg.hidden = {};
      items.forEach((item) => {
        if (!item.checked) cfg.hidden[item.value] = true;
      });
      saveProjectRegistryHiddenColumns();
      updateProjectRegistryColPickerLabel(btn, menu);
      applyProjectRegistryColumnVisibility();
    };
  }

  // Кнопка «Редактировать» для таблицы «Условия контракта»
  function updateContractEditBtn() {
    const root = pane();
    if (!root) return;
    const btn = root.querySelector('#contract-edit-btn');
    if (!btn) return;
    const anyChecked = getRowChecksByName('contract-select').some(b => b.checked);
    btn.disabled = !anyChecked;
  }

  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;
    const colPickerWrap = document.getElementById(PROJECT_REGISTRY_COLPICKER.wrapId);
    const colPickerMenu = document.getElementById(PROJECT_REGISTRY_COLPICKER.menuId);
    if (colPickerWrap && colPickerMenu && !colPickerWrap.contains(e.target)) {
      colPickerMenu.classList.remove('show');
    }

    const editBtn = e.target.closest('#contract-edit-btn');
    if (editBtn && root.contains(editBtn)) {
      const checked = getCheckedByName('contract-select');
      if (!checked.length) return;
      const first = checked[0];
      const tr = first.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;

      window.__tableSel['contract-select'] = checked.map(ch => String(ch.value));
      window.__tableSelLast = 'contract-select';

      await htmx.ajax('GET', url, { target: '#projects-modal .modal-content', swap: 'innerHTML' });
      updateContractEditBtn();
      return;
    }

    const quickEdit = e.target.closest('.project-quick-edit');
    if (quickEdit && root.contains(quickEdit)) {
      const tr = quickEdit.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;

      await htmx.ajax('GET', url, { target: '#projects-modal .modal-content', swap: 'innerHTML' });
      return;
    }
  });

  function getRegistrationStatusEditor(root) {
    return root?.querySelector('#registration-status-editor') || null;
  }

  function getRegistrationManagerEditor(root) {
    return root?.querySelector('#registration-manager-editor') || null;
  }

  function getRegistrationDeadlineEditor(root) {
    return root?.querySelector('#registration-deadline-editor') || null;
  }

  function getRegistrationDeadlineEditorWrap(root) {
    return root?.querySelector('#registration-deadline-editor-wrap') || null;
  }

  function getRegistrationDeadlinePicker(root) {
    return root?.querySelector('#registration-deadline-picker') || null;
  }

  function updateRegistrationLaunchButton(tr, status) {
    const launchBtn = tr?.querySelector('.reg-launch-btn');
    if (!launchBtn) return;
    const canLaunch = status === 'Не начат' && !!launchBtn.dataset.launchUrl;
    const icon = launchBtn.querySelector('.bi');
    launchBtn.classList.remove(
      'reg-launch-indicator',
      'reg-launch-status--work',
      'reg-launch-status--done',
      'reg-launch-status--deferred',
      'reg-launch-status--review'
    );
    launchBtn.disabled = !canLaunch;
    launchBtn.classList.remove('is-pending');
    launchBtn.title = canLaunch ? 'Запустить проект' : status;
    launchBtn.setAttribute('aria-label', canLaunch ? 'Запустить проект' : `Статус проекта: ${status}`);
    if (canLaunch) {
      launchBtn.setAttribute('data-registration-launch', '');
      if (icon) icon.className = 'bi bi-play-circle';
    } else {
      launchBtn.removeAttribute('data-registration-launch');
      launchBtn.classList.add('reg-launch-indicator');
      if (status === 'В работе') launchBtn.classList.add('reg-launch-status--work');
      else if (status === 'Завершён' || status === 'Завершен') launchBtn.classList.add('reg-launch-status--done');
      else if (status === 'Отложен') launchBtn.classList.add('reg-launch-status--deferred');
      else if (status === 'На проверке') launchBtn.classList.add('reg-launch-status--review');
      if (icon) icon.className = 'bi bi-circle';
    }
  }

  function updateRegistrationStatusDom(tr, status) {
    const statusCell = tr?.querySelector('[data-reg-status-cell]');
    if (!statusCell) return;
    statusCell.dataset.statusValue = status;
    const statusBtn = statusCell.querySelector('[data-registration-status]');
    if (statusBtn) {
      statusBtn.textContent = status;
      statusBtn.dataset.statusValue = status;
    } else {
      statusCell.textContent = status;
    }
    updateRegistrationLaunchButton(tr, status);
  }

  function closeRegistrationStatusEditor(root) {
    const editor = getRegistrationStatusEditor(root);
    if (!editor) return;
    editor.classList.add('d-none');
    editor.removeAttribute('style');
    root?.querySelectorAll('.reg-status-btn.is-editing').forEach((btn) => {
      btn.classList.remove('is-editing');
      btn.blur();
    });
    delete editor.dataset.statusUrl;
    delete editor.dataset.projectId;
  }

  function closeRegistrationManagerEditor(root) {
    const editor = getRegistrationManagerEditor(root);
    if (!editor) return;
    editor.classList.add('d-none');
    editor.removeAttribute('style');
    root?.querySelectorAll('.reg-manager-btn.is-editing').forEach((btn) => {
      btn.classList.remove('is-editing');
      btn.blur();
    });
    delete editor.dataset.managerUrl;
    delete editor.dataset.projectId;
  }

  function closeRegistrationDeadlineEditor(root) {
    const editor = getRegistrationDeadlineEditor(root);
    const wrap = getRegistrationDeadlineEditorWrap(root);
    if (!editor || !wrap) return;
    wrap.classList.add('d-none');
    wrap.removeAttribute('style');
    root?.querySelectorAll('.reg-deadline-btn.is-editing').forEach((btn) => {
      btn.classList.remove('is-editing');
      btn.blur();
    });
    delete editor.dataset.deadlineUrl;
    delete editor.dataset.projectId;
    delete editor.dataset.previousValue;
    delete editor.dataset.segment;
    delete editor.dataset.pendingDigits;
    delete editor.dataset.pendingAt;
    delete editor.dataset.dateField;
    delete editor.dataset.datePostField;
    delete editor.dataset.dateResponseField;
    delete editor.dataset.dateResponseLabelField;
  }

  function closeRegistrationInlineEditors() {
    const root = pane();
    closeRegistrationStatusEditor(root);
    closeRegistrationManagerEditor(root);
    closeRegistrationDeadlineEditor(root);
  }

  function openRegistrationStatusEditor(button) {
    const root = pane();
    const editor = getRegistrationStatusEditor(root);
    const td = button.closest('[data-reg-status-cell]');
    const tr = button.closest('tr');
    const url = button.dataset.statusUrl || tr?.dataset?.statusUrl;
    if (!root || !editor || !td || !tr || !url) return;

    closeRegistrationStatusEditor(root);
    closeRegistrationManagerEditor(root);
    closeRegistrationDeadlineEditor(root);
    button.classList.add('is-editing');
    editor.value = button.dataset.statusValue || td.dataset.statusValue || button.textContent.trim();
    editor.dataset.statusUrl = url;
    editor.dataset.projectId = tr.dataset.projectId || '';

    const rect = td.getBoundingClientRect();
    editor.style.position = 'fixed';
    editor.style.left = rect.left + 'px';
    editor.style.top = (rect.top - REGISTRATION_INLINE_EDITOR_FRAME_OFFSET) + 'px';
    editor.style.width = Math.max(rect.width - 4, 120) + 'px';
    editor.style.height = (rect.height + REGISTRATION_INLINE_EDITOR_FRAME_OFFSET * 2) + 'px';
    editor.style.zIndex = '1080';
    editor.classList.remove('d-none');

    try { editor.showPicker(); } catch (_) { editor.focus(); }
  }

  function updateRegistrationManagerDom(tr, managerValue, managerLabel) {
    const managerCell = tr?.querySelector('[data-reg-manager-cell]');
    if (!managerCell) return;
    managerCell.dataset.managerValue = managerValue || '';
    const managerBtn = managerCell.querySelector('[data-registration-manager]');
    if (managerBtn) {
      managerBtn.textContent = managerLabel || '';
      managerBtn.dataset.managerValue = managerValue || '';
    } else {
      managerCell.textContent = managerLabel || '';
    }
  }

  function openRegistrationManagerEditor(button) {
    const root = pane();
    const editor = getRegistrationManagerEditor(root);
    const td = button.closest('[data-reg-manager-cell]');
    const tr = button.closest('tr');
    const url = button.dataset.managerUrl || tr?.dataset?.managerUrl;
    if (!root || !editor || !td || !tr || !url) return;

    closeRegistrationStatusEditor(root);
    closeRegistrationManagerEditor(root);
    closeRegistrationDeadlineEditor(root);
    button.classList.add('is-editing');
    editor.value = button.dataset.managerValue || td.dataset.managerValue || '';
    editor.dataset.managerUrl = url;
    editor.dataset.projectId = tr.dataset.projectId || '';

    const rect = td.getBoundingClientRect();
    editor.style.position = 'fixed';
    editor.style.left = rect.left + 'px';
    editor.style.top = (rect.top - REGISTRATION_INLINE_EDITOR_FRAME_OFFSET) + 'px';
    editor.style.width = Math.max(rect.width - 4, 170) + 'px';
    editor.style.height = (rect.height + REGISTRATION_INLINE_EDITOR_FRAME_OFFSET * 2) + 'px';
    editor.style.zIndex = '1080';
    editor.classList.remove('d-none');

    try { editor.showPicker(); } catch (_) { editor.focus(); }
  }

  function getRegistrationDateCell(tr, fieldName) {
    if (!tr) return null;
    if (fieldName && fieldName !== 'deadline') {
      return tr.querySelector(`[data-reg-date-field="${CSS.escape(fieldName)}"]`);
    }
    return tr.querySelector('[data-reg-deadline-cell]');
  }

  function updateRegistrationDeadlineDom(tr, fieldName, deadlineValue, deadlineLabel) {
    const deadlineCell = getRegistrationDateCell(tr, fieldName);
    if (!deadlineCell) return;
    if (fieldName && fieldName !== 'deadline') {
      deadlineCell.dataset.dateValue = deadlineValue || '';
    } else {
      deadlineCell.dataset.deadlineValue = deadlineValue || '';
    }
    const deadlineBtn = deadlineCell.querySelector('[data-registration-date], [data-registration-deadline]');
    if (deadlineBtn) {
      deadlineBtn.textContent = deadlineLabel || '';
      if (deadlineBtn.hasAttribute('data-registration-date')) {
        deadlineBtn.dataset.dateValue = deadlineValue || '';
      } else {
        deadlineBtn.dataset.deadlineValue = deadlineValue || '';
      }
    } else {
      deadlineCell.textContent = deadlineLabel || '';
    }
  }

  const DEADLINE_SEGMENTS = [
    { name: 'day', start: 0, end: 2, next: 'month', prev: null, length: 2, placeholder: 'дд', max: 31 },
    { name: 'month', start: 3, end: 5, next: 'year', prev: 'day', length: 2, placeholder: 'мм', max: 12 },
    { name: 'year', start: 6, end: 10, next: null, prev: 'month', length: 4, placeholder: 'гггг', max: 9999 },
  ];

  function deadlineDisplayFromIso(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    return match ? `${match[3]}.${match[2]}.${match[1]}` : '';
  }

  function deadlineIsoFromDisplay(value) {
    const match = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value || '');
    if (!match) return '';
    const day = Number(match[1]);
    const month = Number(match[2]);
    const year = Number(match[3]);
    const date = new Date(year, month - 1, day);
    if (
      date.getFullYear() !== year ||
      date.getMonth() !== month - 1 ||
      date.getDate() !== day
    ) {
      return '';
    }
    return `${match[3]}-${match[2]}-${match[1]}`;
  }

  function isDeadlineEmptyDisplay(value) {
    const text = (value || '').trim();
    return !text || text === 'дд.мм.гггг';
  }

  function getDeadlineSegment(name) {
    return DEADLINE_SEGMENTS.find((segment) => segment.name === name) || null;
  }

  function getDeadlineSegmentByCaret(input) {
    const pos = Number(input.selectionStart);
    if (pos <= 2) return getDeadlineSegment('day');
    if (pos <= 5) return getDeadlineSegment('month');
    return getDeadlineSegment('year');
  }

  function getDeadlineSegmentByPointer(input, event) {
    const rect = input.getBoundingClientRect();
    const styles = window.getComputedStyle ? window.getComputedStyle(input) : null;
    const paddingLeft = parseFloat(styles?.paddingLeft || '0') || 0;
    const x = Math.max(0, Number(event.clientX) - rect.left - paddingLeft);
    const textWidth = Math.max(1, rect.width - paddingLeft - (parseFloat(styles?.paddingRight || '0') || 0));
    if (x < textWidth * 0.28) return getDeadlineSegment('day');
    if (x < textWidth * 0.55) return getDeadlineSegment('month');
    return getDeadlineSegment('year');
  }

  function selectDeadlineSegment(input, segment) {
    if (!input || !segment || typeof input.setSelectionRange !== 'function') return;
    input.focus({ preventScroll: true });
    input.setSelectionRange(segment.start, segment.end);
    input.dataset.segment = segment.name;
  }

  function ensureDeadlineMask(input) {
    if (!input.value) input.value = 'дд.мм.гггг';
  }

  function replaceDeadlineSegment(input, segment, text) {
    input.value = input.value.slice(0, segment.start) + text + input.value.slice(segment.end);
  }

  function setDeadlinePending(input, segment, digits) {
    input.dataset.segment = segment.name;
    input.dataset.pendingDigits = digits;
    input.dataset.pendingAt = String(Date.now());
  }

  function clearDeadlinePending(input) {
    delete input.dataset.pendingDigits;
    delete input.dataset.pendingAt;
  }

  function isFreshDeadlinePending(input, segment) {
    const at = Number(input.dataset.pendingAt || 0);
    return input.dataset.segment === segment.name && input.dataset.pendingDigits && Date.now() - at < 2500;
  }

  function normalizeDeadlineSegmentValue(segment, digits) {
    if (segment.name === 'year') return digits.padStart(4, '0').slice(-4);
    const max = segment.max;
    const value = Math.max(1, Math.min(max, Number(digits) || 1));
    return String(value).padStart(2, '0');
  }

  function finalizeDeadlinePendingSegment(input, moveToNext, options) {
    const segment = getDeadlineSegment(input.dataset.segment);
    const digits = input.dataset.pendingDigits || '';
    if (!segment || !digits) return segment;
    const normalized = normalizeDeadlineSegmentValue(segment, digits);
    replaceDeadlineSegment(input, segment, normalized);
    clearDeadlinePending(input);
    const target = moveToNext && segment.next ? getDeadlineSegment(segment.next) : segment;
    if (options?.select !== false) selectDeadlineSegment(input, target);
    return target;
  }

  async function saveRegistrationDeadlineEditor(editor, closeAfterSave) {
    const root = pane();
    const url = editor.dataset.deadlineUrl;
    const dateField = editor.dataset.dateField || 'deadline';
    const postField = editor.dataset.datePostField || 'deadline';
    const responseField = editor.dataset.dateResponseField || 'deadline';
    const responseLabelField = editor.dataset.dateResponseLabelField || 'deadlineLabel';
    const projectId = editor.dataset.projectId || '';
    const tr = projectId
      ? root?.querySelector(`table.reg-table tbody tr[data-project-id="${CSS.escape(projectId)}"]`)
      : null;
    if (!root || !url || !tr) {
      closeRegistrationDeadlineEditor(root);
      return;
    }
    const rawValue = isDeadlineEmptyDisplay(editor.value) ? '' : (editor.value || '').trim();
    const iso = deadlineIsoFromDisplay(rawValue);
    if (!iso && rawValue) return;
    const payloadValue = iso || '';
    if (closeAfterSave) editor.disabled = true;
    try {
      const data = await postRegistrationDeadline(url, payloadValue, postField);
      const savedValue = data[responseField] || payloadValue;
      updateRegistrationDeadlineDom(tr, dateField, savedValue, data[responseLabelField] || '');
      editor.dataset.previousValue = savedValue || '';
      const picker = getRegistrationDeadlinePicker(root);
      if (picker) picker.value = savedValue || '';
      if (closeAfterSave) closeRegistrationDeadlineEditor(root);
    } catch (error) {
      alert(error.message || 'Не удалось изменить дедлайн проекта.');
    } finally {
      if (closeAfterSave) editor.disabled = false;
    }
  }

  async function saveRegistrationDeadlineIfComplete(editor, closeAfterSave) {
    if (isDeadlineEmptyDisplay(editor.value) || deadlineIsoFromDisplay(editor.value)) {
      await saveRegistrationDeadlineEditor(editor, closeAfterSave);
      return true;
    }
    return false;
  }

  async function commitAndCloseRegistrationDeadlineEditor(root) {
    const editor = getRegistrationDeadlineEditor(root);
    const wrap = getRegistrationDeadlineEditorWrap(root);
    if (!editor || !wrap || wrap.classList.contains('d-none')) return;
    finalizeDeadlinePendingSegment(editor, false, { select: false });
    const saved = await saveRegistrationDeadlineIfComplete(editor, true);
    if (!saved) closeRegistrationDeadlineEditor(root);
  }

  function openRegistrationDeadlineEditor(button) {
    const root = pane();
    const editor = getRegistrationDeadlineEditor(root);
    const wrap = getRegistrationDeadlineEditorWrap(root);
    const picker = getRegistrationDeadlinePicker(root);
    const td = button.closest('[data-reg-date-cell], [data-reg-deadline-cell]');
    const tr = button.closest('tr');
    const dateField = button.dataset.dateField || td?.dataset?.regDateField || 'deadline';
    const rowUrlKey = dateField === 'evaluation_date' ? 'evaluationDateUrl' : 'deadlineUrl';
    const url = button.dataset.dateUrl || button.dataset.deadlineUrl || tr?.dataset?.[rowUrlKey];
    if (!root || !editor || !wrap || !td || !tr || !url) return;

    closeRegistrationStatusEditor(root);
    closeRegistrationManagerEditor(root);
    closeRegistrationDeadlineEditor(root);
    editor.spellcheck = false;
    editor.setAttribute('spellcheck', 'false');
    editor.setAttribute('autocorrect', 'off');
    editor.setAttribute('autocapitalize', 'off');
    button.classList.add('is-editing');
    const isoValue = button.dataset.dateValue || button.dataset.deadlineValue || td.dataset.dateValue || td.dataset.deadlineValue || '';
    editor.value = deadlineDisplayFromIso(isoValue);
    editor.dataset.previousValue = isoValue;
    editor.dataset.deadlineUrl = url;
    editor.dataset.projectId = tr.dataset.projectId || '';
    editor.dataset.dateField = dateField;
    editor.dataset.datePostField = button.dataset.datePostField || (dateField === 'deadline' ? 'deadline' : dateField);
    editor.dataset.dateResponseField = button.dataset.dateResponseField || 'deadline';
    editor.dataset.dateResponseLabelField = button.dataset.dateResponseLabelField || 'deadlineLabel';
    if (picker) {
      picker.value = isoValue;
      picker.disabled = true;
    }

    const rect = td.getBoundingClientRect();
    wrap.style.position = 'fixed';
    wrap.style.left = rect.left + 'px';
    wrap.style.top = (rect.top - REGISTRATION_INLINE_EDITOR_FRAME_OFFSET) + 'px';
    wrap.style.width = Math.max(0, rect.width - 4) + 'px';
    wrap.style.height = (rect.height + REGISTRATION_INLINE_EDITOR_FRAME_OFFSET * 2) + 'px';
    wrap.style.zIndex = '1080';
    wrap.classList.remove('d-none');

    ensureDeadlineMask(editor);
    selectDeadlineSegment(editor, getDeadlineSegment('day'));
    if (picker) {
      window.setTimeout(() => { picker.disabled = false; }, 0);
    }
  }

  async function postRegistrationStatus(url, status) {
    const body = new FormData();
    body.append('status', status);
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrftoken,
        'X-Requested-With': 'XMLHttpRequest',
      },
      body,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || 'Не удалось изменить статус проекта.');
    }
    return data;
  }

  async function postRegistrationManager(url, managerValue) {
    const body = new FormData();
    body.append('project_manager', managerValue);
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrftoken,
        'X-Requested-With': 'XMLHttpRequest',
      },
      body,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || 'Не удалось изменить руководителя проекта.');
    }
    return data;
  }

  async function postRegistrationDeadline(url, deadlineValue, fieldName) {
    const body = new FormData();
    body.append(fieldName || 'deadline', deadlineValue);
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrftoken,
        'X-Requested-With': 'XMLHttpRequest',
      },
      body,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || 'Не удалось изменить дедлайн проекта.');
    }
    return data;
  }

  document.addEventListener('click', (e) => {
    const root = pane();
    if (!root) return;
    const statusBtn = e.target.closest('button[data-registration-status]');
    if (statusBtn && root.contains(statusBtn)) {
      openRegistrationStatusEditor(statusBtn);
      return;
    }
    const managerBtn = e.target.closest('button[data-registration-manager]');
    if (managerBtn && root.contains(managerBtn)) {
      openRegistrationManagerEditor(managerBtn);
      return;
    }
    const deadlineBtn = e.target.closest('button[data-registration-date], button[data-registration-deadline]');
    if (deadlineBtn && root.contains(deadlineBtn)) {
      openRegistrationDeadlineEditor(deadlineBtn);
      return;
    }
    const editor = getRegistrationStatusEditor(root);
    if (editor && !editor.classList.contains('d-none') && e.target !== editor) {
      closeRegistrationStatusEditor(root);
    }
    const managerEditor = getRegistrationManagerEditor(root);
    if (managerEditor && !managerEditor.classList.contains('d-none') && e.target !== managerEditor) {
      closeRegistrationManagerEditor(root);
    }
    const deadlineEditor = getRegistrationDeadlineEditor(root);
    const deadlineWrap = getRegistrationDeadlineEditorWrap(root);
    if (deadlineWrap && !deadlineWrap.classList.contains('d-none') && !deadlineWrap.contains(e.target)) {
      commitAndCloseRegistrationDeadlineEditor(root);
    }
  });

  document.addEventListener('pointerdown', (e) => {
    const root = pane();
    const editor = getRegistrationStatusEditor(root);
    const managerEditor = getRegistrationManagerEditor(root);
    const deadlineEditor = getRegistrationDeadlineEditor(root);
    if (!root) return;
    if (editor && !editor.classList.contains('d-none')) {
      if (e.target === editor || e.target.closest('button[data-registration-status]')) return;
      closeRegistrationStatusEditor(root);
    }
    if (managerEditor && !managerEditor.classList.contains('d-none')) {
      if (e.target === managerEditor || e.target.closest('button[data-registration-manager]')) return;
      closeRegistrationManagerEditor(root);
    }
    const deadlineWrap = getRegistrationDeadlineEditorWrap(root);
    if (deadlineWrap && !deadlineWrap.classList.contains('d-none')) {
      if (deadlineWrap.contains(e.target) || e.target.closest('button[data-registration-date], button[data-registration-deadline]')) return;
      commitAndCloseRegistrationDeadlineEditor(root);
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeRegistrationInlineEditors();
    }
  });

  document.addEventListener('scroll', closeRegistrationInlineEditors, true);
  window.addEventListener('resize', closeRegistrationInlineEditors, { passive: true });
  window.addEventListener('wheel', closeRegistrationInlineEditors, { passive: true });

  document.addEventListener('change', async (e) => {
    const root = pane();
    const editor = getRegistrationStatusEditor(root);
    if (!root || !editor || e.target !== editor) return;

    const url = editor.dataset.statusUrl;
    const projectId = editor.dataset.projectId || '';
    const status = editor.value;
    const tr = projectId
      ? root.querySelector(`table.reg-table tbody tr[data-project-id="${CSS.escape(projectId)}"]`)
      : null;
    if (!url || !tr) {
      closeRegistrationStatusEditor(root);
      return;
    }

    editor.disabled = true;
    try {
      const data = await postRegistrationStatus(url, status);
      updateRegistrationStatusDom(tr, data.status || status);
      closeRegistrationStatusEditor(root);
    } catch (error) {
      alert(error.message || 'Не удалось изменить статус проекта.');
    } finally {
      editor.disabled = false;
    }
  });

  document.addEventListener('change', async (e) => {
    const root = pane();
    const editor = getRegistrationDeadlineEditor(root);
    const picker = getRegistrationDeadlinePicker(root);
    if (!root || !editor) return;

    if (e.target === picker) {
      editor.value = deadlineDisplayFromIso(picker.value);
      await saveRegistrationDeadlineEditor(editor, true);
      return;
    }

    if (e.target !== editor) return;
    finalizeDeadlinePendingSegment(editor, false);
    if (deadlineIsoFromDisplay(editor.value)) {
      await saveRegistrationDeadlineEditor(editor, true);
      return;
    }
  });

  document.addEventListener('keydown', async (e) => {
    const root = pane();
    const editor = getRegistrationDeadlineEditor(root);
    if (!root || !editor || e.target !== editor) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    if (e.key === 'Enter') {
      e.preventDefault();
      finalizeDeadlinePendingSegment(editor, false);
      if (deadlineIsoFromDisplay(editor.value)) {
        await saveRegistrationDeadlineEditor(editor, true);
      }
      return;
    }

    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      const current = finalizeDeadlinePendingSegment(editor, false) || getDeadlineSegmentByCaret(editor);
      await saveRegistrationDeadlineIfComplete(editor, false);
      const targetName = e.key === 'ArrowRight' ? current?.next : current?.prev;
      selectDeadlineSegment(editor, getDeadlineSegment(targetName) || current);
      return;
    }

    if (e.key === 'Backspace' || e.key === 'Delete') {
      e.preventDefault();
      if (editor.selectionStart === 0 && editor.selectionEnd === editor.value.length) {
        editor.value = '';
        clearDeadlinePending(editor);
        await saveRegistrationDeadlineEditor(editor, true);
        return;
      }
      ensureDeadlineMask(editor);
      const segment = getDeadlineSegment(editor.dataset.segment) || getDeadlineSegmentByCaret(editor);
      replaceDeadlineSegment(editor, segment, segment.placeholder);
      clearDeadlinePending(editor);
      selectDeadlineSegment(editor, segment);
      return;
    }

    if (!/^\d$/.test(e.key)) return;

    e.preventDefault();
    ensureDeadlineMask(editor);
    const segment = getDeadlineSegment(editor.dataset.segment) || getDeadlineSegmentByCaret(editor);
    const digit = e.key;
    const pending = isFreshDeadlinePending(editor, segment) ? editor.dataset.pendingDigits : '';

    if (segment.name === 'day') {
      if (pending) {
        replaceDeadlineSegment(editor, segment, normalizeDeadlineSegmentValue(segment, pending + digit));
        clearDeadlinePending(editor);
        selectDeadlineSegment(editor, getDeadlineSegment('month'));
        await saveRegistrationDeadlineIfComplete(editor, false);
        return;
      }
      replaceDeadlineSegment(editor, segment, `0${digit}`);
      if (digit === '0' || Number(digit) <= 3) {
        setDeadlinePending(editor, segment, digit);
        selectDeadlineSegment(editor, segment);
      } else {
        clearDeadlinePending(editor);
        selectDeadlineSegment(editor, getDeadlineSegment('month'));
        await saveRegistrationDeadlineIfComplete(editor, false);
      }
      return;
    }

    if (segment.name === 'month') {
      if (pending) {
        if (pending === '1' && Number(digit) > 2) {
          clearDeadlinePending(editor);
          const yearSegment = getDeadlineSegment('year');
          selectDeadlineSegment(editor, yearSegment);
          replaceDeadlineSegment(editor, yearSegment, digit + yearSegment.placeholder.slice(1));
          setDeadlinePending(editor, yearSegment, digit);
          return;
        }
        replaceDeadlineSegment(editor, segment, normalizeDeadlineSegmentValue(segment, pending + digit));
        clearDeadlinePending(editor);
        selectDeadlineSegment(editor, getDeadlineSegment('year'));
        await saveRegistrationDeadlineIfComplete(editor, false);
        return;
      }
      replaceDeadlineSegment(editor, segment, `0${digit}`);
      if (digit === '0' || digit === '1') {
        setDeadlinePending(editor, segment, digit);
        selectDeadlineSegment(editor, segment);
      } else {
        clearDeadlinePending(editor);
        selectDeadlineSegment(editor, getDeadlineSegment('year'));
        await saveRegistrationDeadlineIfComplete(editor, false);
      }
      return;
    }

    const yearDigits = (pending + digit).slice(0, 4);
    replaceDeadlineSegment(editor, segment, yearDigits + segment.placeholder.slice(yearDigits.length));
    if (yearDigits.length >= 4) {
      replaceDeadlineSegment(editor, segment, normalizeDeadlineSegmentValue(segment, yearDigits));
      clearDeadlinePending(editor);
      if (deadlineIsoFromDisplay(editor.value)) {
        await saveRegistrationDeadlineEditor(editor, true);
      } else {
        selectDeadlineSegment(editor, segment);
      }
    } else {
      setDeadlinePending(editor, segment, yearDigits);
      selectDeadlineSegment(editor, segment);
    }
  });

  document.addEventListener('mousedown', async (e) => {
    const root = pane();
    const editor = getRegistrationDeadlineEditor(root);
    if (!root || !editor || e.target !== editor) return;
    e.preventDefault();
    ensureDeadlineMask(editor);
    finalizeDeadlinePendingSegment(editor, false);
    await saveRegistrationDeadlineIfComplete(editor, false);
    selectDeadlineSegment(editor, getDeadlineSegmentByPointer(editor, e));
  });

  document.addEventListener('change', async (e) => {
    const root = pane();
    const editor = getRegistrationManagerEditor(root);
    if (!root || !editor || e.target !== editor) return;

    const url = editor.dataset.managerUrl;
    const projectId = editor.dataset.projectId || '';
    const managerValue = editor.value;
    const tr = projectId
      ? root.querySelector(`table.reg-table tbody tr[data-project-id="${CSS.escape(projectId)}"]`)
      : null;
    if (!url || !tr) {
      closeRegistrationManagerEditor(root);
      return;
    }

    editor.disabled = true;
    try {
      const data = await postRegistrationManager(url, managerValue);
      updateRegistrationManagerDom(tr, data.managerValue || managerValue, data.managerLabel || '');
      closeRegistrationManagerEditor(root);
    } catch (error) {
      alert(error.message || 'Не удалось изменить руководителя проекта.');
    } finally {
      editor.disabled = false;
    }
  });

  // Единый делегированный запуск проекта: меняем только строку, без HTMX-перерисовки таблицы.
  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;
    const btn = e.target.closest('button[data-registration-launch]');
    if (!btn || !root.contains(btn) || btn.disabled) return;

    const url = btn.dataset.launchUrl;
    if (!url) return;

    btn.disabled = true;
    btn.classList.add('is-pending');

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrftoken,
          'X-Requested-With': 'XMLHttpRequest',
        },
      });
      const data = await response.json().catch(() => ({}));
      const tr = btn.closest('tr');
      if (!response.ok || data.ok === false) {
        if (data.status && data.status !== 'Не начат') {
          updateRegistrationStatusDom(tr, data.status);
          return;
        }
        throw new Error(data.error || 'Не удалось запустить проект.');
      }

      const status = data.status || 'В работе';
      updateRegistrationStatusDom(tr, status);
    } catch (error) {
      btn.disabled = false;
      alert(error.message || 'Не удалось запустить проект.');
    } finally {
      btn.classList.remove('is-pending');
    }
  });

  // Делегирование: клики по кнопкам панели РЕГИСТРАЦИИ (строго как в products)
  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;
    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    // Панель теперь общая для трёх таблиц
    const panel = btn.closest('#registrations-actions, #project-schedule-actions, #work-actions, #legal-entities-actions');
    if (!panel) return;

    const action = btn.dataset.panelAction; // "up" | "down" | "edit" | "delete"
    const name = getNameForPanel(panel);    // ожидаем "registration-select"
    if (!name) return;

    const checked = getCheckedByName(name);
    if (!checked.length) return;

    // как в policy: запомним выбор именно этой таблицы
    window.__tableSel[name] = checked.map(ch => String(ch.value));
    window.__tableSelLast = name;

    if (action === 'edit') {
      const first = checked[0];
      const tr = first.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;

      // грузим форму в модалку ПРОЕКТОВ — как в Продуктах
      await htmx.ajax('GET', url, { target: '#projects-modal .modal-content', swap: 'innerHTML' });
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm(getDeleteConfirmationMessage(name, checked.length))) return;
      const urls = checked.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#projects-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      return;
    }

    if (action === 'up' || action === 'down') {
      let urls = checked
        .map(ch => ch.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      if (name === 'project-schedule-select') {
        const selectedIds = checked.map(ch => String(ch.value));
        for (let i = 0; i < urls.length; i++) {
          const isLast = i === urls.length - 1;
          if (isLast) {
            await replaceProjectScheduleWrapFromResponse(urls[i], selectedIds);
          } else {
            await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
          }
        }
        ensureActionsVisibility(name);
        return;
      }
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#projects-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      ensureActionsVisibility(name);
      return;
    }
  });

  // Мастер-чекбокс (один-в-один)
  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const master = e.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (!master || !root.contains(master)) return;
    const name = master.dataset.targetName;
    const boxes = getVisibleRowChecksByName(name);
    boxes.forEach(b => { b.checked = master.checked; });
    master.indeterminate = false;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
    if (name === 'contract-select') updateContractEditBtn();
    if (name === 'registration-select') updateRegWorkspaceBtn();
  });

  // Чекбоксы строк (один-в-один)
  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (!rowCb || !root.contains(rowCb)) return;
    const name = rowCb.name;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
    if (name === 'contract-select') updateContractEditBtn();
    if (name === 'registration-select') updateRegWorkspaceBtn();
  });

  // Восстановление выбора после перерисовки HTMX (один-в-один)
  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (!(e.target && e.target.id === 'projects-pane')) return;
    initProjectRegistryColPicker();
    bindProjectScheduleScrollGaps(e.target);
    scheduleProjectScheduleScrollGapsUpdate();
    const last = window.__tableSelLast;
    if (!last) return;
    const ids = (window.__tableSel && window.__tableSel[last]) || [];
    const set = new Set(ids || []);
    getRowChecksByName(last).forEach(b => { b.checked = set.has(String(b.value)); });
    updateMasterStateFor(last);
    updateRowHighlightFor(last);
    ensureActionsVisibility(last);
    if (last === 'contract-select') updateContractEditBtn();
    if (last === 'registration-select') updateRegWorkspaceBtn();
    try { delete window.__tableSel[last]; } catch(e) { window.__tableSel[last] = []; }
    window.__tableSelLast = null;
  });

  // «Создать» в модальном окне рабочего пространства регистрации
  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;
    const wsConfirmBtn = e.target.closest('#reg-create-workspace-confirm-btn');
    if (!wsConfirmBtn || !root.contains(wsConfirmBtn)) return;

    const checked = getCheckedByName('registration-select');
    if (checked.length !== 1) {
      alert('Выберите ровно один проект.');
      return;
    }
    const tr = checked[0].closest('tr');
    const projectId = tr?.dataset?.projectId;
    if (!projectId) return;

    const actionsRow = root.querySelector('[data-create-workspace-url]');
    const wsUrl = actionsRow?.dataset?.createWorkspaceUrl;
    if (!wsUrl) return;

    const statusEl = root.querySelector('#reg-create-workspace-status');
    const progressEl = root.querySelector('#reg-ws-progress');
    const fillEl = progressEl?.querySelector('.ws-progress-fill');
    const createModalEl = document.getElementById('reg-create-workspace-modal');
    wsConfirmBtn.disabled = true;
    if (statusEl) statusEl.textContent = '';
    if (fillEl) fillEl.style.width = '0%';
    if (progressEl) progressEl.classList.remove('d-none');
    if (createModalEl) createModalEl.dataset.workspaceCreated = '0';

    try {
      const formData = new FormData();
      formData.append('project_id', projectId);

      const response = await fetch(wsUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      });

      if (!response.ok && !response.body) {
        throw new Error('Не удалось создать рабочее пространство.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let lastResult = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) continue;
          const msg = JSON.parse(line);
          if (msg.current !== undefined && msg.total) {
            const pct = Math.round((msg.current / msg.total) * 100);
            if (fillEl) fillEl.style.width = pct + '%';
          }
          if (msg.ok !== undefined) lastResult = msg;
        }
      }
      if (buffer.trim()) {
        const msg = JSON.parse(buffer);
        if (msg.ok !== undefined) lastResult = msg;
      }

      if (!lastResult || !lastResult.ok) {
        throw new Error(lastResult?.error || 'Не удалось создать рабочее пространство.');
      }

      if (fillEl) fillEl.style.width = '100%';
      if (statusEl) statusEl.innerHTML = '<span class="text-success">' + (lastResult.message || 'Готово!') + '</span>';
      if (createModalEl) createModalEl.dataset.workspaceCreated = '1';
    } catch (err) {
      if (progressEl) progressEl.classList.add('d-none');
      if (statusEl) statusEl.innerHTML = '<span class="text-danger">' + (err.message || 'Ошибка') + '</span>';
      else alert(err.message || 'Не удалось создать рабочее пространство.');
    } finally {
      wsConfirmBtn.disabled = false;
    }
  });

  // ── Настройки рабочего пространства (модалка с таблицей папок) ──

  let wsFolders = [];
  let wsIsCustom = false;

  function getSettingsModal() { return document.getElementById('reg-workspace-settings-modal'); }
  function getTbody() { return document.getElementById('ws-folders-tbody'); }

  function updateResetBtn() {
    const btn = document.getElementById('ws-folders-reset-btn');
    if (!btn) return;
    btn.classList.toggle('d-none', !wsIsCustom);
  }

  function renderFolderRows() {
    const tbody = getTbody();
    if (!tbody) return;
    tbody.innerHTML = '';
    wsFolders.forEach((f, idx) => {
      const tr = document.createElement('tr');
      tr.dataset.idx = idx;
      tr.innerHTML =
        '<td class="text-nowrap">' +
          '<div class="form-check">' +
            '<input class="form-check-input ws-folder-check" type="checkbox" data-idx="' + idx + '">' +
          '</div>' +
        '</td>' +
        '<td>' +
          '<select class="form-select form-select-sm ws-folder-level" data-idx="' + idx + '">' +
            '<option value="1"' + (f.level === 1 ? ' selected' : '') + '>1</option>' +
            '<option value="2"' + (f.level === 2 ? ' selected' : '') + '>2</option>' +
            '<option value="3"' + (f.level === 3 ? ' selected' : '') + '>3</option>' +
          '</select>' +
        '</td>' +
        '<td>' +
          '<input type="text" class="form-control form-control-sm ws-folder-name" data-idx="' + idx + '" value="' + escHtml(f.name) + '">' +
        '</td>';
      tbody.appendChild(tr);
    });
    updateFolderRowActions();
  }

  function escHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function getCheckedFolderIdxs() {
    const checks = getTbody()?.querySelectorAll('.ws-folder-check:checked') || [];
    return Array.from(checks).map(c => parseInt(c.dataset.idx, 10));
  }

  function updateFolderRowActions() {
    const panel = document.getElementById('ws-folders-row-actions');
    if (!panel) return;
    const anyChecked = getCheckedFolderIdxs().length > 0;
    panel.classList.toggle('d-none', !anyChecked);
    panel.classList.toggle('d-flex', anyChecked);
  }

  function syncFromInputs() {
    const tbody = getTbody();
    if (!tbody) return;
    tbody.querySelectorAll('.ws-folder-level').forEach(sel => {
      const idx = parseInt(sel.dataset.idx, 10);
      if (wsFolders[idx]) wsFolders[idx].level = parseInt(sel.value, 10);
    });
    tbody.querySelectorAll('.ws-folder-name').forEach(inp => {
      const idx = parseInt(inp.dataset.idx, 10);
      if (wsFolders[idx]) wsFolders[idx].name = inp.value;
    });
  }

  async function loadFolders() {
    const root = pane();
    const url = root?.querySelector('[data-workspace-folders-url]')?.dataset?.workspaceFoldersUrl;
    if (!url) return;
    try {
      const resp = await fetch(url);
      const data = await resp.json();
      wsFolders = (data.folders || []).map(f => ({ level: f.level, name: f.name }));
      wsIsCustom = !!data.is_custom;
    } catch { wsFolders = []; wsIsCustom = false; }
    renderFolderRows();
    updateResetBtn();
  }

  // Delegated modal open listeners (partials loaded via HTMX)
  document.addEventListener('show.bs.modal', (e) => {
    if (e.target.matches('#reg-workspace-settings-modal')) loadFolders();
  });

  document.addEventListener('show.bs.modal', async (e) => {
    if (!e.target.matches('#reg-create-workspace-modal')) return;
    const root = pane();
    const url = root?.querySelector('[data-workspace-folders-url]')?.dataset?.workspaceFoldersUrl;
    const listEl = document.getElementById('reg-ws-folder-counts');
    const storageLabelEl = document.getElementById('reg-create-workspace-storage-label');
    if (!listEl) return;
    listEl.innerHTML = '<li class="text-muted">Загрузка…</li>';

    let folders = [];
    if (url) {
      try {
        const resp = await fetch(url);
        const data = await resp.json();
        folders = data.folders || [];
        if (storageLabelEl && data.storage_label) storageLabelEl.textContent = data.storage_label;
      } catch { /* ignore */ }
    }

    const counts = {};
    folders.forEach(f => { counts[f.level] = (counts[f.level] || 0) + 1; });
    listEl.innerHTML = '';
    [1, 2, 3].forEach(lvl => {
      const li = document.createElement('li');
      li.textContent = 'директории уровня ' + lvl + ': ' + (counts[lvl] || 0);
      listEl.appendChild(li);
    });

    const progressEl = document.getElementById('reg-ws-progress');
    if (progressEl) progressEl.classList.add('d-none');
    const fillEl = progressEl?.querySelector('.ws-progress-fill');
    if (fillEl) fillEl.style.width = '0%';
    const statusEl = document.getElementById('reg-create-workspace-status');
    if (statusEl) statusEl.textContent = '';
  });

  document.addEventListener('hidden.bs.modal', (e) => {
    if (!e.target.matches('#reg-create-workspace-modal')) return;
    if (e.target.dataset.workspaceCreated === '1') {
      clearRegistrationSelection();
    }
    e.target.dataset.workspaceCreated = '0';
  });

  document.addEventListener('change', (e) => {
    if (e.target.closest('.ws-folder-check')) updateFolderRowActions();
  });

  document.addEventListener('click', (e) => {
    if (e.target.closest('#ws-folder-add-btn')) {
      syncFromInputs();
      wsFolders.push({ level: 1, name: '' });
      renderFolderRows();
      const tbody = getTbody();
      const lastInput = tbody?.querySelector('tr:last-child .ws-folder-name');
      if (lastInput) lastInput.focus();
      return;
    }

    if (e.target.closest('#ws-folder-delete-btn')) {
      syncFromInputs();
      const idxs = new Set(getCheckedFolderIdxs());
      wsFolders = wsFolders.filter((_, i) => !idxs.has(i));
      renderFolderRows();
      return;
    }

    if (e.target.closest('#ws-folder-up-btn')) {
      syncFromInputs();
      const idxs = getCheckedFolderIdxs().sort((a, b) => a - b);
      for (const idx of idxs) {
        if (idx > 0 && !idxs.includes(idx - 1)) {
          [wsFolders[idx - 1], wsFolders[idx]] = [wsFolders[idx], wsFolders[idx - 1]];
        }
      }
      renderFolderRows();
      const newIdxs = idxs.map(i => (i > 0 && !idxs.includes(i - 1)) ? i - 1 : i);
      newIdxs.forEach(i => {
        const cb = getTbody()?.querySelector('.ws-folder-check[data-idx="' + i + '"]');
        if (cb) cb.checked = true;
      });
      updateFolderRowActions();
      return;
    }

    if (e.target.closest('#ws-folder-down-btn')) {
      syncFromInputs();
      const idxs = getCheckedFolderIdxs().sort((a, b) => b - a);
      for (const idx of idxs) {
        if (idx < wsFolders.length - 1 && !idxs.includes(idx + 1)) {
          [wsFolders[idx], wsFolders[idx + 1]] = [wsFolders[idx + 1], wsFolders[idx]];
        }
      }
      renderFolderRows();
      const newIdxs = idxs.map(i => (i < wsFolders.length - 1 && !idxs.includes(i + 1)) ? i + 1 : i);
      newIdxs.forEach(i => {
        const cb = getTbody()?.querySelector('.ws-folder-check[data-idx="' + i + '"]');
        if (cb) cb.checked = true;
      });
      updateFolderRowActions();
      return;
    }
  });

  document.addEventListener('click', async (e) => {
    if (!e.target.closest('#ws-folders-save-btn')) return;
    syncFromInputs();

    const root = pane();
    const saveUrl = root?.querySelector('[data-workspace-folders-save-url]')?.dataset?.workspaceFoldersSaveUrl;
    if (!saveUrl) return;

    const btn = e.target.closest('#ws-folders-save-btn');
    btn.disabled = true;

    try {
      const resp = await fetch(saveUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken, 'Content-Type': 'application/json' },
        body: JSON.stringify({ folders: wsFolders }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data?.error || 'Ошибка сохранения.');

      if (data.is_custom !== undefined) wsIsCustom = data.is_custom;
      updateResetBtn();

      const modal = window.bootstrap?.Modal.getInstance(getSettingsModal());
      modal?.hide();
    } catch (err) {
      alert(err.message || 'Не удалось сохранить.');
    } finally {
      btn.disabled = false;
    }
  });

  document.addEventListener('click', async (e) => {
    if (!e.target.closest('#ws-folders-reset-btn')) return;

    const root = pane();
    const resetUrl = root?.querySelector('[data-workspace-folders-reset-url]')?.dataset?.workspaceFoldersResetUrl;
    if (!resetUrl) return;

    const btn = e.target.closest('#ws-folders-reset-btn');
    btn.disabled = true;

    try {
      const resp = await fetch(resetUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data?.error || 'Ошибка сброса.');

      wsFolders = (data.folders || []).map(f => ({ level: f.level, name: f.name }));
      wsIsCustom = !!data.is_custom;
      renderFolderRows();
      updateResetBtn();
    } catch (err) {
      alert(err.message || 'Не удалось сбросить.');
    } finally {
      btn.disabled = false;
    }
  });
})();