import datetime
import io
import os
import shutil
import tempfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import (
    Ingredient,
    IngredientCategory,
    Recipe,
    RecipeCategory,
    RecipeIngredient,
)


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
        for heading in ["Breakfast", "Dinner", "Uncategorized"]:
            self.assertContains(
                response,
                f'<h2 class="recipe-group__title">{heading}</h2>',
                html=True,
            )


class RecipeDetailTests(TestCase):
    def test_shows_category(self):
        category = RecipeCategory.objects.create(name="Dessert")
        recipe = Recipe.objects.create(
            name="Flan", category=category, description="d", servings=4
        )
        response = self.client.get(recipe.get_absolute_url())
        self.assertContains(response, '<span class="badge">Dessert</span>', html=True)

    def test_shows_uncategorized_when_missing(self):
        recipe = Recipe.objects.create(name="Toast", description="d", servings=1)
        response = self.client.get(recipe.get_absolute_url())
        self.assertContains(
            response,
            '<span class="badge badge--neutral">Uncategorized</span>',
            html=True,
        )


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
        for heading in ["Dairy", "Vegetables", "Uncategorized"]:
            self.assertContains(
                response,
                f'<h2 class="recipe-group__title">{heading}</h2>',
                html=True,
            )

    def test_recipe_list_links_to_ingredients(self):
        response = self.client.get(reverse("recipe_list"))
        self.assertContains(response, f'href="{reverse("ingredient_list")}"')


class RecipeCatalogTests(TestCase):
    def setUp(self):
        self.meat = RecipeCategory.objects.create(name="carnes")
        self.soup = RecipeCategory.objects.create(name="sopas")
        Recipe.objects.create(
            name="Pollo", category=self.meat, description="", servings=2
        )
        Recipe.objects.create(
            name="Pollo asado", category=self.meat, description="", servings=4
        )
        Recipe.objects.create(
            name="Crema de pollo", category=self.soup, description="", servings=2
        )
        Recipe.objects.create(name="Tostadas", description="", servings=1)

    def _names(self, **params):
        response = self.client.get(reverse("recipe_list"), params)
        return [r.name for r in response.context["recipe_list"]]

    def test_search_by_name_is_case_insensitive(self):
        self.assertEqual(
            self._names(q="POLLO"), ["Pollo", "Pollo asado", "Crema de pollo"]
        )

    def test_filter_by_category(self):
        self.assertEqual(self._names(category=self.soup.pk), ["Crema de pollo"])

    def test_filter_uncategorized(self):
        self.assertEqual(self._names(category="none"), ["Tostadas"])

    def test_search_and_category_combine(self):
        self.assertEqual(self._names(q="asado", category=self.meat.pk), ["Pollo asado"])

    def test_unknown_category_value_shows_all(self):
        self.assertEqual(len(self._names(category="junk")), 4)

    def test_sidebar_counts_and_active_item(self):
        response = self.client.get(reverse("recipe_list"), {"category": self.meat.pk})
        counts = {c.name: c.recipe_count for c in response.context["categories"]}
        self.assertEqual(counts, {"carnes": 2, "sopas": 1})
        self.assertEqual(response.context["uncategorized_count"], 1)
        self.assertEqual(response.context["total_count"], 4)
        self.assertContains(response, 'class="category-nav__item is-active"')

    def test_cards_show_servings_and_ingredient_count(self):
        recipe = Recipe.objects.get(name="Pollo")
        RecipeIngredient.objects.create(
            recipe=recipe, ingredient=Ingredient.objects.create(name="pollo")
        )
        response = self.client.get(reverse("recipe_list"))
        self.assertContains(response, "1 ingredient<")
        self.assertContains(response, "4 servings")

    def test_no_match_empty_state(self):
        response = self.client.get(reverse("recipe_list"), {"q": "lasaña"})
        self.assertContains(response, "No recipes match “lasaña”")
        self.assertContains(response, "Clear search")

    def test_empty_category_state(self):
        empty = RecipeCategory.objects.create(name="postres")
        response = self.client.get(reverse("recipe_list"), {"category": empty.pk})
        self.assertContains(response, "Nothing in postres yet")

    def test_no_recipes_state(self):
        Recipe.objects.all().delete()
        response = self.client.get(reverse("recipe_list"))
        self.assertContains(response, "No recipes yet")


class RecipeFormTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cook", password="x")
        self.client.force_login(self.user)
        self.category = RecipeCategory.objects.create(name="sopas")

    def _post_data(self, **extra):
        data = {
            "name": "Sopa",
            "category": self.category.pk,
            "description": "Hervir.",
            "servings": 2,
            "recipeingredient_set-TOTAL_FORMS": 1,
            "recipeingredient_set-INITIAL_FORMS": 0,
            "recipeingredient_set-MIN_NUM_FORMS": 0,
            "recipeingredient_set-MAX_NUM_FORMS": 1000,
            "recipeingredient_set-0-ingredient_name": "Cebolla",
            "recipeingredient_set-0-quantity": "100",
            "recipeingredient_set-0-unit": "",
            "recipeingredient_set-0-prep_note": "picada",
        }
        data.update(extra)
        return data

    def test_create_page_renders_formset_rows_and_blueprint(self):
        response = self.client.get(reverse("recipe_create"))
        self.assertContains(response, 'id="empty-ingredient-form"')
        self.assertContains(response, "recipeingredient_set-__prefix__-ingredient_name")
        self.assertContains(response, 'name="recipeingredient_set-0-DELETE"')

    def test_create_saves_recipe_and_ingredients(self):
        response = self.client.post(reverse("recipe_create"), self._post_data())
        recipe = Recipe.objects.get(name="Sopa")
        self.assertRedirects(response, recipe.get_absolute_url())
        row = recipe.recipeingredient_set.get()
        self.assertEqual(row.ingredient.name, "cebolla")
        self.assertEqual(row.prep_note, "picada")

    def test_edit_can_remove_ingredient_row(self):
        self.client.post(reverse("recipe_create"), self._post_data())
        recipe = Recipe.objects.get(name="Sopa")
        row = recipe.recipeingredient_set.get()

        self.client.post(
            reverse("recipe_update", args=[recipe.pk]),
            self._post_data(
                **{
                    "recipeingredient_set-INITIAL_FORMS": 1,
                    "recipeingredient_set-0-id": row.pk,
                    "recipeingredient_set-0-recipe": recipe.pk,
                    "recipeingredient_set-0-DELETE": "on",
                }
            ),
        )

        self.assertFalse(recipe.recipeingredient_set.exists())

    def test_detail_shows_ingredients_and_actions(self):
        self.client.post(reverse("recipe_create"), self._post_data())
        recipe = Recipe.objects.get(name="Sopa")
        response = self.client.get(recipe.get_absolute_url())
        self.assertContains(
            response, '<span class="ingredient-list__amount">100</span>', html=True
        )
        self.assertContains(response, reverse("recipe_update", args=[recipe.pk]))
        self.assertContains(response, reverse("recipe_delete", args=[recipe.pk]))


