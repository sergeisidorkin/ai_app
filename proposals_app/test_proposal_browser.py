import os

import pytest
from django.conf import settings
from django.test import Client

from group_app.models import GroupMember
from proposals_app.models import ProposalRegistration


pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("RUN_BROWSER_SMOKE") != "1",
        reason="set RUN_BROWSER_SMOKE=1 to run the Playwright smoke contour",
    ),
    pytest.mark.django_db(transaction=True),
]


def _login_staff(django_user_model, username):
    user = django_user_model.objects.create_user(
        username=username,
        password="unused",
        is_staff=True,
    )
    django_client = Client()
    django_client.force_login(user)
    return django_client.cookies[settings.SESSION_COOKIE_NAME]


def _open_proposals_tab(page, live_server, session_cookie):
    page.context.add_cookies(
        [
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": session_cookie.value,
                "url": live_server.url,
            }
        ]
    )
    page.goto(live_server.url, wait_until="domcontentloaded")
    page.locator('a[href="#proposals"]').first.click()
    page.locator("#proposals-pane").wait_for()


def _wait_header_actions(page):
    page.wait_for_function(
        """() => {
          const el = document.getElementById('proposal-form-actions');
          return el && el.classList.contains('d-flex') && !el.classList.contains('d-none');
        }"""
    )


def test_proposal_create_header_cancel_resets_then_returns(live_server, django_user_model):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    GroupMember.objects.create(
        short_name="IMC Montan",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=1,
    )
    session_cookie = _login_staff(django_user_model, "proposal-browser-create")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        page = context.new_page()
        try:
            _open_proposals_tab(page, live_server, session_cookie)
            page.locator("#proposal-new-btn").wait_for()
            page.locator("#proposal-new-btn").click()
            page.locator("form#proposal-registration-form").wait_for()
            _wait_header_actions(page)
            cancel_btn = page.locator("#proposal-form-actions [data-proposal-form-cancel-btn]")
            page.wait_for_function(
                """() => {
                  const save = document.querySelector('#proposal-form-actions [data-proposal-form-save-btn]');
                  return save && save.disabled;
                }"""
            )
            number = page.locator("#proposal-number-input")
            original_number = number.input_value()
            number.fill("4321")
            page.wait_for_function(
                """() => {
                  const save = document.querySelector('#proposal-form-actions [data-proposal-form-save-btn]');
                  return save && !save.disabled;
                }"""
            )
            page.once("dialog", lambda dialog: dialog.accept())
            cancel_btn.click()
            page.wait_for_function(
                """(expected) => {
                  const form = document.querySelector('form#proposal-registration-form');
                  const input = document.querySelector('#proposal-number-input');
                  const save = document.querySelector('#proposal-form-actions [data-proposal-form-save-btn]');
                  const actions = document.getElementById('proposal-form-actions');
                  return !!(
                    form
                    && input
                    && input.value === expected
                    && save
                    && save.disabled
                    && actions
                    && actions.classList.contains('d-flex')
                  );
                }""",
                arg=original_number,
            )
            assert page.locator("#proposal-number-input").input_value() == original_number
            cancel_btn.click()
            page.locator(
                "#proposal-form-actions [data-proposal-form-cancel-btn] .spinner-border"
            ).wait_for()
            page.wait_for_function(
                """() => {
                  const actions = document.getElementById('proposal-form-actions');
                  const skeleton = document.querySelector('#proposals-pane .proposal-table-skeleton');
                  const registry = document.getElementById('proposal-new-btn');
                  return !!(
                    actions
                    && actions.classList.contains('d-none')
                    && (skeleton || registry)
                  );
                }"""
            )
            page.locator("#proposal-new-btn").wait_for()
            assert page.locator("form#proposal-registration-form").count() == 0
            page.wait_for_function(
                """() => {
                  const actions = document.getElementById('proposal-form-actions');
                  return actions && actions.classList.contains('d-none');
                }"""
            )
            assert "d-none" in (page.locator("#proposal-form-actions").get_attribute("class") or "")
        finally:
            context.close()
            browser.close()


