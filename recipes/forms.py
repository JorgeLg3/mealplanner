from django.forms import inlineformset_factory

from .models import Recipe, RecipeIngredient

# A formset of RecipeIngredient rows bound to a single Recipe (parent) via the
# RecipeIngredient.recipe ForeignKey.
RecipeIngredientFormSet = inlineformset_factory(
    Recipe,
    RecipeIngredient,
    fields=["ingredient", "quantity", "unit", "prep_note"],
    extra=1,
    can_delete=True,
)
