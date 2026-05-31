from django.views.generic import DetailView, ListView
from .models import Recipe

class RecipeListView(ListView):
    model = Recipe
    template_name = "recipes/recipe_list.html"

class RecipeDetailView(DetailView):
    model = Recipe
    template_name = "recipes/recipe_detail.html"
    queryset = Recipe.objects.prefetch_related(
        "recipeingredient_set__ingredient",
        "recipeingredient_set__unit",
    )