// Small app-wide behaviours. Everything here is progressive: pages work
// without it, this just smooths the HTMX flows and the <details> menus.
(function () {
  // ---------- Feedback when an HTMX request fails ----------
  const toast = document.getElementById("toast");
  let toastTimer;

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast.hidden = true), 5000);
  }

  document.body.addEventListener("htmx:responseError", () =>
    showToast("Something went wrong. Please try again.")
  );
  document.body.addEventListener("htmx:sendError", () =>
    showToast("Couldn't reach the server. Check your connection.")
  );

  // ---------- Expired session ----------
  // A login_required endpoint answers an HTMX call with a redirect to the
  // login page; XHR follows it silently. Go there properly instead of
  // swapping the login page into a meal slot or todo row.
  document.body.addEventListener("htmx:beforeSwap", (event) => {
    const url = event.detail.xhr && event.detail.xhr.responseURL;
    if (url && new URL(url).pathname.startsWith("/auth/login/")) {
      event.detail.shouldSwap = false;
      window.location.href = url;
    }
  });

  // ---------- <details> menus close on outside click / Escape ----------
  document.addEventListener("click", (event) => {
    document.querySelectorAll("details.menu[open]").forEach((menu) => {
      if (!menu.contains(event.target)) menu.removeAttribute("open");
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll("details.menu[open]").forEach((menu) => {
      menu.removeAttribute("open");
      const summary = menu.querySelector("summary");
      if (summary && menu.contains(document.activeElement)) summary.focus();
    });
  });

  // Picking an item inside a menu closes it too.
  document.addEventListener("click", (event) => {
    // (Controls like a stepper inside a menu panel keep it open.)
    const item = event.target.closest(
      ".menu__items button:not(.stepper__btn), .menu__items a"
    );
    if (item) {
      const menu = item.closest("details.menu");
      if (menu) menu.removeAttribute("open");
    }
  });
})();
