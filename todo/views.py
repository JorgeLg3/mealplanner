from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .forms import SubtaskForm, TodoForm
from .models import Subtask, Todo


def _open_todos():
    # Subtasks are prefetched so the nested render stays one query per relation.
    return Todo.objects.filter(is_done=False).prefetch_related("subtasks")


def todo_list(request):
    """Only open todos are listed; done ones drop off on the next page load."""
    return render(request, "todo/todo_list.html", {"todos": _open_todos()})


def _render_todo(request, todo, open=False, oob=False):
    """Re-render just this todo (with its subtasks) in place, so a todo marked
    done stays visible, greyed out, until the page is reloaded. ``open`` keeps
    the <details> expanded after actions taken inside it; ``oob`` marks it for
    an out-of-band swap from the dialog."""
    context = {"todo": todo, "open": open, "oob": oob}
    return render(request, "todo/_todo.html", context)


@login_required
@require_http_methods(["GET"])
def todo_row(request, pk):
    """Return the todo expanded. Used by the subtask edit form's Cancel."""
    return _render_todo(request, get_object_or_404(Todo, pk=pk), open=True)


def _render_dialog(request, form, todo=None):
    return render(request, "todo/_todo_dialog.html", {"form": form, "todo": todo})


@login_required
@require_http_methods(["GET", "POST"])
def todo_create(request):
    """GET opens the dialog; POST creates the todo, closes the dialog and
    re-renders the list out-of-band so the new todo lands in sort order."""
    form = TodoForm(request.POST or None)
    if request.method == "GET" or not form.is_valid():
        return _render_dialog(request, form)
    form.save()
    return render(
        request, "todo/_todo_list.html", {"todos": _open_todos(), "oob": True}
    )


@login_required
@require_http_methods(["GET", "POST"])
def todo_edit(request, pk):
    """GET opens the dialog pre-filled; POST saves, closes the dialog and
    swaps the updated todo in place out-of-band."""
    todo = get_object_or_404(Todo, pk=pk)
    form = TodoForm(request.POST or None, instance=todo)
    if request.method == "GET" or not form.is_valid():
        return _render_dialog(request, form, todo)
    form.save()
    return _render_todo(request, todo, open=True, oob=True)


@login_required
@require_http_methods(["POST"])
def todo_delete(request, pk):
    """Delete the todo and its subtasks; the empty response removes the row."""
    get_object_or_404(Todo, pk=pk).delete()
    return HttpResponse("")


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
def subtask_create(request, pk):
    """Add a subtask from the inline form; re-render the todo expanded."""
    todo = get_object_or_404(Todo, pk=pk)
    form = SubtaskForm(request.POST)
    if form.is_valid():
        form.instance.todo = todo
        form.save()
    return _render_todo(request, todo, open=True)


@login_required
@require_http_methods(["GET", "POST"])
def subtask_edit(request, pk):
    """GET swaps the subtask line for a pre-filled inline form; POST saves
    and re-renders the parent todo expanded."""
    subtask = get_object_or_404(Subtask.objects.select_related("todo"), pk=pk)
    form = SubtaskForm(request.POST or None, instance=subtask)
    if request.method == "POST" and form.is_valid():
        form.save()
        return _render_todo(request, subtask.todo, open=True)
    response = render(
        request, "todo/_subtask_form.html", {"subtask": subtask, "form": form}
    )
    # The form posts to the whole todo; send validation errors back to the
    # subtask line instead so the rest of the todo isn't replaced.
    response["HX-Retarget"] = f"#subtask-{subtask.pk}"
    return response


@login_required
@require_http_methods(["POST"])
def subtask_delete(request, pk):
    subtask = get_object_or_404(Subtask.objects.select_related("todo"), pk=pk)
    subtask.delete()
    return _render_todo(request, subtask.todo, open=True)


@login_required
@require_http_methods(["POST"])
def subtask_toggle(request, pk):
    """Flip the subtask's is_done and re-render its parent todo expanded."""
    subtask = get_object_or_404(Subtask.objects.select_related("todo"), pk=pk)
    subtask.is_done = not subtask.is_done
    subtask.save(update_fields=["is_done"])
    return _render_todo(request, subtask.todo, open=True)
