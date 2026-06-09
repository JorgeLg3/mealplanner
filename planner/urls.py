from django.urls import path
from .views import (
    TemplateWeekList,
    TemplateWeekDetail,
    PlannerCalendar,
    templatemeal_cell,
    templatemeal_form,
    templatemeal,
    calendarmeal_cell,
    calendarmeal_form,
    calendarmeal,
)

urlpatterns = [
    path("", PlannerCalendar.as_view(), name="planner_calendar"),
    path("templates/", TemplateWeekList.as_view(), name="templateweek_list"),
    path(
        "templates/<int:pk>/", TemplateWeekDetail.as_view(), name="templateweek_detail"
    ),
    path(
        "templates/<int:pk>/cell/<int:weekday>/<str:meal_type>/",
        templatemeal_cell,
        name="templatemeal_cell",
    ),
    path(
        "templates/<int:pk>/form/<int:weekday>/<str:meal_type>/",
        templatemeal_form,
        name="templatemeal_form",
    ),
    path(
        "templates/<int:pk>/meal/<int:weekday>/<str:meal_type>/",
        templatemeal,
        name="templatemeal",
    ),
    path(
        "calendar/cell/<str:date>/<str:meal_type>/",
        calendarmeal_cell,
        name="calendarmeal_cell",
    ),
    path(
        "calendar/form/<str:date>/<str:meal_type>/",
        calendarmeal_form,
        name="calendarmeal_form",
    ),
    path(
        "calendar/meal/<str:date>/<str:meal_type>/",
        calendarmeal,
        name="calendarmeal",
    ),
]
