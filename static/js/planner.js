// Mobile planner: keep the sticky day strip in sync with the day in view, and
// scroll to a day when its strip item is tapped. Only the first (selected)
// week has strip items; desktop hides the strip, so nothing happens there.
(function () {
  const bar = document.getElementById("week-bar");
  if (!bar) return;
  const strip = bar.querySelector(".day-strip");
  const items = new Map(
    Array.from(strip.querySelectorAll("[data-day]")).map((a) => [a.dataset.day, a])
  );
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let observer = null;
  const visible = new Set();

  function setActive(day) {
    items.forEach((a, key) => {
      const active = key === day;
      a.classList.toggle("is-active", active);
      if (active) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
  }

  function sections() {
    return Array.from(document.querySelectorAll(".day[data-day]")).filter((s) =>
      items.has(s.dataset.day)
    );
  }

  // A day is "current" while it crosses a thin band just under the sticky
  // bar; when several do, the earliest in the week wins.
  function observe() {
    if (observer) observer.disconnect();
    visible.clear();
    const offset = Math.round(bar.getBoundingClientRect().height);
    observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) visible.add(e.target.dataset.day);
          else visible.delete(e.target.dataset.day);
        });
        const first = sections().find((s) => visible.has(s.dataset.day));
        if (first) setActive(first.dataset.day);
      },
      { rootMargin: `-${offset}px 0px -55% 0px`, threshold: 0 }
    );
    sections().forEach((s) => observer.observe(s));
  }

  strip.addEventListener("click", (event) => {
    const link = event.target.closest("[data-day]");
    if (!link) return;
    const target = document.getElementById("day-" + link.dataset.day);
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
    setActive(link.dataset.day);
    history.replaceState(null, "", "#day-" + link.dataset.day);
  });

  // Start on today if it's in this week, otherwise Monday.
  const today = strip.querySelector(".is-today");
  setActive(today ? today.dataset.day : strip.querySelector("[data-day]").dataset.day);

  observe();
  // HTMX replaces whole week panels (import/export) and slots: re-observe.
  document.body.addEventListener("htmx:afterSettle", observe);
  // Mobile browsers fire resize while the URL bar slides; debounce it.
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(observe, 200);
  });
})();
