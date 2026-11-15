import datetime

from django.shortcuts import render

from planner.models import CalendarMeal, MealType
from todo.views import grouped_open_todos


def home(request):
    """Dashboard: today's lunch and dinner, plus overdue and this week's
    todos (ticked and opened in place, like on the todos page)."""
    today = datetime.date.today()
    meals = {
        meal.meal_type: meal
        for meal in CalendarMeal.objects.filter(date=today).select_related("recipe")
    }
    return render(
        request,
        "pages/home.html",
        {
            "today": today,
            "meals": [
                {"label": label, "meal": meals.get(value)}
                for value, label in MealType.choices
            ],
            "todo_groups": grouped_open_todos(only=("overdue", "week")),
        },
    )
