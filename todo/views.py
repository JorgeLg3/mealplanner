from django.shortcuts import render

from .models import Todo


def todo_list(request):
    # Subtasks are prefetched so the nested render stays one query per relation.
    todos = Todo.objects.prefetch_related("subtasks")
    return render(request, "todo/todo_list.html", {"todos": todos})
