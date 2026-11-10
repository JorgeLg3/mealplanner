import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from recipes.models import Ingredient, Recipe, RecipeIngredient
from todo.models import Todo

from .models import CalendarMeal, MealType, TemplateMeal, TemplateWeek, Weekday


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

        response = self.client.post(
            reverse("week_export_shopping_list", args=[self.monday.isoformat()])
        )
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

        self.client.post(
            reverse("week_export_shopping_list", args=[self.monday.isoformat()])
        )

        # Nothing scheduled this week -> no todo created.
        self.assertFalse(Todo.objects.exists())

    def test_export_next_week_uses_next_weeks_meals(self):
        next_monday = self.monday + datetime.timedelta(days=7)
        recipe = self._recipe_with_ingredients("NextWeek", ["Onion"])
        CalendarMeal.objects.create(
            date=next_monday, meal_type=MealType.LUNCH, recipe=recipe
        )

        self.client.post(
            reverse("week_export_shopping_list", args=[next_monday.isoformat()])
        )

        todo = Todo.objects.get()
        self.assertEqual(todo.name, f"Shopping list week of {next_monday:%Y-%m-%d}")
        self.assertEqual(list(todo.subtasks.values_list("name", flat=True)), ["Onion"])


class WeekActionsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        today = datetime.date.today()
        self.monday = today - datetime.timedelta(days=today.weekday())
        self.next_monday = self.monday + datetime.timedelta(days=7)
        self.recipe = Recipe.objects.create(name="Stew", description="d", servings=2)

    def test_apply_template_to_next_week_leaves_current_week_alone(self):
        current_recipe = Recipe.objects.create(name="Soup", description="d", servings=2)
        CalendarMeal.objects.create(
            date=self.monday, meal_type=MealType.LUNCH, recipe=current_recipe
        )
        template = TemplateWeek.objects.create(name="Usual")
        TemplateMeal.objects.create(
            template=template,
            weekday=Weekday.TUESDAY,
            meal_type=MealType.DINNER,
            recipe=self.recipe,
        )

        response = self.client.post(
            reverse("week_apply_template", args=[self.next_monday.isoformat()]),
            {"template": template.pk},
        )

        self.assertContains(response, f'id="week-{self.next_monday.isoformat()}"')
        self.assertTrue(
            CalendarMeal.objects.filter(
                date=self.next_monday + datetime.timedelta(days=1),
                meal_type=MealType.DINNER,
                recipe=self.recipe,
            ).exists()
        )
        # The current week's meal is untouched.
        self.assertTrue(
            CalendarMeal.objects.filter(
                date=self.monday, recipe=current_recipe
            ).exists()
        )

    def test_save_next_week_as_template(self):
        CalendarMeal.objects.create(
            date=self.next_monday + datetime.timedelta(days=2),
            meal_type=MealType.LUNCH,
            recipe=self.recipe,
        )

        self.client.post(
            reverse("week_save_template", args=[self.next_monday.isoformat()]),
            {"name": "Next"},
        )

        meal = TemplateWeek.objects.get(name="Next").meals.get()
        self.assertEqual(meal.weekday, Weekday.WEDNESDAY)
        self.assertEqual(meal.recipe, self.recipe)

    def test_rejects_dates_that_are_not_mondays(self):
        tuesday = self.monday + datetime.timedelta(days=1)
        for bad in [tuesday.isoformat(), "not-a-date"]:
            response = self.client.get(reverse("week_actions", args=[bad]))
            self.assertEqual(response.status_code, 404)

    def test_calendar_shows_action_bar_for_both_weeks(self):
        response = self.client.get(reverse("planner_calendar"))
        for monday in (self.monday, self.next_monday):
            self.assertContains(
                response, reverse("week_apply_form", args=[monday.isoformat()])
            )


class MealCellTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        self.recipe = Recipe.objects.create(name="Stew", description="d", servings=2)

    def test_calendar_cell_links_to_recipe_and_has_swap_button(self):
        date = datetime.date.today()
        CalendarMeal.objects.create(
            date=date, meal_type=MealType.LUNCH, recipe=self.recipe
        )

        response = self.client.get(
            reverse("calendarmeal_cell", args=[date.isoformat(), MealType.LUNCH])
        )

        self.assertContains(response, f'href="{self.recipe.get_absolute_url()}"')
        self.assertContains(
            response,
            f'hx-get="{reverse("calendarmeal_form", args=[date.isoformat(), MealType.LUNCH])}"',
        )

    def test_template_cell_links_to_recipe_and_has_swap_button(self):
        template = TemplateWeek.objects.create(name="Usual")
        TemplateMeal.objects.create(
            template=template,
            weekday=Weekday.MONDAY,
            meal_type=MealType.DINNER,
            recipe=self.recipe,
        )
        args = [template.pk, Weekday.MONDAY, MealType.DINNER]

        response = self.client.get(reverse("templatemeal_cell", args=args))

        self.assertContains(response, f'href="{self.recipe.get_absolute_url()}"')
        self.assertContains(
            response, f'hx-get="{reverse("templatemeal_form", args=args)}"'
        )
