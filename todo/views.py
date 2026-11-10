from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .models import Subtask, Todo


def todo_list(request):
    """Only open todos are listed; done ones drop off on the next page load.
    Subtasks are prefetched so the nested render stays one query per relation."""
    todos = Todo.objects.filter(is_done=False).prefetch_related("subtasks")
    return render(request, "todo/todo_list.html", {"todos": todos})


def _render_todo(request, todo):
    """Re-render just this todo (with its subtasks) in place, so a todo marked
    done stays visible, greyed out, until the page is reloaded."""
    return render(request, "todo/_todo.html", {"todo": todo})


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
    return _render_todo(request, todo)


@login_required
@require_http_methods(["POST"])
def subtask_toggle(request, pk):
    """Flip the subtask's is_done and re-render its parent todo."""
    subtask = get_object_or_404(Subtask.objects.select_related("todo"), pk=pk)
    subtask.is_done = not subtask.is_done
    subtask.save(update_fields=["is_done"])
    return _render_todo(request, subtask.todo)
