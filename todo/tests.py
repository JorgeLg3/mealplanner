import datetime

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


class TodoCrudTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        self.todo = Todo.objects.create(name="Groceries")

    def test_create_dialog_opens(self):
        response = self.client.get(reverse("todo_create"))
        self.assertContains(response, "<dialog")
        self.assertContains(response, 'name="due_date"')

    def test_create_adds_todo_and_rerenders_list_out_of_band(self):
        response = self.client.post(
            reverse("todo_create"),
            {"name": "Fix tap", "description": "Kitchen", "due_date": "2030-01-05"},
        )

        todo = Todo.objects.get(name="Fix tap")
        self.assertEqual(todo.due_date, datetime.date(2030, 1, 5))
        self.assertEqual(todo.description, "Kitchen")
        self.assertNotContains(response, "<dialog")
        self.assertContains(
            response, 'id="todo-list" class="todo-list" hx-swap-oob="true"'
        )
        self.assertContains(response, "Fix tap")

    def test_create_invalid_keeps_dialog_with_errors(self):
        response = self.client.post(reverse("todo_create"), {"name": ""})
        self.assertContains(response, "<dialog")
        self.assertContains(response, "This field is required.")
        self.assertEqual(Todo.objects.count(), 1)

    def test_edit_dialog_is_prefilled(self):
        self.todo.due_date = datetime.date(2030, 2, 1)
        self.todo.save()
        response = self.client.get(reverse("todo_edit", args=[self.todo.pk]))
        self.assertContains(response, 'value="Groceries"')
        self.assertContains(response, 'value="2030-02-01"')

    def test_edit_saves_and_swaps_row_out_of_band(self):
        response = self.client.post(
            reverse("todo_edit", args=[self.todo.pk]),
            {"name": "Big shop", "description": "", "due_date": ""},
        )
        self.todo.refresh_from_db()
        self.assertEqual(self.todo.name, "Big shop")
        self.assertContains(response, f'id="todo-{self.todo.pk}"')
        self.assertContains(response, 'hx-swap-oob="true"')

    def test_delete_removes_todo_and_subtasks(self):
        Subtask.objects.create(todo=self.todo, name="Milk")
        response = self.client.post(reverse("todo_delete", args=[self.todo.pk]))
        self.assertEqual(response.content, b"")
        self.assertFalse(Todo.objects.exists())
        self.assertFalse(Subtask.objects.exists())

    def test_summary_shows_due_date_overdue_and_progress(self):
        self.todo.due_date = datetime.date.today() - datetime.timedelta(days=1)
        self.todo.save()
        Subtask.objects.create(todo=self.todo, name="Milk", is_done=True)
        Subtask.objects.create(todo=self.todo, name="Eggs")

        response = self.client.get(reverse("todo_list"))

        self.assertContains(response, "todo__due--overdue")
        self.assertContains(response, '<span class="todo__progress">1/2</span>')

    def test_list_rows_start_collapsed(self):
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, '<details class="todo__details">')


class SubtaskCrudTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        self.todo = Todo.objects.create(name="Groceries")
        self.subtask = Subtask.objects.create(todo=self.todo, name="Milk")

    def test_create_adds_subtask_and_keeps_todo_open(self):
        response = self.client.post(
            reverse("subtask_create", args=[self.todo.pk]), {"name": "Eggs"}
        )
        self.assertTrue(self.todo.subtasks.filter(name="Eggs").exists())
        self.assertContains(response, '<details class="todo__details" open>')

    def test_create_ignores_blank_name(self):
        self.client.post(reverse("subtask_create", args=[self.todo.pk]), {"name": ""})
        self.assertEqual(self.todo.subtasks.count(), 1)

    def test_edit_form_is_prefilled(self):
        response = self.client.get(reverse("subtask_edit", args=[self.subtask.pk]))
        self.assertContains(response, 'value="Milk"')

    def test_edit_saves_and_rerenders_todo_open(self):
        response = self.client.post(
            reverse("subtask_edit", args=[self.subtask.pk]),
            {"name": "Oat milk", "due_date": "2030-03-01"},
        )
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.name, "Oat milk")
        self.assertEqual(self.subtask.due_date, datetime.date(2030, 3, 1))
        self.assertContains(response, f'id="todo-{self.todo.pk}"')
        self.assertContains(response, " open>")

    def test_edit_invalid_retargets_to_subtask_line(self):
        response = self.client.post(
            reverse("subtask_edit", args=[self.subtask.pk]), {"name": ""}
        )
        self.assertEqual(response["HX-Retarget"], f"#subtask-{self.subtask.pk}")
        self.subtask.refresh_from_db()
        self.assertEqual(self.subtask.name, "Milk")

    def test_delete_removes_subtask_and_keeps_todo_open(self):
        response = self.client.post(reverse("subtask_delete", args=[self.subtask.pk]))
        self.assertFalse(Subtask.objects.exists())
        self.assertContains(response, " open>")

    def test_todo_row_returns_todo_open(self):
        response = self.client.get(reverse("todo_row", args=[self.todo.pk]))
        self.assertContains(response, " open>")


class TodoPermissionTests(TestCase):
    def setUp(self):
        self.todo = Todo.objects.create(name="Groceries")
        self.subtask = Subtask.objects.create(todo=self.todo, name="Milk")

    def test_write_endpoints_require_login(self):
        urls = [
            ("get", reverse("todo_create")),
            ("post", reverse("todo_create")),
            ("get", reverse("todo_edit", args=[self.todo.pk])),
            ("post", reverse("todo_edit", args=[self.todo.pk])),
            ("post", reverse("todo_delete", args=[self.todo.pk])),
            ("post", reverse("subtask_create", args=[self.todo.pk])),
            ("get", reverse("subtask_edit", args=[self.subtask.pk])),
            ("post", reverse("subtask_edit", args=[self.subtask.pk])),
            ("post", reverse("subtask_delete", args=[self.subtask.pk])),
        ]
        for method, url in urls:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, {"name": "x"})
                self.assertEqual(response.status_code, 302)
        self.assertTrue(Todo.objects.filter(name="Groceries").exists())
        self.assertTrue(Subtask.objects.filter(name="Milk").exists())

    def test_anonymous_list_has_no_edit_controls(self):
        response = self.client.get(reverse("todo_list"))
        self.assertNotContains(response, reverse("todo_create"))
        self.assertNotContains(response, reverse("todo_edit", args=[self.todo.pk]))
        self.assertNotContains(response, "Add subtask")
