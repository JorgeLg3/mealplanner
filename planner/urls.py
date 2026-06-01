from django.urls import path
from .views import (
    TemplateWeekList,
    TemplateWeekDetail,
    PlannerCalendar,
    templatemeal_cell,
    templatemeal_form,
    templatemeal,
)

urlpatterns = [
    path("", PlannerCalendar.as_view(), name="planner_calendar"),
    path("template/", TemplateWeekList.as_view(), name="templateweek_list"),
    path(
        "template/<int:pk>/", TemplateWeekDetail.as_view(), name="templateweek_detail"
    ),
    path(
        "template/<int:pk>/cell/<int:weekday>/<str:meal_type>/",
        templatemeal_cell,
        name="templatemeal_cell",
    ),
    path(
        "template/<int:pk>/form/<int:weekday>/<str:meal_type>/",
        templatemeal_form,
        name="templatemeal_form",
    ),
    path(
        "template/<int:pk>/meal/<int:weekday>/<str:meal_type>/",
        templatemeal,
        name="templatemeal",
    ),
]
