(function () {
  if (window.__performersPanelBound) return;
  window.__performersPanelBound = true;

  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;

  function pane() { return document.getElementById('performers-pane'); }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  const csrftoken = getCookie('csrftoken');

  function getRowChecks(name) {
    return qa(`tbody input.form-check-input[name="${name}"]`, pane());
  }
  function getChecked(name) {
    return getRowChecks(name).filter(b => b.checked);
  }
  function updateRowHighlight(name) {
    getRowChecks(name).forEach(b => {
      const tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updatePerformerMasterState() {
    const boxes = getRowChecks('performer-select');
    const master = pane()?.querySelector('input.form-check-input[data-actions-id="performers-actions"]');
    if (!master) return;
    const checkedCount = boxes.filter(b => b.checked).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function ensurePerformerActionsVisibility() {
    const panel = pane()?.querySelector('#performers-actions');
    if (!panel) return;
    const any = getRowChecks('performer-select').some(b => b.checked);
    panel.classList.toggle('d-none', !any);
    panel.classList.toggle('d-flex', any);
  }

  function getParticipationMaster() {
    return pane()?.querySelector('#participation-master');
  }
  function getParticipationRequestBtn() {
    return pane()?.querySelector('#participation-request-btn');
  }
  function getParticipationRequestPanel() {
    return pane()?.querySelector('#participation-request-actions');
  }
  function getParticipationDeadlineControls() {
    return pane()?.querySelector('#participation-deadline-controls');
  }
  function getParticipationChannels() {
    return qa('.js-participation-channel', pane());
  }
  function getParticipationRows() {
    return qa('#participation-confirmation-section tbody tr[data-project-id]', pane());
  }
  function getVisibleParticipationChecks() {
    return getParticipationRows()
      .filter((row) => !row.classList.contains('d-none'))
      .map((row) => row.querySelector('input[name="participation-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }
  function updateParticipationState() {
    const boxes = getVisibleParticipationChecks();
    const checkedCount = boxes.filter(b => b.checked).length;
    const master = getParticipationMaster();
    if (master) {
      master.checked = boxes.length > 0 && checkedCount === boxes.length;
      master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
    }
    updateRowHighlight('participation-select');

    const requestBtn = getParticipationRequestBtn();
    if (requestBtn) requestBtn.disabled = checkedCount === 0;

    const controls = getParticipationDeadlineControls();
    if (controls) {
      const show = checkedCount > 0;
      controls.classList.toggle('invisible', !show);
      controls.classList.toggle('pe-none', !show);
    }
  }

  function getInfoRequestMaster() {
    return pane()?.querySelector('#info-request-master');
  }
  function getInfoRequestBtn() {
    return pane()?.querySelector('#info-request-btn');
  }
  function getInfoRequestPanel() {
    return pane()?.querySelector('#info-request-actions');
  }
  function getInfoRequestDeadlineControls() {
    return pane()?.querySelector('#info-request-deadline-controls');
  }
  function getInfoRequestChannels() {
    return qa('.js-info-request-channel', pane());
  }
  function getInfoRequestRows() {
    return qa('#info-request-approval-section tbody tr[data-project-id]', pane());
  }
  function getVisibleInfoRequestChecks() {
    return getInfoRequestRows()
      .filter((row) => !row.classList.contains('d-none'))
      .map((row) => row.querySelector('input[name="info-request-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }
  function getCreateWorkspaceBtn() {
    return pane()?.querySelector('#create-workspace-btn');
  }

  function getSelectedInfoRequestProjectId() {
    const filter = window.__infoRequestProjectFilter;
    if (filter && filter.length === 1 && filter[0] !== '__all__') return filter[0];
    return null;
  }

  function updateInfoRequestState() {
    const boxes = getVisibleInfoRequestChecks();
    const checkedCount = boxes.filter(b => b.checked).length;
    const master = getInfoRequestMaster();
    if (master) {
      master.checked = boxes.length > 0 && checkedCount === boxes.length;
      master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
    }
    updateRowHighlight('info-request-select');

    const requestBtn = getInfoRequestBtn();
    if (requestBtn) requestBtn.disabled = checkedCount === 0;

    const controls = getInfoRequestDeadlineControls();
    if (controls) {
      const show = checkedCount > 0;
      controls.classList.toggle('invisible', !show);
      controls.classList.toggle('pe-none', !show);
    }

    const wsBtn = getCreateWorkspaceBtn();
    if (wsBtn) wsBtn.disabled = !getSelectedInfoRequestProjectId();
  }

  function getContractMaster() {
    return pane()?.querySelector('#contract-master');
  }
  function getContractRequestBtn() {
    return pane()?.querySelector('#contract-request-btn');
  }
  function getContractRequestPanel() {
    return pane()?.querySelector('#contract-request-actions');
  }
  function getContractDeadlineControls() {
    return pane()?.querySelector('#contract-deadline-controls');
  }
  function getContractChannels() {
    return qa('.js-contract-channel', pane());
  }
  function getContractRows() {
    return qa('#contract-conclusion-section tbody tr[data-project-id]', pane());
  }
  function getVisibleContractChecks() {
    return getContractRows()
      .filter((row) => !row.classList.contains('d-none'))
      .map((row) => row.querySelector('input[name="contract-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }

  function updateContractState() {
    const boxes = getVisibleContractChecks();
    const checkedCount = boxes.filter(b => b.checked).length;
    const master = getContractMaster();
    if (master) {
      master.checked = boxes.length > 0 && checkedCount === boxes.length;
      master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
    }
    updateRowHighlight('contract-select');

    const requestBtn = getContractRequestBtn();
    if (requestBtn) requestBtn.disabled = checkedCount === 0;

    const controls = getContractDeadlineControls();
    if (controls) {
      const show = checkedCount > 0;
      controls.classList.toggle('invisible', !show);
      controls.classList.toggle('pe-none', !show);
    }
  }

  function applyRowGrouping(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var prevGroupKey = null;
    var prevAssetKey = null;
    var prevDetailTexts = null;
    rows.forEach(function(row) {
      row.classList.remove('group-first', 'group-cont', 'asset-cont');
      var detailCells = row.querySelectorAll('.cell-detail-val');
      detailCells.forEach(function(c) { c.classList.remove('cell-repeated'); });
      if (row.classList.contains('d-none')) return;
      var groupKey = (row.dataset.projectId || '') + '||' + (row.dataset.executor || '');
      var assetKey = groupKey + '||' + (row.dataset.assetName || '');
      if (groupKey !== prevGroupKey) {
        row.classList.add('group-first');
        prevDetailTexts = null;
      } else {
        row.classList.add('group-cont');
        if (assetKey === prevAssetKey) {
          row.classList.add('asset-cont');
        }
      }
      var curDetailTexts = [];
      detailCells.forEach(function(c, i) {
        var txt = c.textContent.trim();
        curDetailTexts.push(txt);
        if (prevDetailTexts && prevDetailTexts[i] === txt) {
          c.classList.add('cell-repeated');
        }
      });
      prevGroupKey = groupKey;
      prevAssetKey = assetKey;
      prevDetailTexts = curDetailTexts;
    });

    var lastVisible = null;
    rows.forEach(function(row) {
      row.classList.remove('last-visible-row');
      if (!row.classList.contains('d-none')) lastVisible = row;
    });
    if (lastVisible) lastVisible.classList.add('last-visible-row');
  }

  function propagateGroupCheck(checkbox, name) {
    var row = checkbox.closest('tr');
    if (!row || !row.classList.contains('group-first')) return;
    var sibling = row.nextElementSibling;
    while (sibling && sibling.classList.contains('group-cont')) {
      var cb = sibling.querySelector('input[name="' + name + '"]');
      if (cb && !cb.disabled) cb.checked = checkbox.checked;
      sibling = sibling.nextElementSibling;
    }
  }

  function initContractProjectFilter() {
    const root = pane();
    if (!root) return;

    const FILTER_ALL = '__all__';
    window.__contractProjectFilter = window.__contractProjectFilter || [FILTER_ALL];

    const dropdown = root.querySelector('#contract-project-filter-toggle')?.closest('.dropdown');
    const checks = root.querySelectorAll('.js-contract-filter');
    const label = root.querySelector('.js-contract-filter-label');
    const master = root.querySelector('#contract-master');

    if (!dropdown || !checks.length || !label || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';

    function syncCheckboxes(values) {
      const set = new Set(values);
      checks.forEach((cb) => {
        cb.checked = set.has(cb.value);
      });
    }

    function updateLabel(values) {
      if (values.includes(FILTER_ALL) || !values.length) {
        label.textContent = 'Все';
        return;
      }
      if (values.length === 1) {
        const input = Array.from(checks).find((cb) => cb.value === values[0]);
        label.textContent = input?.nextElementSibling?.textContent?.trim() || '1 проект';
        return;
      }
      label.textContent = `${values.length} выбрано`;
    }

    function applyFilter(values) {
      window.__contractProjectFilter = values.slice();
      const showAll = values.includes(FILTER_ALL) || !values.length;
      getContractRows().forEach((row) => {
        const pid = row.dataset.projectId || '';
        const visible = showAll || values.includes(pid);
        row.classList.toggle('d-none', !visible);
        if (!visible) {
          const checkbox = row.querySelector('input[name="contract-select"]');
          if (checkbox) checkbox.checked = false;
        }
      });
      if (master && !showAll && !getContractRows().some((row) => !row.classList.contains('d-none'))) {
        master.checked = false;
        master.indeterminate = false;
      }
      updateLabel(values);
      updateContractState();
      applyRowGrouping(root.querySelector('#contract-conclusion-section'));
    }

    function normalizeSelection() {
      let values = Array.from(checks)
        .filter((cb) => cb.checked)
        .map((cb) => cb.value);

      if (!values.length) values = [FILTER_ALL];
      if (values.includes(FILTER_ALL)) values = [FILTER_ALL];

      syncCheckboxes(values);
      return values;
    }

    checks.forEach((cb) => {
      cb.addEventListener('change', (event) => {
        const value = event.target.value;
        if (value === FILTER_ALL && event.target.checked) {
          syncCheckboxes([FILTER_ALL]);
          applyFilter([FILTER_ALL]);
          return;
        }

        if (value === FILTER_ALL && !event.target.checked) {
          const firstProject = Array.from(checks).find((item) => item.value !== FILTER_ALL);
          if (firstProject) firstProject.checked = true;
        } else {
          const allCheckbox = root.querySelector('#contract-filter-all');
          if (allCheckbox && allCheckbox.checked) allCheckbox.checked = false;
        }

        applyFilter(normalizeSelection());
      });
    });

    const initialValues = window.__contractProjectFilter && window.__contractProjectFilter.length
      ? window.__contractProjectFilter
      : [FILTER_ALL];
    syncCheckboxes(initialValues);
    applyFilter(initialValues);
  }

  function initParticipationProjectFilter() {
    const root = pane();
    if (!root) return;

    const FILTER_ALL = '__all__';
    window.__participationProjectFilter = window.__participationProjectFilter || [FILTER_ALL];

    const dropdown = root.querySelector('#participation-project-filter-toggle')?.closest('.dropdown');
    const checks = root.querySelectorAll('.js-participation-filter');
    const label = root.querySelector('.js-participation-filter-label');
    const master = root.querySelector('#participation-master');

    if (!dropdown || !checks.length || !label || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';

    function syncCheckboxes(values) {
      const set = new Set(values);
      checks.forEach((cb) => {
        cb.checked = set.has(cb.value);
      });
    }

    function updateLabel(values) {
      if (values.includes(FILTER_ALL) || !values.length) {
        label.textContent = 'Все';
        return;
      }
      if (values.length === 1) {
        const input = Array.from(checks).find((cb) => cb.value === values[0]);
        label.textContent = input?.nextElementSibling?.textContent?.trim() || '1 проект';
        return;
      }
      label.textContent = `${values.length} выбрано`;
    }

    function applyFilter(values) {
      window.__participationProjectFilter = values.slice();
      const showAll = values.includes(FILTER_ALL) || !values.length;
      getParticipationRows().forEach((row) => {
        const pid = row.dataset.projectId || '';
        const visible = showAll || values.includes(pid);
        row.classList.toggle('d-none', !visible);
        if (!visible) {
          const checkbox = row.querySelector('input[name="participation-select"]');
          if (checkbox) checkbox.checked = false;
        }
      });
      if (master && !showAll && !getParticipationRows().some((row) => !row.classList.contains('d-none'))) {
        master.checked = false;
        master.indeterminate = false;
      }
      updateLabel(values);
      updateParticipationState();
      applyRowGrouping(root.querySelector('#participation-confirmation-section'));
    }

    function normalizeSelection() {
      let values = Array.from(checks)
        .filter((cb) => cb.checked)
        .map((cb) => cb.value);

      if (!values.length) values = [FILTER_ALL];
      if (values.includes(FILTER_ALL)) values = [FILTER_ALL];

      syncCheckboxes(values);
      return values;
    }

    checks.forEach((cb) => {
      cb.addEventListener('change', (event) => {
        const value = event.target.value;
        if (value === FILTER_ALL && event.target.checked) {
          syncCheckboxes([FILTER_ALL]);
          applyFilter([FILTER_ALL]);
          return;
        }

        if (value === FILTER_ALL && !event.target.checked) {
          const firstProject = Array.from(checks).find((item) => item.value !== FILTER_ALL);
          if (firstProject) firstProject.checked = true;
        } else {
          const allCheckbox = root.querySelector('#participation-filter-all');
          if (allCheckbox && allCheckbox.checked) allCheckbox.checked = false;
        }

        applyFilter(normalizeSelection());
      });
    });

    const initialValues = window.__participationProjectFilter && window.__participationProjectFilter.length
      ? window.__participationProjectFilter
      : [FILTER_ALL];
    syncCheckboxes(initialValues);
    applyFilter(initialValues);
  }

  function initInfoRequestProjectFilter() {
    const root = pane();
    if (!root) return;

    window.__infoRequestProjectFilter = window.__infoRequestProjectFilter || [];

    const dropdown = root.querySelector('#info-request-project-filter-toggle')?.closest('.dropdown');
    const radios = root.querySelectorAll('.js-info-request-filter');
    const label = root.querySelector('.js-info-request-filter-label');
    const master = root.querySelector('#info-request-master');

    if (!dropdown || !radios.length || !label || dropdown.dataset.bound === '1') return;
    dropdown.dataset.bound = '1';

    function applyFilter(projectId) {
      window.__infoRequestProjectFilter = projectId ? [projectId] : [];
      getInfoRequestRows().forEach((row) => {
        const pid = row.dataset.projectId || '';
        const visible = projectId && pid === projectId;
        row.classList.toggle('d-none', !visible);
        if (!visible) {
          const checkbox = row.querySelector('input[name="info-request-select"]');
          if (checkbox) checkbox.checked = false;
        }
      });
      if (master) {
        master.checked = false;
        master.indeterminate = false;
      }
      const selected = Array.from(radios).find((r) => r.checked);
      label.textContent = (selected && selected.value)
        ? (selected.nextElementSibling?.textContent?.trim() || '—')
        : 'Не выбран';
      updateInfoRequestState();
      applyRowGrouping(root.querySelector('#info-request-approval-section'));
    }

    function selectProject(projectId) {
      radios.forEach((r) => { r.checked = r.value === projectId; });
      applyFilter(projectId);
    }

    window.__syncInfoRequestFilter = selectProject;

    radios.forEach((r) => {
      r.addEventListener('change', () => {
        if (r.checked) applyFilter(r.value);
      });
    });

    const saved = window.__infoRequestProjectFilter;
    if (saved && saved.length === 1 && saved[0] !== '__all__' && saved[0] !== '') {
      const target = Array.from(radios).find((r) => r.value === saved[0]);
      if (target) {
        target.checked = true;
        applyFilter(saved[0]);
        return;
      }
    }
    selectProject('');
  }

  document.addEventListener('click', async (e) => {
    const root = pane(); if (!root) return;

    const infoRequestBtn = e.target.closest('#info-request-btn');
    if (infoRequestBtn && root.contains(infoRequestBtn)) {
      const checked = getVisibleInfoRequestChecks().filter((cb) => cb.checked);
      if (!checked.length || infoRequestBtn.disabled) return;

      const requestPanel = getInfoRequestPanel();
      const requestUrl = requestPanel?.dataset?.requestUrl;
      const hoursInput = root.querySelector('#info-request-duration-hours');
      const sentAtInput = root.querySelector('#info-request-sent-at');
      const selectedChannels = getInfoRequestChannels().filter((cb) => cb.checked).map((cb) => cb.value);
      const durationHours = parseInt(hoursInput?.value || '', 10);

      if (!Number.isInteger(durationHours) || durationHours <= 0) {
        alert('Укажите срок в целых часах больше нуля.');
        hoursInput?.focus();
        return;
      }
      if (!selectedChannels.length) {
        alert('Выберите хотя бы один способ отправки.');
        return;
      }
      if (!requestUrl) return;

      const formData = new FormData();
      checked.forEach((cb) => formData.append('performer_ids[]', cb.value));
      formData.append('duration_hours', String(durationHours));
      formData.append('request_sent_at', sentAtInput?.value || '');
      selectedChannels.forEach((value) => formData.append('delivery_channels[]', value));

      infoRequestBtn.disabled = true;
      try {
        const response = await fetch(requestUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось запросить согласование.');
        }

        window.__tableSel['info-request-select'] = [];
        window.__tableSel['performer-select'] = (window.__tableSel['performer-select'] || []);
        window.__tableSelLast = null;

        const modalEl = root.querySelector('#info-request-modal');
        const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
        modal?.hide();

        document.body.dispatchEvent(new Event('performers-updated'));
        document.body.dispatchEvent(new Event('notifications-updated'));
      } catch (err) {
        alert(err.message || 'Не удалось запросить согласование.');
        updateInfoRequestState();
      }
      return;
    }

    const wsConfirmBtn = e.target.closest('#create-workspace-confirm-btn');
    if (wsConfirmBtn && root.contains(wsConfirmBtn)) {
      const projectId = getSelectedInfoRequestProjectId();
      if (!projectId) {
        alert('Выберите проект в фильтре.');
        return;
      }
      const panel = getInfoRequestPanel();
      const wsUrl = panel?.dataset?.createWorkspaceUrl;
      if (!wsUrl) return;

      const statusEl = root.querySelector('#create-workspace-status');
      wsConfirmBtn.disabled = true;
      if (statusEl) statusEl.textContent = 'Создание папок…';

      try {
        const formData = new FormData();
        formData.append('project_id', projectId);

        const response = await fetch(wsUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось создать рабочее пространство.');
        }

        if (statusEl) statusEl.innerHTML = '<span class="text-success">' + (data.message || 'Готово!') + '</span>';

        const modalEl = root.querySelector('#create-workspace-modal');
        setTimeout(() => {
          const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
          modal?.hide();
          if (statusEl) statusEl.textContent = '';
        }, 2000);
      } catch (err) {
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">' + (err.message || 'Ошибка') + '</span>';
        else alert(err.message || 'Не удалось создать рабочее пространство.');
      } finally {
        wsConfirmBtn.disabled = false;
      }
      return;
    }

    const contractBtn = e.target.closest('#contract-request-btn');
    if (contractBtn && root.contains(contractBtn)) {
      const checked = getVisibleContractChecks().filter((cb) => cb.checked);
      if (!checked.length || contractBtn.disabled) return;

      const contractPanel = getContractRequestPanel();
      const requestUrl = contractPanel?.dataset?.requestUrl;
      const hoursInput = root.querySelector('#contract-duration-hours');
      const sentAtInput = root.querySelector('#contract-request-sent-at');
      const selectedChannels = getContractChannels().filter((cb) => cb.checked).map((cb) => cb.value);
      const durationHours = parseInt(hoursInput?.value || '', 10);

      if (!Number.isInteger(durationHours) || durationHours <= 0) {
        alert('Укажите срок в целых часах больше нуля.');
        hoursInput?.focus();
        return;
      }
      if (!selectedChannels.length) {
        alert('Выберите хотя бы один способ отправки.');
        return;
      }
      if (!requestUrl) return;

      const formData = new FormData();
      checked.forEach((cb) => formData.append('performer_ids[]', cb.value));
      formData.append('duration_hours', String(durationHours));
      formData.append('request_sent_at', sentAtInput?.value || '');
      selectedChannels.forEach((value) => formData.append('delivery_channels[]', value));

      contractBtn.disabled = true;
      try {
        const response = await fetch(requestUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось отправить проект договора.');
        }

        window.__tableSel['contract-select'] = [];
        window.__tableSel['performer-select'] = (window.__tableSel['performer-select'] || []);
        window.__tableSelLast = null;

        const modalEl = root.querySelector('#contract-request-modal');
        const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
        modal?.hide();

        document.body.dispatchEvent(new Event('performers-updated'));
        document.body.dispatchEvent(new Event('notifications-updated'));
        document.body.dispatchEvent(new Event('contracts-updated'));
      } catch (err) {
        alert(err.message || 'Не удалось отправить проект договора.');
        updateContractState();
      }
      return;
    }

    const requestBtn = e.target.closest('#participation-request-btn');
    if (requestBtn && root.contains(requestBtn)) {
      const checked = getVisibleParticipationChecks().filter((cb) => cb.checked);
      if (!checked.length || requestBtn.disabled) return;

      const requestPanel = getParticipationRequestPanel();
      const requestUrl = requestPanel?.dataset?.requestUrl;
      const hoursInput = root.querySelector('#participation-duration-hours');
      const sentAtInput = root.querySelector('#participation-request-sent-at');
      const selectedChannels = getParticipationChannels().filter((cb) => cb.checked).map((cb) => cb.value);
      const durationHours = parseInt(hoursInput?.value || '', 10);

      if (!Number.isInteger(durationHours) || durationHours <= 0) {
        alert('Укажите срок в целых часах больше нуля.');
        hoursInput?.focus();
        return;
      }
      if (!selectedChannels.length) {
        alert('Выберите хотя бы один способ отправки.');
        return;
      }
      if (!requestUrl) return;

      const formData = new FormData();
      checked.forEach((cb) => formData.append('performer_ids[]', cb.value));
      formData.append('duration_hours', String(durationHours));
      formData.append('request_sent_at', sentAtInput?.value || '');
      selectedChannels.forEach((value) => formData.append('delivery_channels[]', value));

      requestBtn.disabled = true;
      try {
        const response = await fetch(requestUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data?.error || 'Не удалось запросить подтверждение.');
        }

        window.__tableSel['participation-select'] = [];
        window.__tableSel['performer-select'] = (window.__tableSel['performer-select'] || []);
        window.__tableSelLast = null;

        const modalEl = root.querySelector('#participation-request-modal');
        const modal = modalEl ? window.bootstrap?.Modal.getInstance(modalEl) : null;
        modal?.hide();

        document.body.dispatchEvent(new Event('performers-updated'));
        document.body.dispatchEvent(new Event('notifications-updated'));
      } catch (err) {
        alert(err.message || 'Не удалось запросить подтверждение.');
        updateParticipationState();
      }
      return;
    }

    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    const action = btn.dataset.panelAction; // up|down|edit|delete
    const checked = getChecked('performer-select');
    if (!checked.length) return;

    // кеш выбора
    window.__tableSel['performer-select'] = checked.map(ch => String(ch.value));
    window.__tableSelLast = 'performer-select';

    if (action === 'edit') {
      const tr = checked[0].closest('tr');
      const url = tr?.dataset?.editUrl;
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#performers-modal .modal-content', swap: 'innerHTML' });
      ensurePerformerActionsVisibility();
      return;
    }

    if (action === 'delete') {
      if (!confirm(`Удалить ${checked.length} строк(у/и)?`)) return;
      const urls = checked.map(ch => ch.closest('tr')?.dataset?.deleteUrl).filter(Boolean);
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#performers-pane', swap: 'innerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
        }
      }
      return;
    }

    if (action === 'up' || action === 'down') {
      let urls = checked
        .map(ch => ch.closest('tr')?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'])
        .filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#performers-pane', swap: 'innerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
        }
      }
      ensurePerformerActionsVisibility();
    }
  });

  // мастер-чекбокс
  document.addEventListener('change', (e) => {
    const root = pane(); if (!root) return;

    const master = e.target.closest('input.form-check-input[data-actions-id="performers-actions"]');
    if (master && root.contains(master)) {
      getRowChecks('performer-select').forEach(b => { b.checked = master.checked; });
      master.indeterminate = false;
      updatePerformerMasterState();
      updateRowHighlight('performer-select');
      ensurePerformerActionsVisibility();
      return;
    }

    const participationMaster = e.target.closest('#participation-master');
    if (participationMaster && root.contains(participationMaster)) {
      getParticipationRows().forEach((row) => {
        if (row.classList.contains('d-none')) return;
        const checkbox = row.querySelector('input[name="participation-select"]');
        if (!checkbox || checkbox.disabled) return;
        if (checkbox) checkbox.checked = participationMaster.checked;
      });
      participationMaster.indeterminate = false;
      updateParticipationState();
      return;
    }

    const rowCb = e.target.closest('tbody input.form-check-input[name="performer-select"]');
    if (rowCb && root.contains(rowCb)) {
      updatePerformerMasterState();
      updateRowHighlight('performer-select');
      ensurePerformerActionsVisibility();
      return;
    }

    const participationRowCb = e.target.closest('tbody input.form-check-input[name="participation-select"]');
    if (participationRowCb && root.contains(participationRowCb)) {
      propagateGroupCheck(participationRowCb, 'participation-select');
      updateParticipationState();
      return;
    }

    const participationChannelCb = e.target.closest('.js-participation-channel');
    if (participationChannelCb && root.contains(participationChannelCb)) {
      const checkedChannels = getParticipationChannels().filter((cb) => cb.checked);
      if (!checkedChannels.length) {
        participationChannelCb.checked = true;
      }
    }

    const contractMaster = e.target.closest('#contract-master');
    if (contractMaster && root.contains(contractMaster)) {
      getContractRows().forEach((row) => {
        if (row.classList.contains('d-none')) return;
        const checkbox = row.querySelector('input[name="contract-select"]');
        if (!checkbox || checkbox.disabled) return;
        checkbox.checked = contractMaster.checked;
      });
      contractMaster.indeterminate = false;
      updateContractState();
      return;
    }

    const contractRowCb = e.target.closest('tbody input.form-check-input[name="contract-select"]');
    if (contractRowCb && root.contains(contractRowCb)) {
      propagateGroupCheck(contractRowCb, 'contract-select');
      updateContractState();
      return;
    }

    const contractChannelCb = e.target.closest('.js-contract-channel');
    if (contractChannelCb && root.contains(contractChannelCb)) {
      const checkedChannels = getContractChannels().filter((cb) => cb.checked);
      if (!checkedChannels.length) {
        contractChannelCb.checked = true;
      }
    }

    const infoRequestMaster = e.target.closest('#info-request-master');
    if (infoRequestMaster && root.contains(infoRequestMaster)) {
      getInfoRequestRows().forEach((row) => {
        if (row.classList.contains('d-none')) return;
        const checkbox = row.querySelector('input[name="info-request-select"]');
        if (!checkbox || checkbox.disabled) return;
        checkbox.checked = infoRequestMaster.checked;
      });
      infoRequestMaster.indeterminate = false;
      updateInfoRequestState();
      return;
    }

    const infoRequestRowCb = e.target.closest('tbody input.form-check-input[name="info-request-select"]');
    if (infoRequestRowCb && root.contains(infoRequestRowCb)) {
      propagateGroupCheck(infoRequestRowCb, 'info-request-select');
      updateInfoRequestState();
      return;
    }

    const infoRequestChannelCb = e.target.closest('.js-info-request-channel');
    if (infoRequestChannelCb && root.contains(infoRequestChannelCb)) {
      const checkedChannels = getInfoRequestChannels().filter((cb) => cb.checked);
      if (!checkedChannels.length) {
        infoRequestChannelCb.checked = true;
      }
    }
  });

  function restorePerformersPane(root) {
    var performerIds = (window.__tableSel && window.__tableSel['performer-select']) || [];
    var performerSet = new Set(performerIds || []);
    getRowChecks('performer-select').forEach(function(b) { b.checked = performerSet.has(String(b.value)); });
    updatePerformerMasterState();
    updateRowHighlight('performer-select');
    ensurePerformerActionsVisibility();
    try { delete window.__tableSel['performer-select']; } catch(_) {}

    var participationIds = (window.__tableSel && window.__tableSel['participation-select']) || [];
    var participationSet = new Set(participationIds || []);
    getRowChecks('participation-select').forEach(function(b) { b.checked = participationSet.has(String(b.value)); });
    initParticipationProjectFilter();
    updateParticipationState();
    try { delete window.__tableSel['participation-select']; } catch(_) {}

    var contractIds = (window.__tableSel && window.__tableSel['contract-select']) || [];
    var contractSet = new Set(contractIds || []);
    getRowChecks('contract-select').forEach(function(b) { b.checked = contractSet.has(String(b.value)); });
    initContractProjectFilter();
    updateContractState();
    try { delete window.__tableSel['contract-select']; } catch(_) {}

    var infoRequestIds = (window.__tableSel && window.__tableSel['info-request-select']) || [];
    var infoRequestSet = new Set(infoRequestIds || []);
    getRowChecks('info-request-select').forEach(function(b) { b.checked = infoRequestSet.has(String(b.value)); });
    initInfoRequestProjectFilter();
    updateInfoRequestState();
    try { delete window.__tableSel['info-request-select']; } catch(_) {}

    applyRowGrouping(root.querySelector('#participation-confirmation-section'));
    applyRowGrouping(root.querySelector('#contract-conclusion-section'));
    applyRowGrouping(root.querySelector('#info-request-approval-section'));

    window.__tableSelLast = null;
  }

  document.body.addEventListener('htmx:afterSwap', function (e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    restorePerformersPane(root);
  });

  document.addEventListener('DOMContentLoaded', () => {
    initParticipationProjectFilter();
    initContractProjectFilter();
    initInfoRequestProjectFilter();
    var root = pane();
    if (root) {
      applyRowGrouping(root.querySelector('#participation-confirmation-section'));
      applyRowGrouping(root.querySelector('#contract-conclusion-section'));
      applyRowGrouping(root.querySelector('#info-request-approval-section'));
    }
  });
})();