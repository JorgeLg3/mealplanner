import datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
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
from recipes.models import OTHER_CATEGORY, Recipe, RecipeIngredient, Unit
from todo.models import Subtask, Todo
from .models import (
    MAX_SERVINGS,
    CalendarMeal,
    HouseholdSettings,
    MealType,
    TemplateMeal,
    TemplateWeek,
    Weekday,
)


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


def _servings_from_post(request, default_servings):
    """Read the slot form's servings stepper. Returns (servings, error).
    servings is None for "use the household default" (blank, or equal to the
    default, so the meal keeps following it if the default changes)."""
    raw = (request.POST.get("servings") or "").strip()
    if not raw:
        return None, ""
    try:
        servings = int(raw)
    except ValueError:
        return None, "Servings must be a number."
    if not 1 <= servings <= MAX_SERVINGS:
        return None, f"Servings must be between 1 and {MAX_SERVINGS}."
    return (None if servings == default_servings else servings), ""


def _slot_form_context(base, meal, default_servings, recipes=None, error=""):
    """Context for the add/replace form: stepper starts at the meal's servings
    (or the default); the recipe input stays empty (swap = pick something new)
    but says the current recipe is kept if left blank."""
    return {
        **base,
        "recipes": recipes if recipes is not None else Recipe.objects.order_by("name"),
        "current_meal": meal,
        "servings_value": (
            meal.servings if meal and meal.servings else default_servings
        ),
        "default_servings": default_servings,
        "max_servings": MAX_SERVINGS,
        "error": error,
    }


def _save_slot(request, meal, create_or_update, base, form_template, cell_template):
    """Shared POST logic for calendar and template slots.

    - recipe picked: create/replace the slot with it and the stepper's servings
    - recipe blank on a filled slot: keep the recipe, update servings only
    - otherwise: re-render the form with an error
    """
    default_servings = HouseholdSettings.get().default_servings
    servings, error = _servings_from_post(request, default_servings)
    recipe_name = (request.POST.get("recipe") or "").strip()
    recipe = (
        Recipe.objects.filter(name__iexact=recipe_name).first() if recipe_name else None
    )
    if not error and recipe is None:
        if recipe_name or meal is None:
            error = "Pick a recipe from the list."
        else:
            recipe = meal.recipe
    if error:
        context = _slot_form_context(base, meal, default_servings, error=error)
        if "servings" in request.POST:
            context["servings_value"] = request.POST["servings"]
        return render(request, form_template, context)

    meal = create_or_update(recipe, servings)
    return render(request, cell_template, {**base, "meal": meal})


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
    """Return the add/replace form partial. The recipe input is intentionally
    empty even when the slot is filled (swap means pick something new);
    Cancel re-renders the cell to recover the current meal."""
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
    context = _slot_form_context(
        _cell_context(templateweek, weekday, meal_type),
        meal,
        HouseholdSettings.get().default_servings,
    )
    return render(request, "planner/_meal_form.html", context)


