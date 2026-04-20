(function () {
  if (window.__contractsPanelBound) return;
  window.__contractsPanelBound = true;

  function pane() { return document.getElementById('contracts-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getRowChecks() {
    return qa('tbody input.form-check-input[name="contract-row-select"]', pane());
  }
  function getChecked() {
    return getRowChecks().filter(function(b) { return b.checked; });
  }
  function updateRowHighlight() {
    getRowChecks().forEach(function(b) {
      var tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateMasterState() {
    var boxes = getRowChecks();
    var master = pane() && pane().querySelector('#contracts-master');
    if (!master) return;
    var checkedCount = boxes.filter(function(b) { return b.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function ensureActionsVisibility() {
    var panel = pane() && pane().querySelector('#contracts-actions');
    if (!panel) return;
    var any = getRowChecks().some(function(b) { return b.checked; });
    panel.classList.toggle('d-none', !any);
  }
  function updateEditBtn() {
    var root = pane();
    if (!root) return;
    var btn = root.querySelector('#contracts-edit-btn');
    if (!btn) return;
    var anyChecked = getRowChecks().some(function(b) { return b.checked; });
    btn.disabled = !anyChecked;
  }

  function showContractsModal() {
    var modalEl = document.getElementById('contracts-modal');
    if (!modalEl || !window.bootstrap) return;
    var dlg = modalEl.querySelector('.modal-dialog');
    if (dlg) {
      dlg.classList.remove('modal-sm', 'modal-lg', 'modal-xl');
      var sizeEl = modalEl.querySelector('[data-modal-size]');
      if (sizeEl) dlg.classList.add('modal-' + sizeEl.dataset.modalSize);
    }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  document.addEventListener('click', function(e) {
    var root = pane(); if (!root) return;

    var editBtn = e.target.closest('#contracts-edit-btn');
    if (editBtn && root.contains(editBtn)) {
      var checked = getChecked();
      if (!checked.length) return;
      var tr = checked[0].closest('tr');
      var url = tr && tr.dataset.editUrl;
      if (!url) return;
      var target = document.querySelector('#contracts-modal .modal-content');
      if (!target) return;
      htmx.ajax('GET', url, target).then(function() {
        showContractsModal();
      });
      updateEditBtn();
      return;
    }
  });

  document.addEventListener('change', function(e) {
    var root = pane(); if (!root) return;

    var master = e.target.closest('#contracts-master');
    if (master && root.contains(master)) {
      getRowChecks().forEach(function(b) { b.checked = master.checked; });
      master.indeterminate = false;
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
      updateEditBtn();
      return;
    }

    var rowCb = e.target.closest('tbody input.form-check-input[name="contract-row-select"]');
    if (rowCb && root.contains(rowCb)) {
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
      updateEditBtn();
      return;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
    updateEditBtn();
  });

  document.addEventListener('DOMContentLoaded', function() {
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
    updateEditBtn();
  });
})();


/* -----------------------------------------------------------------------
   Development table ("В разработке") panel
   ----------------------------------------------------------------------- */
(function () {
  if (window.__contractsDraftsBound) return;
  window.__contractsDraftsBound = true;
  window.__contractsDraftSel = window.__contractsDraftSel || [];

  function pane() { return document.getElementById('contracts-drafts-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }

  function getRowChecks() {
    return qa('tbody input.form-check-input[name="contracts-draft-select"]', pane());
  }

  function getChecked() {
    return getRowChecks().filter(function(box) { return box.checked; });
  }

  function updateRowHighlight() {
    getRowChecks().forEach(function(box) {
      var tr = box.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!box.checked);
    });
  }

  function updateMasterState() {
    var boxes = getRowChecks();
    var master = pane() && pane().querySelector('#contracts-drafts-master');
    if (!master) return;
    var checkedCount = boxes.filter(function(box) { return box.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }

  function ensureActionsVisibility() {
    var actions = pane() && pane().querySelector('#contracts-drafts-actions');
    if (!actions) return;
    var anyChecked = getChecked().length > 0;
    actions.classList.toggle('d-none', !anyChecked);
    actions.classList.toggle('d-flex', anyChecked);
  }

  function showContractsModal() {
    var modalEl = document.getElementById('contracts-modal');
    if (!modalEl || !window.bootstrap) return;
    var dlg = modalEl.querySelector('.modal-dialog');
    if (dlg) {
      dlg.classList.remove('modal-sm', 'modal-lg', 'modal-xl');
      var sizeEl = modalEl.querySelector('[data-modal-size]');
      if (sizeEl) dlg.classList.add('modal-' + sizeEl.dataset.modalSize);
    }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function openModal(url) {
    var target = document.querySelector('#contracts-modal .modal-content');
    if (!url || !target) return Promise.resolve();
    return htmx.ajax('GET', url, target).then(function() {
      showContractsModal();
    });
  }

  function refreshDraftsPane() {
    var root = pane();
    if (!root) return Promise.resolve();
    var refreshUrl = root.getAttribute('hx-get') || root.dataset.refreshUrl;
    if (!refreshUrl) return Promise.resolve();
    return htmx.ajax('GET', refreshUrl, { target: '#contracts-drafts-pane', swap: 'innerHTML' });
  }

  function postSequential(urls) {
    var csrftoken = getCookie('csrftoken');
    return urls.reduce(function(chain, url) {
      return chain.then(function() {
        return fetch(url, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrftoken, 'HX-Request': 'true' },
        }).then(function(response) {
          if (!response.ok) {
            throw new Error('Операция не выполнена.');
          }
        });
      });
    }, Promise.resolve());
  }

  function restoreSelection(ids) {
    var selected = {};
    (ids || []).forEach(function(id) { selected[String(id)] = true; });
    getRowChecks().forEach(function(box) { box.checked = !!selected[String(box.value)]; });
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
  }

  document.addEventListener('click', function(e) {
    var root = pane();
    if (!root) return;

    var createBtn = e.target.closest('#contracts-drafts-create-btn');
    if (createBtn && root.contains(createBtn)) {
      openModal(createBtn.dataset.url);
      return;
    }

    var panelBtn = e.target.closest('#contracts-drafts-actions button[data-panel-action]');
    if (!panelBtn || !root.contains(panelBtn)) return;

    var checked = getChecked();
    if (!checked.length) return;
    window.__contractsDraftSel = checked.map(function(box) { return String(box.value); });

    var action = panelBtn.dataset.panelAction;
    if (action === 'edit') {
      var tr = checked[0].closest('tr');
      openModal(tr && tr.dataset.editUrl);
      return;
    }

    if (action === 'delete') {
      if (!confirm('Удалить ' + checked.length + ' строк(у/и)?')) return;
      var urls = checked.map(function(box) {
        var tr = box.closest('tr');
        return tr && tr.dataset.deleteUrl;
      }).filter(Boolean);
      postSequential(urls)
        .then(function() { return refreshDraftsPane(); })
        .catch(function(err) { alert(err.message || 'Не удалось удалить строки.'); });
      return;
    }

    if (action === 'up' || action === 'down') {
      var selectedIds = checked.map(function(box) { return String(box.value); });
      var urls = checked.map(function(box) {
        var tr = box.closest('tr');
        return tr && tr.dataset[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'];
      }).filter(Boolean);
      if (action === 'down') urls = urls.reverse();
      postSequential(urls)
        .then(function() { return refreshDraftsPane(); })
        .then(function() { restoreSelection(selectedIds); })
        .catch(function(err) { alert(err.message || 'Не удалось изменить порядок строк.'); });
    }
  });

  document.addEventListener('change', function(e) {
    var root = pane();
    if (!root) return;

    var master = e.target.closest('#contracts-drafts-master');
    if (master && root.contains(master)) {
      getRowChecks().forEach(function(box) { box.checked = master.checked; });
      master.indeterminate = false;
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
      return;
    }

    var rowCb = e.target.closest('tbody input.form-check-input[name="contracts-draft-select"]');
    if (rowCb && root.contains(rowCb)) {
      updateMasterState();
      updateRowHighlight();
      ensureActionsVisibility();
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    if (!(e.target && e.target.id === 'contracts-drafts-pane')) return;
    var ids = window.__contractsDraftSel || [];
    restoreSelection(ids);
    window.__contractsDraftSel = [];
  });

  document.addEventListener('DOMContentLoaded', function() {
    updateMasterState();
    updateRowHighlight();
    ensureActionsVisibility();
  });
})();


/* -----------------------------------------------------------------------
   Signing table ("Подписание договора") panel
   ----------------------------------------------------------------------- */
(function () {
  if (window.__signingPanelBound) return;
  window.__signingPanelBound = true;

  function pane() { return document.getElementById('contracts-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getSigningChecks() {
    return qa('tbody input.form-check-input[name="signing-row-select"]', pane());
  }
  function getSigningActiveChecks() {
    return getSigningChecks().filter(function(b) { return !b.disabled; });
  }
  function getSigningChecked() {
    return getSigningActiveChecks().filter(function(b) { return b.checked; });
  }
  function updateSigningHighlight() {
    getSigningChecks().forEach(function(b) {
      var tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateSigningMaster() {
    var boxes = getSigningActiveChecks();
    var master = pane() && pane().querySelector('#signing-master');
    if (!master) return;
    var checkedCount = boxes.filter(function(b) { return b.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function updateSigningEditBtn() {
    var root = pane();
    if (!root) return;
    var checked = getSigningChecked();
    var btn = root.querySelector('#signing-edit-btn');
    if (btn) btn.disabled = checked.length !== 1;
    var sendBtn = root.querySelector('#signing-send-scan-btn');
    if (sendBtn) {
      var enabled = checked.length === 1
        && checked[0].closest('tr') && checked[0].closest('tr').dataset.hasScan === '1';
      sendBtn.disabled = !enabled;
    }
  }

  function showContractsModal() {
    var modalEl = document.getElementById('contracts-modal');
    if (!modalEl || !window.bootstrap) return;
    var dlg = modalEl.querySelector('.modal-dialog');
    if (dlg) {
      dlg.classList.remove('modal-sm', 'modal-lg', 'modal-xl');
      var sizeEl = modalEl.querySelector('[data-modal-size]');
      if (sizeEl) dlg.classList.add('modal-' + sizeEl.dataset.modalSize);
    }
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
  }

  function refreshSigning() {
    updateSigningMaster();
    updateSigningHighlight();
    updateSigningEditBtn();
  }

  document.addEventListener('click', function(e) {
    var root = pane(); if (!root) return;

    var editBtn = e.target.closest('#signing-edit-btn');
    if (editBtn && root.contains(editBtn)) {
      var checked = getSigningChecked();
      if (!checked.length) return;
      var tr = checked[0].closest('tr');
      var url = tr && tr.dataset.signingEditUrl;
      if (!url) return;
      var target = document.querySelector('#contracts-modal .modal-content');
      if (!target) return;
      htmx.ajax('GET', url, target).then(function() {
        showContractsModal();
      });
      updateSigningEditBtn();
      return;
    }

    var sendScanBtn = e.target.closest('#signing-send-scan-btn');
    if (sendScanBtn && root.contains(sendScanBtn)) {
      var checked = getSigningChecked();
      if (!checked.length) return;
      var url = sendScanBtn.dataset.url;
      if (!url) return;
      sendScanBtn.disabled = true;
      var fd = new FormData();
      checked.forEach(function(cb) { fd.append('performer_ids[]', cb.value); });
      fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') },
        body: fd,
      }).then(function(resp) {
        return resp.json();
      }).then(function(data) {
        if (data.ok) {
          htmx.trigger(document.body, 'contracts-updated');
          htmx.trigger(document.body, 'notifications-updated');
          var contractsPane = document.getElementById('contracts-pane');
          if (contractsPane) {
            var refreshUrl = contractsPane.getAttribute('hx-get') || contractsPane.dataset.refreshUrl;
            if (refreshUrl) {
              htmx.ajax('GET', refreshUrl, { target: '#contracts-pane', swap: 'innerHTML' });
            }
          }
        } else {
          alert(data.error || 'Ошибка при отправке скана.');
        }
      }).catch(function() {
        alert('Ошибка сети при отправке скана.');
      }).finally(function() {
        updateSigningEditBtn();
      });
      return;
    }
  });

  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }

  document.addEventListener('change', function(e) {
    var root = pane(); if (!root) return;

    var master = e.target.closest('#signing-master');
    if (master && root.contains(master)) {
      getSigningActiveChecks().forEach(function(b) { b.checked = master.checked; });
      master.indeterminate = false;
      refreshSigning();
      return;
    }

    var rowCb = e.target.closest('tbody input.form-check-input[name="signing-row-select"]');
    if (rowCb && root.contains(rowCb)) {
      refreshSigning();
      return;
    }

    function handleScanUpload(inputEl, fieldName) {
      var file = inputEl.files && inputEl.files[0];
      if (!file) return;
      var url = inputEl.dataset.uploadUrl;
      if (!url) return;

      var tr = inputEl.closest('tr');
      var rowCb = tr && tr.querySelector('input[name="signing-row-select"]');
      if (rowCb && !rowCb.disabled && !rowCb.checked) {
        rowCb.checked = true;
        refreshSigning();
      }
      var checkedPerformerIds = getSigningChecked().map(function(b) { return b.value; });

      var modalEl = document.getElementById('scan-upload-progress-modal');
      var progressBar = document.getElementById('scan-upload-progress-bar');
      var statusEl = document.getElementById('scan-upload-status');
      var closeBtn = document.getElementById('scan-upload-close-btn');
      var uploadSucceeded = false;
      if (progressBar) progressBar.style.width = '0%';
      if (statusEl) statusEl.textContent = '';
      if (closeBtn) closeBtn.disabled = true;
      if (modalEl && window.bootstrap) {
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
      }

      var fd = new FormData();
      fd.append(fieldName, file);
      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
      xhr.upload.addEventListener('progress', function(ev) {
        if (ev.lengthComputable && progressBar) {
          var pct = Math.round(ev.loaded / ev.total * 100);
          progressBar.style.width = pct + '%';
        }
      });
      xhr.addEventListener('load', function() {
        if (progressBar) progressBar.style.width = '100%';
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            var data = JSON.parse(xhr.responseText);
            if (data.ok && data.scan_name && statusEl) {
              uploadSucceeded = true;
              var storageLabel = data.storage_label || 'облачное хранилище';
              var icon = document.createElement('i');
              icon.className = 'bi bi-check-circle me-1';
              var span = document.createElement('span');
              span.className = 'text-success';
              span.appendChild(icon);
              span.appendChild(document.createTextNode(
                'Документ успешно загружен на ' + storageLabel + ' в папку с проектом договора и переименован в \u00ab'
                + data.scan_name + '\u00bb.'));
              statusEl.textContent = '';
              statusEl.appendChild(span);
            }
          } catch (_) {}
        } else {
          if (statusEl) {
            statusEl.textContent = '';
            var errSpan = document.createElement('span');
            errSpan.className = 'text-danger';
            errSpan.textContent = 'Ошибка при загрузке файла.';
            statusEl.appendChild(errSpan);
          }
        }
        if (closeBtn) closeBtn.disabled = false;
      });
      xhr.addEventListener('error', function() {
        if (statusEl) {
          statusEl.textContent = '';
          var errSpan = document.createElement('span');
          errSpan.className = 'text-danger';
          errSpan.textContent = 'Ошибка сети при загрузке файла.';
          statusEl.appendChild(errSpan);
        }
        if (closeBtn) closeBtn.disabled = false;
      });
      if (modalEl) {
        modalEl.addEventListener('hidden.bs.modal', function onHidden() {
          modalEl.removeEventListener('hidden.bs.modal', onHidden);
          var contractsPane = document.getElementById('contracts-pane');
          if (contractsPane) {
            var refreshUrl = contractsPane.getAttribute('hx-get') || contractsPane.dataset.refreshUrl;
            if (refreshUrl) {
              htmx.ajax('GET', refreshUrl, { target: '#contracts-pane', swap: 'innerHTML' }).then(function() {
                var set = {};
                if (!uploadSucceeded) {
                  checkedPerformerIds.forEach(function(id) { set[id] = true; });
                }
                getSigningChecks().forEach(function(b) { b.checked = !!set[b.value]; });
                refreshSigning();
              });
            }
          }
        }, { once: true });
      }
      xhr.send(fd);
      inputEl.value = '';
    }

    var scanInput = e.target.closest('.js-scan-upload');
    if (scanInput && root.contains(scanInput)) {
      handleScanUpload(scanInput, 'contract_employee_scan');
      return;
    }

    var signedScanInput = e.target.closest('.js-signed-scan-upload');
    if (signedScanInput && root.contains(signedScanInput)) {
      handleScanUpload(signedScanInput, 'contract_signed_scan_file');
      return;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    var root = pane(); if (!root) return;
    if (!(e.target === root || root.contains(e.target))) return;
    refreshSigning();
  });

  document.addEventListener('DOMContentLoaded', refreshSigning);
})();


/* -----------------------------------------------------------------------
   Contract Templates ("Образцы шаблонов") panel
   ----------------------------------------------------------------------- */
(function () {
  if (window.__ctPanelBound) return;
  window.__ctPanelBound = true;

  window.__ctTableSel = window.__ctTableSel || {};

  function ctPane() { return document.getElementById('contract-templates-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  var csrftoken = getCookie('csrftoken');

  var CT_PANELS = {
    'ct-actions': {
      name: 'ct-select',
      modal: '#contract-templates-modal .modal-content',
      modalId: 'contract-templates-modal',
      deleteLabel: 'строк(у/и)',
    },
    'ctv-actions': {
      name: 'ctv-select',
      modal: '#contract-templates-modal .modal-content',
      modalId: 'contract-templates-modal',
      deleteLabel: 'переменных',
    },
  };

  function getRowChecksByName(name) {
    var root = ctPane();
    if (!root) return [];
    return qa('tbody input.form-check-input[name="' + name + '"]', root);
  }
  function getCheckedByName(name) {
    return getRowChecksByName(name).filter(function(b) { return b.checked; });
  }
  function updateRowHighlightFor(name) {
    getRowChecksByName(name).forEach(function(b) {
      var tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateMasterStateFor(name) {
    var boxes = getRowChecksByName(name);
    var root = ctPane();
    if (!root) return;
    var master = root.querySelector('input.form-check-input[data-target-name="' + name + '"]');
    if (!master) return;
    var checkedCount = boxes.filter(function(b) { return b.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function findActionsByName(name) {
    var root = ctPane();
    if (!root) return null;
    var master = root.querySelector('input.form-check-input[data-target-name="' + name + '"]');
    if (!master) return null;
    var actionsId = master.getAttribute('data-actions-id') || '';
    if (!actionsId) return null;
    return root.querySelector('#' + actionsId);
  }
  function ensureActionsVisibility(name) {
    var panel = findActionsByName(name);
    if (!panel) return;
    var anyChecked = getRowChecksByName(name).some(function(b) { return b.checked; });
    panel.classList.toggle('d-none', !anyChecked);
  }

  function findPanelConfig(btn) {
    for (var panelId in CT_PANELS) {
      if (btn.closest('#' + panelId)) return CT_PANELS[panelId];
    }
    return null;
  }

  document.addEventListener('click', function(e) {
    var root = ctPane();
    if (!root) return;
    var btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    var config = findPanelConfig(btn);
    if (!config) return;

    var action = btn.dataset.panelAction;
    var name = config.name;

    var checked = getCheckedByName(name);
    if (!checked.length) return;

    window.__ctTableSel[name] = checked.map(function(ch) { return String(ch.value); });

    var ctVarsEl = document.getElementById('ct-variables');
    window.__ctVarsOpen = !!(ctVarsEl && ctVarsEl.classList.contains('show'));

    if (action === 'edit') {
      var first = checked[0];
      var tr = first.closest('tr');
      var url = tr && tr.dataset.editUrl;
      if (!url) return;
      htmx.ajax('GET', url, { target: config.modal, swap: 'innerHTML' }).then(function() {
        var modalEl = document.getElementById(config.modalId);
        if (modalEl && window.bootstrap) {
          window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
      });
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm('Удалить ' + checked.length + ' ' + config.deleteLabel + '?')) return;
      var urls = checked.map(function(ch) { return ch.closest('tr') && ch.closest('tr').dataset.deleteUrl; }).filter(Boolean);
      (function deleteSequential(i) {
        if (i >= urls.length) return;
        fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } })
          .catch(function() {})
          .then(function() {
            if (i < urls.length - 1) {
              deleteSequential(i + 1);
            } else {
              htmx.trigger(document.body, 'contract-templates-updated');
            }
          });
      })(0);
      return;
    }

    if (action === 'up' || action === 'down') {
      var moveUrls = checked
        .map(function(ch) {
          var t = ch.closest('tr');
          return t && t.dataset[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'];
        })
        .filter(Boolean);
      if (action === 'down') moveUrls = moveUrls.reverse();
      (function moveSequential(i) {
        if (i >= moveUrls.length) return;
        fetch(moveUrls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } })
          .catch(function() {})
          .then(function() {
            if (i < moveUrls.length - 1) {
              moveSequential(i + 1);
            } else {
              htmx.trigger(document.body, 'contract-templates-updated');
            }
          });
      })(0);
      return;
    }
  });

  document.addEventListener('change', function(e) {
    var root = ctPane();
    if (!root) return;
    var master = e.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (master && root.contains(master)) {
      var name = master.dataset.targetName;
      var boxes = getRowChecksByName(name);
      boxes.forEach(function(b) { b.checked = master.checked; });
      master.indeterminate = false;
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
      return;
    }
    var rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (rowCb && root.contains(rowCb)) {
      var cbName = rowCb.name;
      updateMasterStateFor(cbName);
      updateRowHighlightFor(cbName);
      ensureActionsVisibility(cbName);
      return;
    }
  });

  document.body.addEventListener('htmx:beforeRequest', function(e) {
    var tgt = e.detail && e.detail.target;
    if (tgt && tgt.id === 'contract-templates-pane') {
      var v = document.getElementById('ct-variables');
      if (v && v.classList.contains('show')) window.__ctVarsOpen = true;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    if (!(e.target && e.target.id === 'contract-templates-pane')) return;
    var sel = window.__ctTableSel || {};
    for (var name in sel) {
      var ids = sel[name] || [];
      var set = {};
      ids.forEach(function(id) { set[id] = true; });
      getRowChecksByName(name).forEach(function(b) { b.checked = !!set[String(b.value)]; });
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
    }
    window.__ctTableSel = {};
    if (window.__ctVarsOpen) {
      var ctVars = document.getElementById('ct-variables');
      if (ctVars) ctVars.classList.add('show');
      clearTimeout(window.__ctVarsOpenTimer);
      window.__ctVarsOpenTimer = setTimeout(function() { window.__ctVarsOpen = false; }, 1000);
    }
  });
})();


/* -----------------------------------------------------------------------
   Field Parameters / Contract Subject ("Предмет договора") panel
   ----------------------------------------------------------------------- */
(function () {
  if (window.__fpPanelBound) return;
  window.__fpPanelBound = true;

  window.__fpTableSel = window.__fpTableSel || {};

  function fpPane() { return document.getElementById('field-params-pane'); }
  var qa = function(sel, root) { return Array.from((root || document).querySelectorAll(sel)); };

  function getCookie(name) {
    var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  var csrftoken = getCookie('csrftoken');

  var FP_PANELS = {
    'cs-actions': {
      name: 'cs-select',
      modal: '#field-params-modal .modal-content',
      modalId: 'field-params-modal',
      deleteLabel: 'строк(у/и)',
    },
  };

  function getRowChecksByName(name) {
    var root = fpPane();
    if (!root) return [];
    return qa('tbody input.form-check-input[name="' + name + '"]', root);
  }
  function getCheckedByName(name) {
    return getRowChecksByName(name).filter(function(b) { return b.checked; });
  }
  function updateRowHighlightFor(name) {
    getRowChecksByName(name).forEach(function(b) {
      var tr = b.closest('tr');
      if (tr) tr.classList.toggle('table-active', !!b.checked);
    });
  }
  function updateMasterStateFor(name) {
    var boxes = getRowChecksByName(name);
    var root = fpPane();
    if (!root) return;
    var master = root.querySelector('input.form-check-input[data-target-name="' + name + '"]');
    if (!master) return;
    var checkedCount = boxes.filter(function(b) { return b.checked; }).length;
    master.checked = boxes.length > 0 && checkedCount === boxes.length;
    master.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
  }
  function findActionsByName(name) {
    var root = fpPane();
    if (!root) return null;
    var master = root.querySelector('input.form-check-input[data-target-name="' + name + '"]');
    if (!master) return null;
    var actionsId = master.getAttribute('data-actions-id') || '';
    if (!actionsId) return null;
    return root.querySelector('#' + actionsId);
  }
  function ensureActionsVisibility(name) {
    var panel = findActionsByName(name);
    if (!panel) return;
    var anyChecked = getRowChecksByName(name).some(function(b) { return b.checked; });
    panel.classList.toggle('d-none', !anyChecked);
  }

  function findPanelConfig(btn) {
    for (var panelId in FP_PANELS) {
      if (btn.closest('#' + panelId)) return FP_PANELS[panelId];
    }
    return null;
  }

  document.addEventListener('click', function(e) {
    var root = fpPane();
    if (!root) return;
    var btn = e.target.closest('button[data-panel-action]');
    if (!btn || !root.contains(btn)) return;

    var config = findPanelConfig(btn);
    if (!config) return;

    var action = btn.dataset.panelAction;
    var name = config.name;

    var checked = getCheckedByName(name);
    if (!checked.length) return;

    window.__fpTableSel[name] = checked.map(function(ch) { return String(ch.value); });

    if (action === 'edit') {
      var first = checked[0];
      var tr = first.closest('tr');
      var url = tr && tr.dataset.editUrl;
      if (!url) return;
      htmx.ajax('GET', url, { target: config.modal, swap: 'innerHTML' }).then(function() {
        var modalEl = document.getElementById(config.modalId);
        if (modalEl && window.bootstrap) {
          window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
      });
      ensureActionsVisibility(name);
      return;
    }

    if (action === 'delete') {
      if (!confirm('Удалить ' + checked.length + ' ' + config.deleteLabel + '?')) return;
      var urls = checked.map(function(ch) { return ch.closest('tr') && ch.closest('tr').dataset.deleteUrl; }).filter(Boolean);
      (function deleteSequential(i) {
        if (i >= urls.length) return;
        fetch(urls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } })
          .catch(function() {})
          .then(function() {
            if (i < urls.length - 1) {
              deleteSequential(i + 1);
            } else {
              htmx.trigger(document.body, 'field-params-updated');
            }
          });
      })(0);
      return;
    }

    if (action === 'up' || action === 'down') {
      var moveUrls = checked
        .map(function(ch) {
          var t = ch.closest('tr');
          return t && t.dataset[action === 'up' ? 'moveUpUrl' : 'moveDownUrl'];
        })
        .filter(Boolean);
      if (action === 'down') moveUrls = moveUrls.reverse();
      (function moveSequential(i) {
        if (i >= moveUrls.length) return;
        fetch(moveUrls[i], { method: 'POST', headers: { 'X-CSRFToken': csrftoken } })
          .catch(function() {})
          .then(function() {
            if (i < moveUrls.length - 1) {
              moveSequential(i + 1);
            } else {
              htmx.trigger(document.body, 'field-params-updated');
            }
          });
      })(0);
      return;
    }
  });

  document.addEventListener('change', function(e) {
    var root = fpPane();
    if (!root) return;
    var master = e.target.closest('input.form-check-input[data-actions-id][data-target-name]');
    if (master && root.contains(master)) {
      var name = master.dataset.targetName;
      var boxes = getRowChecksByName(name);
      boxes.forEach(function(b) { b.checked = master.checked; });
      master.indeterminate = false;
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
      return;
    }
    var rowCb = e.target.closest('tbody input.form-check-input[name]');
    if (rowCb && root.contains(rowCb)) {
      var cbName = rowCb.name;
      updateMasterStateFor(cbName);
      updateRowHighlightFor(cbName);
      ensureActionsVisibility(cbName);
      return;
    }
  });

  document.body.addEventListener('htmx:afterSettle', function(e) {
    if (!(e.target && e.target.id === 'field-params-pane')) return;
    var sel = window.__fpTableSel || {};
    for (var name in sel) {
      var ids = sel[name] || [];
      var set = {};
      ids.forEach(function(id) { set[id] = true; });
      getRowChecksByName(name).forEach(function(b) { b.checked = !!set[String(b.value)]; });
      updateMasterStateFor(name);
      updateRowHighlightFor(name);
      ensureActionsVisibility(name);
    }
    window.__fpTableSel = {};
  });
})();
