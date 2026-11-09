import datetime

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods
from django.views.generic import (
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


class TemplateWeekDetail(DetailView):
    model = TemplateWeek
    template_name = "planner/templateweek_detail.html"
    queryset = TemplateWeek.objects.prefetch_related("meals__recipe")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["days"] = build_days(self.object.meals.all())
        return context


def _meal_label(meal_type):
    return MealType(meal_type).label


def _cell_context(templateweek, weekday, meal_type, meal=None):
    return {
        "templateweek_pk": templateweek.pk,
        "weekday": weekday,
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
    template_name = "planner/calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        this_monday = monday_of(datetime.date.today())
        mondays = [this_monday + datetime.timedelta(weeks=offset) for offset in (0, 1)]
        range_start = mondays[0]
        range_end = mondays[-1] + datetime.timedelta(days=6)

        # One query covers the whole visible window; bucket by (date, meal_type)
        # so each cell is an O(1) dict lookup.
        meals_by_slot = {
            (m.date, m.meal_type): m
            for m in CalendarMeal.objects.filter(
                date__range=(range_start, range_end)
            ).select_related("recipe")
        }

        context["weekday_labels"] = [day.label for day in Weekday]

        weeks = []
        for monday in mondays:
            days = []
            for offset in range(7):
                date = monday + datetime.timedelta(days=offset)
                days.append(
                    {
                        "date": date,
                        "lunch": meals_by_slot.get((date, MealType.LUNCH)),
                        "dinner": meals_by_slot.get((date, MealType.DINNER)),
                    }
                )
            weeks.append(
                {
                    "start_date": monday,
                    "is_current": monday == this_monday,
                    "days": days,
                }
            )

        context["weeks"] = weeks
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
    return [
        {
            "date": date,
            "lunch": meals_by_slot.get((date, MealType.LUNCH)),
            "dinner": meals_by_slot.get((date, MealType.DINNER)),
        }
        for date in dates
    ]


def _render_week(request, monday, action=None, message="", error=""):
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
            "error": error,
            "templates": TemplateWeek.objects.order_by("name"),
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


@login_required
@require_http_methods(["POST"])
def week_export_shopping_list(request, monday):
    """Export: snapshot this week's scheduled ingredients into a new
    'Shopping list week of <monday>' todo, one subtask per distinct ingredient."""
    monday = _parse_monday(monday)
    dates = _week_dates(monday)
    recipe_ids = CalendarMeal.objects.filter(date__in=dates).values_list(
        "recipe_id", flat=True
    )
    ingredient_names = list(
        RecipeIngredient.objects.filter(recipe_id__in=recipe_ids)
        .values_list("ingredient__name", flat=True)
        .distinct()
        .order_by("ingredient__name")
    )
    if not ingredient_names:
        return _render_week(
            request, monday, error="No ingredients scheduled this week."
        )
    todo = Todo.objects.create(name=f"Shopping list week of {monday:%Y-%m-%d}")
    Subtask.objects.bulk_create(
        [Subtask(todo=todo, name=name.capitalize()) for name in ingredient_names]
    )
    return _render_week(
        request,
        monday,
        message=f"Saved “{todo.name}” with {len(ingredient_names)} items.",
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