def test_proposal_edit_header_cancel_resets_then_returns(live_server, django_user_model):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    group_member = GroupMember.objects.create(
        short_name="IMC Montan",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=1,
    )
    proposal = ProposalRegistration.objects.create(
        number=4503,
        sub_number=0,
        group_member=group_member,
        name="Browser TKP",
        year=2026,
    )
    session_cookie = _login_staff(django_user_model, "proposal-browser-edit")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        page = context.new_page()
        try:
            _open_proposals_tab(page, live_server, session_cookie)
            page.locator(".proposal-quick-edit").first.wait_for()
            page.locator(".proposal-quick-edit").first.click()
            page.locator("form#proposal-registration-form").wait_for()
            _wait_header_actions(page)
            heading = page.locator("#proposals-section-heading")
            heading.wait_for()
            assert proposal.short_uid in heading.inner_text()
            cancel_btn = page.locator("#proposal-form-actions [data-proposal-form-cancel-btn]")
            page.wait_for_function(
                """() => {
                  const save = document.querySelector('#proposal-form-actions [data-proposal-form-save-btn]');
                  return save && save.disabled;
                }"""
            )
            number = page.locator("#proposal-number-input")
            assert number.input_value() == "4503"
            number.fill("8888")
            page.wait_for_function(
                """() => {
                  const save = document.querySelector('#proposal-form-actions [data-proposal-form-save-btn]');
                  return save && !save.disabled;
                }"""
            )
            page.once("dialog", lambda dialog: dialog.accept())
            cancel_btn.click()
            page.wait_for_function(
                """() => {
                  const input = document.querySelector('#proposal-number-input');
                  const save = document.querySelector('#proposal-form-actions [data-proposal-form-save-btn]');
                  return input && input.value === '4503' && save && save.disabled;
                }"""
            )
            cancel_btn.click()
            page.locator(
                "#proposal-form-actions [data-proposal-form-cancel-btn] .spinner-border"
            ).wait_for()
            page.wait_for_function(
                """() => {
                  const actions = document.getElementById('proposal-form-actions');
                  const skeleton = document.querySelector('#proposals-pane .proposal-table-skeleton');
                  const registry = document.getElementById('proposal-new-btn');
                  return !!(
                    actions
                    && actions.classList.contains('d-none')
                    && (skeleton || registry)
                  );
                }"""
            )
            page.locator("#proposal-new-btn").wait_for()
            assert page.locator("form#proposal-registration-form").count() == 0
        finally:
            context.close()
            browser.close()


def test_dispatch_and_template_section_toggles_persist_in_local_storage(live_server, django_user_model):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    GroupMember.objects.create(
        short_name="IMC Montan",
        country_name="Россия",
        country_code="643",
        country_alpha2="RU",
        position=1,
    )
    session_cookie = _login_staff(django_user_model, "proposal-browser-section-toggle")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        page = context.new_page()
        try:
            _open_proposals_tab(page, live_server, session_cookie)
            page.locator("#proposal-dispatch-section-toggle").wait_for()
            page.locator("#proposal-template-section-toggle").wait_for()

            dispatch_body = page.locator("#proposal-dispatch-section-body")
            template_body = page.locator("#proposal-template-section-body")
            assert "d-none" in (dispatch_body.get_attribute("class") or "")
            assert "d-none" in (template_body.get_attribute("class") or "")

            page.locator("#proposal-dispatch-section-toggle").click()
            page.locator("#proposal-template-section-toggle").click()
            page.wait_for_function(
                """() => {
                  const dispatch = document.getElementById('proposal-dispatch-section-body');
                  const template = document.getElementById('proposal-template-section-body');
                  return dispatch && template
                    && !dispatch.classList.contains('d-none')
                    && !template.classList.contains('d-none');
                }"""
            )
            stored = page.evaluate(
                """() => {
                  const keys = Object.keys(localStorage);
                  const dispatchKey = keys.find((key) => key.includes('dispatch-section-collapsed'));
                  const templateKey = keys.find((key) => key.includes('template-section-collapsed'));
                  return {
                    dispatch: dispatchKey ? localStorage.getItem(dispatchKey) : null,
                    template: templateKey ? localStorage.getItem(templateKey) : null,
                  };
                }"""
            )
            assert stored["dispatch"] == "false"
            assert stored["template"] == "false"

            page.reload(wait_until="domcontentloaded")
            page.locator('a[href="#proposals"]').first.click()
            page.locator("#proposal-dispatch-section-toggle").wait_for()
            page.wait_for_function(
                """() => {
                  const dispatch = document.getElementById('proposal-dispatch-section-body');
                  const template = document.getElementById('proposal-template-section-body');
                  const dispatchToggle = document.getElementById('proposal-dispatch-section-toggle');
                  const templateToggle = document.getElementById('proposal-template-section-toggle');
                  return dispatch && template && dispatchToggle && templateToggle
                    && !dispatch.classList.contains('d-none')
                    && !template.classList.contains('d-none')
                    && dispatchToggle.getAttribute('aria-expanded') === 'true'
                    && templateToggle.getAttribute('aria-expanded') === 'true';
                }"""
            )
        finally:
            context.close()
            browser.close()
