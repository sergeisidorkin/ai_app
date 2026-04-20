(function () {
  var P = window.UIPref;
  if (!P) return;
  var SECOND_SIDEBAR_PREF_KEY = 'second-sidebar:collapsed';

  /* ── Sidebar collapsed state ───────────────────────── */

  function getSidebar() {
    return document.getElementById('sidebar');
  }

  function ensureSecondSidebarToggles() {
    document.querySelectorAll('.second-sidebar').forEach(function (sidebar) {
      var spacer = sidebar.querySelector('.second-sidebar-header-spacer');
      if (!spacer || spacer.querySelector('.second-sidebar-toggle')) return;

      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'second-sidebar-toggle';
      button.setAttribute('title', 'Свернуть меню второго уровня');
      button.setAttribute('aria-label', 'Свернуть меню второго уровня');
      button.innerHTML = '<i class="bi bi-chevron-left" aria-hidden="true"></i>';
      spacer.appendChild(button);
    });
  }

  function setSidebarCollapsed(collapsed) {
    var sidebar = getSidebar();
    if (sidebar) sidebar.classList.toggle('is-collapsed', collapsed);

    var toggle = document.getElementById('sidebarToggle');
    var icon = toggle && toggle.querySelector('[data-chevron]');
    if (icon) icon.classList.toggle('rotate-180', collapsed);
    if (toggle) {
      var action = collapsed ? 'Развернуть' : 'Свернуть';
      toggle.setAttribute('title', action + ' меню');
      toggle.setAttribute('aria-label', action + ' меню');
    }
  }

  function setSecondSidebarCollapsed(collapsed) {
    document.body.classList.toggle('second-sidebar-collapsed', collapsed);
  }

  function restoreSidebar() {
    ensureSecondSidebarToggles();
    setSecondSidebarCollapsed(P.get(SECOND_SIDEBAR_PREF_KEY, false));
    setSidebarCollapsed(P.get('sidebar:collapsed', false));
  }

  function bindSidebar() {
    var toggle = document.getElementById('sidebarToggle');
    if (!toggle || toggle.__prefBound) return;
    toggle.__prefBound = true;
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      var sidebar = getSidebar();
      if (!sidebar) return;
      var collapsed = !sidebar.classList.contains('is-collapsed');
      setSidebarCollapsed(collapsed);
      P.set('sidebar:collapsed', collapsed);
      if (!collapsed) {
        setSecondSidebarCollapsed(false);
        P.set(SECOND_SIDEBAR_PREF_KEY, false);
      }
    });
  }

  function bindSecondSidebarToggles() {
    document.querySelectorAll('.second-sidebar-toggle').forEach(function (toggle) {
      if (toggle.__prefBound) return;
      toggle.__prefBound = true;
      toggle.addEventListener('click', function (e) {
        e.preventDefault();
        setSecondSidebarCollapsed(true);
        setSidebarCollapsed(true);
        P.set(SECOND_SIDEBAR_PREF_KEY, true);
        P.set('sidebar:collapsed', true);
      });
    });
  }

  /* ── Main tab (saved preference; URL hash takes priority) */

  function restoreMainTab() {
    if (window.location.hash) return;
    var tab = P.get('main:tab', null);
    if (!tab) return;
    var link = document.querySelector('a[href="' + tab + '"][data-bs-toggle="tab"]');
    if (link && window.bootstrap) {
      window.bootstrap.Tab.getOrCreateInstance(link).show();
    }
  }

  function bindMainTabs() {
    document.querySelectorAll('#sidebar a[data-bs-toggle="tab"]').forEach(function (el) {
      if (el.__prefBound) return;
      el.__prefBound = true;
      el.addEventListener('shown.bs.tab', function () {
        P.set('main:tab', el.getAttribute('href'));
      });
    });
  }

  /* ── Bootstrap ─────────────────────────────────────── */

  function restoreAll() {
    restoreSidebar();
    restoreMainTab();
  }

  function bindAll() {
    ensureSecondSidebarToggles();
    bindSidebar();
    bindSecondSidebarToggles();
    bindMainTabs();
  }

  document.addEventListener('DOMContentLoaded', function () {
    restoreAll();
    bindAll();
  });

  document.body.addEventListener('htmx:afterSettle', function () {
    restoreSidebar();
    bindAll();
  });
})();
