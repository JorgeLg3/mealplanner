import datetime

from django.views.generic import (
    ListView,
    DetailView,
    TemplateView,
)
from .models import TemplateWeek, RealWeek, MealType, Weekday


def build_days(meals):
    """Reshape a flat iterable of meals into one entry per weekday (Mon–Sun),
    so a template can render a grid. Works for both TemplateMeal and RealMeal
    since they share weekday/meal_type/recipe."""
    lookup = {(meal.weekday, meal.meal_type): meal for meal in meals}
    return [
        {
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
