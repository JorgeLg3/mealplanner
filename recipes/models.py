import io
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse


IMAGE_MAX_UPLOAD_MB = 15


def validate_image_size(fieldfile):
    """Reject huge uploads (same idea as the blog's validator). The cap is
    generous because phone photos are big; save() shrinks them anyway."""
    if fieldfile.size > IMAGE_MAX_UPLOAD_MB * 1024 * 1024:
        raise ValidationError(f"Max file size is {IMAGE_MAX_UPLOAD_MB} MB.")


# Fallback category for both recipes and ingredients: new ingredients without
# a category, and anything whose category gets deleted, land here. It can't
# be deleted itself and always sorts last.
OTHER_CATEGORY = "otros"


def other_last(field):
    """Sort key putting the "otros" category after the rest, e.g.
    order_by(other_last("category__name"), "category__name")."""
    return models.Case(
        models.When(**{f"{field}__iexact": OTHER_CATEGORY}, then=1),
        default=0,
        output_field=models.IntegerField(),
    )


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        abstract = True
        # Alphabetical with "otros" last, everywhere (dropdowns, admin, lists).
        ordering = [other_last("name"), "name"]

    def __str__(self):
        return self.name

    @property
    def is_other(self):
        return self.name.lower() == OTHER_CATEGORY

    @classmethod
    def other(cls):
        category = cls.objects.filter(name__iexact=OTHER_CATEGORY).first()
        return category or cls.objects.create(name=OTHER_CATEGORY)

    def delete(self, *args, **kwargs):
        if self.is_other:
            raise models.ProtectedError(
                f"“{OTHER_CATEGORY}” is the fallback category and can't be deleted.",
                {self},
            )
        return super().delete(*args, **kwargs)


def default_recipe_category():
    return RecipeCategory.other().pk


def default_ingredient_category():
    return IngredientCategory.other().pk


class RecipeCategory(Category):
    class Meta(Category.Meta):
        verbose_name_plural = "recipe categories"


class Recipe(models.Model):
    name = models.CharField(max_length=200)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    category = models.ForeignKey(
        RecipeCategory,
        on_delete=models.SET(default_recipe_category),
        default=default_recipe_category,
    )
    description = models.TextField()
    servings = models.PositiveIntegerField()
    image = models.ImageField(
        upload_to="recipes/", blank=True, validators=[validate_image_size]
    )

    # Longest side of stored photos. Phone photos are resized on upload so
    # the list stays light on mobile data.
    IMAGE_MAX_SIZE = 1200

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        previous = None
        if self.pk:
            previous = (
                Recipe.objects.filter(pk=self.pk)
                .values_list("image", flat=True)
                .first()
            )
        if self.image and not self.image._committed:
            self._shrink_image()
        super().save(*args, **kwargs)
        # Replaced or cleared: delete the old file so media/ doesn't fill up.
        if previous and previous != self.image.name:
            self.image.storage.delete(previous)

    def delete(self, *args, **kwargs):
        image_name = self.image.name
        result = super().delete(*args, **kwargs)
        if image_name:
            self.image.storage.delete(image_name)
        return result

    def _shrink_image(self):
        """Fix phone rotation, cap the size and store as JPEG."""
        from PIL import Image, ImageOps

        with Image.open(self.image) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((self.IMAGE_MAX_SIZE, self.IMAGE_MAX_SIZE))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85, optimize=True)
        name = os.path.splitext(os.path.basename(self.image.name))[0] + ".jpg"
        self.image = ContentFile(buffer.getvalue(), name=name)

    def get_absolute_url(self):
        return reverse("recipe_detail", kwargs={"pk": self.pk})


class IngredientCategory(Category):
    class Meta(Category.Meta):
        verbose_name_plural = "ingredient categories"


class Ingredient(models.Model):
    name = models.CharField(max_length=100)
    category = models.ForeignKey(
        IngredientCategory,
        on_delete=models.SET(default_ingredient_category),
        default=default_ingredient_category,
    )

    class Meta:
        constraints = [
            # Case-insensitive uniqueness: blocks "Tomato" vs "tomato" duplicates.
            models.UniqueConstraint(Lower("name"), name="unique_ingredient_name_ci")
        ]

    def save(self, *args, **kwargs):
        # Store ingredient names normalized (stripped + lowercased) so they're
        # consistent regardless of how they were created (form, admin, shell).
        self.name = self.name.strip().lower()
        super().save(*args, **kwargs)

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
        decimal_places=2,
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
        return f"{self.quantity or ''} {self.unit or ''} {self.ingredient}".strip()
