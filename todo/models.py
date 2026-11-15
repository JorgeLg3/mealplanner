import calendar
import datetime
from typing import TYPE_CHECKING

from django.core.validators import MinValueValidator
from django.db import models, transaction

if TYPE_CHECKING:
    # Attributes Django adds at runtime (for type checkers; no runtime effect).
    from django.db.models.fields.related_descriptors import RelatedManager


def add_months(date, months):
    """Shift by whole months, clamping to the month's last day (Jan 31 + 1
    month -> Feb 28/29)."""
    year, month0 = divmod(date.month - 1 + months, 12)
    year += date.year
    day = min(date.day, calendar.monthrange(year, month0 + 1)[1])
    return date.replace(year=year, month=month0 + 1, day=day)


class RecurringTodo(models.Model):
    """A task that repeats every N days/weeks/months/years. It keeps at most
    one open Todo at a time; the next one is created when that one is done
    (or deleted). Due dates always sit on the schedule anchored at
    start_date, so missed occurrences are skipped, never piled up."""

    class Unit(models.TextChoices):
        DAY = "day", "Days"
        WEEK = "week", "Weeks"
        MONTH = "month", "Months"
        YEAR = "year", "Years"

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    every = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.WEEK)
    start_date = models.DateField(help_text="Due date of the first occurrence.")
    # Due date of the most recently generated todo; the next one comes after it.
    last_due = models.DateField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    if TYPE_CHECKING:
        todos: "RelatedManager[Todo]"

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        # The open todo goes with the recurrence; done ones stay as history
        # (their FK is cleared by SET_NULL).
        with transaction.atomic():
            self.todos.filter(is_done=False).delete()
            return super().delete(*args, **kwargs)

    @property
    def schedule_label(self):
        """'Every week', 'Every 3 months'."""
        unit = self.Unit(self.unit).label.lower()
        if self.every == 1:
            return f"Every {unit[:-1]}"
        return f"Every {self.every} {unit}"

    def occurrence(self, n):
        """Due date of the n-th occurrence (0 = start_date). Months/years are
        computed from start_date, not chained, so a 31st doesn't drift."""
        step = self.every * n
        if self.unit == self.Unit.DAY:
            return self.start_date + datetime.timedelta(days=step)
        if self.unit == self.Unit.WEEK:
            return self.start_date + datetime.timedelta(weeks=step)
        if self.unit == self.Unit.MONTH:
            return add_months(self.start_date, step)
        return add_months(self.start_date, 12 * step)

    def first_occurrence_on_or_after(self, date):
        if date <= self.start_date:
            return self.start_date
        if self.unit in (self.Unit.DAY, self.Unit.WEEK):
            step_days = self.every * (7 if self.unit == self.Unit.WEEK else 1)
            n = -(-(date - self.start_date).days // step_days)  # ceil division
            return self.occurrence(n)
        months_per_step = self.every * (12 if self.unit == self.Unit.YEAR else 1)
        months = (date.year - self.start_date.year) * 12 + (
            date.month - self.start_date.month
        )
        n = max(0, months // months_per_step - 1)
        while self.occurrence(n) < date:
            n += 1
        return self.occurrence(n)

    def next_due(self):
        """Next due date: after the last generated one, and not in the past."""
        bound = datetime.date.today()
        if self.last_due is not None:
            bound = max(bound, self.last_due + datetime.timedelta(days=1))
        return self.first_occurrence_on_or_after(bound)

    @transaction.atomic
    def ensure_open_todo(self):
        """Create the next todo if none is open. Returns it (or None)."""
        if self.todos.filter(is_done=False).exists():
            return None
        due = self.next_due()
        todo = Todo.objects.create(
            name=self.name, description=self.description, due_date=due, recurring=self
        )
        self.last_due = due
        self.save(update_fields=["last_due"])
        return todo

    @transaction.atomic
    def apply_edit(self, schedule_changed):
        """After the recurrence is edited, carry the change to its open todo:
        name/description always; the due date only if the schedule changed,
        moving it to the first occurrence from today."""
        open_todos = self.todos.filter(is_done=False)
        fields = {"name": self.name, "description": self.description}
        if schedule_changed:
            due = self.first_occurrence_on_or_after(datetime.date.today())
            fields["due_date"] = due
            self.last_due = due
            self.save(update_fields=["last_due"])
        open_todos.update(**fields)
        self.ensure_open_todo()

    @classmethod
    def ensure_all(cls):
        """Give every recurrence without an open todo its next one."""
        for recurring in cls.objects.exclude(todos__is_done=False):
            recurring.ensure_open_todo()


class Todo(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    # Set when ticked, cleared when reopened; orders the "done" page.
    completed_at = models.DateTimeField(null=True, blank=True)
    # The recurrence that generated this todo. Kept as history when done;
    # cleared if the recurrence is deleted.
    recurring = models.ForeignKey(
        RecurringTodo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="todos",
    )

    if TYPE_CHECKING:
        subtasks: "RelatedManager[Subtask]"
        recurring_id: int | None
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
    # Order within the todo: new subtasks go last; exported shopping lists
    # keep the preview's category order.
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    if TYPE_CHECKING:
        todo_id: int

    class Meta:
        # Open before done, then in list order.
        ordering = ["is_done", "position", "pk"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Append to the end of the list unless a position was given
        # (bulk_create callers such as the shopping export set it themselves).
        if self._state.adding and not self.position:
            last = Subtask.objects.filter(todo_id=self.todo_id).aggregate(
                models.Max("position")
            )["position__max"]
            self.position = (last or 0) + 1
        super().save(*args, **kwargs)
