(function () {
  var P = window.UIPref;
  if (!P) return;

  /* ── Sidebar collapsed state ───────────────────────── */

  function restoreSidebar() {
    var collapsed = P.get('sidebar:collapsed', false);
    var sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.toggle('is-collapsed', collapsed);
    var icon = document.querySelector('#sidebarToggle [data-chevron]');
    if (icon) icon.classList.toggle('rotate-180', collapsed);
  }

  function bindSidebar() {
    var toggle = document.getElementById('sidebarToggle');
    if (!toggle || toggle.__prefBound) return;
    toggle.__prefBound = true;
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      var sidebar = document.getElementById('sidebar');
      if (!sidebar) return;
      sidebar.classList.toggle('is-collapsed');
      var icon = toggle.querySelector('[data-chevron]');
      if (icon) icon.classList.toggle('rotate-180');
      P.set('sidebar:collapsed', sidebar.classList.contains('is-collapsed'));
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
    bindSidebar();
    bindMainTabs();
  }

  document.addEventListener('DOMContentLoaded', function () {
    restoreAll();
    bindAll();
  });

  document.body.addEventListener('htmx:afterSettle', function () {
    bindAll();
  });
})();
