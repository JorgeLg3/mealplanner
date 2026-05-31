from django.contrib import admin
from .models import TemplateWeek, RealWeek, TemplateMeal, RealMeal


admin.site.register((TemplateWeek, RealWeek, TemplateMeal, RealMeal))
