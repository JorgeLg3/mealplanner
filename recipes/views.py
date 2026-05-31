from django.shortcuts import redirect
from django.views.generic import DetailView, ListView, CreateView, UpdateView, DeleteView
from .models import Recipe
from .forms import RecipeIngredientFormSet

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


class RecipeCreateView(CreateView):
    model = Recipe
    template_name = "recipes/recipe_create.html"
    fields = ["name", "category", "description"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            context["ingredient_formset"] = RecipeIngredientFormSet(self.request.POST)
        else:
            context["ingredient_formset"] = RecipeIngredientFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["ingredient_formset"]
        if not formset.is_valid():
            # Re-render the page with both the form and formset errors.
            return self.render_to_response(self.get_context_data(form=form))

        form.instance.author = self.request.user
        self.object = form.save()          # now the Recipe has a PK
        formset.instance = self.object     # point the child rows at it
        formset.save()
        return redirect(self.object.get_absolute_url())