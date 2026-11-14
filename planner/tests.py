import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from recipes.models import (
    Ingredient,
    IngredientCategory,
    Recipe,
    RecipeIngredient,
    Unit,
)
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
        self.iso = self.monday.isoformat()
        self.grams = Unit.objects.create(
            name="gram", abbreviation="g", unit_type=Unit.UnitType.MASS
        )
        self.units = Unit.objects.create(
            name="unit", abbreviation="ud", unit_type=Unit.UnitType.COUNT
        )
        self.veg = IngredientCategory.objects.create(name="Vegetables")
        self.pantry = IngredientCategory.objects.create(name="Pantry")

    def _ingredient(self, name, category=None):
        # Ingredient.save() lowercases names, so look up by the normalized
        # form to avoid tripping the case-insensitive unique constraint.
        ingredient, _ = Ingredient.objects.get_or_create(
            name=name.lower(), defaults={"category": category}
        )
        return ingredient

    def _recipe(self, name, rows):
        """rows: (ingredient, quantity or None, unit or None)."""
        recipe = Recipe.objects.create(name=name, description="d", servings=2)
        for ingredient, quantity, unit in rows:
            RecipeIngredient.objects.create(
                recipe=recipe,
                ingredient=ingredient,
                quantity=None if quantity is None else Decimal(quantity),
                unit=unit,
            )
        return recipe

    def _schedule(self, recipe, day=0, meal_type=MealType.LUNCH):
        CalendarMeal.objects.create(
            date=self.monday + datetime.timedelta(days=day),
            meal_type=meal_type,
            recipe=recipe,
        )

    def _week_setup(self):
        tomato = self._ingredient("Tomato", self.veg)
        pasta = self._ingredient("Pasta", self.pantry)
        salt = self._ingredient("Salt")
        lettuce = self._ingredient("Lettuce", self.veg)
        self._schedule(
            self._recipe(
                "Pasta",
                [
                    (tomato, "1", self.units),
                    (pasta, "200", self.grams),
                    (salt, None, None),
                ],
            )
        )
        self._schedule(
            self._recipe(
                "Salad", [(tomato, "300", self.grams), (lettuce, "1", self.units)]
            ),
            day=1,
        )
        return tomato, pasta, salt, lettuce

    def test_preview_sums_per_unit_and_groups_by_category(self):
        self._week_setup()

        response = self.client.get(reverse("week_shopping_form", args=[self.iso]))

        self.assertContains(response, "<dialog")
        self.assertEqual(
            [i["label"] for i in response.context["items"]],
            # Pantry, Vegetables, then uncategorized last.
            ["Pasta: 200 g", "Lettuce: 1 ud", "Tomato: 1 ud + 300 g", "Salt"],
        )
        self.assertContains(response, "Shopping list week of")
        # Nothing is created until the dialog is confirmed.
        self.assertFalse(Todo.objects.exists())

    def test_recipe_scheduled_twice_counts_twice(self):
        tomato = self._ingredient("Tomato")
        recipe = self._recipe("Salad", [(tomato, "150", self.grams)])
        self._schedule(recipe, day=0)
        self._schedule(recipe, day=0, meal_type=MealType.DINNER)

        response = self.client.get(reverse("week_shopping_form", args=[self.iso]))

        self.assertEqual(
            [i["label"] for i in response.context["items"]], ["Tomato: 300 g"]
        )

    def test_confirm_creates_todo_with_ticked_items_name_and_due_date(self):
        tomato, pasta, salt, lettuce = self._week_setup()

        response = self.client.post(
            reverse("week_export_shopping_list", args=[self.iso]),
            {
                "name": "Big shop",
                "due_date": "2030-01-05",
                "ingredient": [tomato.pk, pasta.pk],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<dialog")
        todo = Todo.objects.get()
        self.assertEqual(todo.name, "Big shop")
        self.assertEqual(todo.due_date, datetime.date(2030, 1, 5))
        self.assertEqual(
            sorted(todo.subtasks.values_list("name", flat=True)),
            ["Pasta: 200 g", "Tomato: 1 ud + 300 g"],
        )

    def test_confirm_ignores_ingredients_not_scheduled(self):
        tomato, *_ = self._week_setup()
        extra = self._ingredient("Caviar")

        self.client.post(
            reverse("week_export_shopping_list", args=[self.iso]),
            {"name": "Shop", "ingredient": [tomato.pk, extra.pk]},
        )

        self.assertEqual(
            list(Todo.objects.get().subtasks.values_list("name", flat=True)),
            ["Tomato: 1 ud + 300 g"],
        )

    def test_confirm_with_nothing_ticked_keeps_dialog_open(self):
        self._week_setup()

        response = self.client.post(
            reverse("week_export_shopping_list", args=[self.iso]), {"name": "Shop"}
        )

        self.assertContains(response, "<dialog")
        self.assertContains(response, "Tick at least one item.")
        self.assertFalse(Todo.objects.exists())

    def test_confirm_rejects_bad_due_date(self):
        tomato, *_ = self._week_setup()

        response = self.client.post(
            reverse("week_export_shopping_list", args=[self.iso]),
            {"name": "Shop", "due_date": "nope", "ingredient": [tomato.pk]},
        )

        self.assertContains(response, "Enter a valid due date.")
        self.assertFalse(Todo.objects.exists())

    def test_preview_ignores_meals_outside_the_week(self):
        tomato = self._ingredient("Onion")
        self._schedule(self._recipe("NextWeek", [(tomato, None, None)]), day=7)

        response = self.client.get(reverse("week_shopping_form", args=[self.iso]))

        self.assertNotContains(response, "<dialog")
        self.assertContains(response, "No ingredients scheduled this week.")

    def test_next_week_preview_uses_next_weeks_meals(self):
        onion = self._ingredient("Onion")
        self._schedule(self._recipe("NextWeek", [(onion, "2", self.units)]), day=7)
        next_monday = self.monday + datetime.timedelta(days=7)

        response = self.client.get(
            reverse("week_shopping_form", args=[next_monday.isoformat()])
        )

        self.assertEqual(
            [i["label"] for i in response.context["items"]], ["Onion: 2 ud"]
        )
        self.assertContains(response, f"Shopping list week of {next_monday:%Y-%m-%d}")


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


class TemplateWeekListTests(TestCase):
    def test_list_previews_each_template_read_only(self):
        recipe = Recipe.objects.create(name="Stew", description="d", servings=2)
        template = TemplateWeek.objects.create(name="Usual")
        TemplateMeal.objects.create(
            template=template,
            weekday=Weekday.WEDNESDAY,
            meal_type=MealType.DINNER,
            recipe=recipe,
        )
        TemplateWeek.objects.create(name="Empty")

        response = self.client.get(reverse("templateweek_list"))

        self.assertContains(response, "<details", count=2)
        self.assertContains(response, "1/14 meals")
        self.assertContains(response, "0/14 meals")
        self.assertContains(response, f'href="{recipe.get_absolute_url()}"')
        self.assertContains(
            response, f'href="{reverse("templateweek_detail", args=[template.pk])}"'
        )
        # Read-only: no swap/remove/add controls in the preview.
        self.assertNotContains(response, "hx-get")
        self.assertNotContains(response, "hx-delete")

    def test_list_uses_constant_queries(self):
        recipe = Recipe.objects.create(name="Stew", description="d", servings=2)
        for name in ["A", "B", "C"]:
            template = TemplateWeek.objects.create(name=name)
            TemplateMeal.objects.create(
                template=template,
                weekday=Weekday.MONDAY,
                meal_type=MealType.LUNCH,
                recipe=recipe,
            )

        # Templates, their meals, and the meals' recipes.
        with self.assertNumQueries(3):
            self.client.get(reverse("templateweek_list"))
