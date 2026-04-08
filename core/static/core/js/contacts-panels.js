(function () {
  const rootSelector = '#contacts';
  window.__contactsTableSel = window.__contactsTableSel || {};
  const TABLE_CONFIG = {
    'prs-select': { target: '#contacts-persons-table-wrap', swap: 'innerHTML', url: '/contacts/prs/table/' },
    'psn-select': { target: '#contacts-positions-table-wrap', swap: 'innerHTML', url: '/contacts/psn/table/' },
  };
  const SECTION_TABLE_MAP = {
    persons: 'prs-select',
    positions: 'psn-select',
  };
  const SECTION_TITLES = {
    persons: 'База контактов',
    positions: 'База контактов',
  };

  function inContacts(node) {
    return !!(node && node.closest && node.closest(rootSelector));
  }

  function paneOf(node) {
    return node && node.closest ? node.closest('#contacts-persons-pane, #contacts-positions-pane') : null;
  }

  function getMasterForName(name) {
    return document.querySelector(rootSelector + ' input.form-check-input[data-target-name="' + name + '"]');
  }

  function getRowChecksByName(name) {
    return Array.from(document.querySelectorAll(rootSelector + ' tbody input.form-check-input[name="' + name + '"]'));
  }

  function getCheckedByName(name) {
    return getRowChecksByName(name).filter(function (item) { return item.checked; });
  }

  function updateRowHighlightFor(name) {
    getRowChecksByName(name).forEach(function (checkbox) {
      var row = checkbox.closest('tr');
      if (row) row.classList.toggle('table-active', checkbox.checked);
    });
  }

  function updateMasterStateFor(name) {
    var master = getMasterForName(name);
    if (!master) return;
    var boxes = getRowChecksByName(name);
    var checked = boxes.filter(function (item) { return item.checked; }).length;
    master.checked = !!boxes.length && checked === boxes.length;
    master.indeterminate = checked > 0 && checked < boxes.length;
  }

  function ensureActionsVisibility(name) {
    var master = getMasterForName(name);
    var actionsId = master && master.dataset ? master.dataset.actionsId : '';
    if (!actionsId) return;
    var panel = document.getElementById(actionsId);
    if (!panel) return;
    panel.classList.toggle('d-none', getCheckedByName(name).length === 0);
  }

  function rememberSelection(name) {
    window.__contactsTableSel[name] = getCheckedByName(name).map(function (item) {
      return String(item.value);
    });
  }

  function restoreSelection(name) {
    var ids = window.__contactsTableSel[name] || [];
    if (!ids.length) return;
    var idSet = new Set(ids);
    getRowChecksByName(name).forEach(function (checkbox) {
      checkbox.checked = idSet.has(String(checkbox.value));
    });
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
  }

  function refreshTable(name) {
    var cfg = TABLE_CONFIG[name];
    if (!cfg || !window.htmx) return Promise.resolve();
    return htmx.ajax('GET', cfg.url, { target: cfg.target, swap: cfg.swap });
  }

  function refreshTables(names) {
    var items = Array.from(new Set((names || []).filter(Boolean)));
    return Promise.all(items.map(function (name) { return refreshTable(name); }));
  }

  function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      var cookies = document.cookie.split(';');
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function switchSection(key) {
    window.__currentContactsSection = key;
    document.querySelectorAll('#contacts .contacts-section-content').forEach(function (node) {
      node.classList.add('d-none');
    });
    var target = document.getElementById('cnt-content-' + key);
    if (target) target.classList.remove('d-none');
    var title = document.getElementById('contacts-section-title');
    if (title) title.textContent = SECTION_TITLES[key] || 'База контактов';
    if (key === 'persons') {
      document.body.dispatchEvent(new CustomEvent('contacts-persons:load'));
    }
    if (key === 'positions') {
      document.body.dispatchEvent(new CustomEvent('contacts-positions:load'));
    }
  }

  function activateSectionLink(key) {
    var sidebar = document.getElementById('contacts-second-sidebar-list');
    if (!sidebar) return;
    sidebar.querySelectorAll('.list-group-item').forEach(function (link) {
      link.classList.remove('active');
    });
    var activeLink = sidebar.querySelector('[data-contacts-section="' + key + '"]');
    if (activeLink) activeLink.classList.add('active');
  }

  document.addEventListener('DOMContentLoaded', function () {
    var sidebar = document.getElementById('contacts-second-sidebar-list');
    if (sidebar && !sidebar.dataset.bound) {
      sidebar.dataset.bound = '1';
      sidebar.addEventListener('click', function (event) {
        var link = event.target.closest('.list-group-item');
        if (!link) return;
        event.preventDefault();
        var key = link.dataset.contactsSection || 'persons';
        activateSectionLink(key);
        switchSection(key);
        if (window.UIPref) window.UIPref.set('contacts:section', key);
      });
    }

    var saved = window.UIPref ? window.UIPref.get('contacts:section', null) : null;
    var initial = saved && SECTION_TABLE_MAP[saved] ? saved : 'persons';
    activateSectionLink(initial);
    switchSection(initial);
  });

  document.addEventListener('change', function (event) {
    var master = event.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (!master || !inContacts(master)) return;
    var name = master.dataset.targetName;
    getRowChecksByName(name).forEach(function (checkbox) { checkbox.checked = master.checked; });
    master.indeterminate = false;
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
  });

  document.addEventListener('change', function (event) {
    var rowCheckbox = event.target.closest('tbody input.form-check-input[name]');
    if (!rowCheckbox || !inContacts(rowCheckbox)) return;
    var name = rowCheckbox.name;
    updateMasterStateFor(name);
    updateRowHighlightFor(name);
    ensureActionsVisibility(name);
  });

  document.addEventListener('click', function (event) {
    var button = event.target.closest('button[data-panel-action]');
    if (!button || !inContacts(button)) return;
    var panel = button.closest('#prs-actions, #psn-actions');
    if (!panel) return;
    var master = paneOf(panel) && paneOf(panel).querySelector('input.form-check-input[data-actions-id]');
    var name = master && master.dataset ? master.dataset.targetName : '';
    if (!name) return;
    var checked = getCheckedByName(name);
    if (!checked.length) return;
    var action = button.dataset.panelAction;

    if (action === 'edit') {
      var editUrl = checked[0].closest('tr') && checked[0].closest('tr').dataset ? checked[0].closest('tr').dataset.editUrl : '';
      if (!editUrl || !window.htmx) return;
      htmx.ajax('GET', editUrl, { target: '#contacts-modal .modal-content', swap: 'innerHTML' });
      return;
    }

    if (action === 'delete') {
      if (!window.confirm('Удалить ' + checked.length + ' строк(у/и)?')) return;
      var deleteUrls = checked.map(function (item) {
        var row = item.closest('tr');
        return row && row.dataset ? row.dataset.deleteUrl : '';
      }).filter(Boolean);
      Promise.resolve().then(async function () {
        for (var i = 0; i < deleteUrls.length; i++) {
          var response = await fetch(deleteUrls[i], {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken'), 'HX-Request': 'true' },
          });
          if (!response.ok) {
            var text = await response.text();
            window.alert(text || 'Операцию не удалось выполнить.');
            break;
          }
        }
        await refreshTable(name);
        if (name === 'prs-select') await refreshTable('psn-select');
      });
      return;
    }

    if (action === 'up' || action === 'down') {
      rememberSelection(name);
      var urls = checked.map(function (item) {
        var row = item.closest('tr');
        if (!row || !row.dataset) return '';
        return action === 'up' ? row.dataset.moveUpUrl : row.dataset.moveDownUrl;
      }).filter(Boolean);
      if (action === 'down') urls.reverse();
      Promise.resolve().then(async function () {
        for (var i = 0; i < urls.length; i++) {
          await fetch(urls[i], {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken'), 'HX-Request': 'true' },
          });
        }
        await refreshTable(name);
        restoreSelection(name);
      });
    }
  });

  document.body.addEventListener('contacts-updated', function (event) {
    var detail = event.detail || {};
    refreshTables(detail.affected || []).catch(function () {});
  });

  document.body.addEventListener('shown.bs.tab', function (event) {
    var trigger = event.target;
    if (!trigger || trigger.getAttribute('href') !== '#contacts') return;
    var section = window.__currentContactsSection || 'persons';
    var tableName = SECTION_TABLE_MAP[section];
    if (tableName) refreshTable(tableName).catch(function () {});
  });
})();
