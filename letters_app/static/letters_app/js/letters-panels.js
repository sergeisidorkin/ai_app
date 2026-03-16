(function () {
  'use strict';

  var quillLoaded = false;
  var quillLoading = false;
  var quillReadyCallbacks = [];
  var activeEditors = {};

  var QUILL_JS  = '/static/letters_app/vendor/quill/quill.min.js';
  var QUILL_CSS = '/static/letters_app/vendor/quill/quill.snow.css';
  var EMPLOYEES_SEARCH_URL = '/letters/employees/search/';

  /* ── Quill lazy loader ── */

  function loadQuill(callback) {
    if (quillLoaded) { callback(); return; }
    quillReadyCallbacks.push(callback);
    if (quillLoading) return;
    quillLoading = true;

    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = QUILL_CSS;
    document.head.appendChild(link);

    var script = document.createElement('script');
    script.src = QUILL_JS;
    script.onload = function () {
      quillLoaded = true;
      quillLoading = false;
      quillReadyCallbacks.forEach(function (cb) { cb(); });
      quillReadyCallbacks = [];
    };
    script.onerror = function () {
      quillLoading = false;
      console.error('Failed to load Quill.js');
    };
    document.body.appendChild(script);
  }

  /* ── Quill init / destroy ── */

  function initEditor(templateType) {
    var editorEl = document.getElementById('letter-editor-' + templateType);
    if (!editorEl || activeEditors[templateType]) return;

    var previewEl = document.getElementById('letter-preview-' + templateType);
    var html = previewEl ? previewEl.innerHTML.trim() : '';

    var quill = new Quill(editorEl, {
      theme: 'snow',
      modules: {
        toolbar: [
          ['bold', 'italic', 'underline'],
          [{ 'color': [] }, { 'background': [] }],
          [{ 'list': 'ordered' }, { 'list': 'bullet' }],
          ['clean'],
        ],
      },
    });

    var delta = quill.clipboard.convert({ html: html });
    quill.setContents(delta, 'silent');
    activeEditors[templateType] = quill;
  }

  function destroyEditor(templateType) {
    if (activeEditors[templateType]) {
      delete activeEditors[templateType];
    }
    var editorEl = document.getElementById('letter-editor-' + templateType);
    if (editorEl) {
      var toolbars = editorEl.parentElement.querySelectorAll('.ql-toolbar');
      toolbars.forEach(function (t) { t.remove(); });
      editorEl.innerHTML = '';
      editorEl.className = '';
    }
  }

  /* ── Show / hide editor ── */

  function showEditor(templateType) {
    var previewArea = document.getElementById('letter-preview-area-' + templateType);
    var wrapper = document.getElementById('letter-editor-wrapper-' + templateType);
    var actions = document.getElementById('letter-actions-' + templateType);
    if (previewArea) previewArea.classList.add('d-none');
    if (wrapper) wrapper.classList.remove('d-none');
    if (actions) actions.classList.add('d-none');
  }

  function hideEditor(templateType) {
    var previewArea = document.getElementById('letter-preview-area-' + templateType);
    var wrapper = document.getElementById('letter-editor-wrapper-' + templateType);
    var actions = document.getElementById('letter-actions-' + templateType);
    if (previewArea) previewArea.classList.remove('d-none');
    if (wrapper) wrapper.classList.add('d-none');
    if (actions) actions.classList.remove('d-none');
    destroyEditor(templateType);
  }

  /* ── CSRF helper ── */

  function getCsrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (!el) el = document.querySelector('meta[name="csrf-token"]');
    return el ? (el.value || el.content || '') : '';
  }

  /* ── CC tags helpers ── */

  function getCcUserIds(templateType) {
    var container = document.getElementById('letter-cc-tags-' + templateType);
    if (!container) return [];
    var ids = [];
    container.querySelectorAll('.letter-cc-tag').forEach(function (tag) {
      ids.push(tag.dataset.userId);
    });
    return ids;
  }

  function addCcTag(templateType, userId, name) {
    var container = document.getElementById('letter-cc-tags-' + templateType);
    var input = document.getElementById('letter-cc-input-' + templateType);
    if (!container) return;
    if (getCcUserIds(templateType).indexOf(String(userId)) !== -1) return;

    var tag = document.createElement('span');
    tag.className = 'badge fw-normal d-inline-flex align-items-center gap-1 py-2 px-2 letter-cc-badge letter-cc-tag';
    tag.dataset.userId = userId;
    tag.innerHTML = name +
      '<button type="button" class="btn-close btn-close-white ms-1 js-cc-remove" ' +
      'style="font-size: .55em;" aria-label="Удалить"></button>';
    container.insertBefore(tag, input);
  }

  function removeCcTag(btn) {
    var tag = btn.closest('.letter-cc-tag');
    if (tag) tag.remove();
  }

  /* ── CC dropdown search ── */

  var ccSearchTimer = null;

  function openCcDropdown(templateType, query) {
    var dropdown = document.getElementById('letter-cc-dropdown-' + templateType);
    if (!dropdown) return;

    fetch(EMPLOYEES_SEARCH_URL + '?q=' + encodeURIComponent(query))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var existing = getCcUserIds(templateType);
        var items = (data.results || []).filter(function (r) {
          return existing.indexOf(String(r.id)) === -1;
        });
        if (!items.length) {
          dropdown.classList.remove('show');
          return;
        }
        dropdown.innerHTML = '';
        items.forEach(function (emp) {
          var a = document.createElement('a');
          a.href = '#';
          a.className = 'dropdown-item js-cc-select';
          a.dataset.userId = emp.id;
          a.dataset.userName = emp.name;
          a.dataset.templateType = templateType;
          a.textContent = emp.name;
          dropdown.appendChild(a);
        });
        dropdown.classList.add('show');
      })
      .catch(function () { dropdown.classList.remove('show'); });
  }

  function closeCcDropdown(templateType) {
    var dropdown = document.getElementById('letter-cc-dropdown-' + templateType);
    if (dropdown) dropdown.classList.remove('show');
  }

  /* ── Event delegation ── */

  document.addEventListener('input', function (e) {
    var input = e.target.closest('.letter-cc-input');
    if (!input) return;
    var templateType = input.id.replace('letter-cc-input-', '');
    var q = input.value.trim();
    clearTimeout(ccSearchTimer);
    if (q.length < 1) {
      closeCcDropdown(templateType);
      return;
    }
    ccSearchTimer = setTimeout(function () {
      openCcDropdown(templateType, q);
    }, 250);
  });

  document.addEventListener('click', function (e) {
    /* CC: select from dropdown */
    var selectItem = e.target.closest('.js-cc-select');
    if (selectItem) {
      e.preventDefault();
      var tt = selectItem.dataset.templateType;
      addCcTag(tt, selectItem.dataset.userId, selectItem.dataset.userName);
      var inp = document.getElementById('letter-cc-input-' + tt);
      if (inp) inp.value = '';
      closeCcDropdown(tt);
      return;
    }

    /* CC: remove tag */
    var removeBtn = e.target.closest('.js-cc-remove');
    if (removeBtn) {
      removeCcTag(removeBtn);
      return;
    }

    /* Close CC dropdown on outside click */
    document.querySelectorAll('.letter-cc-dropdown.show').forEach(function (d) {
      if (!d.contains(e.target) && !e.target.closest('.letter-cc-input')) {
        d.classList.remove('show');
      }
    });

    /* User template row: toggle detail card */
    var tplRow = e.target.closest('.js-user-tpl-row');
    if (tplRow) {
      var targetId = tplRow.dataset.target;
      var detail = document.querySelector(targetId);
      if (detail) {
        var wasHidden = detail.classList.contains('d-none');
        detail.closest('.card-body').querySelectorAll('[id^="user-tpl-detail-"]').forEach(function (el) {
          el.classList.add('d-none');
        });
        tplRow.closest('tbody').querySelectorAll('.js-user-tpl-row').forEach(function (r) {
          r.classList.remove('table-active');
        });
        if (wasHidden) {
          detail.classList.remove('d-none');
          tplRow.classList.add('table-active');
        }
      }
      return;
    }

    /* Edit button */
    var editBtn = e.target.closest('.js-letter-edit');
    if (editBtn) {
      var type = editBtn.dataset.templateType;
      loadQuill(function () {
        showEditor(type);
        initEditor(type);
      });
      return;
    }

    /* Cancel button */
    var cancelBtn = e.target.closest('.js-letter-cancel');
    if (cancelBtn) {
      hideEditor(cancelBtn.dataset.templateType);
      return;
    }

    /* Save button */
    var saveBtn = e.target.closest('.js-letter-save');
    if (saveBtn) {
      var ttype = saveBtn.dataset.templateType;
      var quill = activeEditors[ttype];
      if (!quill) return;

      var bodyHtml = quill.root.innerHTML;
      var subjectInput = document.getElementById('letter-subject-input-' + ttype);
      var subjectValue = subjectInput ? subjectInput.value : '';
      var ccIds = getCcUserIds(ttype);
      var url = saveBtn.dataset.saveUrl;
      var cardEl = document.getElementById('letter-card-' + ttype);
      if (!cardEl) return;

      var token = getCsrfToken();
      var fd = new FormData();
      fd.append('subject_template', subjectValue);
      fd.append('body_html', bodyHtml);
      ccIds.forEach(function (id) { fd.append('cc_recipients[]', id); });
      fd.append('csrfmiddlewaretoken', token);

      saveBtn.disabled = true;
      fetch(url, { method: 'POST', body: fd, headers: { 'X-CSRFToken': token } })
        .then(function (r) {
          if (!r.ok) {
            return r.json().catch(function () { return { error: 'Ошибка сервера' }; }).then(function (data) {
              throw new Error(data.error || 'Ошибка сохранения (HTTP ' + r.status + ')');
            });
          }
          return r.text();
        })
        .then(function (html) {
          destroyEditor(ttype);
          cardEl.outerHTML = html;
        })
        .catch(function (err) {
          console.error('Save failed', err);
          alert(err.message || 'Не удалось сохранить шаблон.');
          saveBtn.disabled = false;
        });
      return;
    }

    /* Reset button */
    var resetBtn = e.target.closest('.js-letter-reset');
    if (resetBtn) {
      if (!confirm('Сбросить шаблон к общему? Ваш персональный шаблон будет удалён.')) return;
      var rtype = resetBtn.dataset.templateType;
      var rurl = resetBtn.dataset.resetUrl;
      var rcard = document.getElementById('letter-card-' + rtype);
      if (!rcard) return;

      var token2 = getCsrfToken();
      var fd2 = new FormData();
      fd2.append('csrfmiddlewaretoken', token2);

      fetch(rurl, { method: 'POST', body: fd2, headers: { 'X-CSRFToken': token2 } })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          destroyEditor(rtype);
          rcard.outerHTML = html;
        })
        .catch(function (err) { console.error('Reset failed', err); });
    }
  });
})();
