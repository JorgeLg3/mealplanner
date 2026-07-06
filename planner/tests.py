import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from recipes.models import Ingredient, Recipe, RecipeIngredient
from todo.models import Todo

from .models import CalendarMeal, MealType


class ExportShoppingListTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        self.monday = datetime.date.today() - datetime.timedelta(
            days=datetime.date.today().weekday()
        )

    def _recipe_with_ingredients(self, name, ingredient_names):
        recipe = Recipe.objects.create(name=name, description="d", servings=2)
        for ing_name in ingredient_names:
            # Ingredient.save() lowercases names, so look up by the normalized
            # form to avoid tripping the case-insensitive unique constraint.
            ingredient, _ = Ingredient.objects.get_or_create(name=ing_name.lower())
            RecipeIngredient.objects.create(recipe=recipe, ingredient=ingredient)
        return recipe

    def test_export_creates_shopping_list_with_distinct_ingredients(self):
        pasta = self._recipe_with_ingredients("Pasta", ["Tomato", "Pasta"])
        salad = self._recipe_with_ingredients("Salad", ["Tomato", "Lettuce"])
        CalendarMeal.objects.create(
            date=self.monday, meal_type=MealType.LUNCH, recipe=pasta
        )
        CalendarMeal.objects.create(
            date=self.monday + datetime.timedelta(days=1),
            meal_type=MealType.DINNER,
            recipe=salad,
        )

        response = self.client.post(reverse("week_export_shopping_list"))
        self.assertEqual(response.status_code, 200)

        todo = Todo.objects.get()
        self.assertTrue(todo.name.startswith("Shopping list "))
        names = sorted(todo.subtasks.values_list("name", flat=True))
        # Tomato appears in both recipes but is listed once.
        self.assertEqual(names, ["Lettuce", "Pasta", "Tomato"])

    def test_export_ignores_meals_outside_the_current_week(self):
        recipe = self._recipe_with_ingredients("NextWeek", ["Onion"])
        CalendarMeal.objects.create(
            date=self.monday + datetime.timedelta(days=7),
            meal_type=MealType.LUNCH,
            recipe=recipe,
        )

        self.client.post(reverse("week_export_shopping_list"))

        # Nothing scheduled this week -> no todo created.
        self.assertFalse(Todo.objects.exists())
