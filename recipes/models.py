from django.conf import settings
from django.db import models
from django.urls import reverse


class RecipeCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Recipe(models.Model):
    name = models.CharField(max_length=200)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    category = models.ForeignKey(
        RecipeCategory,
        on_delete=models.SET_NULL,
        null=True,
    )
    description = models.TextField()

    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse("recipe_detail", kwargs={"pk": self.pk})


class IngredientCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        IngredientCategory,
        on_delete=models.SET_NULL,
        null=True,
    )

    def __str__(self):
        return self.name


class Unit(models.Model):
    class UnitType(models.TextChoices):
        MASS = "mass", "Mass"
        VOLUME = "volume", "Volume"
        COUNT = "count", "Count"
        TEMPERATURE = "temperature", "Temperature"
        LENGTH = "length", "Length"

    name = models.CharField(max_length=100)
    abbreviation = models.CharField(max_length=20)
    unit_type = models.CharField(max_length=30, choices=UnitType.choices)

    def __str__(self):
        return self.abbreviation


class RecipeIngredient(models.Model):
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.PROTECT,
    )
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE)
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    prep_note = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.quantity or ''} {self.unit or ''} {self.ingredient} {self.prep_note or ''}".strip()
