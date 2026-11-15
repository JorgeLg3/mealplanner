import re
import datetime
from decimal import Decimal

from accounts.models import User
from django.test import TestCase
from django.urls import reverse

from django_project.test_utils import LoggedInTestCase

from recipes.models import (
    Ingredient,
    IngredientCategory,
    Recipe,
    RecipeIngredient,
    Unit,
)
from todo.models import Todo

from .models import (
    CalendarMeal,
    HouseholdSettings,
    MealType,
    TemplateMeal,
    TemplateWeek,
    Weekday,
)


class ExportShoppingListTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
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
        self.veg = IngredientCategory.objects.get_or_create(name="Vegetables")[0]
        self.pantry = IngredientCategory.objects.get_or_create(name="Pantry")[0]

    def _ingredient(self, name, category=None):
        # Ingredient.save() lowercases names, so look up by the normalized
        # form to avoid tripping the case-insensitive unique constraint.
        ingredient, _ = Ingredient.objects.get_or_create(
            name=name.lower(),
            defaults={"category": category or IngredientCategory.other()},
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
        # Subtasks keep the preview's category order (Pantry before Vegetables).
        self.assertEqual(
            list(todo.subtasks.values_list("name", flat=True)),
            ["Pasta: 200 g", "Tomato: 1 ud + 300 g"],
        )
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
        self.user = User.objects.create_user(username="tester", password="x")
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

    def test_next_week_actions_reachable_via_week_param(self):
        response = self.client.get(
            reverse("planner_calendar"), {"week": self.next_monday.isoformat()}
        )
        self.assertContains(
            response, reverse("week_apply_form", args=[self.next_monday.isoformat()])
        )
        self.assertNotContains(
            response, reverse("week_apply_form", args=[self.monday.isoformat()])
        )


class MealCellTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
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


class TemplateWeekListTests(LoggedInTestCase):
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

        # Session + user (login), then templates, their meals, and the
        # meals' recipes: constant however many templates there are.
        with self.assertNumQueries(5):
            self.client.get(reverse("templateweek_list"))


class PlannerCalendarPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        self.client.force_login(self.user)
        today = datetime.date.today()
        self.monday = today - datetime.timedelta(days=today.weekday())
        self.recipe = Recipe.objects.create(name="Stew", description="d", servings=2)

    def test_shows_one_week_defaulting_to_this_week(self):
        response = self.client.get(reverse("planner_calendar"))
        self.assertEqual(response.context["selected_monday"], self.monday)
        days = [d["date"] for d in response.context["days"]]
        self.assertEqual(days[0], self.monday)
        self.assertEqual(len(days), 7)
        self.assertContains(response, f'id="week-{self.monday.isoformat()}"', count=1)
        next_monday = self.monday + datetime.timedelta(weeks=1)
        self.assertNotContains(response, f'id="week-{next_monday.isoformat()}"')
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

    def test_logged_out_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("planner_calendar"))
        self.assertRedirects(response, "/auth/login/?next=/planner/")

    def test_week_toolbar_has_desktop_buttons_and_mobile_menu(self):
        response = self.client.get(reverse("planner_calendar"))
        iso = self.monday.isoformat()
        # Each template action appears twice per week: button + menu item.
        self.assertContains(
            response, f'hx-get="{reverse("week_apply_form", args=[iso])}"', count=2
        )
        self.assertContains(response, 'aria-label="Template actions"', count=1)

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
        self.user = User.objects.create_user(username="tester", password="x")
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


class TemplateEditDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        self.client.force_login(self.user)
        self.recipe = Recipe.objects.create(name="Stew", description="d", servings=2)
        self.template = TemplateWeek.objects.create(name="Usual", description="Old")
        TemplateMeal.objects.create(
            template=self.template,
            weekday=Weekday.MONDAY,
            meal_type=MealType.LUNCH,
            recipe=self.recipe,
        )

    def test_detail_offers_edit_and_delete(self):
        response = self.client.get(
            reverse("templateweek_detail", args=[self.template.pk])
        )
        self.assertContains(
            response, reverse("templateweek_update", args=[self.template.pk])
        )
        self.assertContains(
            response, reverse("templateweek_delete", args=[self.template.pk])
        )

    def test_edit_renames_and_keeps_meals(self):
        url = reverse("templateweek_update", args=[self.template.pk])
        self.assertContains(self.client.get(url), 'value="Usual"')
        response = self.client.post(url, {"name": "Winter", "description": "Cosy"})
        self.assertRedirects(
            response, reverse("templateweek_detail", args=[self.template.pk])
        )
        self.template.refresh_from_db()
        self.assertEqual(
            (self.template.name, self.template.description), ("Winter", "Cosy")
        )
        self.assertEqual(self.template.meals.count(), 1)

    def test_delete_removes_template_and_meals_but_not_planned_weeks(self):
        today = datetime.date.today()
        CalendarMeal.objects.create(
            date=today, meal_type=MealType.LUNCH, recipe=self.recipe
        )
        url = reverse("templateweek_delete", args=[self.template.pk])
        self.assertContains(self.client.get(url), "1 meal will be removed")

        response = self.client.post(url)

        self.assertRedirects(response, reverse("templateweek_list"))
        self.assertFalse(TemplateWeek.objects.exists())
        self.assertFalse(TemplateMeal.objects.exists())
        self.assertTrue(CalendarMeal.objects.filter(date=today).exists())

    def test_edit_and_delete_require_login(self):
        self.client.logout()
        for name in ["templateweek_update", "templateweek_delete"]:
            with self.subTest(view=name):
                url = reverse(name, args=[self.template.pk])
                self.assertEqual(self.client.get(url).status_code, 302)
                self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(TemplateWeek.objects.filter(name="Usual").exists())


