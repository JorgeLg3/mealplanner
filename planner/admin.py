from django.contrib import admin
from .models import CalendarMeal, HouseholdSettings, TemplateMeal, TemplateWeek


admin.site.register((TemplateWeek, TemplateMeal, CalendarMeal, HouseholdSettings))
