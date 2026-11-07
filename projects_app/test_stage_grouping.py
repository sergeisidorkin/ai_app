import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from checklists_app.models import ProjectWorkspace
from group_app.models import GroupMember
from policy_app.models import ADMIN_GROUP, DIRECTOR_GROUP, DIRECTION_DIRECTOR_GROUP, Product
from users_app.models import Employee

from projects_app.models import LegalEntity, ProjectRegistration, WorkVolume


class StageGroupingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="stage-grouping-director",
            password="secret",
            is_staff=True,
        )
        Employee.objects.create(user=self.user, role=DIRECTOR_GROUP)
        self.client.force_login(self.user)
        self.group_member = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
            position=0,
        )
        self.other_group = GroupMember.objects.create(
            short_name="IMC KZ",
            country_name="Казахстан",
            country_code="398",
            country_alpha2="KZ",
            position=1,
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )

    def _single_project(self, number, name, position, **stage_extra):
        parent = ProjectRegistration.objects.create(
            number=number,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            name=name,
            status="Не начат",
            year=2026,
            position=position,
            project_manager="Иванов Иван",
        )
        stage_values = {
            "number": number,
            "group_member": self.group_member,
            "agreement_type": ProjectRegistration.AgreementType.MAIN,
            "type": self.product,
            "name": name,
            "status": "Не начат",
            "year": 2026,
            "stage_project": parent,
            "position": position + 1,
            "deadline": date(2026, 6, 1),
            "project_manager": "Иванов Иван",
        }
        stage_values.update(stage_extra)
        stage = ProjectRegistration.objects.create(**stage_values)
        parent.refresh_from_db()
        stage.refresh_from_db()
        return parent, stage

    def _stages(self, number, count, name="Сводный"):
        parent = ProjectRegistration.objects.create(
            number=number,
            group_member=self.group_member,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            name=name,
            status="Не начат",
            year=2026,
            position=1,
            summary_deferred=True,
        )
        stages = []
        for offset in range(count):
            stages.append(
                ProjectRegistration.objects.create(
                    number=number,
                    group_member=self.group_member,
                    agreement_type=ProjectRegistration.AgreementType.MAIN,
                    type=self.product,
                    name=f"{name} {offset + 1}",
                    status="Не начат",
                    year=2026,
                    stage_project=parent,
                    position=offset + 2,
                    deadline=date(2026, 7, offset + 1),
                )
            )
        parent.refresh_from_db()
        for stage in stages:
            stage.refresh_from_db()
        return parent, stages

    def test_merge_asks_for_confirmation_and_then_joins_stages(self):
        first_parent, first = self._single_project(8101, "Общий", 1)
        second_parent, second = self._single_project(
            8101,
            "Чужой",
            10,
            project_manager="Петров Пётр",
            deadline=date(2026, 8, 15),
        )
        first_uid = first.short_uid
        second_uid = second.short_uid
        parent_ids = {first_parent.pk, second_parent.pk}

        preview = self.client.post(
            reverse("registration_stages_merge"),
            {"stage_ids": [first.pk, second.pk]},
        )

        self.assertEqual(preview.status_code, 200)
        payload = preview.json()
        self.assertTrue(payload["needs_confirm"])
        self.assertTrue(any("8101" in line for line in payload["warnings"]))
        self.assertTrue(any("руководитель проекта" in line for line in payload["warnings"]))
        self.assertEqual(
            set(ProjectRegistration.objects.filter(stage_project__isnull=True).values_list("pk", flat=True)),
            parent_ids,
        )

        saved = self.client.post(
            reverse("registration_stages_merge"),
            {"stage_ids": [first.pk, second.pk], "confirm": "1"},
        )

        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["ok"])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.stage_project_id, second.stage_project_id)
        self.assertEqual(first.stage_project_id, first_parent.pk)
        self.assertFalse(ProjectRegistration.objects.filter(pk=second_parent.pk).exists())
        self.assertEqual(second.name, "Общий")
        self.assertEqual(second.project_manager, "Иванов Иван")
        self.assertEqual(second.deadline, date(2026, 8, 15))
        self.assertNotEqual(first.short_uid, first_uid)
        self.assertNotEqual(second.short_uid, second_uid)
        self.assertNotEqual(first.short_uid, second.short_uid)
        self.assertEqual(ProjectRegistration.objects.filter(stage_project_id=first_parent.pk).count(), 2)

    def test_merge_rejects_another_number_started_stage_and_workspace(self):
        _, first = self._single_project(8102, "Первый", 1)
        _, other_number = self._single_project(8103, "Другой номер", 10)
        blocked_number = self.client.post(
            reverse("registration_stages_merge"),
            {"stage_ids": [first.pk, other_number.pk]},
        )
        self.assertEqual(blocked_number.status_code, 400)
        self.assertIn("номера", blocked_number.json()["message"])

        _, started = self._single_project(8102, "В работе", 20, status="В работе")
        blocked_status = self.client.post(
            reverse("registration_stages_merge"),
            {"stage_ids": [first.pk, started.pk]},
        )
        self.assertEqual(blocked_status.status_code, 400)
        self.assertIn("Не начат", blocked_status.json()["message"])

        _, parked = self._single_project(8102, "С папкой", 30)
        ProjectWorkspace.objects.create(project=parked, disk_path="/projects/parked")
        blocked_workspace = self.client.post(
            reverse("registration_stages_merge"),
            {"stage_ids": [first.pk, parked.pk]},
        )
        self.assertEqual(blocked_workspace.status_code, 400)
        self.assertIn("рабочее пространство", blocked_workspace.json()["message"])

    def test_merge_rejects_a_different_group_and_an_existing_project(self):
        _, first = self._single_project(8104, "Россия", 1)
        foreign_parent = ProjectRegistration.objects.create(
            number=8104,
            group_member=self.other_group,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            name="Казахстан",
            status="Не начат",
            year=2026,
            position=10,
        )
        foreign = ProjectRegistration.objects.create(
            number=8104,
            group_member=self.other_group,
            agreement_type=ProjectRegistration.AgreementType.MAIN,
            type=self.product,
            name="Казахстан",
            status="Не начат",
            year=2026,
            stage_project=foreign_parent,
            position=11,
        )
        blocked_group = self.client.post(
            reverse("registration_stages_merge"),
            {"stage_ids": [first.pk, foreign.pk]},
        )
        self.assertEqual(blocked_group.status_code, 400)
        self.assertIn("группы", blocked_group.json()["message"])

        parent, stages = self._stages(8105, 2)
        blocked_same = self.client.post(
            reverse("registration_stages_merge"),
            {"stage_ids": [stage.pk for stage in stages]},
        )
        self.assertEqual(blocked_same.status_code, 400)
        self.assertIn("один проект", blocked_same.json()["message"])
        self.assertTrue(ProjectRegistration.objects.filter(pk=parent.pk).exists())

    def test_merge_rejects_more_than_nine_stages(self):
        _, stages = self._stages(8106, 9, name="Полный")
        _, extra = self._single_project(8106, "Десятый", 30)
        response = self.client.post(
            reverse("registration_stages_merge"),
            {"stage_ids": [stages[0].pk, extra.pk]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("девяти", response.json()["message"])

    def test_split_turns_summary_into_separate_projects_and_breaks_scope(self):
        parent, stages = self._stages(8107, 2)
        original_uids = [stage.short_uid for stage in stages]
        scope_key = uuid.uuid4()
        legal_key = uuid.uuid4()
        volumes = []
        for stage in stages:
            volumes.append(
                WorkVolume.objects.create(
                    project=stage,
                    asset_name="Актив",
                    name="Работа",
                    position=1,
                )
            )
        WorkVolume.objects.filter(pk__in=[volume.pk for volume in volumes]).update(scope_key=scope_key)
        LegalEntity.objects.filter(work_item__in=volumes).update(scope_key=legal_key)

        preview = self.client.post(
            reverse("registration_stages_split"),
            {"project_id": parent.pk},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["needs_confirm"])
        self.assertTrue(any("отдельным проектом" in line for line in preview.json()["warnings"]))
        self.assertTrue(any("Отложен" in line for line in preview.json()["warnings"]))
        self.assertTrue(ProjectRegistration.objects.filter(pk=parent.pk).exists())

        saved = self.client.post(
            reverse("registration_stages_split"),
            {"project_id": parent.pk, "confirm": "1"},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["ok"])
        self.assertFalse(ProjectRegistration.objects.filter(pk=parent.pk).exists())
        refreshed = list(ProjectRegistration.objects.filter(pk__in=[stage.pk for stage in stages]).order_by("position", "id"))
        self.assertEqual(len(refreshed), 2)
        self.assertNotEqual(refreshed[0].stage_project_id, refreshed[1].stage_project_id)
        self.assertTrue(all(stage.stage_project_id for stage in refreshed))
        self.assertEqual(
            [stage.stage_project.summary_deferred for stage in refreshed],
            [True, True],
        )
        self.assertNotEqual(refreshed[0].short_uid, original_uids[0])
        self.assertNotEqual(refreshed[1].short_uid, original_uids[1])
        work_keys = set(WorkVolume.objects.filter(project_id__in=[stage.pk for stage in refreshed]).values_list("scope_key", flat=True))
        legal_keys = set(LegalEntity.objects.filter(project_id__in=[stage.pk for stage in refreshed]).values_list("scope_key", flat=True))
        self.assertEqual(len(work_keys), 2)
        self.assertEqual(len(legal_keys), 2)
        self.assertNotIn(scope_key, work_keys)
        self.assertNotIn(legal_key, legal_keys)

    def test_split_without_a_project_is_blocked(self):
        response = self.client.post(reverse("registration_stages_split"), {"project_id": ""})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["blocked"])


class StageGroupingAccessTests(TestCase):
    def setUp(self):
        self.group_member = GroupMember.objects.create(
            short_name="IMC",
            country_name="Россия",
            country_code="643",
            country_alpha2="RU",
        )
        self.product = Product.objects.create(
            short_name="DD",
            name_en="Due Diligence",
            name_ru="ДД",
            consulting_type="Горный",
            service_category="Аудит",
            service_subtype="Аудит соответствия стандартам",
        )

    def _user(self, username, role=None, group_name=None):
        user = get_user_model().objects.create_user(username=username, password="secret", is_staff=True)
        if role:
            Employee.objects.create(user=user, role=role)
        if group_name:
            group, _created = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)
        return user

    def _stage(self):
        parent = ProjectRegistration.objects.create(
            number=8110,
            group_member=self.group_member,
            name="Доступ",
            status="Не начат",
            year=2026,
            position=1,
        )
        return ProjectRegistration.objects.create(
            number=8110,
            group_member=self.group_member,
            type=self.product,
            name="Доступ этап",
            status="Не начат",
            year=2026,
            stage_project=parent,
            position=2,
        )

    def test_buttons_are_visible_only_to_director_and_administrator(self):
        director = self._user("grouping-director", role=DIRECTOR_GROUP)
        self.client.force_login(director)
        page = self.client.get(reverse("projects_partial"))
        self.assertContains(page, 'id="registration-stages-merge-btn"', html=False)
        self.assertContains(page, 'id="registration-stages-split-btn"', html=False)

        admin = self._user("grouping-admin", group_name=ADMIN_GROUP)
        self.client.force_login(admin)
        page = self.client.get(reverse("projects_partial"))
        self.assertContains(page, 'id="registration-stages-merge-btn"', html=False)

        direction = self._user("grouping-direction", role=DIRECTION_DIRECTOR_GROUP)
        self.client.force_login(direction)
        page = self.client.get(reverse("projects_partial"))
        self.assertNotContains(page, 'id="registration-stages-merge-btn"', html=False)
        self.assertNotContains(page, 'id="registration-stages-split-btn"', html=False)

        staff = self._user("grouping-staff")
        self.client.force_login(staff)
        page = self.client.get(reverse("projects_partial"))
        self.assertNotContains(page, 'id="registration-stages-merge-btn"', html=False)

    def test_post_is_forbidden_for_other_roles(self):
        stage = self._stage()
        staff = self._user("grouping-staff-post")
        self.client.force_login(staff)
        response = self.client.post(
            reverse("registration_stages_merge"),
            {"stage_ids": [stage.pk, stage.pk]},
        )
        self.assertEqual(response.status_code, 403)

        direction = self._user("grouping-direction-post", role=DIRECTION_DIRECTOR_GROUP)
        self.client.force_login(direction)
        response = self.client.post(
            reverse("registration_stages_split"),
            {"project_id": stage.stage_project_id},
        )
        self.assertEqual(response.status_code, 403)
