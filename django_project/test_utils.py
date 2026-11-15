from accounts.models import User
from django.test import TestCase


class LoggedInTestCase(TestCase):
    """The whole site requires login (LoginRequiredMiddleware): page tests
    start with a logged-in household member as self.user."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="member", password="x")
        self.client.force_login(self.user)
