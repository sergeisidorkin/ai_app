(function () {
  if (window.__worktimePanelBound) return;
  window.__worktimePanelBound = true;

  function qa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }
  function panels() { return qa('[data-worktime-panel]'); }
  function panelFor(el) { return el && el.closest('[data-worktime-panel]'); }

  function getRowChecks(root) {
    return qa('tbody input.form-check-input[name="worktime-row-select"]', root);
  }

  function getChecked(root) {
    return getRowChecks(root).filter(function (box) { return box.checked; });
  }

  function updateRowHighlight(root) {
    getRowChecks(root).forEach(function (box) {
      var tr = box.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!box.checked);
    });
  }

  function updateMasterState(root) {
    var boxes = getRowChecks(root);
    var master = root && root.querySelector('[data-worktime-master]');
    if (!master) return;
    var checkedCount = boxes.filter(function (box) { return box.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function ensureActionsVisibility(root) {
    var actions = root && root.querySelector('[data-worktime-actions]');
    if (!actions) return;
    var anyChecked = getChecked(root).length > 0;
    actions.classList.toggle('d-none', !anyChecked);
    actions.classList.toggle('d-flex', anyChecked);
  }

  function updateEditBtn(root) {
    if (!root) return;
    var btn = root.querySelector('[data-worktime-edit-btn]');
    if (!btn) return;
    btn.disabled = getChecked(root).length === 0;
  }

  function updatePaneState(root) {
    if (!root) return;
    updateMasterState(root);
    updateRowHighlight(root);
    ensureActionsVisibility(root);
    updateEditBtn(root);
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

  function hideWorktimeModal() {
    var modalEl = document.getElementById('worktime-modal');
    if (!modalEl || !window.bootstrap) return;
    bootstrap.Modal.getOrCreateInstance(modalEl).hide();
  }

  function openEditModal(root) {
    var checked = getChecked(root);
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
    var root = panelFor(e.target);
    if (!root) return;

    var editBtn = e.target.closest('[data-worktime-edit-btn]');
    if (editBtn) {
      openEditModal(root);
      return;
    }

    var actionBtn = e.target.closest('[data-worktime-actions] [data-panel-action="edit"]');
    if (actionBtn) {
      openEditModal(root);
    }
  });

  document.addEventListener('change', function (e) {
    var root = panelFor(e.target);
    if (!root) return;

    var master = e.target.closest('[data-worktime-master]');
    if (master) {
      getRowChecks(root).forEach(function (box) { box.checked = master.checked; });
      master.indeterminate = false;
      updatePaneState(root);
      return;
    }

    var rowCb = e.target.closest('tbody input.form-check-input[name="worktime-row-select"]');
    if (rowCb) {
      updatePaneState(root);
    }
  });

  document.body.addEventListener('htmx:afterSettle', function (e) {
    var root = e.target && e.target.matches('[data-worktime-panel]')
      ? e.target
      : panelFor(e.target);
    updatePaneState(root);
  });

  document.body.addEventListener('worktime-updated', function () {
    hideWorktimeModal();
  });

  document.addEventListener('DOMContentLoaded', function () {
    panels().forEach(updatePaneState);
  });
})();
