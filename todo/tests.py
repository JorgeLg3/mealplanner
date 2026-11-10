from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Subtask, Todo


class ToggleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.todo = Todo.objects.create(name="Groceries")
        self.subtask = Subtask.objects.create(todo=self.todo, name="Milk")

    def test_toggle_todo_marks_done_then_open(self):
        self.client.force_login(self.user)
        url = reverse("todo_toggle", args=[self.todo.pk])

        response = self.client.post(url)
        self.todo.refresh_from_db()
        self.assertTrue(self.todo.is_done)
        self.assertContains(response, "todo todo--done")

        self.client.post(url)
        self.todo.refresh_from_db()
        self.assertFalse(self.todo.is_done)

    def test_marking_todo_done_marks_all_subtasks_done(self):
        self.client.force_login(self.user)
        other = Subtask.objects.create(todo=self.todo, name="Eggs", is_done=True)
        unrelated = Subtask.objects.create(
            todo=Todo.objects.create(name="Laundry"), name="Socks"
        )

        self.client.post(reverse("todo_toggle", args=[self.todo.pk]))

        self.assertEqual(
            set(self.todo.subtasks.values_list("is_done", flat=True)), {True}
        )
        other.refresh_from_db()
        self.assertTrue(other.is_done)
        unrelated.refresh_from_db()
        self.assertFalse(unrelated.is_done)

    def test_reopening_todo_leaves_subtasks_done(self):
        self.client.force_login(self.user)
        url = reverse("todo_toggle", args=[self.todo.pk])

        self.client.post(url)  # done -> subtasks done
        self.client.post(url)  # reopen

        self.todo.refresh_from_db()
        self.subtask.refresh_from_db()
        self.assertFalse(self.todo.is_done)
        self.assertTrue(self.subtask.is_done)

    def test_toggle_subtask_leaves_parent_alone(self):
        self.client.force_login(self.user)

        self.client.post(reverse("subtask_toggle", args=[self.subtask.pk]))

        self.subtask.refresh_from_db()
        self.todo.refresh_from_db()
        self.assertTrue(self.subtask.is_done)
        self.assertFalse(self.todo.is_done)

    def test_toggle_returns_only_that_todo_greyed_out(self):
        self.client.force_login(self.user)
        Todo.objects.create(name="Laundry")

        response = self.client.post(reverse("todo_toggle", args=[self.todo.pk]))

        self.assertContains(response, f'id="todo-{self.todo.pk}"')
        self.assertContains(response, "todo todo--done")
        self.assertNotContains(response, "Laundry")

    def test_subtask_toggle_rerenders_parent_todo(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("subtask_toggle", args=[self.subtask.pk]))

        self.assertContains(response, f'id="todo-{self.todo.pk}"')
        self.assertContains(response, "Milk")

    def test_list_hides_done_todos(self):
        Todo.objects.create(name="Laundry", is_done=True)

        response = self.client.get(reverse("todo_list"))

        self.assertEqual([t.name for t in response.context["todos"]], ["Groceries"])
        self.assertNotContains(response, "Laundry")

    def test_toggle_requires_login(self):
        response = self.client.post(reverse("todo_toggle", args=[self.todo.pk]))
        self.assertEqual(response.status_code, 302)
        self.todo.refresh_from_db()
        self.assertFalse(self.todo.is_done)

    def test_toggle_rejects_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("todo_toggle", args=[self.todo.pk]))
        self.assertEqual(response.status_code, 405)

    def test_anonymous_list_shows_disabled_checkboxes(self):
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, "disabled")
        self.assertNotContains(response, reverse("todo_toggle", args=[self.todo.pk]))
