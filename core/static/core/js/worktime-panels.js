(function () {
  if (window.__worktimePanelBound) return;
  window.__worktimePanelBound = true;

  function pane() { return document.getElementById('worktime-pane'); }
  function qa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function getRowChecks() {
    return qa('tbody input.form-check-input[name="worktime-row-select"]', pane());
  }

  function getChecked() {
    return getRowChecks().filter(function (box) { return box.checked; });
  }

  function updateRowHighlight() {
    getRowChecks().forEach(function (box) {
      var tr = box.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!box.checked);
    });
  }

  function updateMasterState() {
    var boxes = getRowChecks();
    var master = pane() && pane().querySelector('#worktime-master');
    if (!master) return;
    var checkedCount = boxes.filter(function (box) { return box.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function ensureActionsVisibility() {
    var actions = pane() && pane().querySelector('#worktime-actions');
    if (!actions) return;
    var anyChecked = getChecked().length > 0;
    actions.classList.toggle('d-none', !anyChecked);
    actions.classList.toggle('d-flex', anyChecked);
  }

  function updateEditBtn() {
    var root = pane();
    if (!root) return;
    var btn = root.querySelector('#worktime-edit-btn');
    if (!btn) return;
    btn.disabled = getChecked().length === 0;
  }

  function showWorktimeModal() {
    var modalEl = document.getElementById('worktime-modal');
    if (!modalEl || !window.bootstrap) return;
    var dlg = modalEl.querySelector('.modal-dialog');
    if (dlg) {
      dlg.classList.remove('modal-sm', 'modal-lg', 'modal-xl');
      var sizeEl = modalEl.querySelector('[data-modal-size]');
      if (sizeEl) dlg.classList.add('modal-' + sizeEl.dataset.modalSize);
    }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function openEditModal() {
    var checked = getChecked();
    if (!checked.length) return;
    var tr = checked[0].closest('tr');
    var url = tr && tr.dataset.editUrl;
    var target = document.querySelector('#worktime-modal .modal-content');
    if (!url || !target) return;
    htmx.ajax('GET', url, target).then(function () {
      showWorktimeModal();
    });
  }

  document.addEventListener('click', function (e) {
    var root = pane();
    if (!root) return;

    var editBtn = e.target.closest('#worktime-edit-btn');
    if (editBtn && root.contains(editBtn)) {
      openEditModal();
      return;
    }

    var actionBtn = e.target.closest('#worktime-actions [data-panel-action="edit"]');
    if (actionBtn && root.contains(actionBtn)) {
      openEditModal();
    }
  });

  document.addEventListener('change', function (e) {
    var root = pane();
    if (!root) return;

    var master = e.target.closest('#worktime-master');
    if (master && root.contains(master)) {
      getRowChecks().forEach(function (box) { box.checked = master.checked; });
      master.indeterminate = false;
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
      updateEditBtn();
      return;
    }

    var rowCb = e.target.closest('tbody input.form-check-input[name="worktime-row-select"]');
    if (rowCb && root.contains(rowCb)) {
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
      updateEditBtn();
    }
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    var root = pane();
    if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
    updateEditBtn();
  });

  document.addEventListener('DOMContentLoaded', function () {
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
    updateEditBtn();
  });
})();
