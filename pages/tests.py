import re

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase


class ViewTests(SimpleTestCase):
    def test_home_page(self):
        """Home page should respond with a success 200."""
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)

    def test_about_page_is_gone(self):
        self.assertEqual(self.client.get("/about").status_code, 404)


class NavTests(TestCase):
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
        response = self.client.get("/")
        self.assertContains(response, "Log in")
        self.assertContains(response, "Sign up")

        user = get_user_model().objects.create_user(username="jorge", password="x")
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
        self.assertContains(response, 'aria-label="Account menu"')


class PolishTests(TestCase):
    def test_login_required_redirects_to_the_real_login_page(self):
        response = self.client.get("/todo/create/")
        self.assertRedirects(response, "/auth/login/?next=/todo/create/")

    def test_layout_loads_app_script_and_toast(self):
        response = self.client.get("/")
        self.assertRegex(response.content.decode(), r"/static/js/app\.[0-9a-f]+\.js")
        self.assertContains(response, 'id="toast"')
