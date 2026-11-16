from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    DetailView,
    ListView,
    CreateView,
    UpdateView,
    DeleteView,
)
from planner.models import CalendarMeal, TemplateMeal

from .models import (
    Ingredient,
    Recipe,
    RecipeCategory,
    RecipeIngredient,
    other_last,
)
from .forms import IngredientForm, RecipeIngredientFormSet


class RecipeListView(ListView):
    """Recipe catalog: category sidebar with counts, plus ?q= (name search)
    and ?category= (a category id) filters that combine. Results stay sorted
    by category ("otros" last) so the template can regroup."""

    model = Recipe
    template_name = "recipes/recipe_list.html"

    def get_queryset(self):
        self.query = self.request.GET.get("q", "").strip()
        self.category = self.request.GET.get("category", "")
        recipes = Recipe.objects.select_related("category").annotate(
            ingredient_count=Count("recipeingredient")
        )
        if self.query:
            recipes = recipes.filter(name__icontains=self.query)
        if self.category.isdigit():
            recipes = recipes.filter(category_id=int(self.category))
        else:
            self.category = ""
        return recipes.order_by(other_last("category__name"), "category__name", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Seeded categories may be empty: list only those with recipes (plus
        # the selected one, so its empty state stays reachable).
        categories = [
            c
            # Meta.ordering is ignored on aggregate queries; order explicitly.
            for c in RecipeCategory.objects.annotate(
                recipe_count=Count("recipe")
            ).order_by(other_last("name"), "name")
            # recipe_count comes from annotate(), which type checkers can't see.
            if c.recipe_count or str(c.pk) == self.category  # ty: ignore[unresolved-attribute]
        ]
        selected = next((c for c in categories if str(c.pk) == self.category), None)
        context.update(
            {
                "categories": categories,
                "total_count": Recipe.objects.count(),
                "query": self.query,
                "category": self.category,
                "selected_category": selected,
            }
        )
        return context


class IngredientListView(ListView):
    model = Ingredient
    template_name = "recipes/ingredient_list.html"
    # Sorted by category ("otros" last) so the template can {% regroup %} it.
    queryset = Ingredient.objects.select_related("category").order_by(
        other_last("category__name"), "category__name", "name"
    )


class IngredientCreateView(LoginRequiredMixin, CreateView):
    model = Ingredient
    form_class = IngredientForm
    template_name = "recipes/ingredient_form.html"
    success_url = reverse_lazy("ingredient_list")


class IngredientUpdateView(LoginRequiredMixin, UpdateView):
    """Rename / recategorize. Recipes keep pointing at the same ingredient,
    so a rename shows up in all of them."""

    model = Ingredient
    form_class = IngredientForm
    template_name = "recipes/ingredient_form.html"
    success_url = reverse_lazy("ingredient_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recipe_count"] = (
            RecipeIngredient.objects.filter(ingredient=self.object)
            .values("recipe")
            .distinct()
            .count()
        )
        return context


class IngredientDeleteView(LoginRequiredMixin, DeleteView):
    """Recipe rows PROTECT their ingredient, so one still used in a recipe
    can't be deleted: list those recipes instead of crashing."""

    model = Ingredient
    template_name = "recipes/ingredient_confirm_delete.html"
    success_url = reverse_lazy("ingredient_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["recipes_using"] = Recipe.objects.filter(
            recipeingredient__ingredient=self.object
        ).distinct()
        return context

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            # Became used between opening the page and confirming.
            return self.render_to_response(self.get_context_data())


class RecipeDetailView(DetailView):
    model = Recipe
    template_name = "recipes/recipe_detail.html"
    queryset = Recipe.objects.select_related("category").prefetch_related(
        "recipeingredient_set__ingredient",
        "recipeingredient_set__unit",
    )


class RecipeCreateView(LoginRequiredMixin, CreateView):
    model = Recipe
    template_name = "recipes/recipe_create.html"
    fields = ["name", "category", "description", "servings", "image"]

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
    fields = ["name", "category", "description", "servings", "image"]

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


def _template_names(template_meals):
    """Distinct (pk, name) of the templates these meals belong to."""
    return list(
        template_meals.values_list("template_id", "template__name")
        .distinct()
        .order_by("template__name")
    )


class RecipeDeleteView(LoginRequiredMixin, DeleteView):
    """Planner and template meals PROTECT their recipe, so a recipe in use
    can't be deleted. Say where it's used instead of crashing; Delete is only
    offered once it's free."""

    model = Recipe
    template_name = "recipes/recipe_confirm_delete.html"
    success_url = reverse_lazy("recipe_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        calendar_meals = CalendarMeal.objects.filter(recipe=self.object).order_by(
            "date"
        )
        template_meals = TemplateMeal.objects.filter(recipe=self.object)
        context["calendar_dates"] = list(calendar_meals.values_list("date", flat=True))
        context["templates_using"] = _template_names(template_meals)
        context["in_use"] = bool(
            context["calendar_dates"] or context["templates_using"]
        )
        return context

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            # Became used between opening the page and confirming.
            return self.render_to_response(self.get_context_data())
