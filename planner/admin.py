from django.contrib import admin
from .models import TemplateWeek, TemplateMeal, CalendarMeal


admin.site.register((TemplateWeek, TemplateMeal, CalendarMeal))
