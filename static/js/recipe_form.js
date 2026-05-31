// Adds extra inline-formset rows on demand by cloning the formset's empty_form
// blueprint and keeping the management form's TOTAL_FORMS counter in sync.
document.addEventListener("DOMContentLoaded", function () {
  const addButton = document.getElementById("add-ingredient");
  if (!addButton) return;

  const container = document.getElementById("ingredient-forms");
  const template = document.getElementById("empty-ingredient-form");
  const prefix = container.dataset.prefix;
  const totalForms = document.getElementById("id_" + prefix + "-TOTAL_FORMS");

  addButton.addEventListener("click", function () {
    const index = parseInt(totalForms.value, 10);
    const html = template.innerHTML.replace(/__prefix__/g, index);
    container.insertAdjacentHTML("beforeend", html);
    totalForms.value = index + 1;
  });
});
