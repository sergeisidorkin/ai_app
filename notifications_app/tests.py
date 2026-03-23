from types import SimpleNamespace

from django.core import mail
from django.test import SimpleTestCase, override_settings

from notifications_app.email_delivery import (
    EmailDeliveryError,
    build_plain_text_body,
    send_notification_email,
)
from notifications_app.services import normalize_delivery_channels


class DeliveryChannelTests(SimpleTestCase):
    def test_normalize_delivery_channels_defaults_to_system(self):
        self.assertEqual(normalize_delivery_channels([]), ("system",))

    def test_normalize_delivery_channels_adds_system_for_email(self):
        self.assertEqual(
            normalize_delivery_channels(["email"]),
            ("system", "email"),
        )

    def test_normalize_delivery_channels_rejects_unknown_values(self):
        with self.assertRaisesMessage(ValueError, "неподдерживаемые каналы доставки"):
            normalize_delivery_channels(["sms"])


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
)
class NotificationEmailDeliveryTests(SimpleTestCase):
    def test_send_notification_email_sends_plain_text_email(self):
        recipient = SimpleNamespace(email="expert@example.com", username="expert")

        result = send_notification_email(
            recipient=recipient,
            subject="Тест",
            content="Привет!\nЭто письмо.",
        )

        self.assertEqual(result["recipient_email"], "expert@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Тест")
        self.assertEqual(mail.outbox[0].body, "Привет!\nЭто письмо.")
        self.assertEqual(mail.outbox[0].alternatives, [])

    def test_send_notification_email_sends_html_alternative(self):
        recipient = SimpleNamespace(email="expert@example.com", username="expert")

        send_notification_email(
            recipient=recipient,
            subject="HTML",
            content="<p>Добрый день!</p><ul><li>Пункт 1</li></ul>",
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Добрый день!", mail.outbox[0].body)
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, "text/html")

    def test_send_notification_email_requires_recipient_email(self):
        recipient = SimpleNamespace(email="", username="expert")

        with self.assertRaises(EmailDeliveryError):
            send_notification_email(
                recipient=recipient,
                subject="Тест",
                content="Привет",
            )

    def test_build_plain_text_body_strips_basic_html(self):
        plain = build_plain_text_body("<p>Hello</p><p>World</p>")
        self.assertEqual(plain, "Hello\nWorld")
