import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from checklists_app.models import ProjectWorkspace
from classifiers_app.models import OKSMCountry
from contacts_app.models import CitizenshipRecord, PersonRecord
from core.models import CloudStorageSettings
from core.email_backend import DomainSMTPEmailBackend
from experts_app.models import ExpertProfile
from group_app.models import GroupMember, OrgUnit
from nextcloud_app.models import NextcloudUserLink
from notifications_app.email_delivery import (
    EmailDeliveryError,
    build_plain_text_body,
    send_notification_email,
)
from notifications_app.models import Notification, NotificationPerformerLink
from letters_app.models import LetterTemplate
from notifications_app.services import (
    create_contract_notifications,
    create_participation_notifications,
    create_payment_request_notifications,
    normalize_delivery_channels,
    process_participation_notification,
)
from policy_app.models import DEPARTMENT_HEAD_GROUP, LAWYER_GROUP, Product
from projects_app.models import Performer, ProjectRegistration, ProjectRegistrationProduct
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


class ParticipationBatchNotificationTests(TestCase):
    def setUp(self):
        self.sender = get_user_model().objects.create_user(
            username="sender@example.com",
            password="secret",
            is_staff=True,
        )
        self.recipient = get_user_model().objects.create_user(
            username="recipient@example.com",
            email="recipient@example.com",
            password="secret",
            first_name="Петр",
            is_staff=True,
        )
        self.employee = Employee.objects.create(
            user=self.recipient,
            patronymic="Петрович",
        )
        self.product_a = Product.objects.create(
            short_name="RFR",
            name_en="Red Flag Review",
            name_ru="Red Flag Review",
            display_name="Red Flag Review",
        )
        self.product_b = Product.objects.create(
            short_name="TDD",
            name_en="Technical Due Diligence",
            name_ru="Technical Due Diligence",
            display_name="Technical Due Diligence",
        )
        self.project_a = ProjectRegistration.objects.create(
            number=8123,
            name="Тест 55",
            year=2026,
            project_manager="Иванов Иван Иванович",
        )
        self.project_b = ProjectRegistration.objects.create(
            number=8123,
            name="Тест 55",
            year=2026,
            project_manager="Петров Петр Петрович",
        )
        ProjectRegistrationProduct.objects.create(registration=self.project_a, product=self.product_a, rank=1)
        ProjectRegistrationProduct.objects.create(registration=self.project_b, product=self.product_b, rank=1)
        self.project_a.refresh_from_db()
        self.project_b.refresh_from_db()
        self.batch_id = uuid.uuid4()
        self.performer_a = Performer.objects.create(
            registration=self.project_a,
            employee=self.employee,
            executor="Петров Петр Петрович",
            asset_name="Актив A",
            agreed_amount=Decimal("100.00"),
            participation_batch_id=self.batch_id,
        )
        self.performer_b = Performer.objects.create(
            registration=self.project_b,
            employee=self.employee,
            executor="Петров Петр Петрович",
            asset_name="Актив B",
            agreed_amount=Decimal("200.00"),
            participation_batch_id=self.batch_id,
        )
        self.project_a.gantt_data = {
            "data": [
                {
                    "id": "managed-performer-a",
                    "managed_source": "performer",
                    "performer_id": self.performer_a.pk,
                    "deadline": "2026-05-10",
                },
                {
                    "id": "managed-performer-a-later",
                    "managed_source": "performer",
                    "performer_id": self.performer_a.pk,
                    "deadline": "2026-05-12",
                },
            ],
        }
        self.project_b.gantt_data = {
            "data": [
                {
                    "id": "managed-performer-b",
                    "managed_source": "performer",
                    "performer_id": self.performer_b.pk,
                    "deadline": "2026-06-15",
                },
            ],
        }
        self.project_a.save(update_fields=["gantt_data"])
        self.project_b.save(update_fields=["gantt_data"])

    def test_create_participation_notifications_groups_by_participation_batch(self):
        request_sent_at = timezone.now()

        create_participation_notifications(
            performers=[self.performer_a, self.performer_b],
            sender=self.sender,
            request_sent_at=request_sent_at,
            deadline_at=request_sent_at + timedelta(hours=4),
            duration_hours=4,
            delivery_channels=["system"],
        )

        notification = Notification.objects.get()
        linked_ids = set(notification.performer_links.values_list("performer_id", flat=True))
        payload = notification.payload
        self.assertEqual(linked_ids, {self.performer_a.pk, self.performer_b.pk})
        self.assertEqual(payload["project_number"], "8123")
        self.assertEqual(set(payload["project_ids"]), {self.project_a.pk, self.project_b.pk})
        self.assertEqual(len(payload["project_labels"]), 2)
        self.assertEqual(payload["project_label"], "81230RU RFR-TDD Тест 55")
        self.assertIn("81230RU RFR Тест 55", payload["project_labels"])
        self.assertIn("81230RU TDD Тест 55", payload["project_labels"])
        self.assertNotIn(self.project_a.short_uid, payload["project_label"])
        self.assertNotIn("; 81230RU", payload["project_label"])
        self.assertEqual(
            payload["project_stages"],
            [
                "Этап 1: RFR Red Flag Review",
                "Этап 2: TDD Technical Due Diligence",
            ],
        )
        self.assertEqual(payload["project_manager"], "Этап 1: Иванов И.И.\nЭтап 2: Петров П.П.")
        self.assertEqual(payload["project_deadline_display"], "Этап 1: 12.05.2026\nЭтап 2: 15.06.2026")
        self.assertIn(
            "<p>Руководитель проекта: <ul><li>Этап 1: Иванов И.И.</li><li>Этап 2: Петров П.П.</li></ul></p>",
            notification.content_text,
        )
        self.assertIn(
            "<p>Срок завершения проекта: <ul><li>Этап 1: 12.05.2026</li><li>Этап 2: 15.06.2026</li></ul></p>",
            notification.content_text,
        )
        self.assertIn(
            "<p>Этапы проекта и продукты:</p><ul><li>Этап 1: RFR Red Flag Review</li>"
            "<li>Этап 2: TDD Technical Due Diligence</li></ul>",
            notification.content_text,
        )
        self.assertIn("<p>Этап 1: RFR Red Flag Review</p><ul><li>Актив A</li></ul>", notification.content_text)
        self.assertIn("<p>Этап 2: TDD Technical Due Diligence</p><ul><li>Актив B</li></ul>", notification.content_text)
        self.assertEqual(payload["agreed_amount_display"], "300,00")

    def test_single_project_stage_stays_on_template_line(self):
        request_sent_at = timezone.now()

        create_participation_notifications(
            performers=[self.performer_a],
            sender=self.sender,
            request_sent_at=request_sent_at,
            deadline_at=request_sent_at + timedelta(hours=4),
            duration_hours=4,
            delivery_channels=["system"],
        )

        notification = Notification.objects.get()
        self.assertIn(
            "<p>Этапы проекта и продукты:</p><ul><li>Этап 1: RFR Red Flag Review</li></ul>",
            notification.content_text,
        )
        self.assertNotIn("Этапы проекта и продукты: Этап 1: RFR Red Flag Review", notification.content_text)
        self.assertIn("<ul><li>Актив A</li></ul>", notification.content_text)
        self.assertNotIn("<p>Этап 1: RFR Red Flag Review</p><ul><li>Актив A</li></ul>", notification.content_text)

    def test_create_contract_notifications_groups_by_contract_batch(self):
        request_sent_at = timezone.now()
        contract_batch_id = uuid.uuid4()
        self.project_a.deadline = date(2026, 5, 20)
        self.project_b.deadline = date(2026, 6, 30)
        self.project_a.save(update_fields=["deadline"])
        self.project_b.save(update_fields=["deadline"])
        Performer.objects.filter(pk__in=[self.performer_a.pk, self.performer_b.pk]).update(
            contract_batch_id=contract_batch_id,
        )
        self.performer_a.refresh_from_db()
        self.performer_b.refresh_from_db()

        create_contract_notifications(
            performers=[self.performer_a, self.performer_b],
            sender=self.sender,
            request_sent_at=request_sent_at,
            deadline_at=request_sent_at + timedelta(hours=4),
            duration_hours=4,
            delivery_channels=["system"],
        )

        notification = Notification.objects.get()
        linked_ids = set(notification.performer_links.values_list("performer_id", flat=True))
        payload = notification.payload
        self.assertEqual(linked_ids, {self.performer_a.pk, self.performer_b.pk})
        self.assertEqual(payload["project_label"], "81230RU RFR-TDD Тест 55")
        self.assertEqual(
            payload["project_stages"],
            [
                "Этап 1: RFR Red Flag Review",
                "Этап 2: TDD Technical Due Diligence",
            ],
        )
        self.assertEqual(payload["project_manager"], "Этап 1: Иванов И.И.\nЭтап 2: Петров П.П.")
        self.assertEqual(payload["project_deadline_display"], "30.06.2026")
        self.assertIn(
            "<p>Этапы проекта и продукты:</p><ul><li>Этап 1: RFR Red Flag Review</li>"
            "<li>Этап 2: TDD Technical Due Diligence</li></ul>",
            notification.content_text,
        )
        self.assertIn("<p>Срок завершения проекта: 30.06.2026</p>", notification.content_text)
        self.assertIn("Срок исполнения: до 30.06.2026", notification.content_text)
        self.assertNotIn("загрузить подписанную скан-копию", notification.content_text)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_contract_system_email_sends_copy_recipients_from_template(self):
        cc_user = get_user_model().objects.create_user(
            username="contract-copy@example.com",
            email="contract-copy@example.com",
            password="secret",
            first_name="Анна",
            is_staff=True,
        )
        Employee.objects.create(user=cc_user, patronymic="Андреевна")
        template = LetterTemplate.objects.create(
            template_type="contract_sending",
            user=self.sender,
            subject_template="Договор {project_label}",
            body_html="<p>CONTRACT_COPY_MARKER {recipient_name}</p>",
            is_default=False,
        )
        template.cc_recipients.set([cc_user, self.recipient])

        request_sent_at = timezone.now()
        contract_batch_id = uuid.uuid4()
        Performer.objects.filter(pk=self.performer_a.pk).update(contract_batch_id=contract_batch_id)
        self.performer_a.refresh_from_db()

        with self.captureOnCommitCallbacks(execute=True):
            result = create_contract_notifications(
                performers=[self.performer_a],
                sender=self.sender,
                request_sent_at=request_sent_at,
                deadline_at=request_sent_at + timedelta(hours=4),
                duration_hours=4,
                delivery_channels=["system_email"],
            )

        recipients = sorted(message.to[0] for message in mail.outbox)
        self.assertEqual(recipients, ["contract-copy@example.com", "recipient@example.com"])
        self.assertEqual(result["email_delivery"]["attempted"], 2)
        self.assertEqual(result["email_delivery"]["sent"], 2)
        self.assertEqual(
            result["email_delivery"]["channels"]["system_email"]["attempted"],
            2,
        )
        self.assertTrue(all("CONTRACT_COPY_MARKER" in message.body for message in mail.outbox))

    def _ensure_lawyer_user(self):
        lawyer_group, _ = Group.objects.get_or_create(name=LAWYER_GROUP)
        lawyer = (
            get_user_model().objects
            .filter(groups__name=LAWYER_GROUP, is_staff=True, is_active=True)
            .order_by("pk")
            .first()
        )
        if lawyer:
            return lawyer
        lawyer = get_user_model().objects.create_user(
            username="payment-lawyer@example.com",
            email="payment-lawyer@example.com",
            password="secret",
            first_name="Анна",
            last_name="Юрина",
            is_staff=True,
        )
        Employee.objects.create(user=lawyer, patronymic="Юрьевна")
        lawyer.groups.add(lawyer_group)
        return lawyer

    def test_create_payment_request_notifications_uses_payment_request_template(self):
        lawyer = self._ensure_lawyer_user()
        LetterTemplate.objects.create(
            template_type="payment_request",
            user=None,
            subject_template="Заявка на оплату №{number_of_request}",
            body_html=(
                "<p>Добрый день, {recipient_name_lawer}</p>"
                "<p>Просим произвести оплату в {payment_date}.</p>"
                "<p>[payment_request]</p>"
            ),
            is_default=True,
        )
        request_sent_at = timezone.localtime().replace(day=10, hour=12, minute=0, second=0, microsecond=0)
        contract_batch_id = uuid.uuid4()
        Performer.objects.filter(pk__in=[self.performer_a.pk, self.performer_b.pk]).update(
            contract_batch_id=contract_batch_id,
            contract_number="IMC/8123-PP/02-26",
            prepayment=Decimal("30"),
            final_payment=Decimal("70"),
        )
        self.performer_a.refresh_from_db()
        self.performer_b.refresh_from_db()

        create_payment_request_notifications(
            performers=[self.performer_a, self.performer_b],
            letter_performers=[self.performer_a, self.performer_b],
            sender=self.sender,
            request_sent_at=request_sent_at,
            request_number=7,
            delivery_channels=["system"],
        )

        self.assertEqual(
            Notification.objects.filter(
                notification_type=Notification.NotificationType.PROJECT_PAYMENT_REQUEST,
            ).count(),
            1,
        )
        notification = Notification.objects.get(
            notification_type=Notification.NotificationType.PROJECT_PAYMENT_REQUEST,
        )
        self.assertEqual(notification.recipient_id, lawyer.pk)
        self.assertEqual(notification.title_text, "Заявка на оплату №7")
        self.assertIn("Добрый день, Анна Юрьевна", notification.content_text)
        self.assertIn("середине месяца", notification.content_text)
        self.assertIn("Проект:", notification.content_text)
        self.assertIn("Оплатить:", notification.content_text)
        self.assertIn("30% аванс", notification.content_text)
        self.assertEqual(notification.payload.get("letter_template_type"), "payment_request")
        self.assertEqual(notification.payload.get("payment_date"), notification.payload["payment_date"])
        self.assertIsNone(notification.deadline_at)
        self.assertNotEqual(notification.recipient_id, self.recipient.pk)

    def test_payment_request_payment_date_uses_end_of_month_after_15th(self):
        self._ensure_lawyer_user()
        request_sent_at = timezone.localtime().replace(day=20, hour=12, minute=0, second=0, microsecond=0)
        contract_batch_id = uuid.uuid4()
        Performer.objects.filter(pk=self.performer_a.pk).update(
            contract_batch_id=contract_batch_id,
            contract_number="IMC/8123-PP/02-26",
            prepayment=Decimal("50"),
            final_payment=Decimal("50"),
            agreed_amount=Decimal("180000.00"),
        )
        self.performer_a.refresh_from_db()

        create_payment_request_notifications(
            performers=[self.performer_a],
            letter_performers=[self.performer_a],
            sender=self.sender,
            request_sent_at=request_sent_at,
            request_number=8,
            delivery_channels=["system"],
        )

        notification = Notification.objects.get(
            notification_type=Notification.NotificationType.PROJECT_PAYMENT_REQUEST,
        )
        self.assertEqual(notification.payload["number_of_request"], "8")
        self.assertIn("конце месяца", notification.payload["payment_date"])
        self.assertIn("90 000,00", notification.payload["payment_request"])
        self.assertIn("50% аванс", notification.payload["payment_request"])

    def test_payment_request_final_payment_line_after_advance_sent(self):
        self._ensure_lawyer_user()
        request_sent_at = timezone.localtime().replace(day=20, hour=12, minute=0, second=0, microsecond=0)
        contract_batch_id = uuid.uuid4()
        Performer.objects.filter(pk=self.performer_a.pk).update(
            contract_batch_id=contract_batch_id,
            contract_number="IMC/8123-PP/02-26",
            prepayment=Decimal("50"),
            final_payment=Decimal("50"),
            agreed_amount=Decimal("180000.00"),
            advance_payment_request_sent_at=request_sent_at - timedelta(days=1),
        )
        self.performer_a.refresh_from_db()

        create_payment_request_notifications(
            performers=[self.performer_a],
            letter_performers=[self.performer_a],
            sender=self.sender,
            request_sent_at=request_sent_at,
            request_number=9,
            delivery_channels=["system"],
        )

        notification = Notification.objects.get(
            notification_type=Notification.NotificationType.PROJECT_PAYMENT_REQUEST,
        )
        self.assertEqual(notification.title_text, "Заявка на оплату №9")
        self.assertIn("90 000,00", notification.payload["payment_request"])
        self.assertIn("50% окончательный платеж", notification.payload["payment_request"])
        self.assertNotIn("аванс", notification.payload["payment_request"])

    def test_payment_request_notification_uses_saved_letter_template(self):
        from projects_app.services.payment_request import payment_request_sender_display

        lawyer = self._ensure_lawyer_user()
        self.sender.last_name = "Иванов"
        self.sender.save(update_fields=["last_name"])
        marker = "CUSTOM_PAYMENT_TEMPLATE_MARKER_XYZ"
        LetterTemplate.objects.update_or_create(
            template_type="payment_request",
            user=self.sender,
            defaults={
                "subject_template": "Заявка №{number_of_request} тест",
                "body_html": f"<p>{marker}</p><p>Дата: {{payment_date}}</p><p>[payment_request]</p>",
                "is_default": False,
            },
        )
        request_sent_at = timezone.now()
        contract_batch_id = uuid.uuid4()
        Performer.objects.filter(pk=self.performer_a.pk).update(
            contract_batch_id=contract_batch_id,
            contract_number="IMC/8123-PP/02-26",
            prepayment=Decimal("30"),
            final_payment=Decimal("70"),
        )
        self.performer_a.refresh_from_db()

        create_payment_request_notifications(
            performers=[self.performer_a],
            letter_performers=[self.performer_a],
            sender=self.sender,
            request_sent_at=request_sent_at,
            request_number=11,
            delivery_channels=["system"],
        )

        notification = Notification.objects.get(
            notification_type=Notification.NotificationType.PROJECT_PAYMENT_REQUEST,
            recipient=lawyer,
        )
        self.assertIn(marker, notification.content_text)
        self.assertTrue(notification.payload.get("rendered_from_template"))
        self.assertEqual(notification.title_text, "Заявка №11 тест")
        self.assertEqual(
            notification.payload.get("sender"),
            payment_request_sender_display(self.sender),
        )

    def test_payment_request_batch_creates_single_notification_for_multiple_rows(self):
        self._ensure_lawyer_user()
        request_sent_at = timezone.now()
        batch_a = uuid.uuid4()
        batch_b = uuid.uuid4()
        Performer.objects.filter(pk=self.performer_a.pk).update(
            contract_batch_id=batch_a,
            contract_number="IMC/A/01",
            prepayment=Decimal("50"),
            final_payment=Decimal("50"),
        )
        Performer.objects.filter(pk=self.performer_b.pk).update(
            contract_batch_id=batch_b,
            contract_number="IMC/B/02",
            prepayment=Decimal("50"),
            final_payment=Decimal("50"),
        )
        self.performer_a.refresh_from_db()
        self.performer_b.refresh_from_db()

        create_payment_request_notifications(
            performers=[self.performer_a, self.performer_b],
            letter_performers=[self.performer_a, self.performer_b],
            sender=self.sender,
            request_sent_at=request_sent_at,
            request_number=10,
            delivery_channels=["system"],
        )

        notifications = Notification.objects.filter(
            notification_type=Notification.NotificationType.PROJECT_PAYMENT_REQUEST,
        )
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.first().payload["number_of_request"], "10")
        linked_ids = set(notifications.first().performer_links.values_list("performer_id", flat=True))
        self.assertEqual(linked_ids, {self.performer_a.pk, self.performer_b.pk})

    @patch("nextcloud_app.workspace.grant_project_workspace_editor_access_for_performers")
    @patch("worktime_app.services.ensure_confirmed_assignments_for_performers")
    def test_processing_batch_notification_updates_all_linked_performers(
        self,
        mocked_assignments,
        mocked_nextcloud,
    ):
        notification = Notification.objects.create(
            notification_type=Notification.NotificationType.PROJECT_PARTICIPATION_CONFIRMATION,
            recipient=self.recipient,
            sender=self.sender,
            project=self.project_a,
            title_text="Подтвердите участие",
        )
        NotificationPerformerLink.objects.create(
            notification=notification,
            performer=self.performer_a,
            position=1,
        )
        NotificationPerformerLink.objects.create(
            notification=notification,
            performer=self.performer_b,
            position=2,
        )

        process_participation_notification(
            notification,
            self.recipient,
            Notification.ActionChoice.CONFIRMED,
        )

        self.performer_a.refresh_from_db()
        self.performer_b.refresh_from_db()
        self.assertEqual(self.performer_a.participation_response, Performer.ParticipationResponse.CONFIRMED)
        self.assertEqual(self.performer_b.participation_response, Performer.ParticipationResponse.CONFIRMED)
        mocked_assignments.assert_called_once_with([self.performer_a.pk, self.performer_b.pk])


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

    @patch("worktime_app.services.ensure_confirmed_assignments_for_performers")
    def test_confirming_participation_prefills_one_contract_batch_for_participation_batch(self, mocked_assignments):
        product_b = Product.objects.create(
            short_name="TDD",
            name_en="Technical Due Diligence",
            name_ru="ТДД",
        )
        second_project = ProjectRegistration.objects.create(
            number=self.project.number,
            group_member=self.project_group,
            type=product_b,
            name="Договорный проект",
            year=2026,
        )
        participation_batch_id = uuid.uuid4()
        self.performer.participation_batch_id = participation_batch_id
        self.performer.save(update_fields=["participation_batch_id"])
        second_performer = Performer.objects.create(
            registration=second_project,
            employee=self.employee,
            executor=self.performer.executor,
            participation_batch_id=participation_batch_id,
        )
        NotificationPerformerLink.objects.create(
            notification=self.notification,
            performer=second_performer,
        )

        process_participation_notification(
            self.notification,
            self.expert_user,
            Notification.ActionChoice.CONFIRMED,
        )

        self.performer.refresh_from_db()
        second_performer.refresh_from_db()
        self.assertEqual(self.performer.participation_response, Performer.ParticipationResponse.CONFIRMED)
        self.assertEqual(second_performer.participation_response, Performer.ParticipationResponse.CONFIRMED)
        self.assertIsNotNone(self.performer.contract_batch_id)
        self.assertEqual(self.performer.contract_batch_id, second_performer.contract_batch_id)
        self.assertEqual(self.performer.contract_number, second_performer.contract_number)
        mocked_assignments.assert_called_once_with([self.performer.pk, second_performer.pk])

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
        direction = OrgUnit.objects.create(
            company=self.project_group,
            department_name="Горное дело",
            unit_type="expertise",
        )
        ExpertProfile.objects.create(
            employee=self.employee,
            expertise_direction=direction,
        )
        direction_head_user = get_user_model().objects.create_user(
            username="direction-head@example.com",
            email="direction-head@example.com",
            password="secret",
            first_name="Анна",
            last_name="Руководитель",
            is_staff=True,
            is_active=True,
        )
        Employee.objects.create(
            user=direction_head_user,
            department=direction,
            role=DEPARTMENT_HEAD_GROUP,
        )
        NextcloudUserLink.objects.create(
            user=direction_head_user,
            nextcloud_user_id=f"ncstaff-{direction_head_user.pk}",
            nextcloud_username=f"ncstaff-{direction_head_user.pk}",
            nextcloud_email=direction_head_user.email,
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

        client.ensure_user_share.assert_has_calls(
            [
                call(
                    "cloud-admin",
                    "/Corporate Root/03 Проекты/2026/Проект 7001 Договорный проект",
                    f"ncstaff-{self.expert_user.pk}",
                    permissions=15,
                ),
                call(
                    "cloud-admin",
                    "/Corporate Root/03 Проекты/2026/Проект 7001 Договорный проект",
                    f"ncstaff-{direction_head_user.pk}",
                    permissions=15,
                ),
            ]
        )
        mocked_assignments.assert_called_once_with([self.performer.pk])
