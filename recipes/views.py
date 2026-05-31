from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    DetailView,
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
)
from .models import Recipe, Ingredient
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


class RecipeCreateView(LoginRequiredMixin, CreateView):
    model = Recipe
    template_name = "recipes/recipe_create.html"
    fields = ["name", "category", "description", "servings"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            context["ingredient_formset"] = RecipeIngredientFormSet(self.request.POST)
        else:
            context["ingredient_formset"] = RecipeIngredientFormSet()
        context["ingredients"] = Ingredient.objects.all()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["ingredient_formset"]
        if not formset.is_valid():
            # Re-render the page with both the form and formset errors.
            return self.render_to_response(self.get_context_data(form=form))

        form.instance.author = self.request.user
        self.object = form.save()  # now the Recipe has a PK
        formset.instance = self.object  # point the child rows at it
        formset.save()
        return redirect(self.object.get_absolute_url())


class RecipeUpdateView(LoginRequiredMixin, UpdateView):
    model = Recipe
    template_name = "recipes/recipe_update.html"
    fields = ["name", "category", "description", "servings"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Bind the formset to the existing recipe so its ingredients show up.
        if self.request.method == "POST":
            context["ingredient_formset"] = RecipeIngredientFormSet(
                self.request.POST, instance=self.object
            )
        else:
            context["ingredient_formset"] = RecipeIngredientFormSet(
                instance=self.object
            )
        context["ingredients"] = Ingredient.objects.all()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["ingredient_formset"]
        if not formset.is_valid():
            # Re-render the page with both the form and formset errors.
            return self.render_to_response(self.get_context_data(form=form))

        self.object = form.save()
        formset.instance = self.object
        formset.save()
        return redirect(self.object.get_absolute_url())


class RecipeDeleteView(LoginRequiredMixin, DeleteView):
    model = Recipe
    template_name = "recipes/recipe_confirm_delete.html"
    success_url = reverse_lazy("recipe_list")
