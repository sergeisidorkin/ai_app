(function () {
  if (window.__requestsPanelBound) return;
  window.__requestsPanelBound = true;

  // Кешы выбора (как в policy-panels.js)
  window.__tableSel = window.__tableSel || {};
  window.__tableSelLast = window.__tableSelLast || null;
  window.__tableLastClicked = window.__tableLastClicked || {}; // name -> last id

  function pane() { return document.getElementById('requests-pane'); }
  const qa = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  const csrftoken = getCookie('csrftoken');

  function getMasterForPanel(panel) {
    const id = panel?.id;
    if (!id) return null;
    return pane()?.querySelector(`input.form-check-input[data-actions-id="${CSS.escape(id)}"]`) || null;
  }
  function getNameForPanel(panel) {
    const master = getMasterForPanel(panel);
    return master?.dataset?.targetName || null;
  }
  function getRowChecksByName(name) {
    return qa(`tbody input.form-check-input[name="${CSS.escape(name)}"]`, pane());
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
    const master = pane()?.querySelector(`input.form-check-input[data-target-name="${CSS.escape(name)}"]`);
    if (!master) return;
    const checkedCount = boxes.filter(b => b.checked).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function findActionsByName(name) {
    const master = pane()?.querySelector(`input.form-check-input[data-target-name="${CSS.escape(name)}"]`);
    const actionsId = master?.getAttribute('data-actions-id') || '';
    return actionsId ? pane()?.querySelector('#' + actionsId) : null;
  }
  function ensureActionsVisibility(name) {
    const panel = findActionsByName(name);
    if (!panel) return;
    const anyChecked = getRowChecksByName(name).some(b => b.checked);
    panel.classList.toggle('d-none', !anyChecked);
  }

  // Выбор «правильной» строки для действия Edit: сначала последний кликнутый, иначе — единственный/первый
  function pickEditCheckbox(name) {
    const checked = getCheckedByName(name);
    if (!checked.length) return null;
    const lastId = window.__tableLastClicked?.[name];
    if (lastId) {
      const hit = checked.find(ch => String(ch.value) === String(lastId));
      if (hit) return hit;
    }
    if (checked.length === 1) return checked[0];
    return checked[0]; // бэкап-поведение
  }

  // Делегирование: клики по кнопкам панели
  document.addEventListener('click', async (e) => {
    const root = pane(); if (!root) return;
    const btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    const panel = btn.closest('#requests-actions'); if (!panel) return;
    const action = btn.dataset.panelAction; // "up" | "down" | "edit" | "delete"
    const name = getNameForPanel(panel); if (!name) return;

    const checked = getCheckedByName(name);
    if (!checked.length) return;

    // Сохраняем текущий выбор по имени таблицы
    window.__tableSel[name] = checked.map(ch => String(ch.value));
    window.__tableSelLast = name;

    if (action === 'edit') {
      const tr = checked[0].closest('tr');
      const id = tr?.dataset?.id;
      const url = tr?.dataset?.editUrl || (id ? `/requests/row/${id}/edit/` : null);
      if (!url) return;
      await htmx.ajax('GET', url, { target: '#requests-modal .modal-content', swap: 'innerHTML' });
      const modalEl = document.getElementById('requests-modal');
      if (modalEl && window.bootstrap) window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm(`Удалить ${checked.length} строк(у/и)?`)) return;
      const urls = checked.map(ch => {
        const tr = ch.closest('tr');
        const id = tr?.dataset?.id;
        return tr?.dataset?.deleteUrl || (id ? `/requests/row/${id}/delete/` : null);
      }).filter(Boolean);
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#requests-pane', swap: 'innerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
        }
      }
      // после удаления сбрасываем "последний кликнутый"
      window.__tableLastClicked[name] = null;
      return;
    }

    if (action === 'up' || action === 'down') {
      let urls = checked.map(ch => {
        const tr = ch.closest('tr');
        const id = tr?.dataset?.id;
        return tr?.dataset?.[action === 'up' ? 'moveUpUrl' : 'moveDownUrl']
               || (id ? `/requests/row/${id}/${action === 'up' ? 'up' : 'down'}/` : null);
      }).filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      for (let i = 0; i < urls.length; i++) {
        const isLast = i === urls.length - 1;
        if (isLast) {
          await htmx.ajax('POST', urls[i], { target: '#requests-pane', swap: 'innerHTML' });
        } else {
          await fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } }).catch(()=>{});
        }
      }
      ensureActionsVisibility(name);
    }
  });

  // Делегирование: изменения чекбоксов
  document.addEventListener('change', (e) => {
    const root = pane(); if (!root) return;

    // мастер-чекбокс
    const master = e.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (master && root.contains(master)) {
      const name = master.dataset.targetName;
      const boxes = getRowChecksByName(name);
      boxes.forEach(b => { b.checked = master.checked; });
      if (!master.checked) window.__tableLastClicked[name] = null; // сняли всё — сброс «последнего»
      master.indeterminate = false;
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
      return;
    }

    // чекбоксы строк
    const rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (rowCb && root.contains(rowCb)) {
      const name = rowCb.name;
      if (rowCb.checked) {
        window.__tableLastClicked[name] = String(rowCb.value); // запомнили «последний кликнутый»
      } else if (window.__tableLastClicked[name] === String(rowCb.value)) {
        window.__tableLastClicked[name] = null;
      }
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
    }
  });

  // Восстановление выбора и подсветки после перерисовки партиала
  document.body.addEventListener('htmx:afterSettle', function (e) {
    const root = pane(); if (!root) return;
    // триггерим восстановление, если обновляли requests-pane или что-то внутри него
    if (!(e.target === root || root.contains(e.target))) return;

    const last = window.__tableSelLast;
    if (!last) return;

    const ids = (window.__tableSel && window.__tableSel[last]) || [];
    const set = new Set(ids || []);
    getRowChecksByName(last).forEach(b => { b.checked = set.has(String(b.value)); });
    updateMasterStateFor(last);
    updateRowHighlightFor(last);
    ensureActionsVisibility(last);

    // если «последний кликнутый» больше не отмечен — обнулим
    const lastId = window.__tableLastClicked?.[last];
    if (lastId && !set.has(String(lastId))) window.__tableLastClicked[last] = null;

    try { delete window.__tableSel[last]; } catch(_) { window.__tableSel[last] = []; }
    window.__tableSelLast = null;
  });
})();