class RecipePickerTests(TestCase):
    """The slot forms feed static/js/combobox.js via their <datalist>."""

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        self.client.force_login(self.user)
        Recipe.objects.create(name="Stew", description="d", servings=2)

    def test_calendar_and_template_forms_are_autosubmitting_comboboxes(self):
        template = TemplateWeek.objects.create(name="Usual")
        for url in [
            reverse("calendarmeal_form", args=["2030-01-07", MealType.LUNCH]),
            reverse("templatemeal_form", args=[template.pk, 1, MealType.LUNCH]),
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "data-autosubmit")
                self.assertContains(response, 'data-empty-text="No matching recipe"')
                self.assertContains(
                    response, '<option value="Stew"></option>', html=True
                )

    def test_layout_loads_combobox_script(self):
        response = self.client.get(reverse("planner_calendar"))
        self.assertRegex(
            response.content.decode(), r"/static/js/combobox\.[0-9a-f]+\.js"
        )


class ServingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="x")
        self.client.force_login(self.user)
        today = datetime.date.today()
        self.monday = today - datetime.timedelta(days=today.weekday())
        self.iso = self.monday.isoformat()
        self.grams = Unit.objects.create(
            name="gram", abbreviation="g", unit_type=Unit.UnitType.MASS
        )
        self.units = Unit.objects.create(
            name="unit", abbreviation="ud", unit_type=Unit.UnitType.COUNT
        )
        # A stew written for 4 people.
        self.stew = Recipe.objects.create(name="Stew", description="d", servings=4)
        RecipeIngredient.objects.create(
            recipe=self.stew,
            ingredient=Ingredient.objects.create(name="beef"),
            quantity=Decimal("400"),
            unit=self.grams,
        )
        RecipeIngredient.objects.create(
            recipe=self.stew,
            ingredient=Ingredient.objects.create(name="onion"),
            quantity=Decimal("3"),
            unit=self.units,
        )

    def _labels(self):
        response = self.client.get(reverse("week_shopping_form", args=[self.iso]))
        return sorted(i["label"] for i in response.context["items"])

    def _plan(self, servings=None, day=0, meal_type=MealType.LUNCH):
        return CalendarMeal.objects.create(
            date=self.monday + datetime.timedelta(days=day),
            meal_type=meal_type,
            recipe=self.stew,
            servings=servings,
        )

    def test_household_default_is_two(self):
        self.assertEqual(HouseholdSettings.get().default_servings, 2)

    def test_scales_to_household_default(self):
        self._plan()
        # 2 of 4 servings: half the beef; 1.5 onions round UP to 2.
        self.assertEqual(self._labels(), ["Beef: 200 g", "Onion: 2 ud"])

    def test_per_meal_servings_override_default(self):
        self._plan(servings=6)
        self.assertEqual(self._labels(), ["Beef: 600 g", "Onion: 5 ud"])

    def test_meals_add_up_then_round_once(self):
        self._plan()  # 2 servings
        self._plan(servings=3, meal_type=MealType.DINNER)  # 3 servings
        # 5/4 of the recipe: 500 g beef, 3.75 -> 4 onions.
        self.assertEqual(self._labels(), ["Beef: 500 g", "Onion: 4 ud"])

    def test_mass_rounding_precision(self):
        HouseholdSettings.objects.update_or_create(
            pk=1, defaults={"default_servings": 3}
        )
        self._plan()
        # 400 * 3/4 = 300 exactly; a 3-serving recipe gives repeating decimals.
        self.stew.servings = 7
        self.stew.save()
        labels = self._labels()
        self.assertIn("Beef: 171 g", labels)  # 400 * 3/7 = 171.43 -> 171

    def test_changing_default_updates_meals_without_own_servings(self):
        self._plan()
        self.client.post(reverse("household_servings"), {"default_servings": 4})
        self.assertEqual(HouseholdSettings.get().default_servings, 4)
        self.assertEqual(self._labels(), ["Beef: 400 g", "Onion: 3 ud"])

    def test_household_endpoint_reloads_and_rejects_bad_values(self):
        response = self.client.post(
            reverse("household_servings"), {"default_servings": 3}
        )
        self.assertEqual(response["HX-Refresh"], "true")
        for bad in ["0", "999", "lots"]:
            self.client.post(reverse("household_servings"), {"default_servings": bad})
        self.assertEqual(HouseholdSettings.get().default_servings, 3)

    def test_slot_form_saves_servings_and_default_is_stored_as_empty(self):
        url = reverse("calendarmeal", args=[self.iso, MealType.LUNCH])
        self.client.post(url, {"recipe": "Stew", "servings": "5"})
        self.assertEqual(CalendarMeal.objects.get().servings, 5)
        self.client.post(url, {"recipe": "Stew", "servings": "2"})
        self.assertIsNone(CalendarMeal.objects.get().servings)

    def test_blank_recipe_on_filled_slot_updates_only_servings(self):
        self._plan()
        response = self.client.post(
            reverse("calendarmeal", args=[self.iso, MealType.LUNCH]),
            {"recipe": "", "servings": "4"},
        )
        meal = CalendarMeal.objects.get()
        self.assertEqual((meal.recipe, meal.servings), (self.stew, 4))
        self.assertContains(response, 'title="4 servings"')

    def test_blank_recipe_on_empty_slot_is_an_error(self):
        response = self.client.post(
            reverse("calendarmeal", args=[self.iso, MealType.LUNCH]),
            {"recipe": "", "servings": "4"},
        )
        self.assertContains(response, "Pick a recipe from the list.")
        self.assertFalse(CalendarMeal.objects.exists())

    def test_invalid_servings_keeps_form_open(self):
        response = self.client.post(
            reverse("calendarmeal", args=[self.iso, MealType.LUNCH]),
            {"recipe": "Stew", "servings": "0"},
        )
        self.assertContains(response, "Servings must be between 1 and 50.")
        self.assertFalse(CalendarMeal.objects.exists())

    def test_form_prefills_stepper_and_keeps_recipe_input_empty(self):
        self._plan(servings=5)
        response = self.client.get(
            reverse("calendarmeal_form", args=[self.iso, MealType.LUNCH])
        )
        self.assertContains(response, 'name="servings" value="5"')
        self.assertContains(response, 'placeholder="Keep Stew, or search…"')
        # The recipe <input> itself has no value (the datalist option does).
        recipe_input = re.search(
            r'<input[^>]*name="recipe"[^>]*>', response.content.decode()
        )
        assert recipe_input is not None
        self.assertNotIn("value=", recipe_input.group(0))

    def test_badge_only_for_meals_with_own_servings(self):
        self._plan()
        self._plan(servings=6, meal_type=MealType.DINNER)
        response = self.client.get(reverse("planner_calendar"))
        self.assertContains(response, 'title="6 servings"', count=1)

    def test_applied_template_meals_use_household_default(self):
        template = TemplateWeek.objects.create(name="Usual")
        TemplateMeal.objects.create(
            template=template, weekday=1, meal_type=MealType.LUNCH, recipe=self.stew
        )
        self.client.post(
            reverse("week_apply_template", args=[self.iso]), {"template": template.pk}
        )
        self.assertIsNone(CalendarMeal.objects.get().servings)

    def test_template_forms_have_no_servings(self):
        template = TemplateWeek.objects.create(name="Usual")
        response = self.client.get(
            reverse("templatemeal_form", args=[template.pk, 1, MealType.LUNCH])
        )
        self.assertNotContains(response, 'name="servings"')

    def test_planner_shows_household_control_collapsed(self):
        response = self.client.get(reverse("planner_calendar"))
        # Closed by default: a "👥 2" toggle; the stepper sits in its panel.
        self.assertContains(response, '<details class="menu household-servings">')
        self.assertContains(response, 'aria-label="Cooking for 2. Change"')
        self.assertContains(response, 'name="default_servings" value="2"')


class CalendarSlotRowTests(LoggedInTestCase):
    """Phones show slots as rows: thumbnail · label + name · actions."""

    def test_filled_and_empty_slot_markup(self):
        recipe = Recipe.objects.create(name="Stew", description="d", servings=2)
        date = datetime.date(2030, 1, 7)
        CalendarMeal.objects.create(date=date, meal_type=MealType.LUNCH, recipe=recipe)

        lunch = self.client.get(
            reverse("calendarmeal_cell", args=[date.isoformat(), MealType.LUNCH])
        )
        dinner = self.client.get(
            reverse("calendarmeal_cell", args=[date.isoformat(), MealType.DINNER])
        )

        # No photo: the placeholder tile keeps rows aligned.
        self.assertContains(lunch, "slot__thumb slot__thumb--empty")
        self.assertContains(lunch, '<div class="slot__body">')
        self.assertContains(lunch, "Replace lunch on Monday")
        self.assertContains(dinner, "Nothing planned")
        self.assertContains(dinner, 'aria-label="Add dinner on Monday"')
