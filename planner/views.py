import datetime
from collections import Counter

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_http_methods
from django.views.generic import (
    CreateView,
    DeleteView,
    UpdateView,
    ListView,
    DetailView,
    TemplateView,
)
from recipes.models import Recipe, RecipeIngredient
from todo.models import Subtask, Todo
from .models import TemplateWeek, TemplateMeal, MealType, Weekday, CalendarMeal


def build_days(meals):
    """Reshape a flat iterable of TemplateMeals into one entry per weekday
    (Mon–Sun), so a template can render a grid."""
    lookup = {(meal.weekday, meal.meal_type): meal for meal in meals}
    return [
        {
            "value": day.value,
            "label": day.label,
            "lunch": lookup.get((day.value, MealType.LUNCH)),
            "dinner": lookup.get((day.value, MealType.DINNER)),
        }
        for day in Weekday
    ]


def monday_of(date):
    """Return the Monday on or before the given date."""
    return date - datetime.timedelta(days=date.weekday())


class TemplateWeekList(ListView):
    model = TemplateWeek
    template_name = "planner/templateweek_list.html"
    queryset = TemplateWeek.objects.order_by("name").prefetch_related("meals__recipe")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Each template carries its own grid for the collapsible preview.
        context["templates"] = [
            {"template": template, "days": build_days(meals), "meal_count": len(meals)}
            for template in context["templateweek_list"]
            for meals in [list(template.meals.all())]
        ]
        context["slot_count"] = len(Weekday) * len(MealType)
        return context


class TemplateWeekCreate(LoginRequiredMixin, CreateView):
    """Start an empty template by name; meals are filled in on its page.
    (Templates can also be created from a planner week: "Save as new".)"""

    model = TemplateWeek
    fields = ["name", "description"]
    template_name = "planner/templateweek_form.html"

    def get_success_url(self):
        return reverse("templateweek_detail", args=[self.object.pk])


class TemplateWeekUpdate(LoginRequiredMixin, UpdateView):
    """Rename / re-describe a template. Meals are edited on its page."""

    model = TemplateWeek
    fields = ["name", "description"]
    template_name = "planner/templateweek_form.html"

    def get_success_url(self):
        return reverse("templateweek_detail", args=[self.object.pk])


class TemplateWeekDelete(LoginRequiredMixin, DeleteView):
    """Delete a template and its meals (CASCADE). Planner weeks it was applied
    to keep their meals: applying copies them into the calendar."""

    model = TemplateWeek
    template_name = "planner/templateweek_confirm_delete.html"
    success_url = reverse_lazy("templateweek_list")


class TemplateWeekDetail(DetailView):
    model = TemplateWeek
    template_name = "planner/templateweek_detail.html"
    queryset = TemplateWeek.objects.prefetch_related("meals__recipe")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        meals = list(self.object.meals.all())
        context["days"] = build_days(meals)
        context["meal_count"] = len(meals)
        context["slot_count"] = len(Weekday) * len(MealType)
        return context


def _meal_label(meal_type):
    return MealType(meal_type).label


def _cell_context(templateweek, weekday, meal_type, meal=None):
    return {
        "templateweek_pk": templateweek.pk,
        "weekday": weekday,
        "weekday_label": Weekday(weekday).label if weekday in Weekday.values else "",
        "meal_type": meal_type,
        "meal_type_label": _meal_label(meal_type),
        "meal": meal,
    }


def _validate_slot(pk, weekday, meal_type):
    """Resolve the TemplateWeek and reject unknown weekday/meal_type values."""
    templateweek = get_object_or_404(TemplateWeek, pk=pk)
    if weekday not in Weekday.values or meal_type not in MealType.values:
        return None
    return templateweek


@login_required
@require_http_methods(["GET"])
def templatemeal_cell(request, pk, weekday, meal_type):
    """Return the cell in its current state. Used by the form's Cancel button."""
    templateweek = _validate_slot(pk, weekday, meal_type)
    if templateweek is None:
        return HttpResponseNotAllowed(["GET"])
    meal = (
        TemplateMeal.objects.filter(
            template=templateweek, weekday=weekday, meal_type=meal_type
        )
        .select_related("recipe")
        .first()
    )
    return render(
        request,
        "planner/_meal_cell.html",
        _cell_context(templateweek, weekday, meal_type, meal),
    )


@login_required
@require_http_methods(["GET"])
def templatemeal_form(request, pk, weekday, meal_type):
    """Return the add/swap form partial. The input is intentionally empty even
    when the slot is filled — swap means pick something new; Cancel re-renders
    the cell to recover the current meal."""
    templateweek = _validate_slot(pk, weekday, meal_type)
    if templateweek is None:
        return HttpResponseNotAllowed(["GET"])
    context = _cell_context(templateweek, weekday, meal_type)
    context["recipes"] = Recipe.objects.order_by("name")
    return render(request, "planner/_meal_form.html", context)


