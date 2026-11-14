from django import forms

from .models import RecurringTodo, Subtask, Todo


class TodoForm(forms.ModelForm):
    class Meta:
        model = Todo
        fields = ["name", "description", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class SubtaskForm(forms.ModelForm):
    class Meta:
        model = Subtask
        fields = ["name", "due_date"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


class RecurringTodoForm(forms.ModelForm):
    class Meta:
        model = RecurringTodo
        fields = ["name", "description", "every", "unit", "start_date"]
        labels = {"start_date": "First due date"}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "every": forms.NumberInput(attrs={"min": 1}),
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }
