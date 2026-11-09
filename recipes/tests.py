from django.test import TestCase
from django.urls import reverse

from .models import Recipe, RecipeCategory


class RecipeListTests(TestCase):
    def test_recipes_grouped_by_category_with_uncategorized_last(self):
        dinner = RecipeCategory.objects.create(name="Dinner")
        breakfast = RecipeCategory.objects.create(name="Breakfast")
        Recipe.objects.create(name="Stew", category=dinner, description="d", servings=2)
        Recipe.objects.create(
            name="Curry", category=dinner, description="d", servings=2
        )
        Recipe.objects.create(
            name="Pancakes", category=breakfast, description="d", servings=2
        )
        Recipe.objects.create(name="Toast", description="d", servings=1)

        response = self.client.get(reverse("recipe_list"))

        self.assertEqual(
            [r.name for r in response.context["recipe_list"]],
            ["Pancakes", "Curry", "Stew", "Toast"],
        )
        self.assertContains(response, "<h2>Breakfast</h2>", html=True)
        self.assertContains(response, "<h2>Dinner</h2>", html=True)
        self.assertContains(response, "<h2>Uncategorized</h2>", html=True)


class RecipeDetailTests(TestCase):
    def test_shows_category(self):
        category = RecipeCategory.objects.create(name="Dessert")
        recipe = Recipe.objects.create(
            name="Flan", category=category, description="d", servings=4
        )
        response = self.client.get(recipe.get_absolute_url())
        self.assertContains(response, "Category: Dessert")

    def test_shows_uncategorized_when_missing(self):
        recipe = Recipe.objects.create(name="Toast", description="d", servings=1)
        response = self.client.get(recipe.get_absolute_url())
        self.assertContains(response, "Category: Uncategorized")
