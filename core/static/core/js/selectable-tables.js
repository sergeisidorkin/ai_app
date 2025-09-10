(function () {
  function bindSelectableTables(root) {
    const scope = root || document;
    const pane = document.getElementById('policy-pane');
    if (!pane) return;

    const masters = scope.querySelectorAll('#policy-pane thead input.form-check-input[data-target-name]');
    masters.forEach(master => {
      const table = master.closest('table');
      if (!table) return;
      const name = master.getAttribute('data-target-name');

      const actionsId = master.getAttribute('data-actions-id') || '';
      const actions = actionsId ? table.parentElement.querySelector('#' + actionsId) : null;

      const rowsSelector = `tbody input.form-check-input[name="${name}"]`;
      const getRowChecks = () => table.querySelectorAll(rowsSelector);

      function updateRowHighlight() {
        getRowChecks().forEach(b => {
          const tr = b.closest('tr');
          if (!tr) return;
          tr.classList.toggle('table-active', !!b.checked);
        });
      }
      function updateMasterState() {
        const boxes = Array.from(getRowChecks());
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
        const anyChecked = Array.from(getRowChecks()).some(b => b.checked);
        actions.classList.toggle('d-none', !anyChecked);
      }

      if (!master._selectableBound) {
        master.addEventListener('change', () => {
          const boxes = getRowChecks();
          boxes.forEach(b => { b.checked = master.checked; });
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

  document.addEventListener('DOMContentLoaded', () => bindSelectableTables(document));
  document.body.addEventListener('htmx:afterSettle', (e) => {
    if (e.target && e.target.id === 'policy-pane') bindSelectableTables(e.target);
  });
})();