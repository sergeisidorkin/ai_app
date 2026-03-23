(function () {
  if (window.__performersPanelBound) return;
  window.__performersPanelBound = true;

  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;

  var P = window.UIPref;
  if (P) {
    window.__participationSectionCollapsed = P.get('perf:partSectionCollapsed', false);
    window.__participationAssetCollapsed = P.get('perf:partAssetCollapsed', false);
    window.__contractSectionCollapsed = P.get('perf:contrSectionCollapsed', false);
    window.__contractAssetCollapsed = P.get('perf:contrAssetCollapsed', false);
    window.__infoRequestSectionCollapsed = P.get('perf:irSectionCollapsed', false);
    window.__infoRequestAssetCollapsed = P.get('perf:irAssetCollapsed', false);
  }
  function saveCollapsePrefs() {
    if (!P) return;
    P.set('perf:partSectionCollapsed', !!window.__participationSectionCollapsed);
    P.set('perf:partAssetCollapsed', !!window.__participationAssetCollapsed);
    P.set('perf:contrSectionCollapsed', !!window.__contractSectionCollapsed);
    P.set('perf:contrAssetCollapsed', !!window.__contractAssetCollapsed);
    P.set('perf:irSectionCollapsed', !!window.__infoRequestSectionCollapsed);
    P.set('perf:irAssetCollapsed', !!window.__infoRequestAssetCollapsed);
  }

  function syncCollapseButtons() {
    var root = document.getElementById('performers-pane');
    if (!root) return;
    var pairs = [
      ['#participation-confirmation-section', '#participation-asset-toggle', window.__participationAssetCollapsed],
      ['#participation-confirmation-section', '#participation-section-toggle', window.__participationSectionCollapsed],
      ['#contract-conclusion-section', '#contract-asset-toggle', window.__contractAssetCollapsed],
      ['#contract-conclusion-section', '#contract-section-toggle', window.__contractSectionCollapsed],
      ['#info-request-approval-section', '#info-request-asset-toggle', window.__infoRequestAssetCollapsed],
      ['#info-request-approval-section', '#info-request-section-toggle', window.__infoRequestSectionCollapsed],
    ];
    pairs.forEach(function(p) {
      var section = root.querySelector(p[0]);
      if (!section) return;
      var btn = section.querySelector(p[1]);
      if (!btn) return;
      var active = !!p[2];
      btn.classList.toggle('active', active);
      var icon = btn.querySelector('i');
      if (icon) icon.className = active ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
    });
  }

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
  function isFilterHidden(row) {
    return row.classList.contains('d-none')
      && !row.classList.contains('section-collapsed')
      && !row.classList.contains('asset-collapsed');
  }
  function getVisibleParticipationChecks() {
    return getParticipationRows()
      .filter((row) => !isFilterHidden(row))
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
      .filter((row) => !isFilterHidden(row))
      .map((row) => row.querySelector('input[name="info-request-select"]'))
      .filter((checkbox) => checkbox && !checkbox.disabled);
  }
  function getCreateSourceDataBtn() {
    return pane()?.querySelector('#create-source-data-btn');
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

    const wsBtn = getCreateSourceDataBtn();
    if (wsBtn) wsBtn.disabled = !getSelectedInfoRequestProjectId();
  }

  function getContractMaster() {
    return pane()?.querySelector('#contract-master');
  }
  function getContractRequestBtn() {
    return pane()?.querySelector('#contract-request-btn');
  }
  function getCreateContractBtn() {
    return pane()?.querySelector('#create-contract-btn');
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
      .filter((row) => !isFilterHidden(row))
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

    const createBtn = getCreateContractBtn();
    if (createBtn) createBtn.disabled = checkedCount === 0;

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
      if (isFilterHidden(row)) return;
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

  function applyParticipationSentState() {
    var root = pane();
    var section = root ? root.querySelector('#participation-confirmation-section') : null;
    if (!section) return;
    var tbody = section.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    rows.forEach(function(row) {
      var cb = row.querySelector('input[name="participation-select"]');
      if (cb && cb.dataset.requestSent === '1') {
        cb.disabled = true;
        cb.title = 'Запрос уже отправлен';
      }
    });
    var i = 0;
    while (i < rows.length) {
      if (rows[i].classList.contains('d-none') || !rows[i].classList.contains('group-first')) { i++; continue; }
      var group = [rows[i]];
      var j = i + 1;
      while (j < rows.length && rows[j].classList.contains('group-cont')) {
        group.push(rows[j]);
        j++;
      }
      var hasUnsent = group.some(function(r) {
        var cb = r.querySelector('input[name="participation-select"]');
        return cb && cb.dataset.requestSent !== '1';
      });
      var firstCb = group[0].querySelector('input[name="participation-select"]');
      if (firstCb && firstCb.disabled && hasUnsent) {
        firstCb.disabled = false;
        firstCb.title = '';
      }
      i = j;
    }
  }

  function pluralSections(n) {
    var mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return n + ' раздел';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return n + ' раздела';
    return n + ' разделов';
  }

  function restoreParticipationSectionText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__participationProjectFilter || ['__all__'];
    var showAll = !filterValues.length || filterValues.indexOf('__all__') !== -1;
    rows.forEach(function(row) {
      var td = row.querySelector('.cell-typical-val');
      if (td && td.dataset.originalTypical !== undefined) {
        td.innerHTML = td.dataset.originalTypical;
        delete td.dataset.originalTypical;
      }
      if (row.classList.contains('section-collapsed')) {
        row.classList.remove('section-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function collapseParticipationSections(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var currentFirst = null;
    var currentCount = 0;
    function finishGroup() {
      if (!currentFirst) return;
      var td = currentFirst.querySelector('.cell-typical-val');
      if (td) {
        td.dataset.originalTypical = td.innerHTML;
        td.textContent = pluralSections(currentCount);
      }
    }
    rows.forEach(function(row) {
      if (row.classList.contains('d-none')) return;
      if (!row.classList.contains('asset-cont')) {
        finishGroup();
        currentFirst = row;
        currentCount = 1;
      } else {
        currentCount++;
        row.classList.add('d-none', 'section-collapsed');
      }
    });
    finishGroup();
    applyRowGrouping(sectionEl);
  }

  function expandParticipationSections(sectionEl) {
    restoreParticipationSectionText(sectionEl);
    applyRowGrouping(sectionEl);
  }

  function reapplyParticipationCollapse() {
    if (!window.__participationSectionCollapsed && !window.__participationAssetCollapsed) return;
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#participation-confirmation-section');
    if (!section) return;
    restoreParticipationAssetText(section);
    restoreParticipationSectionText(section);
    applyRowGrouping(section);
    if (window.__participationAssetCollapsed) {
      collapseParticipationAssets(section);
      var assetToggle = section.querySelector('#participation-asset-toggle');
      if (assetToggle) {
        assetToggle.classList.add('active');
        var aIcon = assetToggle.querySelector('i');
        if (aIcon) aIcon.className = 'bi bi-arrows-expand';
      }
    } else if (window.__participationSectionCollapsed) {
      collapseParticipationSections(section);
      var sectionToggle = section.querySelector('#participation-section-toggle');
      if (sectionToggle) {
        sectionToggle.classList.add('active');
        var sIcon = sectionToggle.querySelector('i');
        if (sIcon) sIcon.className = 'bi bi-arrows-expand';
      }
    }
  }

  function toggleParticipationCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#participation-confirmation-section');
    if (!section) return;
    var toggle = section.querySelector('#participation-section-toggle');
    var collapsed = !!window.__participationSectionCollapsed;
    if (window.__participationAssetCollapsed) {
      window.__participationSectionCollapsed = !collapsed;
      if (toggle) {
        toggle.classList.toggle('active', !collapsed);
        var icon = toggle.querySelector('i');
        if (icon) icon.className = !collapsed ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
      }
      saveCollapsePrefs();
      return;
    }
    if (collapsed) {
      expandParticipationSections(section);
      window.__participationSectionCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
    } else {
      collapseParticipationSections(section);
      window.__participationSectionCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    applyParticipationSentState();
    updateParticipationState();
    saveCollapsePrefs();
  }

  function pluralAssets(n) {
    var mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return n + ' актив';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return n + ' актива';
    return n + ' активов';
  }

  function restoreParticipationAssetText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__participationProjectFilter || ['__all__'];
    var showAll = !filterValues.length || filterValues.indexOf('__all__') !== -1;
    rows.forEach(function(row) {
      var assetTd = row.querySelector('.cell-asset-val');
      if (assetTd && assetTd.dataset.originalAsset !== undefined) {
        assetTd.innerHTML = assetTd.dataset.originalAsset;
        delete assetTd.dataset.originalAsset;
      }
      var typicalTd = row.querySelector('.cell-typical-val');
      if (typicalTd && typicalTd.dataset.originalTypicalAsset !== undefined) {
        typicalTd.innerHTML = typicalTd.dataset.originalTypicalAsset;
        delete typicalTd.dataset.originalTypicalAsset;
      }
      if (row.classList.contains('asset-collapsed')) {
        row.classList.remove('asset-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function collapseParticipationAssets(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var i = 0;
    while (i < rows.length) {
      var row = rows[i];
      if (row.classList.contains('d-none') || !row.classList.contains('group-first')) { i++; continue; }
      var groupRows = [row];
      var j = i + 1;
      while (j < rows.length && !rows[j].classList.contains('group-first')) {
        groupRows.push(rows[j]);
        j++;
      }
      var assetSet = new Set();
      var totalSections = 0;
      groupRows.forEach(function(r) {
        if (r.classList.contains('d-none')) return;
        assetSet.add(r.dataset.assetName || '');
        totalSections++;
      });
      for (var k = 1; k < groupRows.length; k++) {
        if (!groupRows[k].classList.contains('d-none')) {
          groupRows[k].classList.add('d-none', 'asset-collapsed');
        }
      }
      var assetTd = row.querySelector('.cell-asset-val');
      if (assetTd) {
        assetTd.dataset.originalAsset = assetTd.innerHTML;
        assetTd.textContent = pluralAssets(assetSet.size);
      }
      var typicalTd = row.querySelector('.cell-typical-val');
      if (typicalTd) {
        typicalTd.dataset.originalTypicalAsset = typicalTd.innerHTML;
        typicalTd.textContent = pluralSections(totalSections);
      }
      i = j;
    }
    applyRowGrouping(sectionEl);
  }

  function toggleParticipationAssetCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#participation-confirmation-section');
    if (!section) return;
    var toggle = section.querySelector('#participation-asset-toggle');
    var collapsed = !!window.__participationAssetCollapsed;
    if (collapsed) {
      restoreParticipationAssetText(section);
      applyRowGrouping(section);
      window.__participationAssetCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
      if (window.__participationSectionCollapsed) {
        collapseParticipationSections(section);
        var sectionToggle = section.querySelector('#participation-section-toggle');
        if (sectionToggle) {
          sectionToggle.classList.add('active');
          var sIcon = sectionToggle.querySelector('i');
          if (sIcon) sIcon.className = 'bi bi-arrows-expand';
        }
      }
    } else {
      if (window.__participationSectionCollapsed) {
        restoreParticipationSectionText(section);
        applyRowGrouping(section);
      }
      collapseParticipationAssets(section);
      window.__participationAssetCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    applyParticipationSentState();
    updateParticipationState();
    saveCollapsePrefs();
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
      reapplyContractCollapse();
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

    window.__syncContractProjectFilter = function(values) {
      var isAll = values[0] === FILTER_ALL;
      var isSingle = !isAll && values.length === 1;
      var set = new Set(values);
      checks.forEach(function(cb) {
        if (isAll) { cb.checked = cb.value === FILTER_ALL; cb.disabled = false; }
        else if (isSingle) { cb.checked = cb.value === values[0]; cb.disabled = true; }
        else {
          if (cb.value === FILTER_ALL) { cb.checked = true; cb.disabled = false; }
          else { cb.checked = set.has(cb.value); cb.disabled = !set.has(cb.value); }
        }
      });
      applyFilter(isAll ? [FILTER_ALL] : values.slice());
    };

    const initialValues = window.__contractProjectFilter && window.__contractProjectFilter.length
      ? window.__contractProjectFilter
      : [FILTER_ALL];
    syncCheckboxes(initialValues);
    applyFilter(initialValues);
  }

  function restoreContractSectionText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__contractProjectFilter || ['__all__'];
    var showAll = !filterValues.length || filterValues.indexOf('__all__') !== -1;
    rows.forEach(function(row) {
      var td = row.querySelector('.cell-typical-val');
      if (td && td.dataset.originalTypical !== undefined) {
        td.innerHTML = td.dataset.originalTypical;
        delete td.dataset.originalTypical;
      }
      if (row.classList.contains('section-collapsed')) {
        row.classList.remove('section-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function restoreContractAssetText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__contractProjectFilter || ['__all__'];
    var showAll = !filterValues.length || filterValues.indexOf('__all__') !== -1;
    rows.forEach(function(row) {
      var assetTd = row.querySelector('.cell-asset-val');
      if (assetTd && assetTd.dataset.originalAsset !== undefined) {
        assetTd.innerHTML = assetTd.dataset.originalAsset;
        delete assetTd.dataset.originalAsset;
      }
      var typicalTd = row.querySelector('.cell-typical-val');
      if (typicalTd && typicalTd.dataset.originalTypicalAsset !== undefined) {
        typicalTd.innerHTML = typicalTd.dataset.originalTypicalAsset;
        delete typicalTd.dataset.originalTypicalAsset;
      }
      if (row.classList.contains('asset-collapsed')) {
        row.classList.remove('asset-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function reapplyContractCollapse() {
    if (!window.__contractSectionCollapsed && !window.__contractAssetCollapsed) return;
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#contract-conclusion-section');
    if (!section) return;
    restoreContractAssetText(section);
    restoreContractSectionText(section);
    applyRowGrouping(section);
    if (window.__contractAssetCollapsed) {
      collapseParticipationAssets(section);
      var assetToggle = section.querySelector('#contract-asset-toggle');
      if (assetToggle) {
        assetToggle.classList.add('active');
        var aIcon = assetToggle.querySelector('i');
        if (aIcon) aIcon.className = 'bi bi-arrows-expand';
      }
    } else if (window.__contractSectionCollapsed) {
      collapseParticipationSections(section);
      var sectionToggle = section.querySelector('#contract-section-toggle');
      if (sectionToggle) {
        sectionToggle.classList.add('active');
        var sIcon = sectionToggle.querySelector('i');
        if (sIcon) sIcon.className = 'bi bi-arrows-expand';
      }
    }
  }

  function toggleContractCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#contract-conclusion-section');
    if (!section) return;
    var toggle = section.querySelector('#contract-section-toggle');
    var collapsed = !!window.__contractSectionCollapsed;
    if (window.__contractAssetCollapsed) {
      window.__contractSectionCollapsed = !collapsed;
      if (toggle) {
        toggle.classList.toggle('active', !collapsed);
        var icon = toggle.querySelector('i');
        if (icon) icon.className = !collapsed ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
      }
      saveCollapsePrefs();
      return;
    }
    if (collapsed) {
      restoreContractSectionText(section);
      applyRowGrouping(section);
      window.__contractSectionCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
    } else {
      collapseParticipationSections(section);
      window.__contractSectionCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    updateContractState();
    saveCollapsePrefs();
  }

  function toggleContractAssetCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#contract-conclusion-section');
    if (!section) return;
    var toggle = section.querySelector('#contract-asset-toggle');
    var collapsed = !!window.__contractAssetCollapsed;
    if (collapsed) {
      restoreContractAssetText(section);
      applyRowGrouping(section);
      window.__contractAssetCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
      if (window.__contractSectionCollapsed) {
        collapseParticipationSections(section);
        var sectionToggle = section.querySelector('#contract-section-toggle');
        if (sectionToggle) {
          sectionToggle.classList.add('active');
          var sIcon = sectionToggle.querySelector('i');
          if (sIcon) sIcon.className = 'bi bi-arrows-expand';
        }
      }
    } else {
      if (window.__contractSectionCollapsed) {
        restoreContractSectionText(section);
        applyRowGrouping(section);
      }
      collapseParticipationAssets(section);
      window.__contractAssetCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    updateContractState();
    saveCollapsePrefs();
  }

  function restoreInfoRequestSectionText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__infoRequestProjectFilter || [];
    var showAll = !filterValues.length || (filterValues.length === 1 && filterValues[0] === '');
    rows.forEach(function(row) {
      var td = row.querySelector('.cell-typical-val');
      if (td && td.dataset.originalTypical !== undefined) {
        td.innerHTML = td.dataset.originalTypical;
        delete td.dataset.originalTypical;
      }
      if (row.classList.contains('section-collapsed')) {
        row.classList.remove('section-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function restoreInfoRequestAssetText(sectionEl) {
    if (!sectionEl) return;
    var tbody = sectionEl.querySelector('table.performers-table tbody');
    if (!tbody) return;
    var rows = Array.from(tbody.querySelectorAll('tr[data-project-id]'));
    var filterValues = window.__infoRequestProjectFilter || [];
    var showAll = !filterValues.length || (filterValues.length === 1 && filterValues[0] === '');
    rows.forEach(function(row) {
      var assetTd = row.querySelector('.cell-asset-val');
      if (assetTd && assetTd.dataset.originalAsset !== undefined) {
        assetTd.innerHTML = assetTd.dataset.originalAsset;
        delete assetTd.dataset.originalAsset;
      }
      var typicalTd = row.querySelector('.cell-typical-val');
      if (typicalTd && typicalTd.dataset.originalTypicalAsset !== undefined) {
        typicalTd.innerHTML = typicalTd.dataset.originalTypicalAsset;
        delete typicalTd.dataset.originalTypicalAsset;
      }
      if (row.classList.contains('asset-collapsed')) {
        row.classList.remove('asset-collapsed');
        var pid = row.dataset.projectId || '';
        if (showAll || filterValues.indexOf(pid) !== -1) {
          row.classList.remove('d-none');
        }
      }
    });
  }

  function reapplyInfoRequestCollapse() {
    if (!window.__infoRequestSectionCollapsed && !window.__infoRequestAssetCollapsed) return;
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#info-request-approval-section');
    if (!section) return;
    restoreInfoRequestAssetText(section);
    restoreInfoRequestSectionText(section);
    applyRowGrouping(section);
    if (window.__infoRequestAssetCollapsed) {
      collapseParticipationAssets(section);
      var assetToggle = section.querySelector('#info-request-asset-toggle');
      if (assetToggle) {
        assetToggle.classList.add('active');
        var aIcon = assetToggle.querySelector('i');
        if (aIcon) aIcon.className = 'bi bi-arrows-expand';
      }
    } else if (window.__infoRequestSectionCollapsed) {
      collapseParticipationSections(section);
      var sectionToggle = section.querySelector('#info-request-section-toggle');
      if (sectionToggle) {
        sectionToggle.classList.add('active');
        var sIcon = sectionToggle.querySelector('i');
        if (sIcon) sIcon.className = 'bi bi-arrows-expand';
      }
    }
  }

  function toggleInfoRequestCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#info-request-approval-section');
    if (!section) return;
    var toggle = section.querySelector('#info-request-section-toggle');
    var collapsed = !!window.__infoRequestSectionCollapsed;
    if (window.__infoRequestAssetCollapsed) {
      window.__infoRequestSectionCollapsed = !collapsed;
      if (toggle) {
        toggle.classList.toggle('active', !collapsed);
        var icon = toggle.querySelector('i');
        if (icon) icon.className = !collapsed ? 'bi bi-arrows-expand' : 'bi bi-arrows-collapse';
      }
      saveCollapsePrefs();
      return;
    }
    if (collapsed) {
      restoreInfoRequestSectionText(section);
      applyRowGrouping(section);
      window.__infoRequestSectionCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
    } else {
      collapseParticipationSections(section);
      window.__infoRequestSectionCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    updateInfoRequestState();
    saveCollapsePrefs();
  }

  function toggleInfoRequestAssetCollapse() {
    var root = pane();
    if (!root) return;
    var section = root.querySelector('#info-request-approval-section');
    if (!section) return;
    var toggle = section.querySelector('#info-request-asset-toggle');
    var collapsed = !!window.__infoRequestAssetCollapsed;
    if (collapsed) {
      restoreInfoRequestAssetText(section);
      applyRowGrouping(section);
      window.__infoRequestAssetCollapsed = false;
      if (toggle) {
        toggle.classList.remove('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-collapse';
      }
      if (window.__infoRequestSectionCollapsed) {
        collapseParticipationSections(section);
        var sectionToggle = section.querySelector('#info-request-section-toggle');
        if (sectionToggle) {
          sectionToggle.classList.add('active');
          var sIcon = sectionToggle.querySelector('i');
          if (sIcon) sIcon.className = 'bi bi-arrows-expand';
        }
      }
    } else {
      if (window.__infoRequestSectionCollapsed) {
        restoreInfoRequestSectionText(section);
        applyRowGrouping(section);
      }
      collapseParticipationAssets(section);
      window.__infoRequestAssetCollapsed = true;
      if (toggle) {
        toggle.classList.add('active');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-arrows-expand';
      }
    }
    updateInfoRequestState();
    saveCollapsePrefs();
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
      applyParticipationSentState();
      reapplyParticipationCollapse();
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

    window.__syncParticipationProjectFilter = function(values) {
      var isAll = values[0] === FILTER_ALL;
      var isSingle = !isAll && values.length === 1;
      var set = new Set(values);
      checks.forEach(function(cb) {
        if (isAll) { cb.checked = cb.value === FILTER_ALL; cb.disabled = false; }
        else if (isSingle) { cb.checked = cb.value === values[0]; cb.disabled = true; }
        else {
          if (cb.value === FILTER_ALL) { cb.checked = true; cb.disabled = false; }
          else { cb.checked = set.has(cb.value); cb.disabled = !set.has(cb.value); }
        }
      });
      applyFilter(isAll ? [FILTER_ALL] : values.slice());
    };

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
      reapplyInfoRequestCollapse();
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

    var sectionToggle = e.target.closest('#participation-section-toggle');
    if (sectionToggle && root.contains(sectionToggle)) {
      toggleParticipationCollapse();
      return;
    }

    var assetToggle = e.target.closest('#participation-asset-toggle');
    if (assetToggle && root.contains(assetToggle)) {
      toggleParticipationAssetCollapse();
      return;
    }

    var contractSectionToggle = e.target.closest('#contract-section-toggle');
    if (contractSectionToggle && root.contains(contractSectionToggle)) {
      toggleContractCollapse();
      return;
    }

    var contractAssetToggle = e.target.closest('#contract-asset-toggle');
    if (contractAssetToggle && root.contains(contractAssetToggle)) {
      toggleContractAssetCollapse();
      return;
    }

    var irSectionToggle = e.target.closest('#info-request-section-toggle');
    if (irSectionToggle && root.contains(irSectionToggle)) {
      toggleInfoRequestCollapse();
      return;
    }

    var irAssetToggle = e.target.closest('#info-request-asset-toggle');
    if (irAssetToggle && root.contains(irAssetToggle)) {
      toggleInfoRequestAssetCollapse();
      return;
    }

    const quickEdit = e.target.closest('.performer-quick-edit');
    if (quickEdit && root.contains(quickEdit)) {
      const tr = quickEdit.closest('tr');
      if (!tr) return;
      const url = tr.dataset.editUrl;
      if (!url) return;

      getRowChecks('performer-select').forEach(b => { b.checked = false; });
      const cb = tr.querySelector('input[name="performer-select"]');
      if (cb) cb.checked = true;

      window.__tableSel['performer-select'] = cb ? [String(cb.value)] : [];
      window.__tableSelLast = 'performer-select';

      updatePerformerMasterState();
      updateRowHighlight('performer-select');
      ensurePerformerActionsVisibility();

      await htmx.ajax('GET', url, { target: '#performers-modal .modal-content', swap: 'innerHTML' });
      return;
    }

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

    const sdConfirmBtn = e.target.closest('#source-data-confirm-btn');
    if (sdConfirmBtn && root.contains(sdConfirmBtn)) {
      const projectId = getSelectedInfoRequestProjectId();
      if (!projectId) {
        alert('Выберите проект в фильтре.');
        return;
      }
      const panel = getInfoRequestPanel();
      const sdUrl = panel?.dataset?.createSourceDataUrl;
      if (!sdUrl) return;

      const statusEl = root.querySelector('#source-data-status');
      const progressEl = root.querySelector('#source-data-progress');
      const fillEl = progressEl?.querySelector('.ws-progress-fill');
      sdConfirmBtn.disabled = true;
      if (statusEl) statusEl.textContent = '';
      if (fillEl) fillEl.style.width = '0%';
      if (progressEl) progressEl.classList.remove('d-none');

      try {
        const formData = new FormData();
        formData.append('project_id', projectId);

        const response = await fetch(sdUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });

        if (!response.ok && !response.body) {
          throw new Error('Не удалось создать пространство исходных данных.');
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
          throw new Error(lastResult?.error || 'Не удалось создать пространство исходных данных.');
        }

        if (fillEl) fillEl.style.width = '100%';
        if (statusEl) statusEl.innerHTML = '<span class="text-success">' + (lastResult.message || 'Готово!') + '</span>';
      } catch (err) {
        if (progressEl) progressEl.classList.add('d-none');
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">' + (err.message || 'Ошибка') + '</span>';
        else alert(err.message || 'Не удалось создать пространство исходных данных.');
      } finally {
        sdConfirmBtn.disabled = false;
      }
      return;
    }

    const createContractConfirm = e.target.closest('#create-contract-confirm-btn');
    if (createContractConfirm && root.contains(createContractConfirm)) {
      const checked = getVisibleContractChecks().filter((cb) => cb.checked);
      if (!checked.length) return;

      const panel = getContractRequestPanel();
      const createUrl = panel?.dataset?.createContractUrl;
      if (!createUrl) return;

      const statusEl = root.querySelector('#create-contract-status');
      const progressEl = root.querySelector('#create-contract-progress');
      const fillEl = progressEl?.querySelector('.ws-progress-fill');
      createContractConfirm.disabled = true;
      if (statusEl) statusEl.textContent = '';
      if (fillEl) fillEl.style.width = '0%';
      if (progressEl) progressEl.classList.remove('d-none');

      const formData = new FormData();
      checked.forEach((cb) => formData.append('performer_ids[]', cb.value));

      try {
        const response = await fetch(createUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });

        if (!response.ok && !response.body) {
          throw new Error('Не удалось создать проект договора.');
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
          throw new Error(lastResult?.error || 'Не удалось создать проект договора.');
        }

        if (fillEl) fillEl.style.width = '100%';
        var resultHtml = '<span class="text-success">' + (lastResult.message || 'Готово!') + '</span>';
        if (lastResult.warnings && lastResult.warnings.length) {
          resultHtml += '<ul class="text-warning small mt-2 mb-0">';
          lastResult.warnings.forEach(function(w) {
            resultHtml += '<li>' + w.replace(/</g, '&lt;') + '</li>';
          });
          resultHtml += '</ul>';
        }
        if (statusEl) statusEl.innerHTML = resultHtml;

        window.__tableSel['contract-select'] = [];
        window.__tableSelLast = null;
        document.body.dispatchEvent(new Event('performers-updated'));
      } catch (err) {
        if (progressEl) progressEl.classList.add('d-none');
        if (statusEl) statusEl.innerHTML = '<span class="text-danger">' + (err.message || 'Ошибка') + '</span>';
        else alert(err.message || 'Не удалось создать проект договора.');
      } finally {
        createContractConfirm.disabled = false;
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
      const checked = getVisibleParticipationChecks().filter((cb) => cb.checked && cb.dataset.requestSent !== '1');
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

        const emailDelivery = data?.email_delivery;
        if (emailDelivery?.requested && emailDelivery?.failed > 0) {
          const errorLines = (emailDelivery.errors || [])
            .slice(0, 5)
            .map((item) => {
              const channelPrefix = item.channel_label ? `[${item.channel_label}] ` : '';
              return `- ${channelPrefix}${item.recipient}: ${item.error}`;
            });
          const moreCount = Math.max((emailDelivery.errors || []).length - errorLines.length, 0);
          const details = [
            `Не удалось отправить ${emailDelivery.failed} из ${emailDelivery.attempted} email-писем.`,
            ...errorLines,
          ];
          if (moreCount > 0) {
            details.push(`- И еще ${moreCount} ошибок.`);
          }
          alert(details.join('\n'));
        }

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
        if (isFilterHidden(row)) return;
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
        if (isFilterHidden(row)) return;
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
        if (isFilterHidden(row)) return;
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

  // ── Source-data settings modal (gear) ──

  function initSourceDataSettingsModal() {
    const modalEl = document.getElementById('source-data-settings-modal');
    if (!modalEl || modalEl.dataset.sdBound === '1') return;
    modalEl.dataset.sdBound = '1';

    modalEl.addEventListener('show.bs.modal', async () => {
      const panel = document.getElementById('info-request-actions');
      const url = panel?.dataset?.sourceDataTargetUrl;
      if (!url) return;

      const select = modalEl.querySelector('#source-data-target-select');
      if (!select) return;

      try {
        const resp = await fetch(url, { headers: { 'X-CSRFToken': csrftoken } });
        const data = await resp.json();
        select.innerHTML = '';
        (data.options || []).forEach((name) => {
          const opt = document.createElement('option');
          opt.value = name;
          opt.textContent = name;
          if (name === data.folder_name) opt.selected = true;
          select.appendChild(opt);
        });
      } catch (_) { /* ignore */ }
    });

    const saveBtn = modalEl.querySelector('#source-data-target-save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        const panel = document.getElementById('info-request-actions');
        const saveUrl = panel?.dataset?.sourceDataTargetSaveUrl;
        if (!saveUrl) return;

        const select = modalEl.querySelector('#source-data-target-select');
        const folderName = select?.value;
        if (!folderName) return;

        saveBtn.disabled = true;
        try {
          const resp = await fetch(saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ folder_name: folderName }),
          });
          const data = await resp.json();
          if (!data.ok) throw new Error(data.error || 'Ошибка сохранения');
          const modal = window.bootstrap?.Modal.getInstance(modalEl);
          modal?.hide();
        } catch (err) {
          alert(err.message || 'Не удалось сохранить.');
        } finally {
          saveBtn.disabled = false;
        }
      });
    }
  }
  initSourceDataSettingsModal();

  // ── Create-contract settings modal (gear) ──

  function initCreateContractSettingsModal() {
    const modalEl = document.getElementById('create-contract-modal');
    if (!modalEl || modalEl.dataset.ccBound === '1') return;
    modalEl.dataset.ccBound = '1';

    modalEl.addEventListener('show.bs.modal', async () => {
      const panel = document.getElementById('contract-request-actions');
      const url = panel?.dataset?.contractTargetUrl;
      if (!url) return;

      const select = modalEl.querySelector('#create-contract-target-select');
      if (!select) return;

      try {
        const resp = await fetch(url, { headers: { 'X-CSRFToken': csrftoken } });
        const data = await resp.json();
        select.innerHTML = '';
        (data.options || []).forEach((name) => {
          const opt = document.createElement('option');
          opt.value = name;
          opt.textContent = name;
          if (name === data.folder_name) opt.selected = true;
          select.appendChild(opt);
        });
      } catch (_) { /* ignore */ }
    });

    const saveBtn = modalEl.querySelector('#create-contract-target-save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', async () => {
        const panel = document.getElementById('contract-request-actions');
        const saveUrl = panel?.dataset?.contractTargetSaveUrl;
        if (!saveUrl) return;

        const select = modalEl.querySelector('#create-contract-target-select');
        const folderName = select?.value;
        if (!folderName) return;

        saveBtn.disabled = true;
        try {
          const resp = await fetch(saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ folder_name: folderName }),
          });
          const data = await resp.json();
          if (!data.ok) throw new Error(data.error || 'Ошибка сохранения');
          const modal = window.bootstrap?.Modal.getInstance(modalEl);
          modal?.hide();
        } catch (err) {
          alert(err.message || 'Не удалось сохранить.');
        } finally {
          saveBtn.disabled = false;
        }
      });
    }
  }
  initCreateContractSettingsModal();

  document.addEventListener('show.bs.modal', (e) => {
    if (!e.target.matches('#create-contract-progress-modal')) return;
    const progressEl = e.target.querySelector('#create-contract-progress');
    const fillEl = progressEl?.querySelector('.ws-progress-fill');
    const statusEl = e.target.querySelector('#create-contract-status');
    if (progressEl) progressEl.classList.add('d-none');
    if (fillEl) fillEl.style.width = '0%';
    if (statusEl) statusEl.textContent = '';
  });

  function restorePerformersPane(root) {
    // Re-apply main performers filter, labels and totals before the browser
    // paints to avoid a visible flash of unfiltered / empty-totals state.
    (function earlyRestore() {
      var FA = '__all__';
      var pf = window.__perfProjectFilter || [FA];
      var af = window.__perfAssetFilter || [FA];
      var allProj = !pf.length || pf.indexOf(FA) !== -1;
      var allAsset = !af.length || af.indexOf(FA) !== -1;

      var perfRows = root.querySelectorAll(
        '#performers-main-section table.performers-table tbody tr[data-project-id]'
      );

      if (!allProj || !allAsset) {
        perfRows.forEach(function(row) {
          var mp = allProj || pf.indexOf(row.dataset.projectId || '') !== -1;
          var ma = allAsset || af.indexOf(row.dataset.assetName || '') !== -1;
          if (!(mp && ma)) row.classList.add('d-none');
        });
      }
      if (typeof window.__enforceMasterOnRows === 'function') window.__enforceMasterOnRows();

      // --- filter labels ---
      var projLabel = root.querySelector('.js-perf-filter-label');
      if (projLabel) {
        if (allProj) {
          projLabel.textContent = 'Все';
        } else if (pf.length === 1) {
          var cb = root.querySelector('.js-perf-filter[value="' + CSS.escape(pf[0]) + '"]');
          projLabel.textContent = cb && cb.nextElementSibling
            ? cb.nextElementSibling.textContent.trim() : '1 проект';
        } else {
          projLabel.textContent = pf.length + ' выбрано';
        }
      }
      var assetLabel = root.querySelector('.js-perf-asset-label');
      if (assetLabel) {
        if (allAsset) assetLabel.textContent = 'Все';
        else if (af.length === 1) assetLabel.textContent = af[0];
        else assetLabel.textContent = af.length + ' выбрано';
      }

      // --- totals ---
      var sums = { actual: {}, estimated: {}, agreed: {} };
      perfRows.forEach(function(row) {
        if (row.classList.contains('d-none')) return;
        var a = row.querySelector('[data-sum-actual]');
        var e = row.querySelector('[data-sum-estimated]');
        var g = row.querySelector('[data-sum-agreed]');
        [['actual', a, 'sumActual'], ['estimated', e, 'sumEstimated'], ['agreed', g, 'sumAgreed']].forEach(function(t) {
          var cell = t[1];
          if (!cell) return;
          var val = parseFloat(cell.dataset[t[2]]) || 0;
          if (!val) return;
          var cur = cell.dataset.currency || '';
          if (!sums[t[0]][cur]) sums[t[0]][cur] = 0;
          sums[t[0]][cur] += val;
        });
      });
      function fmtT(n) {
        var p = n.toFixed(2).split('.');
        p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
        return p.join(',');
      }
      function renderS(obj) {
        var parts = [];
        for (var c in obj) {
          if (!obj[c]) continue;
          var s = fmtT(obj[c]);
          if (c) s += ' ' + c;
          parts.push(s);
        }
        return parts.join(', ');
      }
      var elA = root.querySelector('#perf-total-actual');
      var elE = root.querySelector('#perf-total-estimated');
      var elG = root.querySelector('#perf-total-agreed');
      if (elA) elA.textContent = renderS(sums.actual);
      if (elE) elE.textContent = renderS(sums.estimated);
      if (elG) elG.textContent = renderS(sums.agreed);
    })();

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
    initSourceDataSettingsModal();
    initCreateContractSettingsModal();
    try { delete window.__tableSel['info-request-select']; } catch(_) {}

    applyRowGrouping(root.querySelector('#participation-confirmation-section'));
    applyParticipationSentState();
    reapplyParticipationCollapse();
    applyRowGrouping(root.querySelector('#contract-conclusion-section'));
    reapplyContractCollapse();
    applyRowGrouping(root.querySelector('#info-request-approval-section'));
    reapplyInfoRequestCollapse();
    syncCollapseButtons();

    window.__tableSelLast = null;
  }

  document.body.addEventListener('htmx:beforeSwap', function (e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    window.__perfScrollY = window.scrollY;
  });

  document.body.addEventListener('htmx:afterSwap', function (e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    restorePerformersPane(root);
    if (typeof window.__perfScrollY === 'number') {
      window.scrollTo(0, window.__perfScrollY);
    }
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    ensurePerformerActionsVisibility();
    if (typeof window.__perfScrollY === 'number') {
      window.scrollTo(0, window.__perfScrollY);
      delete window.__perfScrollY;
    }
  });

  // ---- Prev / Next navigation inside performers modal ----

  function getVisiblePerfRows() {
    var root = pane();
    if (!root) return [];
    return Array.from(root.querySelectorAll(
      '#performers-main-section table.performers-table tbody tr[data-project-id]'
    )).filter(function(r) {
      if (r.classList.contains('d-none')) return false;
      var cb = r.querySelector('input[name="performer-select"]');
      return !cb || !cb.disabled;
    });
  }

  function findCurrentPerfIndex(rows) {
    var checked = getChecked('performer-select');
    if (!checked.length) return -1;
    var id = String(checked[0].value);
    for (var i = 0; i < rows.length; i++) {
      var cb = rows[i].querySelector('input[name="performer-select"]');
      if (cb && String(cb.value) === id) return i;
    }
    return -1;
  }

  function updatePerfNavButtons() {
    var modal = document.getElementById('performers-modal');
    if (!modal) return;
    var prevBtn = modal.querySelector('[data-perf-nav="prev"]');
    var nextBtn = modal.querySelector('[data-perf-nav="next"]');
    if (!prevBtn && !nextBtn) return;
    var rows = getVisiblePerfRows();
    var idx = findCurrentPerfIndex(rows);
    if (prevBtn) prevBtn.disabled = idx <= 0;
    if (nextBtn) nextBtn.disabled = idx < 0 || idx >= rows.length - 1;
  }

  document.body.addEventListener('htmx:afterSwap', function (e) {
    var modal = document.getElementById('performers-modal');
    if (!modal) return;
    var mc = modal.querySelector('.modal-content');
    if (mc && (e.target === mc || mc.contains(e.target))) updatePerfNavButtons();
  });

  function rawMoneyValue(v) {
    return String(v).replace(/\s/g, '').replace(/\u00a0/g, '').replace(',', '.');
  }

  function swapModalHtml(container, html) {
    container.innerHTML = html;
    Array.from(container.querySelectorAll('script')).forEach(function(old) {
      var s = document.createElement('script');
      Array.from(old.attributes).forEach(function(a) { s.setAttribute(a.name, a.value); });
      s.textContent = old.textContent;
      old.parentNode.replaceChild(s, old);
    });
    htmx.process(container);
  }

  document.addEventListener('click', async function (e) {
    var navBtn = e.target.closest('[data-perf-nav]');
    if (!navBtn) return;
    var modal = document.getElementById('performers-modal');
    if (!modal || !modal.contains(navBtn)) return;

    var direction = navBtn.dataset.perfNav;
    var rows = getVisiblePerfRows();
    var idx = findCurrentPerfIndex(rows);
    var targetIdx = direction === 'next' ? idx + 1 : idx - 1;
    if (targetIdx < 0 || targetIdx >= rows.length) return;

    var targetRow = rows[targetIdx];
    var targetUrl = targetRow.dataset.editUrl;
    var targetCb = targetRow.querySelector('input[name="performer-select"]');
    var targetId = targetCb ? String(targetCb.value) : null;
    if (!targetUrl || !targetId) return;

    var mc = modal.querySelector('.modal-content');
    var form = mc?.querySelector('form');
    var postUrl = form?.getAttribute('hx-post');

    if (form && postUrl) {
      navBtn.disabled = true;
      mc.querySelectorAll('.js-money-input').forEach(function(inp) {
        inp.value = rawMoneyValue(inp.value);
      });

      var formData = new FormData(form);

      try {
        var resp = await fetch(postUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken },
          body: formData,
        });

        if (resp.status === 204) {
          getRowChecks('performer-select').forEach(function(b) { b.checked = false; });
          if (targetCb) targetCb.checked = true;
          window.__tableSel['performer-select'] = [targetId];
          window.__tableSelLast = 'performer-select';
          updatePerformerMasterState();
          updateRowHighlight('performer-select');
          ensurePerformerActionsVisibility();

          var paneEl = document.getElementById('performers-pane');
          var paneUrl = paneEl?.getAttribute('hx-get');

          await htmx.ajax('GET', targetUrl, {
            target: '#performers-modal .modal-content', swap: 'innerHTML'
          });

          if (paneUrl) {
            htmx.ajax('GET', paneUrl, {
              target: '#performers-pane', swap: 'innerHTML'
            });
          }
        } else {
          var html = await resp.text();
          swapModalHtml(mc, html);
        }
      } catch (err) {
        console.error('perf-nav save error', err);
        navBtn.disabled = false;
      }
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    initParticipationProjectFilter();
    initContractProjectFilter();
    initInfoRequestProjectFilter();
    var root = pane();
    if (root) {
      applyRowGrouping(root.querySelector('#participation-confirmation-section'));
      applyParticipationSentState();
      reapplyParticipationCollapse();
      applyRowGrouping(root.querySelector('#contract-conclusion-section'));
      reapplyContractCollapse();
      applyRowGrouping(root.querySelector('#info-request-approval-section'));
      reapplyInfoRequestCollapse();
      syncCollapseButtons();
    }

    const perfModal = document.getElementById('performers-modal');
    if (perfModal) {
      perfModal.addEventListener('hidden.bs.modal', () => {
        window.__tableSel['performer-select'] = [];
        window.__tableSelLast = null;
        getRowChecks('performer-select').forEach(b => { b.checked = false; });
        updatePerformerMasterState();
        updateRowHighlight('performer-select');
        ensurePerformerActionsVisibility();
      });
    }
  });
})();