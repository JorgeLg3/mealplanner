from django.urls import path
from .views import (
    IngredientListView,
    RecipeListView,
    RecipeDetailView,
    RecipeCreateView,
    RecipeUpdateView,
    RecipeDeleteView,
)

urlpatterns = [
    path("", RecipeListView.as_view(), name="recipe_list"),
    path("<int:pk>/", RecipeDetailView.as_view(), name="recipe_detail"),
    path("ingredients/", IngredientListView.as_view(), name="ingredient_list"),
    path("create/", RecipeCreateView.as_view(), name="recipe_create"),
    path("<int:pk>/edit/", RecipeUpdateView.as_view(), name="recipe_update"),
    path("<int:pk>/delete/", RecipeDeleteView.as_view(), name="recipe_delete"),
]
