from django.test import SimpleTestCase


class ViewTests(SimpleTestCase):
    def test_home_page(self):
        """Home page should respond with a success 200."""
        response = self.client.get("/", follow=True)
        self.assertEqual(response.status_code, 200)

    def test_about_page(self):
        """About page should respond with a success 200."""
        response = self.client.get("/about", follow=True)
        self.assertEqual(response.status_code, 200)
