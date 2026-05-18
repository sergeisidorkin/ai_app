from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from checklists_app.models import ProjectWorkspace
from classifiers_app.models import OKSMCountry
from contacts_app.models import CitizenshipRecord, PersonRecord
from core.models import CloudStorageSettings
from core.email_backend import DomainSMTPEmailBackend
from group_app.models import GroupMember
from nextcloud_app.models import NextcloudUserLink
from notifications_app.email_delivery import (
    EmailDeliveryError,
    build_plain_text_body,
    send_notification_email,
)
from notifications_app.models import Notification, NotificationPerformerLink
from notifications_app.services import normalize_delivery_channels, process_participation_notification
from projects_app.models import Performer, ProjectRegistration
from users_app.forms import FREELANCER_LABEL
from users_app.models import Employee


class DeliveryChannelTests(SimpleTestCase):
    def test_normalize_delivery_channels_defaults_to_system(self):
        self.assertEqual(normalize_delivery_channels([]), ("system",))

    def test_normalize_delivery_channels_maps_legacy_email_to_system_email(self):
        self.assertEqual(
            normalize_delivery_channels(["email"]),
            ("system_email",),
        )

    def test_normalize_delivery_channels_keeps_connected_email_separate(self):
        self.assertEqual(
            normalize_delivery_channels(["system", "connected_email"]),
            ("system", "connected_email"),
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
        self.assertIn("@example.com>", mail.outbox[0].message()["Message-ID"])

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


@override_settings(
    EMAIL_HOST="smtp.example.com",
    EMAIL_PORT=587,
    EMAIL_USE_TLS=False,
    EMAIL_USE_SSL=False,
    EMAIL_LOCAL_HOSTNAME="imcmontanai.ru",
)
class DomainSMTPEmailBackendTests(SimpleTestCase):
    @patch("core.email_backend.smtplib.SMTP")
    def test_open_uses_configured_local_hostname(self, smtp_mock):
        backend = DomainSMTPEmailBackend()

        backend.open()

        smtp_mock.assert_called_once_with(
            "smtp.example.com",
            587,
            local_hostname="imcmontanai.ru",
            timeout=10,
        )


class ParticipationNotificationContractPrefillTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(
            username="actor@example.com",
            password="secret",
            is_staff=True,
        )
        self.expert_user = get_user_model().objects.create_user(
            username="expert@example.com",
            email="expert@example.com",
            password="secret",
            first_name="Иван",
            last_name="Иванов",
            is_staff=True,
        )
        self.country = OKSMCountry.objects.create(
            number=398,
            code="398",
            short_name="Казахстан",
            alpha2="KZ",
            alpha3="KAZ",
        )
        self.group_member = GroupMember.objects.create(
            short_name="Казахстан",
            country_name="Казахстан",
            country_code="398",
            country_alpha2="KZ",
        )
        self.project_group = GroupMember.objects.create(
            short_name="Россия",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=1,
        )
        self.person = PersonRecord.objects.create(
            last_name="Иванов",
            first_name="Иван",
            middle_name="Иванович",
        )
        CitizenshipRecord.objects.create(
            person=self.person,
            country=self.country,
            valid_to=None,
        )
        self.employee = Employee.objects.create(
            user=self.expert_user,
            person_record=self.person,
            patronymic="Иванович",
            employment=FREELANCER_LABEL,
        )
        self.project = ProjectRegistration.objects.create(
            number=7001,
            group_member=self.project_group,
            name="Договорный проект",
            year=2026,
        )
        self.performer = Performer.objects.create(
            registration=self.project,
            employee=self.employee,
            executor="Иванов Иван Иванович",
        )
        self.notification = Notification.objects.create(
            notification_type=Notification.NotificationType.PROJECT_PARTICIPATION_CONFIRMATION,
            recipient=self.expert_user,
            sender=self.actor,
            project=self.project,
            title_text="Подтвердите участие",
        )
        NotificationPerformerLink.objects.create(
            notification=self.notification,
            performer=self.performer,
        )

    @patch("worktime_app.services.ensure_confirmed_assignments_for_performers")
    def test_confirming_participation_prefills_contract_adjustment_fields(self, mocked_assignments):
        process_participation_notification(
            self.notification,
            self.expert_user,
            Notification.ActionChoice.CONFIRMED,
        )

        self.performer.refresh_from_db()
        self.assertEqual(self.performer.participation_response, Performer.ParticipationResponse.CONFIRMED)
        self.assertIsNotNone(self.performer.contract_batch_id)
        self.assertEqual(self.performer.contract_group_member_id, self.group_member.pk)
        self.assertTrue(self.performer.contract_number.startswith("IMCM/7001-ИИ/"))
        self.assertEqual(self.performer.contract_date, timezone.localdate(self.notification.action_at))
        self.assertEqual(self.performer.contract_signing_note, "Разрабатывается проект договора")
        mocked_assignments.assert_called_once_with([self.performer.pk])

    @override_settings(
        NEXTCLOUD_PROVISIONING_BASE_URL="https://cloud.example.com",
        NEXTCLOUD_PROVISIONING_USERNAME="cloud-admin",
        NEXTCLOUD_PROVISIONING_TOKEN="token",
        NEXTCLOUD_OIDC_PROVIDER_ID=1,
    )
    @patch("nextcloud_app.workspace.NextcloudApiClient")
    @patch("worktime_app.services.ensure_confirmed_assignments_for_performers")
    def test_confirming_participation_grants_nextcloud_workspace_editor_access(
        self,
        mocked_assignments,
        mocked_client_cls,
    ):
        settings_obj = CloudStorageSettings.get_solo()
        settings_obj.primary_storage = CloudStorageSettings.PrimaryStorage.NEXTCLOUD
        settings_obj.nextcloud_root_path = "/Corporate Root"
        settings_obj.save()
        ProjectWorkspace.objects.create(
            project=self.project,
            disk_path="/Corporate Root/03 Проекты/2026/Проект 7001 Договорный проект",
            created_by=self.actor,
        )
        NextcloudUserLink.objects.create(
            user=self.expert_user,
            nextcloud_user_id=f"ncstaff-{self.expert_user.pk}",
            nextcloud_username=f"ncstaff-{self.expert_user.pk}",
            nextcloud_email=self.expert_user.email,
        )
        client = Mock()
        client.is_configured = True
        client.username = "cloud-admin"
        client.ensure_user_share.return_value = Mock()
        mocked_client_cls.EDITOR_PERMISSIONS = 15
        mocked_client_cls.return_value = client

        process_participation_notification(
            self.notification,
            self.expert_user,
            Notification.ActionChoice.CONFIRMED,
        )

        client.ensure_user_share.assert_called_once_with(
            "cloud-admin",
            "/Corporate Root/03 Проекты/2026/Проект 7001 Договорный проект",
            f"ncstaff-{self.expert_user.pk}",
            permissions=15,
        )
        mocked_assignments.assert_called_once_with([self.performer.pk])
