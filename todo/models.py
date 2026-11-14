import datetime

from django.db import models


class Todo(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    # Set when ticked, cleared when reopened; orders the "done" page.
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Open items first, then by soonest due date, then newest.
        ordering = ["is_done", "due_date", "-created_at"]

    def __str__(self):
        return self.name

    @property
    def is_overdue(self):
        return (
            not self.is_done
            and self.due_date is not None
            and self.due_date < datetime.date.today()
        )

    @property
    def subtask_progress(self):
        """ "done/total" for the summary line, or "" without subtasks. Uses
        subtasks.all() so a prefetch avoids extra queries."""
        subtasks = self.subtasks.all()
        if not subtasks:
            return ""
        return f"{sum(s.is_done for s in subtasks)}/{len(subtasks)}"


class Subtask(models.Model):
    todo = models.ForeignKey(Todo, on_delete=models.CASCADE, related_name="subtasks")
    name = models.CharField(max_length=200)
    due_date = models.DateField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["is_done", "due_date", "-created_at"]

    def __str__(self):
        return self.name