@login_required
@require_http_methods(["POST", "DELETE"])
def templatemeal(request, pk, weekday, meal_type):
    """POST creates the meal from the submitted recipe name; DELETE removes it.
    Both return the cell partial in its new state for HTMX to swap in."""
    templateweek = _validate_slot(pk, weekday, meal_type)
    if templateweek is None:
        return HttpResponseNotAllowed(["POST", "DELETE"])

    if request.method == "DELETE":
        TemplateMeal.objects.filter(
            template=templateweek, weekday=weekday, meal_type=meal_type
        ).delete()
        return render(
            request,
            "planner/_meal_cell.html",
            _cell_context(templateweek, weekday, meal_type),
        )

    # POST: create (or replace) the meal for this slot.
    recipe_name = (request.POST.get("recipe") or "").strip()
    recipe = (
        Recipe.objects.filter(name__iexact=recipe_name).first() if recipe_name else None
    )
    if recipe is None:
        context = _cell_context(templateweek, weekday, meal_type)
        context["recipes"] = Recipe.objects.order_by("name")
        context["error"] = "Pick a recipe from the list."
        return render(request, "planner/_meal_form.html", context)

    meal, _ = TemplateMeal.objects.update_or_create(
        template=templateweek,
        weekday=weekday,
        meal_type=meal_type,
        defaults={"recipe": recipe},
    )
    return render(
        request,
        "planner/_meal_cell.html",
        _cell_context(templateweek, weekday, meal_type, meal),
    )


class PlannerCalendar(TemplateView):
    """One week at a time (``?week=`` any ISO date; defaults to this week),
    on every screen size; the arrows move between weeks."""

    template_name = "planner/calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        this_monday = monday_of(datetime.date.today())
        try:
            selected = monday_of(datetime.date.fromisoformat(self.request.GET["week"]))
        except KeyError, ValueError:
            selected = this_monday

        context["days"] = _week_days(selected)
        context["selected_monday"] = selected
        context["selected_sunday"] = selected + datetime.timedelta(days=6)
        context["prev_monday"] = selected - datetime.timedelta(weeks=1)
        context["next_monday"] = selected + datetime.timedelta(weeks=1)
        context["this_monday"] = this_monday
        context["templates"] = TemplateWeek.objects.order_by("name")
        return context


def _calendar_cell_context(date, meal_type, meal=None):
    return {
        "date": date,
        "meal_type": meal_type,
        "meal_type_label": _meal_label(meal_type),
        "meal": meal,
    }


def _validate_calendar_slot(date_str, meal_type):
    """Parse the ISO date and reject unknown meal_type values."""
    try:
        date = datetime.date.fromisoformat(date_str)
    except ValueError:
        return None
    if meal_type not in MealType.values:
        return None
    return date


@login_required
@require_http_methods(["GET"])
def calendarmeal_cell(request, date, meal_type):
    """Return the cell in its current state. Used by the form's Cancel button."""
    date = _validate_calendar_slot(date, meal_type)
    if date is None:
        return HttpResponseNotAllowed(["GET"])
    meal = (
        CalendarMeal.objects.filter(date=date, meal_type=meal_type)
        .select_related("recipe")
        .first()
    )
    return render(
        request,
        "planner/_calendar_cell.html",
        _calendar_cell_context(date, meal_type, meal),
    )


@login_required
@require_http_methods(["GET"])
def calendarmeal_form(request, date, meal_type):
    """Return the add/swap form partial. The input is intentionally empty even
    when the slot is filled — swap means pick something new; Cancel re-renders
    the cell to recover the current meal."""
    date = _validate_calendar_slot(date, meal_type)
    if date is None:
        return HttpResponseNotAllowed(["GET"])
    context = _calendar_cell_context(date, meal_type)
    context["recipes"] = Recipe.objects.order_by("name")
    return render(request, "planner/_calendar_form.html", context)


