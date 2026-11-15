import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import RecurringTodo, Subtask, Todo
from .views import DONE_PAGE_SIZE


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

        names = [t.name for g in response.context["groups"] for t in g["todos"]]
        self.assertEqual(names, ["Groceries"])
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
        self.assertContains(response, 'id="todo-list" hx-swap-oob="true"')
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


class GroupingTests(TestCase):
    def _groups(self):
        response = self.client.get(reverse("todo_list"))
        return {
            g["key"]: [t.name for t in g["todos"]] for g in response.context["groups"]
        }

    def test_open_todos_grouped_by_due_date(self):
        today = datetime.date.today()
        sunday = today + datetime.timedelta(days=6 - today.weekday())
        Todo.objects.create(name="Late", due_date=today - datetime.timedelta(days=1))
        Todo.objects.create(name="Today", due_date=today)
        Todo.objects.create(name="Sunday", due_date=sunday)
        Todo.objects.create(name="Next week", due_date=sunday + datetime.timedelta(1))
        Todo.objects.create(name="Someday")

        groups = self._groups()
        # On a Sunday "Today" and "Sunday" share a due date, so their order
        # within the group isn't fixed; compare that group as a set.
        self.assertCountEqual(groups.pop("week"), ["Today", "Sunday"])
        self.assertEqual(
            groups,
            {"overdue": ["Late"], "later": ["Next week"], "none": ["Someday"]},
        )

    def test_empty_groups_hidden_and_later_collapsed(self):
        Todo.objects.create(
            name="Far", due_date=datetime.date.today() + datetime.timedelta(days=30)
        )
        response = self.client.get(reverse("todo_list"))
        self.assertEqual([g["key"] for g in response.context["groups"]], ["later"])
        self.assertContains(response, '<details class="todo-group todo-group--later">')

    def test_done_todos_not_grouped(self):
        Todo.objects.create(name="Finished", is_done=True)
        self.assertEqual(self._groups(), {})

    def test_list_links_to_done_page(self):
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, f'href="{reverse("todo_done")}"')


class DonePageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)

    def test_toggle_sets_and_clears_completed_at(self):
        todo = Todo.objects.create(name="Bins")
        url = reverse("todo_toggle", args=[todo.pk])

        self.client.post(url)
        todo.refresh_from_db()
        self.assertIsNotNone(todo.completed_at)

        self.client.post(url)
        todo.refresh_from_db()
        self.assertIsNone(todo.completed_at)

    def test_done_page_lists_most_recently_completed_first(self):
        now = timezone.now()
        Todo.objects.create(name="Open")
        Todo.objects.create(
            name="Old", is_done=True, completed_at=now - datetime.timedelta(days=2)
        )
        Todo.objects.create(name="Recent", is_done=True, completed_at=now)
        Todo.objects.create(name="Legacy", is_done=True)  # done before the field

        response = self.client.get(reverse("todo_done"))

        self.assertEqual(
            [t.name for t in response.context["page"]], ["Recent", "Old", "Legacy"]
        )

    def test_done_page_is_paginated(self):
        Todo.objects.bulk_create(
            [Todo(name=f"T{i}", is_done=True) for i in range(DONE_PAGE_SIZE + 1)]
        )
        first = self.client.get(reverse("todo_done"))
        second = self.client.get(reverse("todo_done"), {"page": 2})
        self.assertEqual(len(first.context["page"]), DONE_PAGE_SIZE)
        self.assertEqual(len(second.context["page"]), 1)
        self.assertContains(first, "?page=2")


class EditRegroupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        self.todo = Todo.objects.create(name="Bins")

    def test_changing_due_date_reloads_page(self):
        response = self.client.post(
            reverse("todo_edit", args=[self.todo.pk]),
            {"name": "Bins", "description": "", "due_date": "2030-01-01"},
        )
        self.assertEqual(response["HX-Refresh"], "true")

    def test_other_edits_swap_row_in_place(self):
        response = self.client.post(
            reverse("todo_edit", args=[self.todo.pk]),
            {"name": "Recycling", "description": "", "due_date": ""},
        )
        self.assertNotIn("HX-Refresh", response)
        self.assertContains(response, f'id="todo-{self.todo.pk}"')


