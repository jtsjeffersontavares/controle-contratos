import os
from importlib import reload
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import resolve

import config.settings as settings_module
from config.entrypoint_utils import resolve_database_host_and_port


class RenderSettingsTests(SimpleTestCase):
    def _reload_settings(self):
        return reload(settings_module)

    def test_database_url_is_used_for_postgresql(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://usuario:senha@db.example.com:5432/contratos",
                "DB_ENGINE": "sqlite",
                "POSTGRES_DB": "",
                "POSTGRES_USER": "",
                "POSTGRES_PASSWORD": "",
                "POSTGRES_HOST": "",
                "POSTGRES_PORT": "",
            },
            clear=False,
        ):
            settings = self._reload_settings()
            self.assertEqual(
                settings.DATABASES["default"]["ENGINE"], "django.db.backends.postgresql"
            )
            self.assertEqual(settings.DATABASES["default"]["NAME"], "contratos")
            self.assertEqual(settings.DATABASES["default"]["HOST"], "db.example.com")
            self.assertEqual(settings.DATABASES["default"]["PORT"], "5432")

    def test_unrecognized_deployment_hostname_is_not_added_to_allowed_hosts(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_ALLOWED_HOSTS": "localhost",
                "CUSTOM_HOSTNAME": "app.example.com",
            },
            clear=False,
        ):
            settings = self._reload_settings()
            self.assertIn("localhost", settings.ALLOWED_HOSTS)
            self.assertNotIn("app.example.com", settings.ALLOWED_HOSTS)
            self.assertNotIn("https://app.example.com", settings.CSRF_TRUSTED_ORIGINS)

    def test_render_external_hostname_is_added_to_allowed_hosts(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_ALLOWED_HOSTS": "localhost",
                "RENDER_EXTERNAL_HOSTNAME": "app.onrender.com",
            },
            clear=False,
        ):
            settings = self._reload_settings()
            self.assertIn("localhost", settings.ALLOWED_HOSTS)
            self.assertIn("app.onrender.com", settings.ALLOWED_HOSTS)
            self.assertIn("https://app.onrender.com", settings.CSRF_TRUSTED_ORIGINS)

    def test_entrypoint_uses_database_url_host_for_postgresql(self):
        with patch.dict(
            os.environ,
            {
                "DB_ENGINE": "postgresql",
                "DATABASE_URL": "postgresql://user:pass@db.example.com:5432/contratos",
                "POSTGRES_HOST": "",
                "POSTGRES_PORT": "",
            },
            clear=False,
        ):
            host, port = resolve_database_host_and_port()
            self.assertEqual(host, "db.example.com")
            self.assertEqual(port, 5432)

    def test_login_and_logout_routes_resolve_with_and_without_trailing_slash(self):
        self.assertEqual(resolve("/login").view_name, "login")
        self.assertEqual(resolve("/login/").view_name, "login")
        self.assertEqual(resolve("/logout").view_name, "logout")
        self.assertEqual(resolve("/logout/").view_name, "logout")