@login_required
@require_http_methods(["POST", "DELETE"])
def calendarmeal(request, date, meal_type):
    """POST creates (or replaces) the meal for this slot from the submitted
    recipe name; DELETE removes it. Both return the cell partial in its new
    state for HTMX to swap in."""
    date = _validate_calendar_slot(date, meal_type)
    if date is None:
        return HttpResponseNotAllowed(["POST", "DELETE"])

    if request.method == "DELETE":
        CalendarMeal.objects.filter(date=date, meal_type=meal_type).delete()
        return render(
            request,
            "planner/_calendar_cell.html",
            _calendar_cell_context(date, meal_type),
        )

    # POST: create (or replace) the meal for this slot.
    recipe_name = (request.POST.get("recipe") or "").strip()
    recipe = (
        Recipe.objects.filter(name__iexact=recipe_name).first() if recipe_name else None
    )
    if recipe is None:
        context = _calendar_cell_context(date, meal_type)
        context["recipes"] = Recipe.objects.order_by("name")
        context["error"] = "Pick a recipe from the list."
        return render(request, "planner/_calendar_form.html", context)

    meal, _ = CalendarMeal.objects.update_or_create(
        date=date,
        meal_type=meal_type,
        defaults={"recipe": recipe},
    )
    return render(
        request,
        "planner/_calendar_cell.html",
        _calendar_cell_context(date, meal_type, meal),
    )


def _week_dates(monday):
    """The seven dates of the Mon–Sun week starting at ``monday``."""
    return [monday + datetime.timedelta(days=offset) for offset in range(7)]


def _parse_monday(monday_str):
    """Parse the ISO date from the URL; 404 unless it's a Monday."""
    try:
        monday = datetime.date.fromisoformat(monday_str)
    except ValueError:
        raise Http404("Invalid week.")
    if monday.weekday() != 0:
        raise Http404("Weeks start on Monday.")
    return monday


def _week_days(monday):
    """Render-ready day dicts (date + lunch/dinner CalendarMeal) for the grid."""
    dates = _week_dates(monday)
    meals_by_slot = {
        (m.date, m.meal_type): m
        for m in CalendarMeal.objects.filter(date__in=dates).select_related("recipe")
    }
    today = datetime.date.today()
    return [
        {
            "date": date,
            "is_today": date == today,
            "lunch": meals_by_slot.get((date, MealType.LUNCH)),
            "dinner": meals_by_slot.get((date, MealType.DINNER)),
        }
        for date in dates
    ]


def _render_week(
    request, monday, action=None, message="", error="", message_link=None, **extra
):
    """Re-render one week's whole region (grid + action bar). Every
    import/export endpoint returns this so a single #week-<monday> swap keeps
    the meals and the action bar in sync."""
    return render(
        request,
        "planner/_week.html",
        {
            "monday": monday,
            "days": _week_days(monday),
            "action": action,
            "message": message,
            "message_link": message_link,
            "error": error,
            "this_monday": monday_of(datetime.date.today()),
            "templates": TemplateWeek.objects.order_by("name"),
            **extra,
        },
    )


@login_required
@require_http_methods(["GET"])
def week_actions(request, monday):
    """Reset the action bar to its buttons (used by each form's Cancel)."""
    monday = _parse_monday(monday)
    return _render_week(request, monday)


@login_required
@require_http_methods(["GET"])
def week_apply_form(request, monday):
    monday = _parse_monday(monday)
    return _render_week(request, monday, action="apply")


@login_required
@require_http_methods(["GET"])
def week_save_form(request, monday):
    monday = _parse_monday(monday)
    return _render_week(request, monday, action="save")


@login_required
@require_http_methods(["GET"])
def week_update_form(request, monday):
    monday = _parse_monday(monday)
    return _render_week(request, monday, action="update")


def _copy_week_into_template(template, dates):
    """Replace a template's meals with snapshots of the given week's meals."""
    template.meals.all().delete()
    TemplateMeal.objects.bulk_create(
        [
            TemplateMeal(
                template=template,
                weekday=meal.date.weekday() + 1,
                meal_type=meal.meal_type,
                recipe=meal.recipe,
            )
            for meal in CalendarMeal.objects.filter(date__in=dates).select_related(
                "recipe"
            )
        ]
    )


@login_required
@require_http_methods(["POST"])
def week_apply_template(request, monday):
    """Import: replace this week's meals with a template's meals."""
    monday = _parse_monday(monday)
    template = TemplateWeek.objects.filter(pk=request.POST.get("template") or 0).first()
    if template is None:
        return _render_week(request, monday, action="apply", error="Pick a template.")
    dates = _week_dates(monday)
    CalendarMeal.objects.filter(date__in=dates).delete()
    CalendarMeal.objects.bulk_create(
        [
            CalendarMeal(
                date=monday + datetime.timedelta(days=meal.weekday - 1),
                meal_type=meal.meal_type,
                recipe=meal.recipe,
            )
            for meal in template.meals.select_related("recipe")
        ]
    )
    return _render_week(request, monday, message=f"Applied “{template.name}”.")


