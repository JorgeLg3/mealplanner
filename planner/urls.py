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
    week_actions,
    week_apply_form,
    week_save_form,
    week_update_form,
    week_apply_template,
    week_save_template,
    week_update_template,
    week_export_shopping_list,
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
    path("week/actions/", week_actions, name="week_actions"),
    path("week/apply/form/", week_apply_form, name="week_apply_form"),
    path("week/save/form/", week_save_form, name="week_save_form"),
    path("week/update/form/", week_update_form, name="week_update_form"),
    path("week/apply/", week_apply_template, name="week_apply_template"),
    path("week/save/", week_save_template, name="week_save_template"),
    path("week/update/", week_update_template, name="week_update_template"),
    path(
        "week/shopping-list/",
        week_export_shopping_list,
        name="week_export_shopping_list",
    ),
]
