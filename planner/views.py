import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods
from django.views.generic import (
    ListView,
    DetailView,
    TemplateView,
)
from recipes.models import Recipe
from .models import TemplateWeek, TemplateMeal, RealWeek, MealType, Weekday


def build_days(meals):
    """Reshape a flat iterable of meals into one entry per weekday (Mon–Sun),
    so a template can render a grid. Works for both TemplateMeal and RealMeal
    since they share weekday/meal_type/recipe."""
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


class PlannerCalendar(TemplateView):
    template_name = "planner/calendar.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        this_monday = monday_of(datetime.date.today())
        mondays = [this_monday + datetime.timedelta(weeks=offset) for offset in (-1, 0, 1)]

        # One query for any already-materialized weeks in range; missing ones
        # simply render as empty grids (lazy: viewing never creates RealWeeks).
        real_weeks = {
            week.start_date: week
            for week in RealWeek.objects.filter(
                start_date__in=mondays
            ).prefetch_related("meals__recipe")
        }

        # Weekday names live once at the top of the calendar, shared by every row.
        context["weekday_labels"] = [day.label for day in Weekday]

        weeks = []
        for monday in mondays:
            is_current = monday == this_monday
            real_week = real_weeks.get(monday)

            # Current and upcoming weeks show meals; the past week is date-only.
            show_meals = monday >= this_monday
            meals = {}
            if show_meals and real_week is not None:
                meals = {
                    (m.weekday, m.meal_type): m for m in real_week.meals.all()
                }

            days = []
            for offset in range(7):
                date = monday + datetime.timedelta(days=offset)
                weekday = offset + 1  # Monday = 1, matching Weekday choices
                days.append(
                    {
                        "date": date,
                        "lunch": meals.get((weekday, MealType.LUNCH)),
                        "dinner": meals.get((weekday, MealType.DINNER)),
                    }
                )

            weeks.append(
                {
                    "start_date": monday,
                    "is_current": is_current,
                    "show_meals": show_meals,
                    "real_week": real_week,
                    "days": days,
                }
            )

        context["weeks"] = weeks
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
    meal = TemplateMeal.objects.filter(
        template=templateweek, weekday=weekday, meal_type=meal_type
    ).select_related("recipe").first()
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
    recipe = Recipe.objects.filter(name__iexact=recipe_name).first() if recipe_name else None
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
