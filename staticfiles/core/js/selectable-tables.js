(function () {
  function resolvePolicyPane(root) {
    const scope = root || document;
    if (scope instanceof Element && scope.id === 'policy-pane') return scope;
    const fromScope = scope instanceof Element ? scope.querySelector('#policy-pane') : null;
    const all = document.querySelectorAll('#policy-pane');
    return fromScope || (all.length ? all[all.length - 1] : null);
  }

  function bindSelectableTables(root) {
    const pane = resolvePolicyPane(root);
    if (!pane) return;

    const masters = pane.querySelectorAll('thead input.form-check-input[data-target-name]');
    masters.forEach(master => {
      const table = master.closest('table');
      if (!table) return;
      const name = master.getAttribute('data-target-name');

      const actionsId = master.getAttribute('data-actions-id') || '';
      const actions = actionsId ? table.parentElement.querySelector('#' + actionsId) : null;

      const rowsSelector = `tbody input.form-check-input[name="${name}"]`;
      function isSelectableRowCheckbox(box) {
        const tr = box?.closest('tr');
        return !!tr && !tr.classList.contains('d-none') && !box.disabled;
      }
      function getAllRowChecks() {
        return Array.from(table.querySelectorAll(rowsSelector));
      }
      function getRowChecks() {
        return getAllRowChecks().filter(isSelectableRowCheckbox);
      }

      function updateRowHighlight() {
        getAllRowChecks().forEach(b => {
          const tr = b.closest('tr');
          if (!tr) return;
          tr.classList.toggle('table-active', !!b.checked);
        });
      }
      function updateMasterState() {
        const boxes = getRowChecks();
        if (!boxes.length) {
          master.checked = false;
          master.indeterminate = false;
          return;
        }
        const checkedCount = boxes.filter(b => b.checked).length;
        master.checked = checkedCount === boxes.length;
        master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
      }
      function updateActionsVisibility() {
        if (!actions) return;
        const anyChecked = getRowChecks().some(b => b.checked);
        actions.classList.toggle('d-none', !anyChecked);
      }

      if (!master._selectableBound) {
        master.addEventListener('change', () => {
          getAllRowChecks().forEach(b => {
            if (!isSelectableRowCheckbox(b)) {
              b.checked = false;
              return;
            }
            b.checked = master.checked;
          });
          master.indeterminate = false;
          updateRowHighlight();
          updateMasterState();
          updateActionsVisibility();
        });
        table.addEventListener('change', (e) => {
          const t = e.target;
          if (t && t.matches(rowsSelector)) {
            updateRowHighlight();
            updateMasterState();
            updateActionsVisibility();
          }
        });
        master._selectableBound = true;
      }

      // init
      updateRowHighlight();
      updateMasterState();
      updateActionsVisibility();
    });
  }

  window.__refreshPolicySelectableTables = function () {
    const pane = resolvePolicyPane(document);
    if (!pane) return;
    bindSelectableTables(pane);
  };

  document.addEventListener('DOMContentLoaded', () => bindSelectableTables(document));
  document.body.addEventListener('htmx:afterSettle', (e) => {
    if (e.target && e.target.id === 'policy-pane') bindSelectableTables(e.target);
  });
})();
