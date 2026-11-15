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

        self.assertContains(response, '<details class="template-row"', count=2)
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


class PlannerCalendarPageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        today = datetime.date.today()
        self.monday = today - datetime.timedelta(days=today.weekday())
        self.recipe = Recipe.objects.create(name="Stew", description="d", servings=2)

    def test_defaults_to_this_week_and_the_next(self):
        response = self.client.get(reverse("planner_calendar"))
        self.assertEqual(response.context["selected_monday"], self.monday)
        self.assertEqual(
            [w["monday"] for w in response.context["weeks"]],
            [self.monday, self.monday + datetime.timedelta(weeks=1)],
        )
        self.assertContains(response, "This week")

    def test_week_param_selects_that_week_and_snaps_to_monday(self):
        wednesday = self.monday + datetime.timedelta(weeks=3, days=2)
        response = self.client.get(
            reverse("planner_calendar"), {"week": wednesday.isoformat()}
        )
        selected = self.monday + datetime.timedelta(weeks=3)
        self.assertEqual(response.context["selected_monday"], selected)
        self.assertContains(
            response,
            f'href="?week={(selected - datetime.timedelta(weeks=1)).isoformat()}"',
        )
        self.assertContains(
            response,
            f'href="?week={(selected + datetime.timedelta(weeks=1)).isoformat()}"',
        )
        self.assertContains(response, "Back to this week")

    def test_bad_week_param_falls_back_to_this_week(self):
        response = self.client.get(reverse("planner_calendar"), {"week": "soon"})
        self.assertEqual(response.context["selected_monday"], self.monday)

    def test_day_strip_links_to_each_day_section(self):
        response = self.client.get(reverse("planner_calendar"))
        for offset in range(7):
            iso = (self.monday + datetime.timedelta(days=offset)).isoformat()
            self.assertContains(response, f'href="#day-{iso}"')
            self.assertContains(response, f'id="day-{iso}"')

    def test_add_only_on_empty_slots(self):
        CalendarMeal.objects.create(
            date=self.monday, meal_type=MealType.LUNCH, recipe=self.recipe
        )
        lunch = self.client.get(
            reverse("calendarmeal_cell", args=[self.monday.isoformat(), MealType.LUNCH])
        )
        dinner = self.client.get(
            reverse(
                "calendarmeal_cell", args=[self.monday.isoformat(), MealType.DINNER]
            )
        )
        self.assertNotContains(lunch, "slot__add")
        self.assertContains(lunch, "Replace lunch on Monday")
        self.assertContains(lunch, "Remove lunch on Monday")
        self.assertContains(dinner, 'aria-label="Add dinner on Monday"')

    def test_anonymous_sees_meals_but_no_controls(self):
        CalendarMeal.objects.create(
            date=self.monday, meal_type=MealType.LUNCH, recipe=self.recipe
        )
        self.client.logout()
        response = self.client.get(reverse("planner_calendar"))
        self.assertContains(response, "Stew")
        self.assertNotContains(response, "slot__add")
        self.assertNotContains(response, "Export shopping list")

    def test_week_toolbar_has_desktop_buttons_and_mobile_menu(self):
        response = self.client.get(reverse("planner_calendar"))
        iso = self.monday.isoformat()
        # Each template action appears twice per week: button + menu item.
        self.assertContains(
            response, f'hx-get="{reverse("week_apply_form", args=[iso])}"', count=2
        )
        self.assertContains(response, 'aria-label="Template actions"', count=2)

    def test_export_success_links_to_todos(self):
        recipe = Recipe.objects.create(name="Salad", description="d", servings=1)
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=Ingredient.objects.create(name="lettuce")
        )
        CalendarMeal.objects.create(
            date=self.monday, meal_type=MealType.LUNCH, recipe=recipe
        )
        lettuce = Ingredient.objects.get(name="lettuce")
        response = self.client.post(
            reverse("week_export_shopping_list", args=[self.monday.isoformat()]),
            {"name": "Shop", "ingredient": [lettuce.pk]},
        )
        self.assertContains(response, "notice--success")
        self.assertContains(response, f'href="{reverse("todo_list")}"')


class TemplatePagesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        self.recipe = Recipe.objects.create(name="Stew", description="d", servings=2)
        self.template = TemplateWeek.objects.create(
            name="Usual", description="Our week"
        )
        TemplateMeal.objects.create(
            template=self.template,
            weekday=Weekday.MONDAY,
            meal_type=MealType.LUNCH,
            recipe=self.recipe,
        )

    def test_create_page_and_redirect_to_new_template(self):
        self.assertEqual(
            self.client.get(reverse("templateweek_create")).status_code, 200
        )
        response = self.client.post(
            reverse("templateweek_create"), {"name": "Summer", "description": ""}
        )
        created = TemplateWeek.objects.get(name="Summer")
        self.assertRedirects(
            response, reverse("templateweek_detail", args=[created.pk])
        )

    def test_create_requires_name_and_login(self):
        response = self.client.post(reverse("templateweek_create"), {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TemplateWeek.objects.count(), 1)
        self.client.logout()
        response = self.client.get(reverse("templateweek_create"))
        self.assertEqual(response.status_code, 302)

    def test_list_rows_show_count_description_and_open(self):
        response = self.client.get(reverse("templateweek_list"))
        self.assertContains(response, "1/14 meals")
        self.assertContains(response, "Our week")
        self.assertContains(response, reverse("templateweek_create"))
        # Preview slots are read-only: empty ones say so instead of offering Add.
        self.assertContains(response, "slot--readonly")
        self.assertNotContains(response, "slot__add")

    def test_list_empty_state(self):
        TemplateWeek.objects.all().delete()
        response = self.client.get(reverse("templateweek_list"))
        self.assertContains(response, "No week templates yet")

    def test_detail_uses_editable_slots_with_day_labels(self):
        response = self.client.get(
            reverse("templateweek_detail", args=[self.template.pk])
        )
        self.assertContains(response, "1/14 meals · Our week")
        self.assertContains(response, 'id="cell-1-lunch"')
        self.assertContains(response, 'aria-label="Replace lunch on Monday"')
        self.assertContains(response, 'aria-label="Add dinner on Monday"')

    def test_swapped_cell_keeps_day_label(self):
        response = self.client.get(
            reverse("templatemeal_cell", args=[self.template.pk, 2, MealType.DINNER])
        )
        self.assertContains(response, 'aria-label="Add dinner on Tuesday"')
