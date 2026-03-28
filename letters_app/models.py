from django.conf import settings
from django.db import models


class LetterTemplate(models.Model):
    TEMPLATE_TYPE_CHOICES = [
        ("participation_confirmation", "Подтверждение участия эксперта"),
        ("direction_confirmation", "Подтверждение по направлению"),
        ("contract_sending", "Отправка проекта договора"),
        ("scan_sending", "Отправка скана сотрудника"),
        ("project_start", "Начало проекта"),
        ("request_approval", "Согласование запроса"),
    ]

    TEMPLATE_CARD_TITLES = {
        "participation_confirmation": "Шаблон запроса подтверждения участия в проекте",
        "direction_confirmation": "Шаблон запроса подтверждения по направлению",
        "contract_sending": "Шаблон отправки проекта договора",
        "scan_sending": "Шаблон отправки скана сотрудника",
        "project_start": "Шаблон уведомления о начале проекта",
        "request_approval": "Шаблон согласования запроса",
    }

    TEMPLATE_VARIABLES = {
        "participation_confirmation": [
            ("{recipient_name}", "Имя и отчество получателя"),
            ("{project_label}",
             "Обозначение проекта в формате «XXXXNYZZ Тип Название проекта», где: "
             "XXXX — четырехзначный номер проекта, "
             "N — порядковый номер соглашения, начиная с 0, "
             "Y — номер строки компании в составе группы для выбранной страны, начиная с 0, "
             "ZZ — двузначный код страны регистрации компании группы IMC Montan"),
            ("{project_manager}", "Руководитель проекта"),
            ("{project_deadline}", "Срок завершения проекта (дедлайн)"),
            ("{project_type}", "Тип проекта"),
            ("{services_list}", "Список разделов исполнителя с указанием активов"),
            ("{agreed_amount}", "Согласованная оплата услуг"),
            ("{currency_code}", "Валюта договора"),
            ("{duration_hours}", "Срок для принятия решения (часов)"),
            ("{deadline_at}", "Крайний срок ответа"),
        ],
        "direction_confirmation": [
            ("{recipient_name}", "Имя и отчество получателя"),
            ("{project_label}",
             "Обозначение проекта в формате «XXXXNYZZ Тип Название проекта», где: "
             "XXXX — четырехзначный номер проекта, "
             "N — порядковый номер соглашения, начиная с 0, "
             "Y — номер строки компании в составе группы для выбранной страны, начиная с 0, "
             "ZZ — двузначный код страны регистрации компании группы IMC Montan"),
            ("{project_manager}", "Руководитель проекта"),
            ("{project_deadline}", "Срок завершения проекта (дедлайн)"),
            ("{project_type}", "Тип проекта"),
            ("{services_list}", "Список разделов исполнителя с указанием активов"),
            ("{agreed_amount}", "Согласованная оплата услуг"),
            ("{currency_code}", "Валюта договора"),
            ("{duration_hours}", "Срок для принятия решения (часов)"),
            ("{deadline_at}", "Крайний срок ответа"),
        ],
        "contract_sending": [
            ("{recipient_name}", "Имя и отчество получателя"),
            ("{project_label}",
             "Обозначение проекта в формате «XXXXNYZZ Тип Название проекта»"),
            ("{executor}", "Исполнитель"),
            ("{services_list}", "Список разделов исполнителя с указанием активов"),
            ("{agreed_amount}", "Согласованная оплата услуг"),
            ("{currency_code}", "Валюта договора"),
            ("{prepayment_percent}", "Размер аванса в процентах"),
            ("{final_payment_percent}", "Размер окончательного платежа в процентах"),
            ("{document_link}",
             "Ссылка для скачивания документа (столбец «Ссылка» таблицы «Заключение договора»)"),
            ("{project_deadline}", "Срок завершения проекта (дедлайн)"),
            ("{duration_hours}", "Срок для принятия решения (часов)"),
            ("{deadline_at}", "Крайний срок ответа"),
        ],
        "scan_sending": [
            ("{recipient_name_lawer}", "Имя Отчество пользователя с ролью «Юрист»"),
            ("{project_label}",
             "Обозначение проекта в формате «XXXXNYZZ Тип Название проекта»"),
            ("{executor}", "Исполнитель"),
            ("{agreed_amount}", "Согласованная оплата услуг"),
            ("{prepayment_percent}", "Размер аванса в процентах"),
            ("{final_payment_percent}", "Размер окончательного платежа в процентах"),
            ("{project_deadline}", "Срок завершения проекта (дедлайн)"),
            ("{document_link_scan}", "Скан-копия договора, подписанная исполнителем"),
        ],
        "project_start": [
            ("{recipient_name}", "Имя получателя"),
            ("{project_label}", "Обозначение проекта"),
        ],
        "request_approval": [
            ("{recipient_name}", "Имя и отчество получателя"),
            ("{project_label}",
             "Обозначение проекта в формате «XXXXNYZZ Тип Название проекта»"),
            ("{services_list}", "Список разделов исполнителя с указанием активов"),
            ("{duration_hours}", "Срок для принятия решения (часов)"),
            ("{deadline_at}", "Крайний срок ответа"),
        ],
    }

    template_type = models.CharField(
        "Тип шаблона",
        max_length=64,
        choices=TEMPLATE_TYPE_CHOICES,
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="letter_templates",
        verbose_name="Автор",
        null=True,
        blank=True,
    )
    subject_template = models.CharField(
        "Заголовок письма (шаблон)",
        max_length=500,
        blank=True,
        default="",
    )
    body_html = models.TextField("Тело письма (HTML)")
    cc_recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="letter_cc_templates",
        verbose_name="Копия",
        blank=True,
    )
    is_default = models.BooleanField("Шаблон по умолчанию", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Шаблон письма"
        verbose_name_plural = "Шаблоны писем"
        constraints = [
            models.UniqueConstraint(
                fields=["template_type", "user"],
                name="unique_letter_template_per_user_type",
            ),
        ]

    def __str__(self):
        label = self.get_template_type_display()
        if self.user:
            return f"{label} — {self.user.get_full_name() or self.user.username}"
        return f"{label} (по умолчанию)"