@login_required
@require_http_methods(["POST", "DELETE"])
def templatemeal(request, pk, weekday, meal_type):
    """POST creates/replaces the meal's recipe; DELETE removes it. Both
    return the cell partial in its new state for HTMX to swap in. (Templates
    have no servings: applied meals use the household default.)"""
    templateweek = _validate_slot(pk, weekday, meal_type)
    if templateweek is None:
        return HttpResponseNotAllowed(["POST", "DELETE"])
    slot = {"template": templateweek, "weekday": weekday, "meal_type": meal_type}
    base = _cell_context(templateweek, weekday, meal_type)

    if request.method == "DELETE":
        TemplateMeal.objects.filter(**slot).delete()
        return render(request, "planner/_meal_cell.html", base)

    def create_or_update(recipe, servings):
        # Templates don't store servings; only calendar meals do.
        meal, _ = TemplateMeal.objects.update_or_create(
            **slot, defaults={"recipe": recipe}
        )
        return meal

    meal = TemplateMeal.objects.filter(**slot).select_related("recipe").first()
    return _save_slot(
        request,
        meal,
        create_or_update,
        base,
        "planner/_meal_form.html",
        "planner/_meal_cell.html",
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
        context["default_servings"] = HouseholdSettings.get().default_servings
        context["max_servings"] = MAX_SERVINGS
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
    """Return the add/replace form partial. The recipe input is intentionally
    empty even when the slot is filled (swap means pick something new);
    leaving it blank keeps the recipe and only updates servings. Cancel
    re-renders the cell to recover the current meal."""
    date = _validate_calendar_slot(date, meal_type)
    if date is None:
        return HttpResponseNotAllowed(["GET"])
    meal = (
        CalendarMeal.objects.filter(date=date, meal_type=meal_type)
        .select_related("recipe")
        .first()
    )
    context = _slot_form_context(
        _calendar_cell_context(date, meal_type),
        meal,
        HouseholdSettings.get().default_servings,
    )
    return render(request, "planner/_calendar_form.html", context)


@login_required
@require_http_methods(["POST", "DELETE"])
def calendarmeal(request, date, meal_type):
    """POST creates/replaces the meal (or just its servings, see _save_slot);
    DELETE removes it. Both return the cell partial in its new state for
    HTMX to swap in."""
    date = _validate_calendar_slot(date, meal_type)
    if date is None:
        return HttpResponseNotAllowed(["POST", "DELETE"])
    slot = {"date": date, "meal_type": meal_type}
    base = _calendar_cell_context(date, meal_type)

    if request.method == "DELETE":
        CalendarMeal.objects.filter(**slot).delete()
        return render(request, "planner/_calendar_cell.html", base)

    def create_or_update(recipe, servings):
        meal, _ = CalendarMeal.objects.update_or_create(
            **slot, defaults={"recipe": recipe, "servings": servings}
        )
        return meal

    meal = CalendarMeal.objects.filter(**slot).select_related("recipe").first()
    return _save_slot(
        request,
        meal,
        create_or_update,
        base,
        "planner/_calendar_form.html",
        "planner/_calendar_cell.html",
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
                # Templates have no servings: applied meals follow the
                # household default until changed in the planner.
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


def _round_quantity(quantity, unit):
    """Scaled amounts: countable things (and unitless amounts like "2") round
    UP to whole numbers, since half an onion isn't something you buy. Weights
    and volumes get a sensible precision: whole numbers from 10 up (133 g),
    one decimal from 1 (1.3 kg), two below (0.25 l)."""
    if unit is None or unit.unit_type == Unit.UnitType.COUNT:
        return quantity.to_integral_value(rounding=ROUND_CEILING)
    if quantity >= 10:
        step = Decimal("1")
    elif quantity >= 1:
        step = Decimal("0.1")
    else:
        step = Decimal("0.01")
    return quantity.quantize(step, rounding=ROUND_HALF_UP)


def _shopping_items(dates):
    """One entry per distinct ingredient scheduled on ``dates``, sorted by
    ingredient category ("otros" last) then name. Each meal's
    ingredients are scaled by (meal servings / recipe servings), where meal
    servings falls back to the household default. Quantities are then summed
    per unit, without converting between units, e.g. "1 ud + 300 g", and
    rounded once at the end."""
    default_servings = HouseholdSettings.get().default_servings
    meals = list(CalendarMeal.objects.filter(date__in=dates).select_related("recipe"))
    factors_by_recipe = {}
    for meal in meals:
        made = meal.recipe.servings or 1  # guard against 0-serving recipes
        eaten = meal.servings or default_servings
        factors_by_recipe.setdefault(meal.recipe_id, []).append(
            Decimal(eaten) / Decimal(made)
        )

    by_ingredient = {}
    for row in (
        RecipeIngredient.objects.filter(recipe_id__in=factors_by_recipe)
        .select_related("ingredient__category", "unit")
        .order_by("pk")
    ):
        entry = by_ingredient.setdefault(
            row.ingredient_id, {"ingredient": row.ingredient, "totals": {}}
        )
        if row.quantity is not None:
            totals = entry["totals"]
            added = row.quantity * sum(factors_by_recipe[row.recipe_id])
            totals[row.unit] = totals.get(row.unit, 0) + added

    items = []
    for entry in by_ingredient.values():
        ingredient = entry["ingredient"]
        # Units keep the order they first appear in (rows are ordered by pk).
        amounts = " + ".join(
            f"{_format_quantity(_round_quantity(qty, unit))} {unit}"
            if unit
            else _format_quantity(_round_quantity(qty, unit))
            for unit, qty in entry["totals"].items()
        )
        name = ingredient.name.capitalize()
        items.append(
            {
                "id": ingredient.pk,
                "category": ingredient.category.name,
                "label": f"{name}: {amounts}" if amounts else name,
            }
        )
    items.sort(
        key=lambda i: (
            i["category"].lower() == OTHER_CATEGORY,
            i["category"],
            i["label"],
        )
    )
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
            [
                Subtask(todo=todo, name=item["label"], position=position)
                for position, item in enumerate(selected, start=1)
            ]
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


@login_required
@require_http_methods(["POST"])
def household_servings(request):
    """Set how many people the household usually cooks for. Reloads the page:
    every meal without its own servings follows the new default."""
    settings = HouseholdSettings.get()
    try:
        value = int(request.POST.get("default_servings", ""))
    except ValueError:
        value = 0
    if 1 <= value <= MAX_SERVINGS:
        settings.default_servings = value
        settings.save(update_fields=["default_servings"])
    response = HttpResponse("")
    response["HX-Refresh"] = "true"
    return response
