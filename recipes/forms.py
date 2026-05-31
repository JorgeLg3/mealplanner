from django import forms
from django.forms import inlineformset_factory

from .models import Recipe, RecipeIngredient, Ingredient


class RecipeIngredientForm(forms.ModelForm):
    # Free-text ingredient: lets a user reference an ingredient that may not
    # exist yet. Existing names are offered via the <datalist> in the template
    # (see the `list` attr below), but anything typed is accepted and created
    # on save if it's new.
    ingredient_name = forms.CharField(
        max_length=100,
        label="Ingredient",
        widget=forms.TextInput(attrs={"list": "ingredient-options"}),
    )

    class Meta:
        model = RecipeIngredient
        # The `ingredient` FK is intentionally omitted; we set it in save()
        # from ingredient_name instead.
        fields = ["quantity", "unit", "prep_note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill the text field when editing an existing row.
        if self.instance.pk and self.instance.ingredient_id:
            self.fields["ingredient_name"].initial = self.instance.ingredient.name

    def save(self, commit=True):
        name = self.cleaned_data["ingredient_name"].strip()
        # Reuse a matching ingredient (case-insensitive) or create a new one.
        ingredient = Ingredient.objects.filter(name__iexact=name).first()
        if ingredient is None:
            ingredient = Ingredient.objects.create(name=name)
        self.instance.ingredient = ingredient
        return super().save(commit=commit)


# A formset of RecipeIngredient rows bound to a single Recipe (parent) via the
# RecipeIngredient.recipe ForeignKey, using the custom form above.
RecipeIngredientFormSet = inlineformset_factory(
    Recipe,
    RecipeIngredient,
    form=RecipeIngredientForm,
    extra=1,
    can_delete=True,
)
