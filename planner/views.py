from django.views.generic import (
    ListView,
    DetailView,
)
from .models import TemplateWeek, MealType, Weekday


class TemplateWeekList(ListView):
    model = TemplateWeek
    template_name = "planner/templateweek_list.html"


class TemplateWeekDetail(DetailView):
    model = TemplateWeek
    template_name = "planner/templateweek_detail.html"
    queryset = TemplateWeek.objects.prefetch_related("meals__recipe")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Reshape the flat meal list into one column per weekday so the template
        # can render a Mon–Sun grid (templates can't index by (weekday, type)).
        meals = {
            (meal.weekday, meal.meal_type): meal for meal in self.object.meals.all()
        }
        context["days"] = [
            {
                "label": day.label,
                "lunch": meals.get((day.value, MealType.LUNCH)),
                "dinner": meals.get((day.value, MealType.DINNER)),
            }
            for day in Weekday
        ]
        return context
