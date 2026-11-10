from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .models import Subtask, Todo


def _todos():
    # Subtasks are prefetched so the nested render stays one query per relation.
    return Todo.objects.prefetch_related("subtasks")


def todo_list(request):
    return render(request, "todo/todo_list.html", {"todos": _todos()})


def _render_list(request):
    """Re-render the whole list, since the model ordering moves done items
    below open ones."""
    return render(request, "todo/_todo_list.html", {"todos": _todos()})


@login_required
@require_http_methods(["POST"])
def todo_toggle(request, pk):
    """Flip the todo's is_done. Marking it done also marks all its subtasks
    done; reopening it leaves the subtasks as they are."""
    todo = get_object_or_404(Todo, pk=pk)
    todo.is_done = not todo.is_done
    with transaction.atomic():
        todo.save(update_fields=["is_done"])
        if todo.is_done:
            todo.subtasks.update(is_done=True)
    return _render_list(request)


@login_required
@require_http_methods(["POST"])
def subtask_toggle(request, pk):
    subtask = get_object_or_404(Subtask, pk=pk)
    subtask.is_done = not subtask.is_done
    subtask.save(update_fields=["is_done"])
    return _render_list(request)
