from django.urls import path
from .views import TemplateWeekList, TemplateWeekDetail

urlpatterns = [
    path("template/", TemplateWeekList.as_view(), name="templateweek_list"),
    path(
        "template/<int:pk>/", TemplateWeekDetail.as_view(), name="templateweek_detail"
    ),
]
