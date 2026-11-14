from django.contrib import admin

from .models import RecurringTodo, Subtask, Todo


class SubtaskInline(admin.TabularInline):
    model = Subtask
    extra = 1


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ("name", "due_date", "is_done", "created_at")
    list_filter = ("is_done",)
    search_fields = ("name",)
    inlines = [SubtaskInline]


@admin.register(RecurringTodo)
class RecurringTodoAdmin(admin.ModelAdmin):
    list_display = ("name", "every", "unit", "start_date", "last_due")
