(function () {
  'use strict';

  var quillLoaded = false;
  var quillLoading = false;
  var quillReadyCallbacks = [];
  var activeEditors = {};

  var QUILL_JS  = '/static/letters_app/vendor/quill/quill.min.js';
  var QUILL_CSS = '/static/letters_app/vendor/quill/quill.snow.css';
  var EMPLOYEES_SEARCH_URL = '/letters/employees/search/';

  var LIST_MARKER_TYPES = ['bullet', 'dash', 'check'];
  var LIST_MARKER_LABELS = {
    bullet: 'Точка',
    dash: 'Дефис',
    check: 'Галочка',
  };
  var LIST_MARKER_ICON_URLS = {
    bullet: '/static/core/icons/list-ul2.svg',
    dash: '/static/core/icons/list-dash.svg',
    check: '/static/core/icons/list-check.svg',
  };

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

  function isListMarkerType(value) {
    return LIST_MARKER_TYPES.indexOf(String(value || '').trim()) !== -1;
  }

  function renderListMarkerPrimaryIcon(primary, activeMarker) {
    var iconSrc = LIST_MARKER_ICON_URLS[activeMarker] || LIST_MARKER_ICON_URLS.bullet;
    var icon = primary.querySelector('[data-list-marker-icon]');
    if (!icon || icon.tagName !== 'IMG') {
      primary.innerHTML = '<img src="' + iconSrc + '" alt="" class="proposal-service-text-toolbar__icon" data-list-marker-icon>';
    } else {
      icon.src = iconSrc;
      icon.className = 'proposal-service-text-toolbar__icon';
    }
  }

  function updateListMarkerControl(toolbar, listType) {
    if (!toolbar) return;
    var activeMarker = isListMarkerType(listType)
      ? String(listType)
      : (isListMarkerType(toolbar.dataset.listMarker) ? toolbar.dataset.listMarker : 'bullet');
    toolbar.dataset.listMarker = activeMarker;
    var primary = toolbar.querySelector('[data-list-marker-primary]');
    if (primary) {
      primary.dataset.list = activeMarker;
      primary.setAttribute('aria-label', LIST_MARKER_LABELS[activeMarker] || 'Маркированный список');
      primary.setAttribute('title', LIST_MARKER_LABELS[activeMarker] || 'Маркированный список');
      renderListMarkerPrimaryIcon(primary, activeMarker);
    }
    toolbar.querySelectorAll('[data-list-marker-option]').forEach(function (option) {
      var isSelected = option.dataset.list === activeMarker;
      option.classList.toggle('active', isSelected);
      option.setAttribute('aria-current', isSelected ? 'true' : 'false');
    });
  }

  function createLetterToolbar(editorEl) {
    var toolbar = document.createElement('div');
    toolbar.className = 'ql-toolbar ql-snow letter-quill-toolbar proposal-service-text-toolbar';
    toolbar.innerHTML =
      '<span class="ql-formats">' +
        '<button type="button" class="ql-bold" aria-label="Жирный"></button>' +
        '<button type="button" class="ql-italic" aria-label="Курсив"></button>' +
        '<button type="button" class="ql-underline" aria-label="Подчеркнутый"></button>' +
      '</span>' +
      '<span class="ql-formats">' +
        '<span class="proposal-service-text-toolbar__color-combo" data-color-combo="color">' +
          '<button type="button" class="btn btn-light btn-sm proposal-service-text-toolbar__btn proposal-service-text-toolbar__btn--combo" data-apply-color="color" aria-label="Применить цвет текста" title="Применить цвет текста"><i class="bi bi-palette"></i></button>' +
          '<button type="button" class="proposal-service-text-toolbar__color" data-color-toggle="color" title="Выбрать цвет текста" aria-label="Выбрать цвет текста" aria-expanded="false">' +
            '<span class="proposal-service-text-toolbar__color-swatch" data-color-preview="color" style="background:#000000;"></span>' +
          '</button>' +
          '<span class="proposal-service-text-toolbar__color-popover" data-color-popover="color" hidden>' +
            '<span class="proposal-service-text-toolbar__color-sv" data-color-sv="color"><span class="proposal-service-text-toolbar__color-sv-handle" data-color-sv-handle="color"></span></span>' +
            '<span class="proposal-service-text-toolbar__color-hue" data-color-hue="color" role="slider" tabindex="0" aria-label="Оттенок цвета текста" aria-valuemin="0" aria-valuemax="360" aria-valuenow="0"><span class="proposal-service-text-toolbar__color-hue-handle" data-color-hue-handle="color"></span></span>' +
            '<span class="proposal-service-text-toolbar__color-rgb">' +
              '<label><input type="number" min="0" max="255" value="0" data-color-rgb="color" data-color-channel="r"><span>R</span></label>' +
              '<label><input type="number" min="0" max="255" value="0" data-color-rgb="color" data-color-channel="g"><span>G</span></label>' +
              '<label><input type="number" min="0" max="255" value="0" data-color-rgb="color" data-color-channel="b"><span>B</span></label>' +
            '</span>' +
            '<span class="proposal-service-text-toolbar__color-actions">' +
              '<button type="button" class="btn btn-primary btn-sm flex-grow-1" data-color-commit="color">Применить</button>' +
              '<button type="button" class="btn btn-outline-secondary btn-sm proposal-service-text-toolbar__color-reset" data-color-reset="color" title="Сбросить цвет текста" aria-label="Сбросить цвет текста"><i class="bi bi-arrow-counterclockwise"></i></button>' +
            '</span>' +
          '</span>' +
        '</span>' +
        '<span class="proposal-service-text-toolbar__color-combo" data-color-combo="background">' +
          '<button type="button" class="btn btn-light btn-sm proposal-service-text-toolbar__btn proposal-service-text-toolbar__btn--combo" data-apply-color="background" aria-label="Применить цвет фона" title="Применить цвет фона"><i class="bi bi-paint-bucket"></i></button>' +
          '<button type="button" class="proposal-service-text-toolbar__color" data-color-toggle="background" title="Выбрать цвет фона" aria-label="Выбрать цвет фона" aria-expanded="false">' +
            '<span class="proposal-service-text-toolbar__color-swatch" data-color-preview="background" style="background:#ffffff;"></span>' +
          '</button>' +
          '<span class="proposal-service-text-toolbar__color-popover" data-color-popover="background" hidden>' +
            '<span class="proposal-service-text-toolbar__color-sv" data-color-sv="background"><span class="proposal-service-text-toolbar__color-sv-handle" data-color-sv-handle="background"></span></span>' +
            '<span class="proposal-service-text-toolbar__color-hue" data-color-hue="background" role="slider" tabindex="0" aria-label="Оттенок цвета фона" aria-valuemin="0" aria-valuemax="360" aria-valuenow="0"><span class="proposal-service-text-toolbar__color-hue-handle" data-color-hue-handle="background"></span></span>' +
            '<span class="proposal-service-text-toolbar__color-rgb">' +
              '<label><input type="number" min="0" max="255" value="255" data-color-rgb="background" data-color-channel="r"><span>R</span></label>' +
              '<label><input type="number" min="0" max="255" value="255" data-color-rgb="background" data-color-channel="g"><span>G</span></label>' +
              '<label><input type="number" min="0" max="255" value="255" data-color-rgb="background" data-color-channel="b"><span>B</span></label>' +
            '</span>' +
            '<span class="proposal-service-text-toolbar__color-actions">' +
              '<button type="button" class="btn btn-primary btn-sm flex-grow-1" data-color-commit="background">Применить</button>' +
              '<button type="button" class="btn btn-outline-secondary btn-sm proposal-service-text-toolbar__color-reset" data-color-reset="background" title="Сбросить цвет фона" aria-label="Сбросить цвет фона"><i class="bi bi-arrow-counterclockwise"></i></button>' +
            '</span>' +
          '</span>' +
        '</span>' +
      '</span>' +
      '<span class="ql-formats letter-quill-toolbar__list-group">' +
        '<button type="button" class="proposal-service-text-toolbar__btn" data-letter-list="ordered" data-list="ordered" aria-label="Нумерованный список" title="Нумерованный список"><img src="/static/core/icons/list-number.svg" alt="" class="proposal-service-text-toolbar__icon"></button>' +
      '</span>' +
      '<span class="ql-formats letter-quill-toolbar__marker-group">' +
        '<span class="proposal-service-text-toolbar__list-split dropdown" data-list-marker-control>' +
          '<button type="button" class="proposal-service-text-toolbar__btn proposal-service-text-toolbar__btn--list-primary" data-letter-list="marker" data-list="bullet" data-list-marker-primary aria-label="Маркированный список" title="Маркированный список"><img src="/static/core/icons/list-ul2.svg" alt="" class="proposal-service-text-toolbar__icon" data-list-marker-icon></button>' +
          '<button type="button" class="proposal-service-text-toolbar__btn proposal-service-text-toolbar__btn--list-toggle dropdown-toggle dropdown-toggle-split" data-bs-toggle="dropdown" data-bs-popper="static" data-bs-placement="bottom-start" data-bs-offset="0,2" aria-expanded="false" aria-label="Выбрать тип маркера"></button>' +
          '<ul class="dropdown-menu proposal-service-text-toolbar__list-menu">' +
            '<li><button type="button" class="dropdown-item" data-letter-list="marker-option" data-list="bullet" data-list-marker-option><span class="proposal-service-text-toolbar__marker-preview">•</span>Точка</button></li>' +
            '<li><button type="button" class="dropdown-item" data-letter-list="marker-option" data-list="dash" data-list-marker-option><span class="proposal-service-text-toolbar__marker-preview">-</span>Дефис</button></li>' +
            '<li><button type="button" class="dropdown-item" data-letter-list="marker-option" data-list="check" data-list-marker-option><span class="proposal-service-text-toolbar__marker-preview">✓</span>Галочка</button></li>' +
          '</ul>' +
        '</span>' +
      '</span>' +
      '<span class="ql-formats letter-quill-toolbar__clean-group">' +
        '<button type="button" class="ql-clean" aria-label="Очистить форматирование"></button>' +
      '</span>';
    editorEl.parentElement.insertBefore(toolbar, editorEl);
    return toolbar;
  }

  var COLOR_DEFAULTS = {
    color: '#000000',
    background: '#ffffff',
  };

  function normalizeToolbarColor(value, fallback) {
    var source = String(value || '').trim();
    if (!source) return fallback;
    if (/^#([0-9a-f]{3}){1,2}$/i.test(source)) {
      if (source.length === 4) {
        return '#' + source.slice(1).split('').map(function (part) { return part + part; }).join('');
      }
      return source;
    }
    var rgbMatch = source.match(/^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})/i);
    if (!rgbMatch) return fallback;
    return '#' + rgbMatch.slice(1, 4).map(function (part) {
      return Math.max(0, Math.min(255, Number(part) || 0)).toString(16).padStart(2, '0');
    }).join('');
  }

  function getColorDefault(kind) {
    return COLOR_DEFAULTS[kind] || '#000000';
  }

  function getColorDatasetKey(kind, state) {
    return state + (kind === 'background' ? 'BackgroundColor' : 'TextColor');
  }

  function clampColorChannel(value) {
    return Math.max(0, Math.min(255, Math.round(Number(value) || 0)));
  }

  function clampUnit(value) {
    return Math.max(0, Math.min(1, Number(value) || 0));
  }

  function hexToRgb(value) {
    var hex = normalizeToolbarColor(value, '#000000').slice(1);
    return {
      r: parseInt(hex.slice(0, 2), 16) || 0,
      g: parseInt(hex.slice(2, 4), 16) || 0,
      b: parseInt(hex.slice(4, 6), 16) || 0,
    };
  }

  function rgbToHex(rgb) {
    return '#' + ['r', 'g', 'b'].map(function (channel) {
      return clampColorChannel(rgb[channel]).toString(16).padStart(2, '0');
    }).join('');
  }

  function rgbToHsv(rgb) {
    var r = clampColorChannel(rgb.r) / 255;
    var g = clampColorChannel(rgb.g) / 255;
    var b = clampColorChannel(rgb.b) / 255;
    var max = Math.max(r, g, b);
    var min = Math.min(r, g, b);
    var delta = max - min;
    var hue = 0;
    if (delta) {
      if (max === r) hue = ((g - b) / delta) % 6;
      else if (max === g) hue = (b - r) / delta + 2;
      else hue = (r - g) / delta + 4;
      hue = Math.round(hue * 60);
      if (hue < 0) hue += 360;
    }
    return {
      h: hue,
      s: max === 0 ? 0 : delta / max,
      v: max,
    };
  }

  function hsvToRgb(hsv) {
    var h = ((Number(hsv.h) || 0) % 360 + 360) % 360;
    var s = clampUnit(hsv.s);
    var v = clampUnit(hsv.v);
    var c = v * s;
    var x = c * (1 - Math.abs((h / 60) % 2 - 1));
    var m = v - c;
    var r1 = 0;
    var g1 = 0;
    var b1 = 0;
    if (h < 60) {
      r1 = c;
      g1 = x;
    } else if (h < 120) {
      r1 = x;
      g1 = c;
    } else if (h < 180) {
      g1 = c;
      b1 = x;
    } else if (h < 240) {
      g1 = x;
      b1 = c;
    } else if (h < 300) {
      r1 = x;
      b1 = c;
    } else {
      r1 = c;
      b1 = x;
    }
    return {
      r: (r1 + m) * 255,
      g: (g1 + m) * 255,
      b: (b1 + m) * 255,
    };
  }

  function getAppliedToolbarColor(toolbar, kind) {
    var key = getColorDatasetKey(kind, 'applied');
    return normalizeToolbarColor(toolbar.dataset[key], getColorDefault(kind));
  }

  function getPendingToolbarColor(toolbar, kind) {
    var pendingKey = getColorDatasetKey(kind, 'pending');
    return normalizeToolbarColor(toolbar.dataset[pendingKey], getAppliedToolbarColor(toolbar, kind));
  }

  function updateColorPreviews(toolbar) {
    toolbar.querySelectorAll('[data-color-preview]').forEach(function (preview) {
      var kind = preview.dataset.colorPreview;
      preview.style.backgroundColor = getAppliedToolbarColor(toolbar, kind);
    });
  }

  function updateColorPickerControls(toolbar, kind, value) {
    var rgb = hexToRgb(value);
    var hsv = rgbToHsv(rgb);
    var previousHue = Number(toolbar.dataset[getColorDatasetKey(kind, 'hue')]);
    var hue = hsv.s === 0 && Number.isFinite(previousHue) ? previousHue : hsv.h;
    toolbar.dataset[getColorDatasetKey(kind, 'hue')] = String(hue);

    var hueInput = toolbar.querySelector('[data-color-hue="' + kind + '"]');
    if (hueInput) {
      hueInput.dataset.colorHueValue = String(Math.round(hue));
      hueInput.setAttribute('aria-valuenow', String(Math.round(hue)));
    }

    var hueHandle = toolbar.querySelector('[data-color-hue-handle="' + kind + '"]');
    if (hueHandle) hueHandle.style.left = (hue / 360 * 100) + '%';

    toolbar.querySelectorAll('[data-color-rgb="' + kind + '"]').forEach(function (input) {
      input.value = String(clampColorChannel(rgb[input.dataset.colorChannel]));
    });

    var sv = toolbar.querySelector('[data-color-sv="' + kind + '"]');
    if (sv) sv.style.setProperty('--proposal-color-picker-hue', String(Math.round(hue)));

    var handle = toolbar.querySelector('[data-color-sv-handle="' + kind + '"]');
    if (handle) {
      handle.style.left = (hsv.s * 100) + '%';
      handle.style.top = ((1 - hsv.v) * 100) + '%';
    }
  }

  function setToolbarColor(toolbar, kind, value, commit) {
    var normalized = normalizeToolbarColor(value, getColorDefault(kind));
    toolbar.dataset[getColorDatasetKey(kind, 'pending')] = normalized;
    if (commit) {
      toolbar.dataset[getColorDatasetKey(kind, 'applied')] = normalized;
    }
    updateColorPickerControls(toolbar, kind, normalized);
    updateColorPreviews(toolbar);
    return normalized;
  }

  function closeColorPopovers(toolbar, exceptKind) {
    toolbar.querySelectorAll('[data-color-popover]').forEach(function (popover) {
      var kind = popover.dataset.colorPopover;
      var keepOpen = exceptKind && kind === exceptKind;
      popover.hidden = !keepOpen;
      var toggle = toolbar.querySelector('[data-color-toggle="' + kind + '"]');
      if (toggle) toggle.setAttribute('aria-expanded', keepOpen ? 'true' : 'false');
    });
  }

  function openColorPopover(toolbar, kind) {
    var popover = toolbar.querySelector('[data-color-popover="' + kind + '"]');
    if (!popover) return;
    var shouldOpen = popover.hidden;
    closeColorPopovers(toolbar, shouldOpen ? kind : null);
    if (!shouldOpen) return;
    setToolbarColor(toolbar, kind, getAppliedToolbarColor(toolbar, kind), false);
  }

  function commitToolbarColor(toolbar, kind) {
    setToolbarColor(toolbar, kind, getPendingToolbarColor(toolbar, kind), true);
    closeColorPopovers(toolbar);
  }

  function resetToolbarColor(toolbar, kind) {
    setToolbarColor(toolbar, kind, getColorDefault(kind), false);
  }

  function initializeToolbarColors(toolbar) {
    ['color', 'background'].forEach(function (kind) {
      setToolbarColor(toolbar, kind, getColorDefault(kind), true);
    });
  }

  function updateColorFromSv(toolbar, kind, event) {
    var sv = toolbar.querySelector('[data-color-sv="' + kind + '"]');
    if (!sv) return;
    var rect = sv.getBoundingClientRect();
    var saturation = clampUnit((event.clientX - rect.left) / Math.max(1, rect.width));
    var value = clampUnit(1 - ((event.clientY - rect.top) / Math.max(1, rect.height)));
    var currentHsv = rgbToHsv(hexToRgb(getPendingToolbarColor(toolbar, kind)));
    var hue = Number(toolbar.dataset[getColorDatasetKey(kind, 'hue')]);
    if (!Number.isFinite(hue)) hue = currentHsv.h;
    setToolbarColor(toolbar, kind, rgbToHex(hsvToRgb({ h: hue, s: saturation, v: value })), false);
  }

  function updateColorFromHue(toolbar, kind, hue) {
    var currentHsv = rgbToHsv(hexToRgb(getPendingToolbarColor(toolbar, kind)));
    var saturation = currentHsv.s > 0.01 ? currentHsv.s : 1;
    var value = currentHsv.v > 0.01 ? currentHsv.v : 1;
    setToolbarColor(toolbar, kind, rgbToHex(hsvToRgb({
      h: Number(hue) || 0,
      s: saturation,
      v: value,
    })), false);
  }

  function updateColorFromHueStrip(toolbar, kind, event) {
    var strip = toolbar.querySelector('[data-color-hue="' + kind + '"]');
    if (!strip) return;
    var rect = strip.getBoundingClientRect();
    var ratio = clampUnit((event.clientX - rect.left) / Math.max(1, rect.width));
    updateColorFromHue(toolbar, kind, ratio * 360);
  }

  function updateColorFromRgb(toolbar, kind) {
    var rgb = { r: 0, g: 0, b: 0 };
    toolbar.querySelectorAll('[data-color-rgb="' + kind + '"]').forEach(function (input) {
      rgb[input.dataset.colorChannel] = clampColorChannel(input.value);
    });
    setToolbarColor(toolbar, kind, rgbToHex(rgb), false);
  }

  function syncLetterListToolbar(toolbar, quill, lastRange) {
    var format = quill.getFormat(lastRange || quill.getSelection() || undefined);
    var currentList = String(format.list || '');
    updateListMarkerControl(toolbar, currentList);
    toolbar.querySelectorAll('[data-letter-list]').forEach(function (button) {
      if (button.dataset.listMarkerOption) return;
      var isActive = currentList === button.dataset.list;
      button.classList.toggle('is-active', isActive);
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  function attachLetterListToolbar(toolbar, quill) {
    var lastRange = null;
    var colorDragKind = null;

    function restoreSelection() {
      quill.focus();
      if (lastRange) {
        quill.setSelection(lastRange.index, lastRange.length, 'silent');
      } else {
        quill.getSelection(true);
      }
    }

    toolbar.addEventListener('click', function (event) {
      var colorToggle = event.target.closest('button[data-color-toggle]');
      if (colorToggle && toolbar.contains(colorToggle)) {
        event.preventDefault();
        openColorPopover(toolbar, colorToggle.dataset.colorToggle);
        return;
      }
      var colorCommit = event.target.closest('button[data-color-commit]');
      if (colorCommit && toolbar.contains(colorCommit)) {
        event.preventDefault();
        commitToolbarColor(toolbar, colorCommit.dataset.colorCommit);
        return;
      }
      var colorReset = event.target.closest('button[data-color-reset]');
      if (colorReset && toolbar.contains(colorReset)) {
        event.preventDefault();
        resetToolbarColor(toolbar, colorReset.dataset.colorReset);
        return;
      }
      var applyColor = event.target.closest('button[data-apply-color]');
      if (applyColor && toolbar.contains(applyColor)) {
        event.preventDefault();
        restoreSelection();
        quill.format(applyColor.dataset.applyColor, getAppliedToolbarColor(toolbar, applyColor.dataset.applyColor));
        syncLetterListToolbar(toolbar, quill, lastRange);
        return;
      }
      var button = event.target.closest('[data-letter-list]');
      if (!button || !toolbar.contains(button)) return;
      event.preventDefault();
      restoreSelection();
      var listType = button.dataset.list;
      var currentList = quill.getFormat().list || false;
      var toggleCurrent = !button.dataset.listMarkerOption && currentList === listType;
      if (isListMarkerType(listType)) updateListMarkerControl(toolbar, listType);
      quill.format('list', toggleCurrent ? false : listType);
      syncLetterListToolbar(toolbar, quill, lastRange);
    });
    toolbar.addEventListener('input', function (event) {
      var rgbInput = event.target.closest('[data-color-rgb]');
      if (rgbInput && toolbar.contains(rgbInput)) {
        updateColorFromRgb(toolbar, rgbInput.dataset.colorRgb);
      }
    });
    toolbar.addEventListener('pointerdown', function (event) {
      var hue = event.target.closest('[data-color-hue]');
      if (hue && toolbar.contains(hue)) {
        event.preventDefault();
        colorDragKind = 'hue:' + hue.dataset.colorHue;
        updateColorFromHueStrip(toolbar, hue.dataset.colorHue, event);
        return;
      }
      var sv = event.target.closest('[data-color-sv]');
      if (!sv || !toolbar.contains(sv)) return;
      event.preventDefault();
      colorDragKind = sv.dataset.colorSv;
      updateColorFromSv(toolbar, colorDragKind, event);
    });
    document.addEventListener('pointermove', function (event) {
      if (!colorDragKind || !document.body.contains(toolbar)) return;
      event.preventDefault();
      if (colorDragKind.indexOf('hue:') === 0) {
        updateColorFromHueStrip(toolbar, colorDragKind.slice(4), event);
        return;
      }
      updateColorFromSv(toolbar, colorDragKind, event);
    });
    document.addEventListener('pointerup', function () {
      colorDragKind = null;
    });
    document.addEventListener('click', function (event) {
      if (!document.body.contains(toolbar)) return;
      if (!toolbar.contains(event.target)) closeColorPopovers(toolbar);
    });
    document.addEventListener('keydown', function (event) {
      if (!document.body.contains(toolbar)) return;
      if (event.key === 'Escape') {
        closeColorPopovers(toolbar);
        return;
      }
      var hue = event.target.closest && event.target.closest('[data-color-hue]');
      if (!hue || !toolbar.contains(hue)) return;
      var delta = event.key === 'ArrowRight' || event.key === 'ArrowUp'
        ? 5
        : (event.key === 'ArrowLeft' || event.key === 'ArrowDown' ? -5 : 0);
      if (!delta) return;
      event.preventDefault();
      var current = Number(hue.dataset.colorHueValue) || 0;
      updateColorFromHue(toolbar, hue.dataset.colorHue, current + delta);
    });
    quill.on('selection-change', function (range) {
      if (range) lastRange = range;
      syncLetterListToolbar(toolbar, quill, lastRange);
    });
    quill.on('text-change', function () {
      syncLetterListToolbar(toolbar, quill, lastRange);
    });
    updateListMarkerControl(toolbar, 'bullet');
    initializeToolbarColors(toolbar);
    syncLetterListToolbar(toolbar, quill, lastRange);
  }

  function initEditor(templateType) {
    var editorEl = document.getElementById('letter-editor-' + templateType);
    if (!editorEl || activeEditors[templateType]) return;

    var previewEl = document.getElementById('letter-preview-' + templateType);
    var html = previewEl ? previewEl.innerHTML.trim() : '';
    var toolbar = createLetterToolbar(editorEl);

    var quill = new Quill(editorEl, {
      theme: 'snow',
      modules: {
        toolbar: toolbar,
      },
    });

    var delta = quill.clipboard.convert({ html: html });
    quill.setContents(delta, 'silent');
    attachLetterListToolbar(toolbar, quill);
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
