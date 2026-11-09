from django.test import TestCase
from django.urls import reverse

from .models import Ingredient, IngredientCategory, Recipe, RecipeCategory


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


class IngredientListTests(TestCase):
    def test_ingredients_grouped_by_category_with_uncategorized_last(self):
        veg = IngredientCategory.objects.create(name="Vegetables")
        dairy = IngredientCategory.objects.create(name="Dairy")
        Ingredient.objects.create(name="tomato", category=veg)
        Ingredient.objects.create(name="carrot", category=veg)
        Ingredient.objects.create(name="milk", category=dairy)
        Ingredient.objects.create(name="salt")

        response = self.client.get(reverse("ingredient_list"))

        self.assertEqual(
            [i.name for i in response.context["ingredient_list"]],
            ["milk", "carrot", "tomato", "salt"],
        )
        self.assertContains(response, "<h2>Dairy</h2>", html=True)
        self.assertContains(response, "<h2>Vegetables</h2>", html=True)
        self.assertContains(response, "<h2>Uncategorized</h2>", html=True)

    def test_recipe_list_links_to_ingredients(self):
        response = self.client.get(reverse("recipe_list"))
        self.assertContains(response, f'href="{reverse("ingredient_list")}"')
