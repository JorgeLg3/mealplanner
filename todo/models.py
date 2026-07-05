from django.db import models


class Todo(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Open items first, then by soonest due date, then newest.
        ordering = ["is_done", "due_date", "-created_at"]

    def __str__(self):
        return self.name


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