@login_required
@require_http_methods(["POST"])
def week_save_template(request, monday):
    """Export: snapshot this week into a brand-new template."""
    monday = _parse_monday(monday)
    name = (request.POST.get("name") or "").strip()
    if not name:
        return _render_week(request, monday, action="save", error="Name is required.")
    dates = _week_dates(monday)
    template = TemplateWeek.objects.create(name=name)
    _copy_week_into_template(template, dates)
    return _render_week(request, monday, message=f"Saved as “{template.name}”.")


def _format_quantity(quantity):
    """Decimal -> shortest string: 300.00 -> "300", 0.50 -> "0.5"."""
    return f"{quantity.normalize():f}"


def _shopping_items(dates):
    """One entry per distinct ingredient scheduled on ``dates``, sorted by
    ingredient category (uncategorized last) then name. Quantities are summed
    per unit, without converting between units, e.g. "1 ud + 300 g". A recipe
    scheduled twice counts twice."""
    meals_per_recipe = Counter(
        CalendarMeal.objects.filter(date__in=dates).values_list("recipe_id", flat=True)
    )
    by_ingredient = {}
    for row in (
        RecipeIngredient.objects.filter(recipe_id__in=meals_per_recipe)
        .select_related("ingredient__category", "unit")
        .order_by("pk")
    ):
        entry = by_ingredient.setdefault(
            row.ingredient_id, {"ingredient": row.ingredient, "totals": {}}
        )
        if row.quantity is not None:
            totals = entry["totals"]
            added = row.quantity * meals_per_recipe[row.recipe_id]
            totals[row.unit] = totals.get(row.unit, 0) + added

    items = []
    for entry in by_ingredient.values():
        ingredient = entry["ingredient"]
        # Units keep the order they first appear in (rows are ordered by pk).
        amounts = " + ".join(
            f"{_format_quantity(qty)} {unit}" if unit else _format_quantity(qty)
            for unit, qty in entry["totals"].items()
        )
        name = ingredient.name.capitalize()
        items.append(
            {
                "id": ingredient.pk,
                "category": ingredient.category.name if ingredient.category else None,
                "label": f"{name}: {amounts}" if amounts else name,
            }
        )
    items.sort(key=lambda i: (i["category"] is None, i["category"] or "", i["label"]))
    return items


@login_required
@require_http_methods(["GET"])
def week_shopping_form(request, monday):
    """Open the shopping-list preview dialog: editable name/due date and one
    checkbox per ingredient, all ticked."""
    monday = _parse_monday(monday)
    items = _shopping_items(_week_dates(monday))
    if not items:
        return _render_week(
            request, monday, error="No ingredients scheduled this week."
        )
    return _render_week(
        request,
        monday,
        action="shopping",
        items=items,
        selected_ids={item["id"] for item in items},
        list_name=f"Shopping list week of {monday:%Y-%m-%d}",
        due_date="",
    )


@login_required
@require_http_methods(["POST"])
def week_export_shopping_list(request, monday):
    """Export: create a todo from the preview, one subtask per ticked
    ingredient. Items are recomputed from the calendar and filtered by the
    ticked ids, so the dialog can only remove items, never add them."""
    monday = _parse_monday(monday)
    items = _shopping_items(_week_dates(monday))
    selected_ids = set()
    for value in request.POST.getlist("ingredient"):
        if value.isdigit():
            selected_ids.add(int(value))
    name = (request.POST.get("name") or "").strip()
    due_date_str = (request.POST.get("due_date") or "").strip()

    error = ""
    due_date = None
    if due_date_str:
        try:
            due_date = datetime.date.fromisoformat(due_date_str)
        except ValueError:
            error = "Enter a valid due date."
    selected = [item for item in items if item["id"] in selected_ids]
    if not name:
        error = "Name is required."
    elif not selected:
        error = "Tick at least one item."
    if error:
        return _render_week(
            request,
            monday,
            action="shopping",
            error=error,
            items=items,
            selected_ids=selected_ids,
            list_name=name,
            due_date=due_date_str,
        )

    with transaction.atomic():
        todo = Todo.objects.create(name=name, due_date=due_date)
        Subtask.objects.bulk_create(
            [Subtask(todo=todo, name=item["label"]) for item in selected]
        )
    return _render_week(
        request,
        monday,
        message=f"Saved “{todo.name}” with {len(selected)} items.",
        message_link={"url": reverse("todo_list"), "label": "View todos"},
    )


@login_required
@require_http_methods(["POST"])
def week_update_template(request, monday):
    """Export: overwrite an existing template with this week's meals."""
    monday = _parse_monday(monday)
    template = TemplateWeek.objects.filter(pk=request.POST.get("template") or 0).first()
    if template is None:
        return _render_week(request, monday, action="update", error="Pick a template.")
    dates = _week_dates(monday)
    _copy_week_into_template(template, dates)
    return _render_week(request, monday, message=f"Updated “{template.name}”.")