def _photo(name="photo.png", size=(2400, 1600), color=(200, 120, 60), fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return SimpleUploadedFile(
        name, buffer.getvalue(), content_type=f"image/{fmt.lower()}"
    )


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="mealplanner-test-media-"))
class RecipeImageTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="cook", password="x")
        self.client.force_login(self.user)
        self.category = RecipeCategory.objects.create(name="carnes")

    def _create(self, **extra):
        data = {
            "name": "Pollo",
            "category": self.category.pk,
            "description": "Plancha.",
            "servings": 2,
            "recipeingredient_set-TOTAL_FORMS": 0,
            "recipeingredient_set-INITIAL_FORMS": 0,
            "recipeingredient_set-MIN_NUM_FORMS": 0,
            "recipeingredient_set-MAX_NUM_FORMS": 1000,
        }
        data.update(extra)
        return self.client.post(reverse("recipe_create"), data)

    def test_upload_is_resized_and_stored_as_jpeg(self):
        self._create(image=_photo())
        recipe = Recipe.objects.get()
        self.assertTrue(recipe.image.name.startswith("recipes/"))
        self.assertTrue(recipe.image.name.endswith(".jpg"))
        with Image.open(recipe.image.path) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertEqual(max(img.size), Recipe.IMAGE_MAX_SIZE)
            self.assertEqual(img.size, (1200, 800))

    def test_image_is_optional(self):
        self._create()
        self.assertFalse(Recipe.objects.get().image)

    def test_non_image_upload_is_rejected(self):
        bogus = SimpleUploadedFile(
            "notes.txt", b"not an image", content_type="text/plain"
        )
        response = self._create(image=bogus)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Recipe.objects.exists())

    def test_replacing_and_clearing_delete_old_files(self):
        self._create(image=_photo())
        recipe = Recipe.objects.get()
        first_path = recipe.image.path

        recipe.image = _photo(name="second.png", color=(10, 200, 10))
        recipe.save()
        self.assertFalse(os.path.exists(first_path))
        second_path = recipe.image.path
        self.assertTrue(os.path.exists(second_path))

        self.client.post(
            reverse("recipe_update", args=[recipe.pk]),
            {
                "name": "Pollo",
                "category": self.category.pk,
                "description": "Plancha.",
                "servings": 2,
                "image-clear": "on",
                "recipeingredient_set-TOTAL_FORMS": 0,
                "recipeingredient_set-INITIAL_FORMS": 0,
                "recipeingredient_set-MIN_NUM_FORMS": 0,
                "recipeingredient_set-MAX_NUM_FORMS": 1000,
            },
        )
        recipe.refresh_from_db()
        self.assertFalse(recipe.image)
        self.assertFalse(os.path.exists(second_path))

    def test_deleting_recipe_deletes_photo(self):
        self._create(image=_photo())
        recipe = Recipe.objects.get()
        path = recipe.image.path
        self.client.post(reverse("recipe_delete", args=[recipe.pk]))
        self.assertFalse(os.path.exists(path))

    def test_list_and_detail_show_photo_or_placeholder(self):
        self._create(image=_photo())
        Recipe.objects.create(
            name="Sin foto", category=self.category, description="", servings=1
        )
        recipe = Recipe.objects.get(name="Pollo")

        listing = self.client.get(reverse("recipe_list"))
        self.assertContains(listing, f'src="{recipe.image.url}"')
        self.assertContains(listing, "recipe-card__thumb--empty")

        detail = self.client.get(recipe.get_absolute_url())
        self.assertContains(detail, "recipe-hero--with-image")
        without = self.client.get(
            Recipe.objects.get(name="Sin foto").get_absolute_url()
        )
        self.assertNotContains(without, "recipe-hero--with-image")

    def test_form_has_multipart_and_photo_controls(self):
        response = self.client.get(reverse("recipe_create"))
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="image"')

    def test_oversized_upload_is_rejected(self):
        from recipes.models import IMAGE_MAX_UPLOAD_MB, validate_image_size
        from django.core.exceptions import ValidationError

        class Big:
            size = IMAGE_MAX_UPLOAD_MB * 1024 * 1024 + 1

        with self.assertRaises(ValidationError):
            validate_image_size(Big())


class RecipeDeleteInUseTests(TestCase):
    def setUp(self):
        from planner.models import CalendarMeal, MealType, TemplateMeal, TemplateWeek

        self.user = get_user_model().objects.create_user(username="cook", password="x")
        self.client.force_login(self.user)
        self.recipe = Recipe.objects.create(name="Stew", description="d", servings=2)
        self.date = datetime.date(2030, 1, 9)
        CalendarMeal.objects.create(
            date=self.date, meal_type=MealType.LUNCH, recipe=self.recipe
        )
        self.template = TemplateWeek.objects.create(name="Usual")
        TemplateMeal.objects.create(
            template=self.template,
            weekday=1,
            meal_type=MealType.DINNER,
            recipe=self.recipe,
        )
        self.url = reverse("recipe_delete", args=[self.recipe.pk])

    def test_page_lists_where_the_recipe_is_used_and_offers_no_delete(self):
        response = self.client.get(self.url)
        self.assertContains(response, "is in use")
        self.assertContains(response, f"?week={self.date.isoformat()}")
        self.assertContains(
            response, reverse("templateweek_detail", args=[self.template.pk])
        )
        self.assertNotContains(response, "Delete recipe</button>")

    def test_posting_anyway_does_not_crash_or_delete(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is in use")
        self.assertTrue(Recipe.objects.filter(pk=self.recipe.pk).exists())

    def test_unused_recipe_can_be_deleted(self):
        free = Recipe.objects.create(name="Toast", description="d", servings=1)
        url = reverse("recipe_delete", args=[free.pk])
        self.assertContains(self.client.get(url), "Delete recipe</button>")
        self.assertRedirects(self.client.post(url), reverse("recipe_list"))
        self.assertFalse(Recipe.objects.filter(pk=free.pk).exists())
