from django.urls import path
from .views import RecipeListView, RecipeDetailView

urlpatterns = [
    path("", RecipeListView.as_view(), name="recipe_list"),
    path("<int:pk>/", RecipeDetailView.as_view(), name="recipe_detail"),
]