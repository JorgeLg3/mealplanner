from django.urls import path

from .views import subtask_toggle, todo_list, todo_toggle

urlpatterns = [
    path("", todo_list, name="todo_list"),
    path("<int:pk>/toggle/", todo_toggle, name="todo_toggle"),
    path("subtasks/<int:pk>/toggle/", subtask_toggle, name="subtask_toggle"),
]