class RecurrenceScheduleTests(TestCase):
    """Pure date math; no requests."""

    def _rec(self, start, every=1, unit=RecurringTodo.Unit.WEEK, **kwargs):
        return RecurringTodo(
            name="R", start_date=start, every=every, unit=unit, **kwargs
        )

    def test_monthly_on_31st_clamps_without_drifting(self):
        rec = self._rec(datetime.date(2027, 1, 31), unit=RecurringTodo.Unit.MONTH)
        self.assertEqual(
            [rec.occurrence(n) for n in range(4)],
            [
                datetime.date(2027, 1, 31),
                datetime.date(2027, 2, 28),
                datetime.date(2027, 3, 31),
                datetime.date(2027, 4, 30),
            ],
        )

    def test_yearly_leap_day(self):
        rec = self._rec(datetime.date(2028, 2, 29), unit=RecurringTodo.Unit.YEAR)
        self.assertEqual(rec.occurrence(1), datetime.date(2029, 2, 28))
        self.assertEqual(rec.occurrence(4), datetime.date(2032, 2, 29))

    def test_first_occurrence_on_or_after(self):
        monday = datetime.date(2026, 11, 2)
        weekly = self._rec(monday)
        self.assertEqual(
            weekly.first_occurrence_on_or_after(datetime.date(2026, 11, 2)), monday
        )
        self.assertEqual(
            weekly.first_occurrence_on_or_after(datetime.date(2026, 11, 26)),
            datetime.date(2026, 11, 30),
        )
        fortnightly = self._rec(monday, every=2)
        self.assertEqual(
            fortnightly.first_occurrence_on_or_after(datetime.date(2026, 11, 10)),
            datetime.date(2026, 11, 16),
        )
        quarterly = self._rec(
            datetime.date(2026, 1, 15), every=3, unit=RecurringTodo.Unit.MONTH
        )
        self.assertEqual(
            quarterly.first_occurrence_on_or_after(datetime.date(2026, 5, 1)),
            datetime.date(2026, 7, 15),
        )
        daily = self._rec(monday, every=3, unit=RecurringTodo.Unit.DAY)
        self.assertEqual(
            daily.first_occurrence_on_or_after(datetime.date(2026, 11, 6)),
            datetime.date(2026, 11, 8),
        )

    def test_future_start_is_first_due(self):
        start = datetime.date.today() + datetime.timedelta(days=10)
        self.assertEqual(self._rec(start).next_due(), start)

    def test_schedule_label(self):
        self.assertEqual(self._rec(datetime.date.today()).schedule_label, "Every week")
        self.assertEqual(
            self._rec(
                datetime.date.today(), every=3, unit=RecurringTodo.Unit.MONTH
            ).schedule_label,
            "Every 3 months",
        )


class RecurringFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        self.today = datetime.date.today()
        # A weekly task anchored on this week's Monday.
        self.monday = self.today - datetime.timedelta(days=self.today.weekday())

    def _weekly(self, start=None, **kwargs):
        rec = RecurringTodo.objects.create(
            name="Bins", start_date=start or self.monday, **kwargs
        )
        rec.ensure_open_todo()
        return rec

    def _open(self, rec):
        return rec.todos.get(is_done=False)

    def test_creating_recurrence_creates_first_open_todo(self):
        self.client.post(
            reverse("recurring_create"),
            {
                "name": "Water plants",
                "description": "",
                "every": 3,
                "unit": "day",
                "start_date": self.today.isoformat(),
            },
        )
        rec = RecurringTodo.objects.get()
        todo = self._open(rec)
        self.assertEqual(todo.name, "Water plants")
        self.assertEqual(todo.due_date, self.today)

    def test_past_start_gets_first_occurrence_from_today(self):
        rec = self._weekly(start=self.monday - datetime.timedelta(weeks=5))
        due = self._open(rec).due_date
        self.assertGreaterEqual(due, self.today)
        self.assertEqual(due.weekday(), 0)

    def test_ticking_creates_next_occurrence_one_interval_later(self):
        rec = self._weekly(start=self.today)
        todo = self._open(rec)

        response = self.client.post(reverse("todo_toggle", args=[todo.pk]))

        nxt = self._open(rec)
        self.assertEqual(nxt.due_date, self.today + datetime.timedelta(weeks=1))
        self.assertContains(response, "Next:")
        self.assertEqual(rec.todos.count(), 2)

    def test_ticking_overdue_skips_missed_and_keeps_weekday(self):
        rec = self._weekly(start=self.monday - datetime.timedelta(weeks=3))
        todo = self._open(rec)
        # Simulate it having been left open for three weeks.
        todo.due_date = self.monday - datetime.timedelta(weeks=3)
        todo.save()
        rec.last_due = todo.due_date
        rec.save()

        self.client.post(reverse("todo_toggle", args=[todo.pk]))

        nxt = self._open(rec)
        self.assertGreaterEqual(nxt.due_date, self.today)
        self.assertLess(nxt.due_date, self.today + datetime.timedelta(weeks=1))
        self.assertEqual(nxt.due_date.weekday(), 0)

    def test_unticking_undoes_next_occurrence(self):
        rec = self._weekly(start=self.today)
        todo = self._open(rec)
        url = reverse("todo_toggle", args=[todo.pk])

        self.client.post(url)
        self.client.post(url)

        self.assertEqual(list(rec.todos.filter(is_done=False)), [todo])
        rec.refresh_from_db()
        self.assertEqual(rec.last_due, todo.due_date)

    def test_deleting_open_todo_skips_to_next_on_page_load(self):
        rec = self._weekly(start=self.today)
        todo = self._open(rec)
        self.client.post(reverse("todo_delete", args=[todo.pk]))

        self.client.get(reverse("todo_list"))

        self.assertEqual(
            self._open(rec).due_date, self.today + datetime.timedelta(weeks=1)
        )

    def test_page_load_does_not_duplicate_open_todo(self):
        rec = self._weekly()
        self.client.get(reverse("todo_list"))
        self.client.get(reverse("todo_list"))
        self.assertEqual(rec.todos.filter(is_done=False).count(), 1)

    def test_edit_updates_open_todo_and_keeps_done_history(self):
        rec = self._weekly(start=self.today)
        done = self._open(rec)
        self.client.post(reverse("todo_toggle", args=[done.pk]))
        open_todo = self._open(rec)

        self.client.post(
            reverse("recurring_update", args=[rec.pk]),
            {
                "name": "Recycling",
                "description": "Blue bin",
                "every": 1,
                "unit": "week",
                "start_date": self.today.isoformat(),
            },
        )

        open_todo.refresh_from_db()
        done.refresh_from_db()
        self.assertEqual(open_todo.name, "Recycling")
        self.assertEqual(open_todo.description, "Blue bin")
        self.assertEqual(open_todo.due_date, self.today + datetime.timedelta(weeks=1))
        self.assertEqual(done.name, "Bins")

    def test_edit_schedule_moves_open_todo_due_date(self):
        rec = self._weekly(start=self.today + datetime.timedelta(days=3))
        new_start = self.today + datetime.timedelta(days=1)

        self.client.post(
            reverse("recurring_update", args=[rec.pk]),
            {
                "name": "Bins",
                "description": "",
                "every": 2,
                "unit": "week",
                "start_date": new_start.isoformat(),
            },
        )

        self.assertEqual(self._open(rec).due_date, new_start)
        self.assertEqual(rec.todos.filter(is_done=False).count(), 1)

    def test_delete_removes_open_todo_keeps_done_ones(self):
        rec = self._weekly(start=self.today)
        done = self._open(rec)
        self.client.post(reverse("todo_toggle", args=[done.pk]))

        self.client.post(reverse("recurring_delete", args=[rec.pk]))

        self.assertFalse(RecurringTodo.objects.exists())
        self.assertEqual(list(Todo.objects.all()), [done])
        done.refresh_from_db()
        self.assertIsNone(done.recurring)

    def test_list_shows_next_and_last_done(self):
        rec = self._weekly(start=self.today)
        self.client.post(reverse("todo_toggle", args=[self._open(rec).pk]))

        response = self.client.get(reverse("recurring_list"))

        row = response.context["recurringtodo_list"][0]
        self.assertEqual(row.next_due, self.today + datetime.timedelta(weeks=1))
        self.assertIsNotNone(row.last_done)
        self.assertContains(response, "Every week")

    def test_todo_row_shows_recurring_badge(self):
        self._weekly()
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, "Every week")
        self.assertContains(response, 'class="todo__recurring"')

    def test_rejects_every_zero(self):
        response = self.client.post(
            reverse("recurring_create"),
            {"name": "X", "every": 0, "unit": "day", "start_date": "2030-01-01"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RecurringTodo.objects.exists())

    def test_write_pages_require_login(self):
        rec = self._weekly()
        self.client.logout()
        for url in [
            reverse("recurring_create"),
            reverse("recurring_update", args=[rec.pk]),
            reverse("recurring_delete", args=[rec.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 302)


class TodoLayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)

    def test_tabs_mark_the_current_view(self):
        for name, label in [
            ("todo_list", "All"),
            ("todo_done", "Show done"),
            ("recurring_list", "Recurring"),
        ]:
            with self.subTest(view=name):
                response = self.client.get(reverse(name))
                self.assertContains(
                    response,
                    f'<a class="tabs__tab is-active" href="{reverse(name)}" aria-current="page">{label}</a>',
                    html=True,
                )

    def test_primary_action_per_view(self):
        self.assertContains(self.client.get(reverse("todo_list")), "New todo")
        self.assertContains(
            self.client.get(reverse("recurring_list")), "New recurring todo"
        )

    def test_empty_states(self):
        self.assertContains(self.client.get(reverse("todo_list")), "Nothing to do")
        self.assertContains(self.client.get(reverse("todo_done")), "Nothing done yet")
        self.assertContains(
            self.client.get(reverse("recurring_list")), "No recurring todos yet"
        )

    def test_overdue_date_has_text_not_only_colour(self):
        Todo.objects.create(
            name="Late", due_date=datetime.date.today() - datetime.timedelta(days=2)
        )
        response = self.client.get(reverse("todo_list"))
        self.assertContains(response, '<span class="visually-hidden">Overdue: </span>')
        self.assertContains(response, "todo-group--overdue")


class SubtaskOrderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="x"
        )
        self.client.force_login(self.user)
        self.todo = Todo.objects.create(name="Groceries")

    def _names(self):
        return list(self.todo.subtasks.values_list("name", flat=True))

    def test_new_subtasks_are_appended(self):
        for name in ["Milk", "Eggs", "Bread"]:
            self.client.post(
                reverse("subtask_create", args=[self.todo.pk]), {"name": name}
            )
        self.assertEqual(self._names(), ["Milk", "Eggs", "Bread"])

    def test_done_subtasks_sink_but_keep_their_order(self):
        for name in ["Milk", "Eggs", "Bread"]:
            Subtask.objects.create(todo=self.todo, name=name)
        milk = Subtask.objects.get(name="Milk")
        self.client.post(reverse("subtask_toggle", args=[milk.pk]))
        self.assertEqual(self._names(), ["Eggs", "Bread", "Milk"])

    def test_positions_are_per_todo(self):
        other = Todo.objects.create(name="Other")
        Subtask.objects.create(todo=other, name="X")
        first = Subtask.objects.create(todo=self.todo, name="A")
        self.assertEqual(first.position, 1)
