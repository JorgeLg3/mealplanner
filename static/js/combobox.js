// Styled autocomplete for any <input list="…">, replacing the browser's
// unstylable <datalist> popup. The <datalist> stays in the markup as the data
// source and as the no-JS fallback.
//
// - Enhanced lazily on first focus, so inputs added later (HTMX swaps, the
//   recipe form's "Add ingredient") work without extra wiring.
// - Case- and accent-insensitive substring match; the match is bolded.
// - ARIA combobox pattern: ↑/↓ move, Enter picks, Esc closes.
// - data-autosubmit on the input submits its form when an option is picked.
// - data-empty-text: message when nothing matches (omit to show nothing,
//   e.g. ingredients, where a new name is fine).
// - The list lives on <body> (positioned under the input) so scrolling or
//   overflow-hidden containers can't clip it.
(function () {
  const MAX_RESULTS = 50;
  let counter = 0;

  const fold = (text) =>
    text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

  function enhance(input) {
    const datalist = document.getElementById(input.getAttribute("list"));
    if (!datalist) return;
    const options = Array.from(datalist.options, (o) => o.value).filter(Boolean);
    input.removeAttribute("list"); // no native popup from now on
    input.dataset.comboboxReady = "true";

    const id = `combobox-${++counter}`;
    const list = document.createElement("ul");
    list.className = "combobox-list";
    list.id = id;
    list.setAttribute("role", "listbox");
    list.hidden = true;
    document.body.appendChild(list);

    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", id);

    let active = -1;
    let matches = [];

    function position() {
      const rect = input.getBoundingClientRect();
      list.style.left = `${rect.left + window.scrollX}px`;
      list.style.top = `${rect.bottom + window.scrollY + 4}px`;
      list.style.width = `${Math.max(rect.width, 200)}px`;
    }

    function close() {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }

    function setActive(index) {
      const items = list.querySelectorAll('[role="option"]');
      items.forEach((li, i) => li.setAttribute("aria-selected", String(i === index)));
      active = index;
      if (index >= 0 && items[index]) {
        input.setAttribute("aria-activedescendant", items[index].id);
        items[index].scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function render() {
      const query = fold(input.value.trim());
      matches = options
        .filter((value) => !query || fold(value).includes(query))
        .slice(0, MAX_RESULTS);
      list.replaceChildren();

      if (!matches.length) {
        if (!query || !input.dataset.emptyText) return close();
        const empty = document.createElement("li");
        empty.className = "combobox-list__empty";
        empty.textContent = input.dataset.emptyText;
        list.appendChild(empty);
      }

      matches.forEach((value, i) => {
        const li = document.createElement("li");
        li.id = `${id}-${i}`;
        li.className = "combobox-list__option";
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        // Bold the matched part. The folded text has the same length as the
        // original for these strings, so indexes line up.
        const start = query ? fold(value).indexOf(query) : -1;
        if (start >= 0) {
          li.append(value.slice(0, start));
          const mark = document.createElement("strong");
          mark.textContent = value.slice(start, start + query.length);
          li.append(mark, value.slice(start + query.length));
        } else {
          li.textContent = value;
        }
        // mousedown (not click) so the input doesn't blur first.
        li.addEventListener("mousedown", (event) => {
          event.preventDefault();
          pick(value);
        });
        list.appendChild(li);
      });

      position();
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      setActive(-1);
    }

    function pick(value) {
      input.value = value;
      close();
      input.dispatchEvent(new Event("change", { bubbles: true }));
      if (input.dataset.autosubmit !== undefined && input.form) {
        input.form.requestSubmit();
      }
    }

    input.addEventListener("input", render);
    input.addEventListener("focus", render);
    input.addEventListener("blur", close);
    input.addEventListener("keydown", (event) => {
      const open = !list.hidden && matches.length;
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (list.hidden) render();
        else if (matches.length) setActive((active + 1) % matches.length);
      } else if (event.key === "ArrowUp" && open) {
        event.preventDefault();
        setActive(active <= 0 ? matches.length - 1 : active - 1);
      } else if (event.key === "Enter" && open && active >= 0) {
        event.preventDefault(); // pick, don't submit with half-typed text
        pick(matches[active]);
      } else if (event.key === "Escape" && !list.hidden) {
        event.preventDefault();
        event.stopPropagation(); // don't also close a surrounding dialog/menu
        close();
      }
    });

    const reposition = () => !list.hidden && position();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);

    // Drop the list (and listeners) when HTMX swaps the input away.
    const cleanup = new MutationObserver(() => {
      if (!document.body.contains(input)) {
        list.remove();
        window.removeEventListener("resize", reposition);
        window.removeEventListener("scroll", reposition, true);
        cleanup.disconnect();
      }
    });
    cleanup.observe(document.body, { childList: true, subtree: true });
  }

  document.addEventListener("focusin", (event) => {
    const input = event.target;
    if (input.matches && input.matches("input[list]") && !input.dataset.comboboxReady) {
      enhance(input);
      // The focus event that triggered us has passed; show the list now.
      input.dispatchEvent(new Event("focus"));
    }
  });
})();
