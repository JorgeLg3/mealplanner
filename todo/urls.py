from django.urls import path

from .views import (
    subtask_create,
    subtask_delete,
    subtask_edit,
    subtask_toggle,
    todo_create,
    todo_delete,
    todo_done,
    todo_edit,
    todo_list,
    todo_row,
    todo_toggle,
)

urlpatterns = [
    path("", todo_list, name="todo_list"),
    path("done/", todo_done, name="todo_done"),
    path("create/", todo_create, name="todo_create"),
    path("<int:pk>/", todo_row, name="todo_row"),
    path("<int:pk>/edit/", todo_edit, name="todo_edit"),
    path("<int:pk>/delete/", todo_delete, name="todo_delete"),
    path("<int:pk>/toggle/", todo_toggle, name="todo_toggle"),
    path("<int:pk>/subtasks/", subtask_create, name="subtask_create"),
    path("subtasks/<int:pk>/edit/", subtask_edit, name="subtask_edit"),
    path("subtasks/<int:pk>/delete/", subtask_delete, name="subtask_delete"),
    path("subtasks/<int:pk>/toggle/", subtask_toggle, name="subtask_toggle"),
]
