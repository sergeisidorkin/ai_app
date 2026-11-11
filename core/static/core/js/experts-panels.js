(function () {
  if (window.__expertsPanelBound) return;
  window.__expertsPanelBound = true;

  window.__espTableSel = window.__espTableSel || {};
  window.__expertsPaneDirty = window.__expertsPaneDirty || false;

  function pane() { return document.getElementById('experts-pane'); }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  const expertsFooterSyncs = new Set();

  function updateExpertsTableScrollGaps() {
    const root = pane();
    if (!root) return;
    qa('.experts-profiles-table-wrap', root).forEach((wrap) => {
      wrap.classList.toggle('has-horizontal-scroll', wrap.scrollWidth > wrap.clientWidth + 1);
    });
    expertsFooterSyncs.forEach((sync) => sync());
  }

  function scheduleExpertsTableScrollGapsUpdate() {
    window.requestAnimationFrame(updateExpertsTableScrollGaps);
  }

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  const csrftoken = getCookie('csrftoken');

  const PANELS = {
    'epr-actions': {
      name: 'epr-select',
      modal: '#experts-profile-modal .modal-content',
      modalId: 'experts-profile-modal',
      deleteLabel: 'строк(у/и)',
    },
    'ecd-actions': {
      name: 'ecd-select',
      modal: '#experts-contract-details-modal .modal-content',
      modalId: 'experts-contract-details-modal',
      deleteLabel: 'строк(у/и)',
    },
  };

  function getRowChecksByName(name) {
    const root = pane();
    return qa(`tbody input.form-check-input[name="${CSS.escape(name)}"]`, root);
  }
  function getCheckedByName(name) {
    return getRowChecksByName(name).filter(b => b.checked);
  }
  function updateRowHighlightFor(name) {
    getRowChecksByName(name).forEach(b => {
      const tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateMasterStateFor(name) {
    const boxes = getRowChecksByName(name);
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
    const anyChecked = getRowChecksByName(name).some(b => b.checked);
    panel.classList.toggle('d-none', !anyChecked);
  }

  function updateEditBtnState() {
    const root = pane();
    if (!root) return;
    const btn = root.querySelector('#epr-edit-btn');
    if (btn) {
      const checked = getCheckedByName('epr-select');
      btn.disabled = checked.length !== 1;
    }
  }

  function updateContractDetailsEditBtn() {
    const root = pane();
    if (!root) return;
    const btn = root.querySelector('#ecd-edit-btn');
    if (!btn) return;
    const anyChecked = getRowChecksByName('ecd-select').some(b => b.checked);
    btn.disabled = !anyChecked;
  }

  function findPanelConfig(btn) {
    for (const [panelId, config] of Object.entries(PANELS)) {
      if (btn.closest('#' + panelId)) return config;
    }
    return null;
  }

  function expertsTabIsActive() {
    return !!document.querySelector('#experts.tab-pane.show.active, #experts.tab-pane.active.show');
  }

  function expertsModalIsOpen() {
    return !!document.querySelector('#experts-modal.show, #experts-profile-modal.show, #experts-contract-details-modal.show');
  }

  function expertsPageQuery() {
    const root = pane();
    const params = new URLSearchParams();
    params.set('page', root?.dataset.expertsPage || '1');
    params.set('page_size', root?.dataset.expertsPageSize || '25');
    const sort = root?.dataset.expertsFullNameSort || '';
    if (sort === 'asc' || sort === 'desc') params.set('full_name_sort', sort);
    (root?.dataset.expertsSpecialties || '').split(',').filter(Boolean).forEach(function (specialtyId) {
      params.append('specialty', specialtyId);
    });
    return params.toString();
  }

  function expertsPartialUrl() {
    return '/experts/partial/?' + expertsPageQuery();
  }

  async function refreshExpertsPane() {
    if (!window.htmx) return;
    if (expertsModalIsOpen()) {
      window.__expertsPaneDirty = true;
      return;
    }
    await htmx.ajax('GET', expertsPartialUrl(), { target: '#experts-pane', swap: 'outerHTML' });
    window.__expertsPaneDirty = false;
  }

  async function doEdit(name, config) {
    const checked = getCheckedByName(name);
    if (!checked.length) return;
    const first = checked[0];
    const tr = first.closest('tr');
    const url = tr?.dataset?.editUrl;
    if (!url) return;
    // После закрытия модалки выделение снимается (table-selection.js);
    // кэш забываем, чтобы afterSettle после «Сохранить» его не восстановил.
    try { delete window.__espTableSel[name]; } catch (_) { window.__espTableSel[name] = []; }
    window.TableSelection?.clearOnModalHide(config.modalId, name, pane());
    await htmx.ajax('GET', url, { target: config.modal, swap: 'innerHTML' });
    const modalEl = document.getElementById(config.modalId);
    if (modalEl && window.bootstrap) {
      window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }
    ensureActionsVisibility(name);
  }

  document.addEventListener('click', async (e) => {
    const root = pane();
    if (!root) return;

    const quickEdit = e.target.closest('.epr-quick-edit');
    if (quickEdit && root.contains(quickEdit)) {
      e.preventDefault();
      const tr = quickEdit.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;
      const config = PANELS['epr-actions'];
      try { delete window.__espTableSel['epr-select']; } catch (_) { window.__espTableSel['epr-select'] = []; }
      window.TableSelection?.clearOnModalHide(config.modalId, 'epr-select', pane());
      await htmx.ajax('GET', url, { target: config.modal, swap: 'innerHTML' });
      const modalEl = document.getElementById(config.modalId);
      if (modalEl && window.bootstrap) {
        window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
      }
      return;
    }

    const editBtn = e.target.closest('#epr-edit-btn');
    if (editBtn && root.contains(editBtn)) {
      e.preventDefault();
      const config = PANELS['epr-actions'];
      window.__espTableSel['epr-select'] = getCheckedByName('epr-select').map(ch => String(ch.value));
      await doEdit('epr-select', config);
      return;
    }

    const ecdEditBtn = e.target.closest('#ecd-edit-btn');
    if (ecdEditBtn && root.contains(ecdEditBtn)) {
      e.preventDefault();
      const checked = getCheckedByName('ecd-select');
      if (!checked.length) return;
      const first = checked[0];
      const tr = first.closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;

      // После закрытия модалки выделение снимается (table-selection.js);
      // кэш не запоминаем, чтобы afterSettle после «Сохранить» его не восстановил.
      try { delete window.__espTableSel['ecd-select']; } catch (_) { window.__espTableSel['ecd-select'] = []; }

      const config = PANELS['ecd-actions'];
      window.TableSelection?.clearOnModalHide(config.modalId, 'ecd-select', root);
      await htmx.ajax('GET', url, { target: config.modal, swap: 'innerHTML' });
      const modalEl = document.getElementById(config.modalId);
      if (modalEl && window.bootstrap) {
        window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
      }
      updateContractDetailsEditBtn();
      return;
    }

    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    const config = findPanelConfig(btn);
    if (!config) return;

    const action = btn.dataset.panelAction;
    const name = config.name;

    const checked = getCheckedByName(name);
    if (!checked.length) return;

    window.__espTableSel[name] = checked.map(ch => String(ch.value));

    if (action === 'edit') {
      await doEdit(name, config);
      return;
    }

    if (action === 'delete') {
      if (!confirm(`Удалить ${checked.length} ${config.deleteLabel}?`)) return;
      const urls = checked.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      const progress = window.TableActionProgress?.begin(checked);
      try {
        for (let i = 0; i < urls.length; i++) {
          const isLast = i === urls.length - 1;
          if (isLast) {
            await htmx.ajax('POST', urls[i], { target: '#experts-pane', swap: 'outerHTML' });
          } else {
            await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
          }
        }
      } finally {
        progress?.end();
      }
      return;
    }

    if (action === 'up' || action === 'down') {
      if (window.__queuedRowOrder?.handleMoveAction({
        checked,
        action,
        refresh: () => htmx.ajax('GET', expertsPartialUrl(), { target: '#experts-pane', swap: 'outerHTML' }),
      })) {
        ensureActionsVisibility(name);
        return;
      }
      let urls = checked
        .map(ch => ch.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#experts-pane', swap: 'outerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(() => {});
        }
      }
      ensureActionsVisibility(name);
      return;
    }
  });

  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const master = e.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (!master || !root.contains(master)) return;
    const name = master.dataset.targetName;
    const boxes = getRowChecksByName(name);
    boxes.forEach(b => { b.checked = master.checked; });
    master.indeterminate = false;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
    if (name === 'epr-select') updateEditBtnState();
    if (name === 'ecd-select') updateContractDetailsEditBtn();
  });

  document.addEventListener('change', (e) => {
    const root = pane();
    if (!root) return;
    const colpickerInput = e.target.closest('#epr-colpicker-menu input.form-check-input');
    if (colpickerInput && root.contains(colpickerInput)) {
      scheduleExpertsTableScrollGapsUpdate();
      return;
    }
    const rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (!rowCb || !root.contains(rowCb)) return;
    const name = rowCb.name;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
    if (name === 'epr-select') updateEditBtnState();
    if (name === 'ecd-select') updateContractDetailsEditBtn();
  });

  function attachExpertsTableFooterStickyState(footer) {
    const editor = footer?.closest('.experts-table-editor');
    if (!footer || !editor || !footer.closest('#experts-pane')) return;
    if (footer.dataset.stickyStateBound === '1') return;
    footer.dataset.stickyStateBound = '1';

    const marker = document.createElement('span');
    marker.className = 'policy-sticky-actions-marker';
    marker.setAttribute('aria-hidden', 'true');
    footer.insertAdjacentElement('afterend', marker);

    let intersectionObserver = null;
    let resizeObserver = null;

    function release() {
      expertsFooterSyncs.delete(syncStickyState);
      intersectionObserver?.disconnect();
      resizeObserver?.disconnect();
      window.removeEventListener('scroll', syncStickyState, true);
      window.removeEventListener('resize', syncStickyState);
      document.removeEventListener('shown.bs.tab', syncStickyState);
    }

    function syncStickyState() {
      if (!footer.isConnected) {
        release();
        return;
      }
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      const editorRect = editor.getBoundingClientRect();
      const markerRect = marker.getBoundingClientRect();
      const isStuck = (
        editorRect.top < viewportHeight
        && editorRect.bottom > 0
        && markerRect.top >= viewportHeight
      );
      footer.classList.toggle('is-stuck', isStuck);
    }

    expertsFooterSyncs.add(syncStickyState);
    if ('IntersectionObserver' in window) {
      intersectionObserver = new IntersectionObserver(syncStickyState, {
        threshold: [0, 1],
      });
      intersectionObserver.observe(editor);
      intersectionObserver.observe(marker);
    }
    if ('ResizeObserver' in window) {
      resizeObserver = new ResizeObserver(syncStickyState);
      resizeObserver.observe(editor);
    }
    window.addEventListener('scroll', syncStickyState, true);
    window.addEventListener('resize', syncStickyState);
    document.addEventListener('shown.bs.tab', syncStickyState);
    window.requestAnimationFrame(syncStickyState);
  }

  let expertProfileSpecialtySession = null;
  const expertProfileSpecialtySaveTokens = new Map();

  function createExpertProfileSpecialtyAdapter(section) {
    let specialties = [];
    try {
      const node = section.querySelector('[data-policy-inline-options]');
      const parsed = JSON.parse(node ? node.textContent : '{}');
      specialties = parsed.specialties || [];
    } catch (err) {
      specialties = [];
    }
    return {
      getSelectOptions: function (ref) {
        if (ref.field !== 'specialty_ids') return [];
        let selected = [];
        try {
          const parsed = JSON.parse(ref.cell.getAttribute('data-inline-value') || '[]');
          selected = Array.isArray(parsed) ? parsed.map(function (id) { return String(id); }) : [];
        } catch (err) {
          selected = [];
        }
        const currentId = ref.cell.dataset.inlineActiveIndex != null
          ? (selected[Number(ref.cell.dataset.inlineActiveIndex)] || '')
          : '';
        return [{ value: '', label: '---------' }].concat(specialties.filter(function (item) {
          const id = String(item.id);
          const isCurrent = currentId && id === String(currentId);
          return isCurrent || selected.indexOf(id) === -1;
        }).map(function (item) {
          return { value: String(item.id), label: item.label || '' };
        }));
      },
      getSpecialtyOptions: function () {
        return specialties;
      },
      normalizeValue: function (ref, value) {
        if (ref.field === 'specialty_ids') {
          return { value: Array.isArray(value) ? value : [], label: '' };
        }
        return { value: value, label: value };
      },
      afterChange: function (ref, value, session) {
        if (ref.field !== 'specialty_ids') return;
        const row = ref.cell.closest('tr');
        const url = row && row.dataset.specialtiesSaveUrl;
        const rowId = row && row.dataset.inlineRowId;
        if (!url || !rowId || !session) return;
        const token = (expertProfileSpecialtySaveTokens.get(rowId) || 0) + 1;
        expertProfileSpecialtySaveTokens.set(rowId, token);
        const body = new URLSearchParams();
        (value || []).forEach(function (id) {
          const text = String(id || '').trim();
          if (text) body.append('specialty_id', text);
        });
        fetch(url, {
          method: 'POST',
          headers: {
            'X-CSRFToken': csrftoken,
            'X-Requested-With': 'fetch',
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: body.toString(),
        }).then(function (response) {
          if (expertProfileSpecialtySaveTokens.get(rowId) !== token) return null;
          if (!response.ok) throw new Error('save failed');
          return response.json();
        }).then(function (data) {
          if (!data || expertProfileSpecialtySaveTokens.get(rowId) !== token) return;
          if (data.ok === false) throw new Error(data.error || 'save failed');
          session.clearFieldError('expert-profiles', rowId, 'specialty_ids');
          session.snapshotRow('expert-profiles', rowId, { specialty_ids: value });
          if (window.WorkspaceInlineEditor) {
            window.WorkspaceInlineEditor.applyErrorsToDom(session, section);
          }
        }).catch(function () {
          if (expertProfileSpecialtySaveTokens.get(rowId) !== token) return;
          session.setErrors([{
            table: 'expert-profiles',
            id: rowId,
            field: 'specialty_ids',
            message: 'Не удалось сохранить специальности.',
          }]);
          if (window.WorkspaceInlineEditor) {
            window.WorkspaceInlineEditor.applyErrorsToDom(session, section);
          }
        });
      },
    };
  }

  function bindExpertProfileSpecialties(section) {
    if (!section || section.dataset.policyTableKey !== 'expert-profiles') return;
    if (section.dataset.policyInline !== '1' || !window.WorkspaceInlineEditor) return;
    if (expertProfileSpecialtySession && expertProfileSpecialtySession.hasSection(section)) return;
    if (expertProfileSpecialtySession) window.WorkspaceInlineEditor.detach(expertProfileSpecialtySession);
    expertProfileSpecialtySession = window.WorkspaceInlineEditor.createSession();
    window.WorkspaceInlineEditor.attach(expertProfileSpecialtySession);
    window.WorkspaceInlineEditor.bindSection(
      expertProfileSpecialtySession,
      section,
      createExpertProfileSpecialtyAdapter(section)
    );
  }

  function initExpertsTableFooterStickyState(root) {
    const scope = root && root.querySelector ? root : (pane() || document);
    const footers = scope.matches?.('.policy-table-footer')
      ? [scope]
      : qa('.policy-table-footer', scope);
    footers.forEach(attachExpertsTableFooterStickyState);
  }

  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (!(e.target && e.target.id === 'experts-pane')) return;
    initExpertsTableFooterStickyState(e.target);
    const sel = window.__espTableSel || {};
    Object.keys(sel).forEach(name => {
      const ids = sel[name] || [];
      const set = new Set(ids);
      getRowChecksByName(name).forEach(b => { b.checked = set.has(String(b.value)); });
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
    });
    updateEditBtnState();
    updateContractDetailsEditBtn();
    window.__espTableSel = {};
    persistExpertsTableView(e.target);
    bindExpertProfileSpecialties(e.target);
    initWrapToggle();
    scheduleExpertsTableScrollGapsUpdate();
  });

  // Снятие выделения выполняет общий модуль table-selection.js (hidden.bs.modal);
  // здесь досинхронизируем состояние кнопок редактирования.
  document.addEventListener('table-selection:cleared', function (e) {
    const name = e.detail && e.detail.name;
    if (name === 'epr-select') updateEditBtnState();
    if (name === 'ecd-select') updateContractDetailsEditBtn();
  });

  document.body.addEventListener('contacts-updated', function () {
    window.__expertsPaneDirty = true;
    if (expertsTabIsActive()) {
      refreshExpertsPane().catch(() => {});
    }
  });

  document.addEventListener('shown.bs.tab', function (e) {
    const trigger = e.target;
    if (!trigger || trigger.getAttribute('href') !== '#experts') return;
    if (!window.__expertsPaneDirty) return;
    refreshExpertsPane().catch(() => {});
  });

  var P = window.UIPref;
  var EXPERTS_SORT_PREF_KEY = 'experts:fullNameSort';
  var EXPERTS_SPECIALTY_PREF_KEY = 'experts:specialtyFilter';
  window.__eprWrapActive = P ? P.get('experts:wrapActive', true) : true;

  function savedExpertsSort() {
    const value = P ? P.get(EXPERTS_SORT_PREF_KEY, '') : '';
    return value === 'asc' || value === 'desc' ? value : '';
  }

  function savedExpertsSpecialties() {
    const value = P ? P.get(EXPERTS_SPECIALTY_PREF_KEY, []) : [];
    if (!Array.isArray(value)) return [];
    return value.map(function (item) { return String(item || '').trim(); }).filter(Boolean);
  }

  function persistExpertsTableView(root) {
    if (!P || !root || root.id !== 'experts-pane' || !Object.prototype.hasOwnProperty.call(root.dataset, 'expertsPage')) return;
    const sort = root.dataset.expertsFullNameSort || '';
    const specialties = (root.dataset.expertsSpecialties || '').split(',').map(function (item) {
      return item.trim();
    }).filter(Boolean);
    P.set(EXPERTS_SORT_PREF_KEY, sort === 'asc' || sort === 'desc' ? sort : '');
    P.set(EXPERTS_SPECIALTY_PREF_KEY, specialties);
  }

  document.body.addEventListener('htmx:configRequest', function (event) {
    const detail = event.detail || {};
    const elt = detail.elt;
    const path = String(detail.path || '');
    if (!elt || elt.id !== 'experts-pane' || elt.getAttribute('hx-trigger') !== 'load') return;
    if (path.indexOf('/experts/partial') === -1) return;
    const queryIndex = path.indexOf('?');
    const params = new URLSearchParams(queryIndex === -1 ? '' : path.slice(queryIndex + 1));
    if (params.has('full_name_sort') || params.has('specialty') || params.has('page')) return;
    const sort = savedExpertsSort();
    const specialties = savedExpertsSpecialties();
    if (!sort && !specialties.length) return;
    if (sort) params.set('full_name_sort', sort);
    specialties.forEach(function (specialtyId) { params.append('specialty', specialtyId); });
    const bare = queryIndex === -1 ? path : path.slice(0, queryIndex);
    detail.path = bare + '?' + params.toString();
  });

  function initWrapToggle() {
    const toggle = document.getElementById('epr-wrap-toggle');
    if (!toggle) return;
    toggle.classList.toggle('active', !!window.__eprWrapActive);
    const wrap = document.getElementById('epr-table-wrap');
    const table = wrap ? wrap.querySelector('table') : null;
    if (table) table.classList.toggle('clf-truncated', !!window.__eprWrapActive);
  }

  document.addEventListener('click', function (e) {
    const toggle = e.target.closest('#epr-wrap-toggle');
    if (!toggle) return;
    const wrap = document.getElementById('epr-table-wrap');
    const table = wrap?.querySelector('table');
    if (!table) return;
    table.classList.toggle('clf-truncated');
    const active = table.classList.contains('clf-truncated');
    toggle.classList.toggle('active', active);
    window.__eprWrapActive = active;
    if (P) P.set('experts:wrapActive', active);
    scheduleExpertsTableScrollGapsUpdate();
  });

  window.addEventListener('resize', scheduleExpertsTableScrollGapsUpdate);
  window.addEventListener('load', scheduleExpertsTableScrollGapsUpdate);

  function showExpertsCsvResult(html) {
    var body = document.getElementById('experts-csv-result-body');
    var modalEl = document.getElementById('experts-csv-result-modal');
    if (!body || !modalEl) {
      alert(html.replace(/<[^>]+>/g, ''));
      return;
    }
    body.innerHTML = html;
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  async function handleExpertsTableUpload(uploadUrl, file) {
    var formData = new FormData();
    formData.append('csv_file', file);
    try {
      var resp = await fetch(uploadUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrftoken },
        body: formData,
      });
      var data = await resp.json();
      if (data.ok) {
        var html;
        if (typeof data.updated === 'number') {
          html = '<div class="mb-2"><strong>Обновлено строк: ' + data.updated + '</strong></div>';
        } else {
          html = '<div class="mb-2"><strong>Загружено строк: ' + data.created + '</strong></div>';
        }
        if (data.warnings && data.warnings.length) {
          html += '<div class="text-danger mb-1"><strong>Предупреждения (' + data.warnings.length + '):</strong></div>';
          html += '<div class="text-danger">';
          for (var i = 0; i < data.warnings.length; i++) {
            html += '<div class="mb-1">' + data.warnings[i].replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>';
          }
          html += '</div>';
        }
        showExpertsCsvResult(html);
        await refreshExpertsPane();
      } else {
        showExpertsCsvResult('<div class="text-danger"><strong>Ошибка:</strong> ' +
          (data.error || 'Неизвестная ошибка').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
      }
    } catch (err) {
      showExpertsCsvResult('<div class="text-danger"><strong>Ошибка загрузки:</strong> ' +
        err.message.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</div>');
    }
  }

  document.addEventListener('click', function (event) {
    var uploadMapping = {
      'epr-csv-upload-btn': 'epr-csv-file-input',
    };
    for (var btnId in uploadMapping) {
      if (!event.target.closest('#' + btnId)) continue;
      var fileInput = document.getElementById(uploadMapping[btnId]);
      if (fileInput) fileInput.click();
      return;
    }
  });

  document.addEventListener('change', async function (event) {
    var uploadMapping = {
      'epr-csv-file-input': '/experts/profile/csv-upload/',
    };
    var uploadUrl = uploadMapping[event.target.id];
    if (!uploadUrl) return;
    var file = event.target.files && event.target.files[0];
    event.target.value = '';
    if (!file) return;
    await handleExpertsTableUpload(uploadUrl, file);
  });

  function reopenExpertsSpecialtyFilter(root) {
    if (!root || !window.bootstrap?.Dropdown) return;
    const toggle = root.querySelector('[data-experts-specialty-filter] [data-bs-toggle="dropdown"]');
    if (!toggle) return;
    window.bootstrap.Dropdown.getOrCreateInstance(toggle).show();
  }

  async function refreshExpertsSpecialtyFilter() {
    const root = pane();
    if (!root || !window.htmx) return;
    const params = new URLSearchParams();
    params.set('page', '1');
    params.set('page_size', root.dataset.expertsPageSize || '25');
    const sort = root.dataset.expertsFullNameSort || '';
    if (sort === 'asc' || sort === 'desc') params.set('full_name_sort', sort);
    root.querySelectorAll('.js-experts-specialty-filter').forEach(function (checkbox) {
      if (checkbox.checked && checkbox.value && checkbox.value !== '__all__') {
        params.append('specialty', checkbox.value);
      }
    });
    await htmx.ajax('GET', '/experts/partial/?' + params.toString(), {
      target: '#experts-pane',
      swap: 'outerHTML',
    });
    reopenExpertsSpecialtyFilter(pane());
  }

  document.addEventListener('change', function (event) {
    const input = event.target;
    if (!input?.classList?.contains('js-experts-specialty-filter')) return;
    const root = pane();
    if (!root || !root.contains(input)) return;
    const dropdown = input.closest('[data-experts-specialty-filter]');
    const checks = dropdown
      ? Array.from(dropdown.querySelectorAll('.js-experts-specialty-filter'))
      : [];
    if (input.value === '__all__' && input.checked) {
      checks.forEach(function (checkbox) {
        checkbox.checked = checkbox.value === '__all__';
      });
    } else if (input.value === '__all__' && !input.checked) {
      const first = checks.find(function (checkbox) { return checkbox.value !== '__all__'; });
      if (first) first.checked = true;
      else input.checked = true;
    } else if (input.checked) {
      const allCheckbox = checks.find(function (checkbox) { return checkbox.value === '__all__'; });
      if (allCheckbox) allCheckbox.checked = false;
    } else if (!checks.some(function (checkbox) {
      return checkbox.value !== '__all__' && checkbox.checked;
    })) {
      const allCheckbox = checks.find(function (checkbox) { return checkbox.value === '__all__'; });
      if (allCheckbox) allCheckbox.checked = true;
    }
    refreshExpertsSpecialtyFilter();
  });

  initExpertsTableFooterStickyState(pane());
})();
