from django.urls import path
from .views import (
    IngredientCreateView,
    IngredientDeleteView,
    IngredientListView,
    IngredientUpdateView,
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
    path(
        "ingredients/create/",
        IngredientCreateView.as_view(),
        name="ingredient_create",
    ),
    path(
        "ingredients/<int:pk>/edit/",
        IngredientUpdateView.as_view(),
        name="ingredient_update",
    ),
    path(
        "ingredients/<int:pk>/delete/",
        IngredientDeleteView.as_view(),
        name="ingredient_delete",
    ),
    path("create/", RecipeCreateView.as_view(), name="recipe_create"),
    path("<int:pk>/edit/", RecipeUpdateView.as_view(), name="recipe_update"),
    path("<int:pk>/delete/", RecipeDeleteView.as_view(), name="recipe_delete"),
]
