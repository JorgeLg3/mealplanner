from django.contrib import admin, messages

from .models import (
    IngredientCategory,
    Ingredient,
    RecipeCategory,
    Recipe,
    RecipeIngredient,
    Unit,
)


class CategoryAdmin(admin.ModelAdmin):
    """ "otros" is the fallback category: it can't be deleted, not even via
    the bulk delete action (which bypasses Category.delete)."""

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_other:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        kept = [c for c in queryset if c.is_other]
        if kept:
            messages.warning(request, "“otros” is the fallback category and was kept.")
        for category in queryset:
            if not category.is_other:
                category.delete()  # moves its items to "otros"


admin.site.register(RecipeCategory, CategoryAdmin)
admin.site.register(IngredientCategory, CategoryAdmin)
admin.site.register((Recipe, Ingredient, Unit, RecipeIngredient))
