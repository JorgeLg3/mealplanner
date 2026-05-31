from django.contrib import admin
from .models import (
    IngredientCategory,
    Ingredient,
    RecipeCategory,
    Recipe,
    RecipeIngredient,
    Unit,
)


admin.site.register(
    (RecipeCategory, Recipe, IngredientCategory, Ingredient, Unit, RecipeIngredient)
)
