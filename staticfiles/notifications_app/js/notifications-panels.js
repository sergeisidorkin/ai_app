(function () {
  if (window.__notificationsPanelBound) return;
  window.__notificationsPanelBound = true;

  function getCookie(name) {
    const match = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return match ? match.pop() : "";
  }

  function notificationsPane() {
    return document.getElementById("notifications-pane");
  }

  async function refreshCounters() {
    const pane = notificationsPane();
    const countersUrl = pane?.dataset?.countersUrl || document.body.dataset.notificationsCountersUrl;
    if (!countersUrl) return;
    try {
      const response = await fetch(countersUrl, { headers: { "X-Requested-With": "fetch" } });
      if (!response.ok) return;
      const data = await response.json();
      const total = Number(data.total || 0);
      document.querySelectorAll("[data-notification-counter-total]").forEach((node) => {
        node.textContent = String(total);
        node.classList.toggle("d-none", total <= 0);
      });

      const sections = data.sections || {};
      document.querySelectorAll("[data-notification-counter-section]").forEach((node) => {
        const key = node.dataset.notificationCounterSection || "";
        const value = Number(sections[key] || 0);
        node.textContent = String(value);
        node.classList.toggle("d-none", value <= 0);
      });
    } catch (_err) {
      // keep the last rendered counters if refresh fails
    }
  }

  async function postJson(url, payload) {
    const csrftoken = getCookie("csrftoken");
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrftoken,
        "X-Requested-With": "fetch",
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
      },
      body: new URLSearchParams(payload || {}),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data?.error || "Не удалось обработать уведомление.");
    }
    return data;
  }

  async function toggleNotificationCard(card, toggleBtn) {
    const details = card?.querySelector(".notification-card__details");
    const button = toggleBtn || card?.querySelector(".js-notification-toggle");
    const icon = button?.querySelector("i");
    if (!card || !details || !button) return;

    const willOpen = details.classList.contains("d-none");
    details.classList.toggle("d-none", !willOpen);
    button.setAttribute("aria-expanded", willOpen ? "true" : "false");
    if (icon) {
      icon.classList.toggle("bi-chevron-down", !willOpen);
      icon.classList.toggle("bi-chevron-up", willOpen);
    }

    if (willOpen && card.dataset.unread === "1") {
      const markReadUrl = button.dataset.markReadUrl;
      if (markReadUrl) {
        try {
          await postJson(markReadUrl, {});
          card.dataset.unread = "0";
          card.classList.remove("notification-card--unread");
          refreshCounters();
        } catch (_err) {
          // keep card open even if marking read failed
        }
      }
    }
  }

  document.addEventListener("click", async (event) => {
    const bellBtn = event.target.closest(".notifications-bell-btn");
    if (bellBtn) {
      const targetSelector = bellBtn.getAttribute("href");
      const tabLink = targetSelector
        ? document.querySelector(`a[href="${targetSelector}"][data-bs-toggle="tab"]`)
        : null;
      if (tabLink && window.bootstrap) {
        event.preventDefault();
        window.bootstrap.Tab.getOrCreateInstance(tabLink).show();
        return;
      }
    }

    const toggleBtn = event.target.closest(".js-notification-toggle");
    if (toggleBtn) {
      event.preventDefault();
      const card = toggleBtn.closest(".notification-card");
      await toggleNotificationCard(card, toggleBtn);
      return;
    }

    const cardRow = event.target.closest(".js-notification-row");
    if (cardRow) {
      const clickedAction = event.target.closest(".js-notification-action");
      const clickedButton = event.target.closest("button, a, input, textarea, select, label");
      if (!clickedAction && !clickedButton) {
        const card = cardRow.closest(".notification-card");
        await toggleNotificationCard(card);
      }
    }

    const actionBtn = event.target.closest(".js-notification-action");
    if (!actionBtn) return;

    event.preventDefault();
    if (actionBtn.disabled) return;
    const url = actionBtn.dataset.url;
    const action = actionBtn.dataset.action;
    if (!url || !action) return;
    if (action === "declined" && !window.confirm("Отклонить участие в проекте?")) return;

    actionBtn.disabled = true;
    try {
      await postJson(url, { action: action });
      document.body.dispatchEvent(new Event("notifications-updated"));
      document.body.dispatchEvent(new Event("performers-updated"));
    } catch (err) {
      alert(err.message || "Не удалось обработать уведомление.");
      actionBtn.disabled = false;
    }
  });

  document.addEventListener("DOMContentLoaded", refreshCounters);
  document.body.addEventListener("notifications-updated", refreshCounters);
})();
