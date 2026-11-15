import datetime
import re

from accounts.models import User
from django.test import SimpleTestCase, TestCase

from django_project.test_utils import LoggedInTestCase


class ViewTests(SimpleTestCase):
    def test_home_page(self):
        """Home page should respond with a success 200."""
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)

    def test_about_page_is_gone(self):
        self.assertEqual(self.client.get("/about").status_code, 404)


class NavTests(LoggedInTestCase):
    def _active(self, url):
        html = self.client.get(url).content.decode()
        nav = html.split('class="site-nav"')[1].split("</nav>")[0]
        return re.findall(r'<a href="([^"]+)"\s+class="is-active"', nav)

    def test_highlights_current_section_only(self):
        self.assertEqual(self._active("/"), [])
        self.assertEqual(self._active("/planner/"), ["/planner/"])
        self.assertEqual(self._active("/planner/templates/"), ["/planner/templates/"])
        self.assertEqual(self._active("/recipes/ingredients/"), ["/recipes/"])
        self.assertEqual(self._active("/todo/recurring/"), ["/todo/"])

    def test_auth_controls(self):
        self.client.logout()
        response = self.client.get("/auth/login/")
        self.assertContains(response, "Log in")
        self.assertNotContains(response, "Sign up")

        user = User.objects.create_user(username="jorge", password="x")
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertContains(response, "Log out")
        self.assertContains(
            response, '<span class="site-auth__user">jorge</span>', html=True
        )

    def test_login_page_uses_layout(self):
        response = self.client.get("/auth/login/")
        self.assertContains(response, 'class="site-header"')

    def test_mobile_tab_bar_and_account_menu(self):
        response = self.client.get("/recipes/")
        tab_bar = (
            response.content.decode().split('class="tab-bar"')[1].split("</nav>")[0]
        )
        self.assertIn('href="/recipes/" class="is-active"', tab_bar)
        self.assertContains(response, 'aria-label="Account menu for member"')


class PolishTests(TestCase):
    def test_login_required_redirects_to_the_real_login_page(self):
        response = self.client.get("/todo/create/")
        self.assertRedirects(response, "/auth/login/?next=/todo/create/")

    def test_layout_loads_app_script_and_toast(self):
        response = self.client.get("/auth/login/")
        self.assertRegex(response.content.decode(), r"/static/js/app\.[0-9a-f]+\.js")
        self.assertContains(response, 'id="toast"')

    def test_mobile_avatar_shows_user_initial(self):
        user = User.objects.create_user(username="jorge", password="x")
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertContains(response, 'aria-label="Account menu for jorge"')
        avatar = response.content.decode().split('class="site-avatar"')[1]
        self.assertEqual(avatar.split(">", 1)[1].split("<", 1)[0].strip(), "J")


class LoginRequiredTests(TestCase):
    def test_every_section_redirects_to_login_when_logged_out(self):
        for url in [
            "/",
            "/planner/",
            "/planner/templates/",
            "/recipes/",
            "/recipes/1/",
            "/todo/",
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"].split("?")[0], "/auth/login/")

    def test_public_pages_stay_reachable(self):
        for url in [
            "/auth/login/",
            "/auth/password_reset/",
            "/health/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_logged_out_pages_hide_section_navigation(self):
        response = self.client.get("/auth/login/")
        self.assertNotContains(response, 'class="site-nav"')
        self.assertNotContains(response, 'class="tab-bar"')

    def test_login_then_lands_on_requested_page(self):
        User.objects.create_user(username="jorge", password="pw-12345!")
        response = self.client.post(
            "/auth/login/?next=/recipes/",
            {"username": "jorge", "password": "pw-12345!", "next": "/recipes/"},
        )
        self.assertRedirects(response, "/recipes/")

    def test_signup_is_closed(self):
        self.assertEqual(self.client.get("/auth/signup/").status_code, 404)


class HomeDashboardTests(LoggedInTestCase):
    def setUp(self):
        super().setUp()
        from recipes.models import Recipe

        self.today = datetime.date.today()
        self.stew = Recipe.objects.create(name="Stew", description="d", servings=2)

    def test_shows_todays_meals_and_empty_slots(self):
        from planner.models import CalendarMeal, MealType

        CalendarMeal.objects.create(
            date=self.today, meal_type=MealType.LUNCH, recipe=self.stew
        )
        # Tomorrow's meal must not appear.
        CalendarMeal.objects.create(
            date=self.today + datetime.timedelta(days=1),
            meal_type=MealType.DINNER,
            recipe=self.stew,
        )
        response = self.client.get("/")
        meals = {m["label"]: m["meal"] for m in response.context["meals"]}
        self.assertEqual(meals["Lunch"].recipe, self.stew)
        self.assertIsNone(meals["Dinner"])
        self.assertContains(response, f'href="{self.stew.get_absolute_url()}"')
        self.assertContains(response, "Nothing planned")

    def test_shows_only_overdue_and_this_weeks_todos(self):
        from todo.models import Todo

        sunday = self.today + datetime.timedelta(days=6 - self.today.weekday())
        Todo.objects.create(name="Late", due_date=self.today - datetime.timedelta(1))
        Todo.objects.create(name="Soon", due_date=sunday)
        Todo.objects.create(name="Far", due_date=sunday + datetime.timedelta(1))
        Todo.objects.create(name="Whenever")
        Todo.objects.create(name="Finished", due_date=self.today, is_done=True)

        response = self.client.get("/")

        groups = {
            g["key"]: [t.name for t in g["todos"]]
            for g in response.context["todo_groups"]
        }
        self.assertEqual(groups, {"overdue": ["Late"], "week": ["Soon"]})
        # Rows are the interactive todo partial (tick in place).
        self.assertContains(response, 'id="todo-list"', count=0)
        self.assertContains(response, "todo__details")

    def test_empty_todos_message(self):
        response = self.client.get("/")
        self.assertContains(response, "Nothing overdue or due this week.")

    def test_home_creates_missing_recurring_todos(self):
        from todo.models import RecurringTodo

        RecurringTodo.objects.create(name="Bins", start_date=self.today)
        response = self.client.get("/")
        names = [t.name for g in response.context["todo_groups"] for t in g["todos"]]
        self.assertIn("Bins", names)


class EmbeddingTests(LoggedInTestCase):
    def test_framing_is_same_origin_by_default_via_csp(self):
        response = self.client.get("/")
        self.assertEqual(response["Content-Security-Policy"], "frame-ancestors 'self'")
        # Replaced by CSP: X-Frame-Options can't allow a specific other site.
        self.assertNotIn("X-Frame-Options", response)

    def test_configured_origins_may_embed(self):
        from django.test import override_settings
        from django.utils.csp import CSP

        policy = {"frame-ancestors": [CSP.SELF, "https://test.example.com"]}
        with override_settings(SECURE_CSP=policy):
            response = self.client.get("/")
        self.assertEqual(
            response["Content-Security-Policy"],
            "frame-ancestors 'self' https://test.example.com",
        )
