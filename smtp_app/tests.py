from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from smtp_app.forms import ExternalSMTPAccountForm
from smtp_app.backends import ExternalSMTPEmailBackend
from smtp_app.models import ExternalSMTPAccount
from smtp_app.services import (
    SMTPServiceError,
    build_smtp_connection,
    get_user_notification_email_options,
    send_test_email,
    test_smtp_connection,
)


User = get_user_model()


class ExternalSMTPAccountFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="smtp-user@example.com",
            email="smtp-user@example.com",
            password="secret12345",
        )

    def test_form_encrypts_password_on_save(self):
        form = ExternalSMTPAccountForm(
            data={
                "label": "Corporate SMTP",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "username": "smtp-user@example.com",
                "smtp_password": "app-password-123",
                "from_email": "smtp-user@example.com",
                "reply_to_email": "",
                "use_tls": "on",
                "use_ssl": "",
                "skip_tls_verify": "on",
                "is_active": "on",
                "use_for_notifications": "on",
            },
            user=self.user,
        )

        self.assertTrue(form.is_valid(), form.errors)
        account = form.save()
        self.assertNotEqual(account.password_ciphertext, "app-password-123")
        self.assertEqual(account.get_password(), "app-password-123")
        self.assertTrue(account.skip_tls_verify)

    def test_form_requires_password_on_create(self):
        form = ExternalSMTPAccountForm(
            data={
                "label": "Corporate SMTP",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "username": "smtp-user@example.com",
                "smtp_password": "",
                "from_email": "smtp-user@example.com",
                "reply_to_email": "",
                "use_tls": "on",
                "use_ssl": "",
                "skip_tls_verify": "",
                "is_active": "on",
                "use_for_notifications": "on",
            },
            user=self.user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("smtp_password", form.errors)


class SMTPServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="smtp-service@example.com",
            email="smtp-service@example.com",
            password="secret12345",
        )
        self.account = ExternalSMTPAccount.objects.create(
            user=self.user,
            label="SMTP",
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="smtp-service@example.com",
            from_email="smtp-service@example.com",
            use_tls=True,
            use_ssl=False,
            is_active=True,
            use_for_notifications=True,
        )
        self.account.set_password("super-secret")
        self.account.save(update_fields=["password_ciphertext"])

    def test_build_smtp_connection_uses_account_credentials(self):
        connection = build_smtp_connection(self.account)
        self.assertEqual(connection.host, "smtp.example.com")
        self.assertEqual(connection.port, 587)
        self.assertEqual(connection.username, "smtp-service@example.com")
        self.assertEqual(connection.password, "super-secret")
        self.assertIsInstance(connection, ExternalSMTPEmailBackend)

    def test_build_smtp_connection_respects_skip_tls_verify(self):
        self.account.skip_tls_verify = True
        connection = build_smtp_connection(self.account)
        self.assertTrue(connection.skip_tls_verify)

    @patch("smtp_app.services.build_smtp_connection")
    def test_test_smtp_connection_reports_success(self, mock_build):
        fake_connection = MagicMock()
        fake_connection.open.return_value = True
        mock_build.return_value = fake_connection

        result = test_smtp_connection(self.account)

        self.assertTrue(result["ok"])
        self.account.refresh_from_db()
        self.assertEqual(self.account.last_test_status, ExternalSMTPAccount.TestStatus.OK)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="fallback@example.com",
    )
    def test_send_test_email_sends_message(self):
        with patch("smtp_app.services.build_smtp_connection") as mock_build:
            mock_build.return_value = mail.get_connection()
            result = send_test_email(self.account, "recipient@example.com")

        self.assertTrue(result["ok"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "smtp-service@example.com")

    def test_get_user_notification_email_options_falls_back_when_disabled(self):
        self.account.use_for_notifications = False
        self.account.save(update_fields=["use_for_notifications"])

        self.assertEqual(get_user_notification_email_options(self.user), {})


class SMTPViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="smtp-view@example.com",
            email="smtp-view@example.com",
            password="secret12345",
        )
        self.client.force_login(self.user)

    def test_save_account_creates_record(self):
        response = self.client.post(
            reverse("smtp_save_account"),
            {
                "label": "Corporate SMTP",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "username": "smtp-view@example.com",
                "smtp_password": "secret-123",
                "from_email": "smtp-view@example.com",
                "reply_to_email": "",
                "use_tls": "on",
                "skip_tls_verify": "on",
                "is_active": "on",
                "use_for_notifications": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ExternalSMTPAccount.objects.filter(user=self.user).exists())

    @patch("smtp_app.views.test_smtp_connection", return_value={"ok": True, "error": ""})
    def test_test_account_returns_hx_panel(self, mock_test):
        ExternalSMTPAccount.objects.create(
            user=self.user,
            label="SMTP",
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="smtp-view@example.com",
            from_email="smtp-view@example.com",
        )
        response = self.client.post(reverse("smtp_test_account"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Внешний SMTP", response.content.decode("utf-8"))

    def test_send_test_email_without_account_shows_message_in_panel(self):
        response = self.client.post(reverse("smtp_send_test_email"), HTTP_HX_REQUEST="true")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Не удалось обработать SMTP-настройки.", content)

    @patch("smtp_app.views.send_test_email", return_value={"ok": True, "recipient_email": "smtp-view@example.com"})
    def test_send_test_email_uses_unsaved_form_values(self, mock_send):
        response = self.client.post(
            reverse("smtp_send_test_email"),
            {
                "label": "Corporate SMTP",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "username": "smtp-view@example.com",
                "smtp_password": "secret-123",
                "from_email": "smtp-view@example.com",
                "reply_to_email": "",
                "use_tls": "on",
                "is_active": "on",
                "use_for_notifications": "on",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        account = mock_send.call_args.args[0]
        self.assertEqual(account.smtp_host, "smtp.example.com")
        self.assertEqual(account.username, "smtp-view@example.com")
        self.assertEqual(account.get_password(), "secret-123")
