from django import forms

from .models import Subtask, Todo


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
