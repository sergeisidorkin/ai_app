import os
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import Client

from experts_app.models import ExpertSpecialty
from policy_app.models import (
    ConsultingDirection,
    ConsultingDirectionType,
    ConsultingServiceSubtype,
    ConsultingServiceType,
    Grade,
    Product,
    ServiceGoalReport,
    TypicalSection,
    TypicalSectionSpecialty,
    SectionStructure,
    ReportStructure,
    Tariff,
    TypicalServiceComposition,
    TypicalServiceTerm,
    ensure_system_dsc_section,
)


pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("RUN_BROWSER_SMOKE") != "1",
        reason="set RUN_BROWSER_SMOKE=1 to run the Playwright smoke contour",
    ),
    pytest.mark.django_db(transaction=True),
]


def test_policy_tab_is_lazy_and_product_modal_opens(live_server, django_user_model):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    user = django_user_model.objects.create_user(
        username="policy-browser-staff",
        password="unused",
        is_staff=True,
    )
    direction = ConsultingDirection.objects.create(position=1)
    consulting_type = ConsultingDirectionType.objects.create(
        direction=direction,
        name="Browser consulting",
        position=1,
    )
    service_type = ConsultingServiceType.objects.create(
        direction=direction,
        consulting_type=consulting_type,
        name="Browser service",
        code="BROWSER",
        position=1,
    )
    service_subtype = ConsultingServiceSubtype.objects.create(
        direction=direction,
        service_type=service_type,
        name="Browser subtype",
        position=1,
    )
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        policy_requests = []
        page.on(
            "request",
            lambda request: policy_requests.append(request.url)
            if "/policy/policy/" in request.url
            else None,
        )

        page.goto(live_server.url, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        assert not policy_requests

        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        products_title = page.locator('#policy-products-section h5.table-section-title')
        products_title.wait_for()
        assert "Типовые продукты" in products_title.inner_text()
        assert products_title.locator("i.bi-table").count() == 1
        assert page.locator(
            "#policy-pane .policy-group-card-title", has_text="Спецификации продуктов"
        ).count() == 1
        assert page.locator(
            "#policy-pane .policy-group-card-title", has_text="Общие настройки продуктов"
        ).count() == 1
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator("#policy-pane #policy-products-section").scroll_into_view_if_needed()
        assert policy_requests

        page.locator(
            '#policy-products-section [hx-get*="/policy/policy/product/create/"]'
        ).first.click()
        page.locator("#policy-modal form#product-form").wait_for()

        page.locator("#id_short_name").fill("BROWSER_PRODUCT")
        page.locator("#id_name_en").fill("Browser product")
        page.locator("#id_display_name").fill("Browser product")
        page.locator("#id_name_ru").fill("Браузерный продукт")
        page.locator("#id_consulting_type").select_option(str(consulting_type.pk))
        page.locator("#id_service_category").select_option(str(service_type.pk))
        page.locator("#id_service_subtype").select_option(str(service_subtype.pk))
        with page.expect_response(
            lambda response: "/policy/policy/product/create/" in response.url
            and response.request.method == "POST"
        ) as save_response:
            page.locator("#policy-modal form#product-form button[type=submit]").click()
        assert save_response.value.status == 200
        page.locator("#policy-modal").wait_for(state="hidden")
        page.locator("#policy-products-section").scroll_into_view_if_needed()
        page.locator("#policy-products-section").get_by_text(
            "BROWSER_PRODUCT", exact=True
        ).wait_for()

        context.close()
        browser.close()


def test_expert_specialties_table_lives_in_products_not_experts(
    live_server, django_user_model
):
    user = django_user_model.objects.create_user(
        username="policy-browser-expert-specialties",
        password="unused",
        is_staff=True,
    )
    ExpertSpecialty.objects.create(
        specialty="Browser geologist",
        specialty_en="Browser geologist",
        position=1,
    )
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")

        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator(
            '#policy-pane [data-policy-table-key="expert-specialties"]'
        ).scroll_into_view_if_needed()
        page.locator("#policy-expert-specialties-section table#esp-table").wait_for()
        assert page.locator("#policy-expert-specialties-section").get_by_text(
            "Специальности исполнителей"
        ).count() == 1
        assert page.locator(
            "#policy-expert-specialties-section td[data-col='specialty']"
        ).get_by_text("Browser geologist", exact=True).count() == 1
        pagination = page.locator(
            "#policy-expert-specialties-section .policy-table-pagination"
        )
        pagination.wait_for()
        assert pagination.get_by_text("Показано строк").count() == 1
        assert pagination.locator(".policy-table-page-size-select").count() == 1
        assert pagination.get_by_label("Страницы таблицы").count() == 1
        keys = page.locator("#policy-pane [data-policy-table-key]").evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('data-policy-table-key'))"
        )
        assert keys.index("consulting-directions") < keys.index("expertise-directions")
        assert keys.index("expert-specialties") < keys.index("specialty-tariffs")

        english_col = page.locator('#esp-table thead [data-col="specialty-en"]')
        assert english_col.is_visible()
        page.locator("#esp-colpicker-btn").click()
        page.locator("#esp-colpicker-menu.show").wait_for()
        page.locator("label[for='esp-col-specialty-en']").click()
        page.wait_for_function(
            """() => {
              const cell = document.querySelector('#esp-table thead [data-col="specialty-en"]');
              return cell && getComputedStyle(cell).display === 'none';
            }"""
        )
        assert page.locator("#esp-colpicker-btn").inner_text().strip() == "6 из 7"

        page.locator(
            '#policy-expert-specialties-section [hx-get*="/experts/create/"]'
        ).first.click()
        page.locator("#policy-modal form[data-policy-modal-size='xl']").wait_for()
        assert page.locator("#policy-modal .modal-dialog.modal-xl").count() == 1
        page.locator("#policy-modal .btn-close").click()
        page.locator("#policy-modal").wait_for(state="hidden")

        page.locator('a[href="#experts"]').first.click()
        experts_tab = page.locator("#experts")
        experts_tab.get_by_text("База физлиц-исполнителей").wait_for()
        assert experts_tab.locator("#esp-table").count() == 0
        assert experts_tab.get_by_text("Специальности исполнителей").count() == 0

        context.close()
        browser.close()


def test_policy_row_move_updates_dom_before_server(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-reorder",
        password="unused",
        is_staff=True,
    )
    Product.objects.create(
        short_name="BR-P1",
        name_en="First browser product",
        name_ru="Первый браузерный продукт",
        position=1,
    )
    Product.objects.create(
        short_name="BR-P2",
        name_en="Second browser product",
        name_ru="Второй браузерный продукт",
        position=2,
    )
    Grade.objects.create(
        grade_en="BR-G1",
        grade_ru="Грейд 1",
        created_by=user,
        position=1,
    )
    Grade.objects.create(
        grade_en="BR-G2",
        grade_ru="Грейд 2",
        created_by=user,
        position=2,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane [data-policy-table-key='products']").scroll_into_view_if_needed()
        page.locator("#policy-pane #policy-products-section table").wait_for()

        def product_names():
            return page.locator(
                "#policy-products-section tbody tr[data-move-up-url] td:nth-child(2)"
            ).all_inner_texts()

        names_before = product_names()
        assert "BR-P1" in names_before and "BR-P2" in names_before
        p2_index = names_before.index("BR-P2")
        if p2_index > 0:
            page.locator(
                '#policy-products-section tbody tr[data-move-up-url]',
                has_text="BR-P2",
            ).locator('input[name="product-select"]').check()
            page.locator("#products-actions-up").click()
            names_after = product_names()
            assert names_after.index("BR-P2") == p2_index - 1
            assert names_after[p2_index] == names_before[p2_index - 1]
        else:
            page.locator(
                '#policy-products-section tbody tr[data-move-up-url]',
                has_text="BR-P1",
            ).locator('input[name="product-select"]').check()
            page.locator("#products-actions-down").click()
            names_after = product_names()
            assert names_after.index("BR-P1") == names_before.index("BR-P1") + 1

        page.locator("#policy-grades-section").scroll_into_view_if_needed()
        page.locator("#policy-pane #policy-grades-section table").wait_for(timeout=15000)
        grade_rows = page.locator("#policy-grades-section tbody tr[data-move-up-url]")
        grade_rows.nth(1).locator('input[name="grade-select"]').check()
        page.locator('#grades-actions [data-panel-action="up"]').click()
        assert grade_rows.nth(0).locator("td").nth(1).inner_text() == "BR-G2"
        assert grade_rows.nth(1).locator("td").nth(1).inner_text() == "BR-G1"

        context.close()
        browser.close()


def test_product_edit_modal_clears_checkbox_on_close(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-product-modal",
        password="unused",
        is_staff=True,
    )
    Product.objects.create(
        short_name="BR-MODAL",
        name_en="Modal browser product",
        name_ru="Браузерный продукт модалки",
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator("#policy-pane #policy-products-section").scroll_into_view_if_needed()

        row = page.locator(
            '#policy-products-section tbody tr[data-edit-url]',
            has_text="BR-MODAL",
        )
        checkbox = row.locator('input[name="product-select"]')
        checkbox.check()
        page.locator("#products-actions-edit").click()
        page.locator("#policy-modal form#product-form").wait_for()

        page.locator("#policy-modal .modal-footer button[data-bs-dismiss='modal']").click()
        page.locator("#policy-modal").wait_for(state="hidden")
        assert checkbox.is_checked() is False

        checkbox.check()
        page.locator("#products-actions-edit").click()
        page.locator("#policy-modal form#product-form").wait_for()
        page.locator("#policy-modal .btn-close").click()
        page.locator("#policy-modal").wait_for(state="hidden")
        assert checkbox.is_checked() is False

        checkbox.check()
        page.locator("#products-actions-edit").click()
        page.locator("#policy-modal form#product-form").wait_for()
        with page.expect_response(
            lambda response: "/policy/policy/product/" in response.url
            and "/edit/" in response.url
            and response.request.method == "POST"
        ):
            page.locator("#policy-modal form#product-form button[type=submit]").click()
        page.locator("#policy-modal").wait_for(state="hidden")
        page.locator("#policy-products-section").get_by_text("BR-MODAL", exact=True).wait_for()
        refreshed = page.locator(
            '#policy-products-section tbody tr[data-edit-url]',
            has_text="BR-MODAL",
        ).locator('input[name="product-select"]')
        assert refreshed.is_checked() is False

        context.close()
        browser.close()


def test_policy_products_footer_stays_visible_while_scrolling(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-sticky-footer",
        password="unused",
        is_staff=True,
    )
    for index in range(1, 26):
        Product.objects.create(
            short_name=f"BR-STICKY-{index:02d}",
            name_en=f"Sticky browser product {index}",
            name_ru=f"Липкий браузерный продукт {index}",
            position=index,
        )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context(viewport={"width": 1280, "height": 520})
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator("#policy-pane #policy-products-section").scroll_into_view_if_needed()

        footer = page.locator("#policy-products-section .policy-table-footer")
        assert footer.count() == 1
        assert page.locator("#policy-products-section .policy-table-editor").count() == 1
        assert page.evaluate(
            "el => getComputedStyle(el).position",
            footer.element_handle(),
        ) == "sticky"

        page.locator(
            '#policy-products-section tbody tr[data-edit-url] input[name="product-select"]'
        ).first.check()
        page.locator("#products-actions").wait_for(state="visible")
        page.locator("#policy-products-section .policy-sticky-actions-marker").wait_for()

        page.evaluate(
            """() => {
              const editor = document.querySelector('#policy-products-section .policy-table-editor');
              window.scrollTo(0, window.scrollY + editor.getBoundingClientRect().top + 80);
            }"""
        )
        page.wait_for_function(
            """() => {
              const footer = document.querySelector('#policy-products-section .policy-table-footer');
              return !!(footer && footer.classList.contains('is-stuck'));
            }"""
        )

        metrics = page.evaluate(
            """() => {
              const footer = document.querySelector('#policy-products-section .policy-table-footer');
              const actions = document.querySelector('#products-actions');
              const footerRect = footer.getBoundingClientRect();
              const actionsRect = actions.getBoundingClientRect();
              return {
                isStuck: footer.classList.contains('is-stuck'),
                footerBottom: footerRect.bottom,
                footerTop: footerRect.top,
                viewportHeight: window.innerHeight,
                actionsVisible: actionsRect.bottom > 0 && actionsRect.top < window.innerHeight,
              };
            }"""
        )
        assert metrics["isStuck"] is True
        assert metrics["actionsVisible"] is True
        assert abs(metrics["footerBottom"] - metrics["viewportHeight"]) <= 2
        assert 0 <= metrics["footerTop"] < metrics["viewportHeight"]

        context.close()
        browser.close()


def test_product_workspace_opens_from_products_table_pencil(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-workspace",
        password="unused",
        is_staff=True,
    )
    Product.objects.create(
        short_name="BR-WS",
        name_en="Workspace browser product",
        display_name="Workspace browser display",
        name_ru="Браузерный продукт workspace",
        position=1,
    )
    Product.objects.create(
        short_name="BR-OTHER",
        name_en="Other browser product",
        display_name="Other browser display",
        name_ru="Другой браузерный продукт",
        position=2,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator("#policy-pane #policy-products-section").scroll_into_view_if_needed()

        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-WS",
        ).locator(".product-quick-edit").click()

        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.wait_for_function("() => window.scrollY <= 8")
        assert page.locator(
            "#policy-pane .policy-group-card-title", has_text="Спецификации продуктов"
        ).count() == 1
        assert page.locator(
            "#policy-pane .policy-group-card-title", has_text="Общие настройки продуктов"
        ).count() == 0
        heading = page.locator("#policy-section-heading")
        heading.get_by_text("Продукты", exact=True).wait_for()
        heading.get_by_text("BR-WS Workspace browser display", exact=True).wait_for()
        assert " / " in heading.inner_text()

        for dropdown_id in (
            "master-policy-consulting-filter-dropdown",
            "master-policy-category-filter-dropdown",
            "master-policy-subtype-filter-dropdown",
            "master-policy-product-filter-dropdown",
        ):
            assert "d-none" in (
                page.locator(f"#{dropdown_id}").get_attribute("class") or ""
            )

        assert page.locator("#policy-pane [data-policy-table-key='products']").count() == 1
        assert page.locator("#policy-pane [data-policy-table-key='tariffs']").count() == 1
        assert page.locator("#policy-pane [data-policy-table-key='expertise-directions']").count() == 0
        assert page.locator("#policy-pane [data-policy-table-key='grades']").count() == 0
        page.locator("#policy-products-section").get_by_text("BR-WS", exact=True).wait_for()
        assert page.locator("#policy-products-section").get_by_text("BR-OTHER", exact=True).count() == 0
        assert page.locator("#policy-pane .policy-table-pagination").count() == 0
        assert page.evaluate(
            """() => {
              const header = document.querySelector(
                '#policy-pane[data-policy-workspace="1"] #policy-products-section .table-section-header'
              );
              return header ? getComputedStyle(header).marginTop : '';
            }"""
        ) == "0px"

        page.locator("[data-policy-workspace-cancel-btn]").click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]:not([data-policy-workspace])').wait_for()
        assert page.locator("#policy-section-heading").inner_text().strip() == "Продукты"
        assert page.locator(
            "#policy-pane .policy-group-card-title", has_text="Общие настройки продуктов"
        ).count() == 1
        assert "d-none" not in (
            page.locator("#master-policy-product-filter-dropdown").get_attribute("class") or ""
        )

        context.close()
        browser.close()


def test_product_workspace_inline_edit_save_and_cancel(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-inline",
        password="unused",
        is_staff=True,
    )
    direction = ConsultingDirection.objects.create(position=1)
    consulting_type = ConsultingDirectionType.objects.create(
        direction=direction,
        name="Browser consulting",
        position=1,
    )
    service_type = ConsultingServiceType.objects.create(
        direction=direction,
        consulting_type=consulting_type,
        name="Browser service",
        code="BRS",
        position=1,
    )
    service_subtype = ConsultingServiceSubtype.objects.create(
        direction=direction,
        service_type=service_type,
        name="Browser subtype",
        position=1,
    )
    product = Product.objects.create(
        short_name="BR-IN",
        name_en="Inline browser product",
        display_name="Отображаемое имя типового продукта достаточно длинное для проверки ширины",
        name_ru="Браузерный inline продукт",
        consulting_type_ref=consulting_type,
        service_category_ref=service_type,
        service_subtype_ref=service_subtype,
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()

        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-IN",
        ).locator(".product-quick-edit").click()

        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator('#policy-products-section[data-policy-inline="1"] table').wait_for()
        actions = page.locator("#policy-workspace-actions")
        actions.wait_for()
        assert "d-none" not in (actions.get_attribute("class") or "")
        save_btn = page.locator("[data-policy-workspace-save-btn]")
        cancel_btn = page.locator("[data-policy-workspace-cancel-btn]")
        assert save_btn.is_disabled()
        assert cancel_btn.is_enabled()

        display_name = page.locator('#policy-products-section td[data-inline-field="display_name"]')
        width_before = display_name.evaluate("el => el.getBoundingClientRect().width")
        table_w_before = display_name.evaluate(
            "el => el.closest('table').getBoundingClientRect().width"
        )
        row_h_before = display_name.evaluate(
            "el => el.closest('tr').getBoundingClientRect().height"
        )
        display_name.dblclick()
        editor = page.locator(".inline-table-text-input")
        editor.wait_for()
        width_while_editing = display_name.evaluate("el => el.getBoundingClientRect().width")
        assert abs(width_while_editing - width_before) <= 2
        assert width_while_editing > 80
        halo = page.locator(".inline-table-text-wrap").evaluate(
            """el => {
              const cs = getComputedStyle(el);
              const wrap = el.getBoundingClientRect();
              const cell = el.parentElement.getBoundingClientRect();
              return {
                outline: cs.outline,
                boxShadow: cs.boxShadow,
                overflow: cs.overflow,
                padTop: parseFloat(cs.paddingTop),
                padLeft: parseFloat(cs.paddingLeft),
                top: wrap.top - cell.top,
                left: wrap.left - cell.left,
                right: cell.right - wrap.right,
                bottom: cell.bottom - wrap.bottom,
              };
            }"""
        )
        assert "2px" in halo["boxShadow"] and "inset" in halo["boxShadow"]
        assert "solid" in halo["outline"] and "2px" in halo["outline"]
        assert halo["overflow"] == "visible"
        assert halo["padTop"] >= 4
        assert halo["padLeft"] >= 4
        assert abs(halo["top"]) <= 1
        assert abs(halo["left"]) <= 1
        assert abs(halo["right"]) <= 1
        assert abs(halo["bottom"]) <= 1
        overflow = page.evaluate(
            """() => {
              const scroller = document.querySelector('#policy-products-section .table-responsive');
              const table = scroller.querySelector('table');
              const row = document.querySelector(
                '#policy-products-section td[data-inline-field="display_name"]'
              ).closest('tr');
              return {
                overflowY: scroller.scrollHeight - scroller.clientHeight,
                rowH: row.getBoundingClientRect().height,
                tableW: table.getBoundingClientRect().width,
              };
            }"""
        )
        assert overflow["overflowY"] <= 1
        assert abs(overflow["tableW"] - table_w_before) <= 2
        assert abs(overflow["rowH"] - row_h_before) <= 1
        editor.fill(("длинное отображаемое имя продукта для переноса строки " * 8).strip())
        grown = page.evaluate(
            """() => {
              const scroller = document.querySelector('#policy-products-section .table-responsive');
              const table = scroller.querySelector('table');
              const row = document.querySelector(
                '#policy-products-section td[data-inline-field="display_name"]'
              ).closest('tr');
              return {
                overflowY: scroller.scrollHeight - scroller.clientHeight,
                rowH: row.getBoundingClientRect().height,
                tableW: table.getBoundingClientRect().width,
              };
            }"""
        )
        assert grown["rowH"] > overflow["rowH"] + 8
        assert grown["overflowY"] <= 1
        assert abs(grown["tableW"] - overflow["tableW"]) <= 2
        editor.fill("Saved display")
        editor.press("Enter")
        page.wait_for_function(
            """() => {
              const cell = document.querySelector('#policy-products-section td[data-inline-field="display_name"]');
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              return cell && cell.classList.contains('inline-cell-dirty') && save && !save.disabled;
            }"""
        )

        page.once("dialog", lambda dialog: dialog.accept())
        cancel_btn.click()
        page.locator(
            '#policy-products-section td[data-inline-field="display_name"]',
            has_text="Отображаемое имя типового продукта достаточно длинное для проверки ширины",
        ).wait_for()
        assert save_btn.is_disabled()

        display_name = page.locator('#policy-products-section td[data-inline-field="display_name"]')
        display_name.dblclick()
        editor = page.locator(".inline-table-text-input")
        editor.wait_for()
        editor.fill("Saved display")
        editor.press("Enter")
        save_btn.click()
        page.locator("#policy-section-heading").get_by_text("BR-IN Saved display", exact=True).wait_for()
        page.wait_for_function(
            """() => {
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              return save && save.disabled;
            }"""
        )

        context.close()
        browser.close()

    product.refresh_from_db()
    assert product.display_name == "Saved display"


def test_product_workspace_service_goal_inline_edit_saves(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-goals-inline",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-GOAL",
        name_en="Goal browser product",
        display_name="Goal display",
        name_ru="Браузерный продукт целей",
        position=1,
    )
    goal = ServiceGoalReport.objects.create(
        product=product,
        service_goal=(
            "Оценка воздействия планируемой деятельности на окружающую среду "
            "и подготовка материалов общественных обсуждений"
        ),
        service_goal_genitive="Старой цели",
        report_title="Старый титул",
        product_name="Старое имя",
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-GOAL",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator(
            '#policy-service-goal-reports-section[data-policy-inline="1"] table'
        ).wait_for()

        hidden = page.evaluate(
            """() => {
              const checkbox = document.querySelector(
                '#policy-service-goal-reports-section .policy-workspace-checkbox-cell'
              );
              const product = document.querySelector(
                '#policy-service-goal-reports-section .policy-workspace-product-cell'
              );
              const display = function (el) {
                return el ? getComputedStyle(el).display : '';
              };
              return {
                checkbox: display(checkbox),
                product: display(product),
              };
            }"""
        )
        assert hidden["checkbox"] == "none"
        assert hidden["product"] == "none"

        cell = page.locator(
            '#policy-service-goal-reports-section td[data-inline-field="service_goal"]'
        )
        width_before = cell.evaluate("el => el.getBoundingClientRect().width")
        scroll_before = page.evaluate(
            """() => {
              const scroller = document.querySelector(
                '#policy-service-goal-reports-section .table-responsive'
              );
              const table = scroller.querySelector('table');
              const row = document.querySelector(
                '#policy-service-goal-reports-section td[data-inline-field="service_goal"]'
              ).closest('tr');
              return {
                overflowX: scroller.scrollWidth - scroller.clientWidth,
                tableW: table.getBoundingClientRect().width,
                rowH: row.getBoundingClientRect().height,
              };
            }"""
        )
        cell.dblclick()
        editor = page.locator(".inline-table-text-input")
        editor.wait_for()
        width_while_editing = cell.evaluate("el => el.getBoundingClientRect().width")
        wrap_width = page.locator(".inline-table-text-wrap").evaluate(
            "el => el.getBoundingClientRect().width"
        )
        assert abs(width_while_editing - width_before) <= 2
        assert abs(wrap_width - width_before) <= 2
        assert width_while_editing > 80
        overflow = page.evaluate(
            """() => {
              const scroller = document.querySelector(
                '#policy-service-goal-reports-section .table-responsive'
              );
              const table = scroller.querySelector('table');
              const row = document.querySelector(
                '#policy-service-goal-reports-section td[data-inline-field="service_goal"]'
              ).closest('tr');
              return {
                overflowX: scroller.scrollWidth - scroller.clientWidth,
                overflowY: scroller.scrollHeight - scroller.clientHeight,
                rowH: row.getBoundingClientRect().height,
                tableW: table.getBoundingClientRect().width,
              };
            }"""
        )
        assert overflow["overflowX"] <= scroll_before["overflowX"] + 1
        assert abs(overflow["tableW"] - scroll_before["tableW"]) <= 2
        assert overflow["overflowY"] <= 1
        assert abs(overflow["rowH"] - scroll_before["rowH"]) <= 1
        editor.fill(("цель услуги для переноса на новые строки таблицы " * 10).strip())
        grown = page.evaluate(
            """() => {
              const scroller = document.querySelector(
                '#policy-service-goal-reports-section .table-responsive'
              );
              const table = scroller.querySelector('table');
              const row = document.querySelector(
                '#policy-service-goal-reports-section td[data-inline-field="service_goal"]'
              ).closest('tr');
              return {
                overflowX: scroller.scrollWidth - scroller.clientWidth,
                overflowY: scroller.scrollHeight - scroller.clientHeight,
                rowH: row.getBoundingClientRect().height,
                tableW: table.getBoundingClientRect().width,
              };
            }"""
        )
        assert grown["rowH"] > overflow["rowH"] + 8
        assert grown["overflowX"] <= scroll_before["overflowX"] + 1
        assert grown["overflowY"] <= 1
        assert abs(grown["tableW"] - scroll_before["tableW"]) <= 2
        editor.fill("Новая цель браузера")
        editor.press("Enter")
        page.locator("[data-policy-workspace-save-btn]").click()
        page.wait_for_function(
            """() => {
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              const cell = document.querySelector(
                '#policy-service-goal-reports-section td[data-inline-field="service_goal"]'
              );
              return save && save.disabled && cell && cell.textContent.includes('Новая цель браузера');
            }"""
        )

        context.close()
        browser.close()

    goal.refresh_from_db()
    assert goal.service_goal == "Новая цель браузера"


def test_product_workspace_typical_section_inline_edit_saves(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-sections-inline",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-SEC",
        name_en="Section browser product",
        display_name="Section display",
        name_ru="Браузерный продукт разделов",
        position=1,
    )
    ensure_system_dsc_section(product)
    section = TypicalSection.objects.create(
        product=product,
        code="SEC-BR",
        short_name="sec-br",
        short_name_ru="разд-br",
        name_en="Browser section EN",
        name_ru="Браузерный раздел",
        accounting_type="Раздел",
        position=1,
    )
    mining = ExpertSpecialty.objects.create(specialty="Горное дело BR", position=1)
    geology = ExpertSpecialty.objects.create(specialty="Геология BR", position=2)
    TypicalSectionSpecialty.objects.create(section=section, specialty=mining, rank=1)
    TypicalSectionSpecialty.objects.create(section=section, specialty=geology, rank=2)

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-SEC",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator(
            '#policy-typical-sections-section[data-policy-inline="1"] table'
        ).wait_for()

        chrome = page.evaluate(
            """() => {
              const display = function (el) {
                return el ? getComputedStyle(el).display : '';
              };
              return {
                product: display(document.querySelector(
                  '#policy-typical-sections-section .policy-workspace-product-cell'
                )),
                csv: display(document.querySelector('#sections-csv-download-btn')),
                csvUpload: display(document.querySelector('#sections-csv-upload-btn')),
                add: display(document.querySelector(
                  '#policy-typical-sections-section button[hx-get*="section/create"]'
                )),
                checkbox: display(document.querySelector(
                  '#policy-typical-sections-section input[name="section-select"]'
                )),
              };
            }"""
        )
        assert chrome["product"] == "none"
        assert chrome["csv"] == "none"
        assert chrome["csvUpload"] == "none"
        assert chrome["add"] != "none"
        assert chrome["checkbox"] != "none"

        dsc_color = page.evaluate(
            """() => {
              const row = document.querySelector('#policy-typical-sections-section tr.typical-section-system-row');
              if (!row) return null;
              const code = row.querySelector('.typical-section-dsc-code');
              const name = row.querySelectorAll('td')[6];
              return {
                code: code ? getComputedStyle(code).color : '',
                name: name ? getComputedStyle(name).color : '',
              };
            }"""
        )
        assert dsc_color
        assert dsc_color["code"] == dsc_color["name"]
        assert dsc_color["name"] == "rgb(173, 181, 189)"

        spec_cell = page.locator(
            '#policy-typical-sections-section td[data-inline-field="specialty_ids"]'
        )
        spec_rows = spec_cell.locator(".inline-specialty-row")
        assert spec_rows.count() == 2
        assert spec_rows.nth(0).locator(".inline-specialty-label").inner_text() == "Горное дело BR"
        assert spec_rows.nth(1).locator(".inline-specialty-label").inner_text() == "Геология BR"
        dash = spec_rows.nth(0).evaluate("el => getComputedStyle(el).backgroundImage")
        assert "repeating-linear-gradient" in dash
        width_before_hover = spec_cell.evaluate("el => el.getBoundingClientRect().width")
        actions_display = spec_rows.nth(0).locator(".inline-specialty-actions").evaluate(
            "el => getComputedStyle(el).display"
        )
        assert actions_display in ("inline-flex", "flex")
        spec_rows.nth(0).hover()
        assert spec_rows.nth(0).locator('[data-specialty-action="add"]').is_visible()
        assert spec_rows.nth(0).locator('[data-specialty-action="remove"]').is_visible()
        width_after_hover = spec_cell.evaluate("el => el.getBoundingClientRect().width")
        assert abs(width_after_hover - width_before_hover) <= 1
        icon_layout = spec_rows.nth(0).evaluate(
            """(el) => {
              const chevron = el.querySelector('.inline-specialty-chevron');
              const add = el.querySelector('.inline-specialty-add');
              const actions = el.querySelector('.inline-specialty-actions');
              const cr = chevron.getBoundingClientRect();
              const ar = add.getBoundingClientRect();
              const row = el.getBoundingClientRect();
              return {
                addAfterChevron: ar.left >= cr.right - 1,
                addInsideRow: ar.top >= row.top - 1 && ar.bottom <= row.bottom + 1,
                actionsBg: actions ? getComputedStyle(actions).backgroundColor : '',
              };
            }"""
        )
        assert icon_layout["addAfterChevron"]
        assert icon_layout["addInsideRow"]
        assert icon_layout["actionsBg"] in ("rgba(0, 0, 0, 0)", "transparent")
        spec_rows.nth(0).locator('[data-specialty-action="add"]').click(force=True)
        page.wait_for_function(
            """() => {
              const rows = document.querySelectorAll(
                '#policy-typical-sections-section td[data-inline-field="specialty_ids"] .inline-specialty-row'
              );
              const overlay = document.querySelector('.inline-table-select-editor');
              return rows.length === 3
                && (!overlay || overlay.classList.contains('d-none'));
            }"""
        )
        spec_cell.locator(".inline-specialty-row").nth(1).locator(
            '[data-specialty-action="remove"]'
        ).click(force=True)
        page.wait_for_function(
            """() => {
              const labels = Array.from(document.querySelectorAll(
                '#policy-typical-sections-section td[data-inline-field="specialty_ids"] .inline-specialty-label'
              )).map((el) => el.textContent.trim());
              return labels.length === 2
                && labels[0] === 'Горное дело BR'
                && labels[1] === 'Геология BR';
            }"""
        )
        spec_rows = spec_cell.locator(".inline-specialty-row")
        spec_rows.nth(0).hover()
        spec_rows.nth(0).locator('[data-specialty-action="move"][data-dir="1"]').click(force=True)
        page.wait_for_function(
            """() => {
              const labels = Array.from(document.querySelectorAll(
                '#policy-typical-sections-section td[data-inline-field="specialty_ids"] .inline-specialty-label'
              )).map((el) => el.textContent.trim());
              return labels[0] === 'Геология BR' && labels[1] === 'Горное дело BR';
            }"""
        )

        name_cell = page.locator(
            '#policy-typical-sections-section td[data-inline-field="name_ru"]'
        )
        scroll_before = page.evaluate(
            """() => {
              const scroller = document.querySelector(
                '#policy-typical-sections-section .table-responsive'
              );
              const table = scroller.querySelector('table');
              const row = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="name_ru"]'
              ).closest('tr');
              return {
                overflowX: scroller.scrollWidth - scroller.clientWidth,
                tableW: table.getBoundingClientRect().width,
                rowH: row.getBoundingClientRect().height,
              };
            }"""
        )
        name_cell.dblclick()
        editor = page.locator(".inline-table-text-input")
        editor.wait_for()
        overflow = page.evaluate(
            """() => {
              const scroller = document.querySelector(
                '#policy-typical-sections-section .table-responsive'
              );
              const table = scroller.querySelector('table');
              const row = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="name_ru"]'
              ).closest('tr');
              const chevronTop = getComputedStyle(
                document.querySelector(
                  '#policy-typical-sections-section td[data-inline-field="accounting_type"]'
                ),
                '::after'
              ).top;
              return {
                overflowX: scroller.scrollWidth - scroller.clientWidth,
                overflowY: scroller.scrollHeight - scroller.clientHeight,
                rowH: row.getBoundingClientRect().height,
                tableW: table.getBoundingClientRect().width,
                chevronTop: chevronTop,
              };
            }"""
        )
        assert overflow["overflowX"] <= scroll_before["overflowX"] + 1
        assert abs(overflow["tableW"] - scroll_before["tableW"]) <= 2
        assert overflow["overflowY"] <= 1
        assert abs(overflow["rowH"] - scroll_before["rowH"]) <= 1
        chevron_top = overflow["chevronTop"]
        assert chevron_top.endswith("px")
        assert 0 < float(chevron_top[:-2]) < 18
        editor.fill(("длинное наименование раздела для нескольких строк " * 8).strip())
        grown = page.evaluate(
            """() => {
              const scroller = document.querySelector(
                '#policy-typical-sections-section .table-responsive'
              );
              const table = scroller.querySelector('table');
              const row = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="name_ru"]'
              ).closest('tr');
              return {
                overflowX: scroller.scrollWidth - scroller.clientWidth,
                overflowY: scroller.scrollHeight - scroller.clientHeight,
                rowH: row.getBoundingClientRect().height,
                tableW: table.getBoundingClientRect().width,
              };
            }"""
        )
        assert grown["rowH"] > overflow["rowH"] + 8
        assert grown["overflowX"] <= scroll_before["overflowX"] + 1
        assert grown["overflowY"] <= 1
        assert abs(grown["tableW"] - scroll_before["tableW"]) <= 2
        editor.fill("Новый браузерный раздел")
        editor.press("Enter")
        page.wait_for_function(
            """() => {
              const nameCell = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="name_ru"]'
              );
              return nameCell && nameCell.textContent.includes('Новый браузерный раздел')
                && !document.querySelector('.inline-table-text-input');
            }"""
        )

        accounting_cell = page.locator(
            '#policy-typical-sections-section td[data-inline-field="accounting_type"]'
        )
        page.evaluate(
            """() => {
              const cell = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="accounting_type"]'
              );
              if (!cell) return;
              cell.scrollIntoView({ block: 'nearest', inline: 'nearest' });
              cell.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            }"""
        )
        overlay = page.locator(".inline-table-select-editor")
        page.wait_for_function(
            """() => {
              const overlay = document.querySelector('.inline-table-select-editor');
              return overlay && overlay.dataset.inlineOpen === '1' && !overlay.classList.contains('d-none');
            }"""
        )
        overlay.select_option(value="Услуги", force=True)
        page.wait_for_function(
            """() => {
              const typeCell = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="accounting_type"]'
              );
              return typeCell && typeCell.textContent.includes('Услуги');
            }"""
        )
        tkp_box = page.locator(
            '#policy-typical-sections-section td[data-inline-field="exclude_from_tkp_autofill"] input[type="checkbox"]'
        )
        assert tkp_box.count() == 1
        assert not tkp_box.is_disabled()
        assert not tkp_box.is_checked()
        tkp_box.click()
        page.wait_for_function(
            """() => {
              const cell = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="exclude_from_tkp_autofill"]'
              );
              const input = cell && cell.querySelector('input[type="checkbox"]');
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              return cell && cell.classList.contains('inline-cell-dirty')
                && input && input.checked
                && save && !save.disabled;
            }"""
        )
        page.locator("[data-policy-workspace-save-btn]").click()
        page.wait_for_function(
            """() => {
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              const nameCell = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="name_ru"]'
              );
              const typeCell = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="accounting_type"]'
              );
              const tkp = document.querySelector(
                '#policy-typical-sections-section td[data-inline-field="exclude_from_tkp_autofill"] input[type="checkbox"]'
              );
              return save && save.disabled
                && nameCell && nameCell.textContent.includes('Новый браузерный раздел')
                && typeCell && typeCell.textContent.includes('Услуги')
                && tkp && tkp.checked;
            }"""
        )

        context.close()
        browser.close()

    section.refresh_from_db()
    assert section.name_ru == "Новый браузерный раздел"
    assert section.accounting_type == "Услуги"
    assert section.exclude_from_tkp_autofill is True
    assert list(
        section.ranked_specialties.order_by("rank").values_list("specialty__specialty", flat=True)
    ) == [
        "Геология BR",
        "Горное дело BR",
    ]


def test_product_workspace_typical_section_row_insert_saves(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-sections-insert",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-INS",
        name_en="Section insert product",
        display_name="Insert display",
        name_ru="Браузерный продукт вставки",
        position=1,
    )
    ensure_system_dsc_section(product)
    section = TypicalSection.objects.create(
        product=product,
        code="SEC-CUR",
        short_name="sec-cur",
        short_name_ru="разд-тек",
        name_en="Current section EN",
        name_ru="Текущий раздел",
        accounting_type="Раздел",
        position=2,
    )
    ensure_system_dsc_section(product)
    section.refresh_from_db()

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-INS",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator(
            '#policy-typical-sections-section[data-policy-inline="1"] table'
        ).wait_for()
        page.wait_for_load_state("networkidle")
        page.wait_for_function(
            f"""() => {{
              const section = document.querySelector(
                '#policy-typical-sections-section[data-policy-inline="1"][data-policy-row-insert-bound="1"]'
              );
              return !!(section && section.querySelector(
                'tbody tr[data-inline-row-id="{section.pk}"]'
              ));
            }}"""
        )

        row = page.locator(
            f'#policy-typical-sections-section tbody tr[data-inline-row-id="{section.pk}"]'
        )
        row.wait_for()

        def hover_insert_zone(field="check", edge="after"):
            shown = page.evaluate(
                """({ rowId, field, edge }) => {
                  const row = document.querySelector(
                    '#policy-typical-sections-section tbody tr[data-inline-row-id="' + rowId + '"]'
                  );
                  if (!row) return false;
                  row.scrollIntoView({ block: 'center', inline: 'start' });
                  const cells = Array.from(row.children).filter((cell) => {
                    return cell.tagName === 'TD' && getComputedStyle(cell).display !== 'none';
                  });
                  let cell = cells[0];
                  if (field === 'code') cell = cells[1] || cells[0];
                  if (field === 'name') {
                    cell = row.querySelector('td[data-inline-field="name_ru"]');
                  }
                  if (!cell) return false;
                  const rect = cell.getBoundingClientRect();
                  const clientX = rect.left + Math.min(8, Math.max(2, rect.width / 2));
                  const clientY = edge === 'before' ? rect.top + 2 : rect.bottom - 2;
                  cell.dispatchEvent(new PointerEvent('pointermove', {
                    bubbles: true,
                    cancelable: true,
                    clientX: clientX,
                    clientY: clientY,
                    pointerType: 'mouse',
                  }));
                  return !!document.querySelector(
                    '#policy-typical-sections-section .proposal-row-insert'
                  );
                }""",
                {"rowId": str(section.pk), "field": field, "edge": edge},
            )
            return shown

        assert hover_insert_zone("check")
        insert = page.locator(
            "#policy-typical-sections-section .proposal-row-insert"
        )
        insert.wait_for()
        geometry = page.evaluate(
            """() => {
              const button = document.querySelector(
                '#policy-typical-sections-section .proposal-row-insert'
              );
              const icon = button && button.querySelector('.bi');
              const add = document.querySelector(
                '#policy-typical-sections-section button[hx-get*="section/create"] .bi-plus-circle'
              );
              const checkInput = document.querySelector(
                '#policy-typical-sections-section tbody tr[data-inline-row-id] .form-check-input'
              );
              if (!button || !icon || !add || !checkInput) return null;
              const buttonRect = button.getBoundingClientRect();
              const iconRect = icon.getBoundingClientRect();
              const addRect = add.getBoundingClientRect();
              const checkRect = checkInput.getBoundingClientRect();
              const row = checkInput.closest('tr');
              const lineWidth = parseFloat(
                button.style.getPropertyValue('--proposal-service-row-insert-line-width') || '0'
              );
              return {
                iconSize: Math.round(iconRect.width * 100) / 100,
                addSize: Math.round(addRect.width * 100) / 100,
                iconCenterX: (iconRect.left + iconRect.right) / 2,
                checkLeft: checkRect.left,
                buttonLeft: buttonRect.left,
                lineWidth: lineWidth,
                rowWidth: row ? row.getBoundingClientRect().width : 0,
                hostedOnWrap: !!button.closest('.table-responsive')
                  && !button.closest('td'),
              };
            }"""
        )
        assert geometry
        assert abs(geometry["iconSize"] - geometry["addSize"]) <= 1
        assert geometry["iconCenterX"] <= geometry["checkLeft"] + 1
        assert geometry["hostedOnWrap"]
        assert geometry["lineWidth"] > geometry["rowWidth"] * 0.7

        assert hover_insert_zone("code")
        insert.wait_for()
        border_stability = page.evaluate(
            """({ rowId }) => {
              const row = document.querySelector(
                '#policy-typical-sections-section tbody tr[data-inline-row-id="' + rowId + '"]'
              );
              if (!row) return null;
              const cells = Array.from(row.children).filter((cell) => {
                return cell.tagName === 'TD' && getComputedStyle(cell).display !== 'none';
              });
              const codeCell = cells[1];
              if (!codeCell) return null;
              const sample = () => {
                const cs = getComputedStyle(codeCell);
                const rowCs = getComputedStyle(row);
                return {
                  top: cs.borderTopWidth,
                  bottom: cs.borderBottomWidth,
                  rowPosition: rowCs.position,
                  rowZ: rowCs.zIndex,
                };
              };
              const first = sample();
              const rect = codeCell.getBoundingClientRect();
              const samples = [first];
              for (let i = 0; i < 16; i += 1) {
                codeCell.dispatchEvent(new PointerEvent('pointermove', {
                  bubbles: true,
                  cancelable: true,
                  clientX: rect.left + 6,
                  clientY: rect.top + 1 + (i % 4),
                  pointerType: 'mouse',
                }));
                samples.push(sample());
              }
              return {
                samples: samples,
                hasInsert: !!document.querySelector(
                  '#policy-typical-sections-section .proposal-row-insert'
                ),
              };
            }""",
            {"rowId": str(section.pk)},
        )
        assert border_stability
        assert border_stability["hasInsert"]
        for sample in border_stability["samples"]:
            assert sample["rowPosition"] == "static"
            assert sample["rowZ"] in ("auto", "0")
            assert sample["top"] == border_stability["samples"][0]["top"]
            assert sample["bottom"] == border_stability["samples"][0]["bottom"]

        assert hover_insert_zone("name") is False
        page.wait_for_function(
            """() => !document.querySelector(
              '#policy-typical-sections-section .proposal-row-insert'
            )"""
        )

        assert hover_insert_zone("check")
        insert.wait_for()
        page.evaluate(
            """() => {
              const button = document.querySelector(
                '#policy-typical-sections-section .proposal-row-insert'
              );
              if (button) button.click();
            }"""
        )
        new_row = page.locator(
            '#policy-typical-sections-section tbody tr[data-inline-new="1"]'
        )
        new_row.wait_for()

        def fill_text(field, value):
            cell = new_row.locator(f'td[data-inline-field="{field}"]')
            editor = page.locator(".inline-table-text-input")
            if not editor.count():
                cell.dblclick()
            editor.wait_for()
            editor.fill(value)
            editor.press("Enter")

        fill_text("code", "SEC-INS")
        fill_text("short_name", "sec-ins")
        fill_text("name_en", "Inserted EN")
        fill_text("name_ru", "Вставленный RU")

        page.locator("[data-policy-workspace-save-btn]").click()
        page.wait_for_function(
            """() => {
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              const rows = Array.from(document.querySelectorAll(
                '#policy-typical-sections-section tbody tr'
              ));
              const inserted = rows.find((row) => {
                const cell = row.querySelector('td.typical-section-code-col');
                return cell && cell.textContent.trim() === 'SEC-INS';
              });
              const current = rows.findIndex((row) => {
                const cell = row.querySelector('td.typical-section-code-col');
                return cell && cell.textContent.trim() === 'SEC-CUR';
              });
              const insertedIndex = rows.findIndex((row) => {
                const cell = row.querySelector('td.typical-section-code-col');
                return cell && cell.textContent.trim() === 'SEC-INS';
              });
              const structures = document.querySelector(
                '#policy-section-structures-section [data-policy-inline-options]'
              );
              return save && save.disabled
                && inserted
                && inserted.dataset.deleteUrl
                && inserted.dataset.editUrl
                && inserted.dataset.moveUpUrl
                && inserted.dataset.moveDownUrl
                && current >= 0
                && insertedIndex === current + 1
                && structures
                && structures.textContent.includes('SEC-INS');
            }"""
        )

        inserted_row = page.locator(
            '#policy-typical-sections-section tbody tr',
            has=page.locator('td.typical-section-code-col', has_text="SEC-INS"),
        )
        inserted_row.locator('input[name="section-select"]').check()
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#sections-actions-delete").click()
        page.wait_for_function(
            """() => {
              const codes = Array.from(document.querySelectorAll(
                '#policy-typical-sections-section tbody tr td.typical-section-code-col'
              )).map((cell) => cell.textContent.trim());
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              return !codes.includes('SEC-INS') && save && !save.disabled;
            }"""
        )
        page.locator("[data-policy-workspace-save-btn]").click()
        page.wait_for_function(
            """() => {
              const codes = Array.from(document.querySelectorAll(
                '#policy-typical-sections-section tbody tr td.typical-section-code-col'
              )).map((cell) => cell.textContent.trim());
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              return !codes.includes('SEC-INS') && save && save.disabled;
            }"""
        )

        context.close()
        browser.close()

    assert not TypicalSection.objects.filter(product=product, code="SEC-INS").exists()


def test_product_workspace_related_table_row_insert_saves(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-related-insert",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-REL",
        name_en="Related insert product",
        display_name="Related display",
        name_ru="Браузерный продукт связанных таблиц",
        position=1,
    )
    section = TypicalSection.objects.create(
        product=product,
        code="REL-CUR",
        short_name="rel-cur",
        name_en="Related section EN",
        name_ru="Связанный раздел",
        accounting_type="Раздел",
        position=1,
    )
    structure = SectionStructure.objects.create(
        product=product,
        section=section,
        subsections="Текущие подразделы",
        position=1,
    )
    composition = TypicalServiceComposition.objects.create(
        product=product,
        section=section,
        service_composition="Текущий состав",
        position=1,
    )
    tariff = Tariff.objects.create(
        product=product,
        section=section,
        base_rate_vpm="10.00",
        service_hours=4,
        service_days_tkp=2,
        created_by=user,
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-REL",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator('#policy-section-structures-section[data-policy-row-insert-bound="1"]').wait_for()
        page.locator('#policy-typical-service-compositions-section[data-policy-row-insert-bound="1"]').wait_for()
        page.locator('#policy-tariffs-section[data-policy-row-insert-bound="1"]').wait_for()

        def hover_insert(section_sel, row_id, field="check"):
            return page.evaluate(
                """({ sectionSel, rowId, field }) => {
                  const row = document.querySelector(
                    sectionSel + ' tbody tr[data-inline-row-id="' + rowId + '"]'
                  );
                  if (!row) return false;
                  row.scrollIntoView({ block: 'center', inline: 'start' });
                  const cells = Array.from(row.children).filter((cell) => {
                    return cell.tagName === 'TD' && getComputedStyle(cell).display !== 'none';
                  });
                  let cell = cells[0];
                  if (field === 'code') cell = cells[1] || cells[0];
                  if (field === 'other') cell = cells[3] || cells[cells.length - 1];
                  if (!cell) return false;
                  const rect = cell.getBoundingClientRect();
                  cell.dispatchEvent(new PointerEvent('pointermove', {
                    bubbles: true,
                    cancelable: true,
                    clientX: rect.left + Math.min(8, Math.max(2, rect.width / 2)),
                    clientY: rect.bottom - 2,
                    pointerType: 'mouse',
                  }));
                  return !!document.querySelector(sectionSel + ' .proposal-row-insert');
                }""",
                {"sectionSel": section_sel, "rowId": str(row_id), "field": field},
            )

        def click_insert(section_sel):
            page.evaluate(
                """(sectionSel) => {
                  const button = document.querySelector(sectionSel + ' .proposal-row-insert');
                  if (button) button.click();
                }""",
                section_sel,
            )

        assert hover_insert("#policy-section-structures-section", structure.pk, "check")
        assert hover_insert("#policy-section-structures-section", structure.pk, "code")
        assert hover_insert("#policy-section-structures-section", structure.pk, "other") is False
        assert hover_insert("#policy-section-structures-section", structure.pk, "check")
        click_insert("#policy-section-structures-section")
        new_structure = page.locator(
            '#policy-section-structures-section tbody tr[data-inline-new="1"]'
        )
        new_structure.wait_for()
        cell = new_structure.locator('td[data-inline-field="subsections"]')
        cell.dblclick()
        editor = page.locator(".inline-table-text-input")
        editor.wait_for()
        editor.fill("Вставленные подразделы")
        editor.press("Enter")

        assert hover_insert("#policy-typical-service-compositions-section", composition.pk, "check")
        click_insert("#policy-typical-service-compositions-section")
        page.locator(
            '#policy-typical-service-compositions-section tbody tr[data-inline-new="1"]'
        ).wait_for()
        page.keyboard.press("Escape")

        assert hover_insert("#policy-tariffs-section", tariff.pk, "check")
        click_insert("#policy-tariffs-section")
        page.locator('#policy-tariffs-section tbody tr[data-inline-new="1"]').wait_for()

        page.locator("[data-policy-workspace-save-btn]").click()
        page.wait_for_function(
            """() => {
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              const structure = Array.from(document.querySelectorAll(
                '#policy-section-structures-section tbody tr'
              )).find((row) => (row.textContent || '').includes('Вставленные подразделы'));
              const compositions = document.querySelectorAll(
                '#policy-typical-service-compositions-section tbody tr[data-inline-row-id]'
              );
              const tariffs = document.querySelectorAll(
                '#policy-tariffs-section tbody tr[data-inline-row-id]'
              );
              return save && save.disabled
                && structure && structure.dataset.deleteUrl
                && compositions.length === 2
                && tariffs.length === 2;
            }"""
        )

        context.close()
        browser.close()

    assert SectionStructure.objects.filter(
        product=product, subsections="Вставленные подразделы"
    ).exists()
    assert TypicalServiceComposition.objects.filter(product=product).count() == 2
    assert Tariff.objects.filter(product=product).count() == 2


def test_product_workspace_typical_section_delete_can_be_cancelled(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-sections-delete",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-DEL",
        name_en="Section delete product",
        display_name="Delete display",
        name_ru="Браузерный продукт удаления",
        position=1,
    )
    ensure_system_dsc_section(product)
    section = TypicalSection.objects.create(
        product=product,
        code="SEC-DEL",
        short_name="sec-del",
        short_name_ru="разд-del",
        name_en="Delete section EN",
        name_ru="Удаляемый раздел",
        accounting_type="Раздел",
        position=2,
    )
    ensure_system_dsc_section(product)
    section.refresh_from_db()

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-DEL",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator(
            '#policy-typical-sections-section[data-policy-inline="1"] table'
        ).wait_for()
        save_btn = page.locator("[data-policy-workspace-save-btn]")
        assert save_btn.is_disabled()
        add_gap = page.evaluate(
            """() => {
              const table = document.querySelector(
                '#policy-typical-sections-section .typical-sections-table'
              );
              const button = document.querySelector(
                '#policy-typical-sections-section .policy-table-footer-actions > .btn'
              );
              if (!table || !button) return null;
              return button.getBoundingClientRect().top - table.getBoundingClientRect().bottom;
            }"""
        )
        assert add_gap is not None
        assert abs(add_gap - 24) <= 2

        target_row = page.locator(
            '#policy-typical-sections-section tbody tr',
            has=page.locator('td.typical-section-code-col', has_text="SEC-DEL"),
        )
        target_row.locator('input[name="section-select"]').check()
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("#sections-actions-delete").click()
        page.wait_for_function(
            """() => {
              const codes = Array.from(document.querySelectorAll(
                '#policy-typical-sections-section tbody tr td.typical-section-code-col'
              )).map((cell) => cell.textContent.trim());
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              return !codes.includes('SEC-DEL') && save && !save.disabled;
            }"""
        )

        page.once("dialog", lambda dialog: dialog.accept())
        page.locator("[data-policy-workspace-cancel-btn]").click()
        page.wait_for_function(
            """() => {
              const codes = Array.from(document.querySelectorAll(
                '#policy-typical-sections-section tbody tr td.typical-section-code-col'
              )).map((cell) => cell.textContent.trim());
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              const restored = Array.from(document.querySelectorAll(
                '#policy-typical-sections-section tbody tr'
              )).find((row) => {
                const cell = row.querySelector('td.typical-section-code-col');
                return cell && cell.textContent.trim() === 'SEC-DEL';
              });
              const checkbox = restored && restored.querySelector('input[name="section-select"]');
              return codes.includes('SEC-DEL') && save && save.disabled
                && checkbox && !checkbox.checked;
            }"""
        )

        context.close()
        browser.close()

    assert TypicalSection.objects.filter(pk=section.pk).exists()


def test_product_workspace_section_structure_inline_edit_saves(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-structures-inline",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-STR",
        name_en="Structure browser product",
        display_name="Structure display",
        name_ru="Браузерный продукт структуры",
        position=1,
    )
    current = TypicalSection.objects.create(
        product=product,
        code="STR-CUR",
        short_name="str-cur",
        name_en="Current structure section",
        name_ru="Текущий раздел структуры",
        accounting_type="Раздел",
        position=1,
    )
    target = TypicalSection.objects.create(
        product=product,
        code="STR-NEW",
        short_name="str-new",
        name_en="New structure section",
        name_ru="Новый раздел структуры",
        accounting_type="Раздел",
        position=2,
    )
    structure = SectionStructure.objects.create(
        product=product,
        section=current,
        subsections="Старые подразделы",
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-STR",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator(
            '#policy-section-structures-section[data-policy-inline="1"] table'
        ).wait_for()
        page.locator('#policy-typical-sections-section .typical-section-code-col').first.wait_for()

        chrome = page.evaluate(
            """() => {
              const display = function (el) {
                return el ? getComputedStyle(el).display : '';
              };
              const codeWidth = function (root) {
                const el = document.querySelector(root + ' .typical-section-code-col');
                return el ? Math.round(el.getBoundingClientRect().width) : 0;
              };
              return {
                product: display(document.querySelector(
                  '#policy-section-structures-section .policy-workspace-product-cell'
                )),
                csv: display(document.querySelector('#structures-csv-download-btn')),
                csvUpload: display(document.querySelector('#structures-csv-upload-btn')),
                add: display(document.querySelector(
                  '#policy-section-structures-section button[hx-get*="structure/create"]'
                )),
                code: (function () {
                  const el = document.querySelector(
                    '#policy-section-structures-section .typical-section-dsc-code'
                  );
                  return el ? getComputedStyle(el).color : '';
                })(),
                sectionsCodeWidth: codeWidth('#policy-typical-sections-section'),
                structuresCodeWidth: codeWidth('#policy-section-structures-section'),
              };
            }"""
        )
        assert chrome["product"] == "none"
        assert chrome["csv"] == "none"
        assert chrome["csvUpload"] == "none"
        assert chrome["add"] != "none"
        assert chrome["code"] == "rgb(173, 181, 189)"
        assert chrome["sectionsCodeWidth"] > 0
        assert abs(chrome["structuresCodeWidth"] - chrome["sectionsCodeWidth"]) <= 8

        def code_widths():
            return page.evaluate(
                """() => {
                  const width = function (root) {
                    const el = document.querySelector(root + ' td.typical-section-code-col');
                    return el ? Math.round(el.getBoundingClientRect().width) : 0;
                  };
                  const align = function (root) {
                    const el = document.querySelector(root + ' td.typical-section-code-col');
                    return el ? getComputedStyle(el).textAlign : '';
                  };
                  return {
                    sections: width('#policy-typical-sections-section'),
                    structures: width('#policy-section-structures-section'),
                    structuresAlign: align('#policy-section-structures-section'),
                  };
                }"""
            )

        before_codes = code_widths()
        page.locator(
            '#policy-typical-sections-section td[data-inline-field="name_ru"]'
        ).first.dblclick()
        page.locator(".inline-table-text-input").wait_for()
        during_sections_edit = code_widths()
        assert abs(during_sections_edit["sections"] - before_codes["sections"]) <= 2
        assert abs(during_sections_edit["structures"] - before_codes["structures"]) <= 2
        assert during_sections_edit["structuresAlign"] == "left"
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.querySelector('.inline-table-text-input')")

        page.locator(
            '#policy-section-structures-section td[data-inline-field="subsections"]'
        ).dblclick()
        page.locator(".inline-table-text-input").wait_for()
        during_structures_edit = code_widths()
        assert abs(during_structures_edit["sections"] - before_codes["sections"]) <= 2
        assert abs(during_structures_edit["structures"] - before_codes["structures"]) <= 2
        assert during_structures_edit["structuresAlign"] == "left"
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.querySelector('.inline-table-text-input')")

        option_labels = page.evaluate(
            """() => {
              const node = document.querySelector(
                '#policy-section-structures-section [data-policy-inline-options]'
              );
              const sections = node ? (JSON.parse(node.textContent).sections || []) : [];
              return sections.map(function (item) { return item.label; });
            }"""
        )
        assert "STR-NEW Новый раздел структуры" in option_labels
        assert "STR-CUR Текущий раздел структуры" in option_labels

        opened = False
        for _ in range(3):
            page.evaluate(
                """() => {
                  const cell = document.querySelector(
                    '#policy-section-structures-section td[data-inline-field="section"]'
                  );
                  if (!cell) return;
                  cell.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                  cell.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                }"""
            )
            try:
                page.wait_for_function(
                    """() => {
                      const overlay = document.querySelector('.inline-table-select-editor');
                      return overlay && overlay.dataset.inlineOpen === '1'
                        && !overlay.classList.contains('d-none');
                    }""",
                    timeout=3000,
                )
                opened = True
                break
            except Exception:
                continue
        assert opened, "section select overlay did not open"
        overlay = page.locator(".inline-table-select-editor")
        overlay_labels = overlay.evaluate(
            "el => Array.from(el.options).map(option => option.textContent.trim())"
        )
        assert "STR-NEW Новый раздел структуры" in overlay_labels
        overlay.select_option(value=str(target.pk), force=True)
        page.wait_for_function(
            """() => {
              const sectionCell = document.querySelector(
                '#policy-section-structures-section td[data-inline-field="section"]'
              );
              const code = document.querySelector(
                '#policy-section-structures-section .typical-section-dsc-code'
              );
              return sectionCell && sectionCell.textContent.includes('Новый раздел структуры')
                && !sectionCell.textContent.includes('STR-NEW')
                && code && code.textContent.includes('STR-NEW');
            }"""
        )

        cell = page.locator(
            '#policy-section-structures-section td[data-inline-field="subsections"]'
        )
        cell.dblclick()
        editor = page.locator(".inline-table-text-input")
        editor.wait_for()
        editor.fill("Новые подразделы браузера")
        editor.press("Enter")
        page.wait_for_function(
            """() => {
              const cell = document.querySelector(
                '#policy-section-structures-section td[data-inline-field="subsections"]'
              );
              return cell && cell.textContent.includes('Новые подразделы браузера')
                && !document.querySelector('.inline-table-text-input');
            }"""
        )

        page.locator("[data-policy-workspace-save-btn]").click()
        page.wait_for_function(
            """() => {
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              const sectionCell = document.querySelector(
                '#policy-section-structures-section td[data-inline-field="section"]'
              );
              const subCell = document.querySelector(
                '#policy-section-structures-section td[data-inline-field="subsections"]'
              );
              const code = document.querySelector(
                '#policy-section-structures-section .typical-section-dsc-code'
              );
              return save && save.disabled
                && sectionCell && sectionCell.textContent.includes('Новый раздел структуры')
                && !sectionCell.textContent.includes('STR-NEW')
                && subCell && subCell.textContent.includes('Новые подразделы браузера')
                && code && code.textContent.includes('STR-NEW');
            }"""
        )

        context.close()
        browser.close()

    structure.refresh_from_db()
    assert structure.section_id == target.pk
    assert structure.subsections == "Новые подразделы браузера"


def test_product_workspace_report_structure_inline_edit_saves(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-report-structures-inline",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-RPT",
        name_en="Report structure browser product",
        display_name="Report display",
        name_ru="Браузерный продукт структуры отчета",
        position=1,
    )
    report = ReportStructure.objects.create(
        product=product,
        level=1,
        code="RS-BR",
        name="Старое наименование отчета",
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-RPT",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator(
            '#policy-report-structures-section[data-policy-inline="1"] table'
        ).wait_for()

        chrome = page.evaluate(
            """() => {
              const display = function (el) {
                return el ? getComputedStyle(el).display : '';
              };
              const headers = Array.from(document.querySelectorAll(
                '#report-structures-table thead .report-structure-compact-col'
              )).map(function (th) {
                const style = getComputedStyle(th);
                return {
                  text: (th.textContent || '').trim(),
                  whiteSpace: style.whiteSpace,
                  wrap: th.scrollHeight > th.clientHeight + 1,
                };
              });
              return {
                product: display(document.querySelector(
                  '#policy-report-structures-section .policy-workspace-product-cell'
                )),
                csv: display(document.querySelector('#report-structures-csv-download-btn')),
                csvUpload: display(document.querySelector('#report-structures-csv-upload-btn')),
                add: display(document.querySelector(
                  '#policy-report-structures-section button[hx-get*="report-structure/create"]'
                )),
                headers: headers,
              };
            }"""
        )
        assert chrome["product"] == "none"
        assert chrome["csv"] == "none"
        assert chrome["csvUpload"] == "none"
        assert chrome["add"] != "none"
        assert [item["text"] for item in chrome["headers"]] == ["Уровень", "Номер", "Код"]
        assert all(item["whiteSpace"] == "nowrap" for item in chrome["headers"])
        assert all(not item["wrap"] for item in chrome["headers"])

        cell = page.locator(
            '#policy-report-structures-section td[data-inline-field="name"]'
        )
        cell.dblclick()
        editor = page.locator(".inline-table-text-input")
        editor.wait_for()
        editor.fill("Новое наименование отчета браузера")
        editor.press("Enter")
        page.wait_for_function(
            """() => {
              const cell = document.querySelector(
                '#policy-report-structures-section td[data-inline-field="name"]'
              );
              return cell && cell.textContent.includes('Новое наименование отчета браузера')
                && !document.querySelector('.inline-table-text-input');
            }"""
        )

        page.locator("[data-policy-workspace-save-btn]").click()
        page.wait_for_function(
            """() => {
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              const cell = document.querySelector(
                '#policy-report-structures-section td[data-inline-field="name"]'
              );
              return save && save.disabled
                && cell && cell.textContent.includes('Новое наименование отчета браузера');
            }"""
        )

        context.close()
        browser.close()

    report.refresh_from_db()
    assert report.name == "Новое наименование отчета браузера"


def test_product_workspace_tariff_inline_edit_saves(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-tariffs-inline",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-TAR",
        name_en="Tariff browser product",
        display_name="Tariff display",
        name_ru="Браузерный продукт тарифа",
        position=1,
    )
    current = TypicalSection.objects.create(
        product=product,
        code="TAR-CUR",
        short_name="tar-cur",
        name_en="Current tariff section",
        name_ru="Текущий раздел тарифа",
        accounting_type="Раздел",
        position=1,
    )
    target = TypicalSection.objects.create(
        product=product,
        code="TAR-NEW",
        short_name="tar-new",
        name_en="New tariff section",
        name_ru="Новый раздел тарифа",
        accounting_type="Раздел",
        position=2,
    )
    tariff = Tariff.objects.create(
        product=product,
        section=current,
        base_rate_vpm="10.50",
        service_hours=8,
        service_days_tkp=5,
        created_by=user,
        position=1,
    )
    tariff2 = Tariff.objects.create(
        product=product,
        section=target,
        base_rate_vpm="1.00",
        service_hours=3,
        service_days_tkp=1,
        created_by=user,
        position=2,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-TAR",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator(
            '#policy-tariffs-section[data-policy-inline="1"] table'
        ).wait_for()

        chrome = page.evaluate(
            """() => {
              const display = function (el) {
                return el ? getComputedStyle(el).display : '';
              };
              return {
                product: display(document.querySelector(
                  '#policy-tariffs-section .policy-workspace-product-cell'
                )),
                csv: display(document.querySelector('#tariffs-csv-download-btn')),
                csvUpload: display(document.querySelector('#tariffs-csv-upload-btn')),
                add: display(document.querySelector(
                  '#policy-tariffs-section button[hx-get*="tariff/create"]'
                )),
                code: (function () {
                  const el = document.querySelector(
                    '#policy-tariffs-section .typical-section-dsc-code'
                  );
                  return el ? getComputedStyle(el).color : '';
                })(),
              };
            }"""
        )
        assert chrome["product"] == "none"
        assert chrome["csv"] == "none"
        assert chrome["csvUpload"] == "none"
        assert chrome["add"] != "none"
        assert chrome["code"] == "rgb(173, 181, 189)"

        page.evaluate(
            """() => {
              const cell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="base_rate_vpm"]'
              );
              if (cell) cell.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            }"""
        )
        page.locator(
            '#policy-tariffs-section td[data-inline-field="base_rate_vpm"]'
        ).first.dblclick()
        editor = page.locator(".inline-table-number-input")
        editor.wait_for()
        editor_meta = editor.evaluate(
            """el => ({
              type: el.type,
              step: el.step,
              min: el.min,
              lang: el.lang,
            })"""
        )
        assert editor_meta["type"] == "number"
        assert editor_meta["step"] == "0.01"
        assert editor_meta["min"] == "0"
        assert editor_meta["lang"] == "ru"
        page.wait_for_function(
            """() => {
              const el = document.querySelector('.inline-table-number-input');
              return el && document.activeElement === el;
            }"""
        )
        page.keyboard.press("5")
        assert editor.input_value() in ("5", "5.0", "5.00")
        editor.fill("12.75")
        spinner_guard = page.evaluate(
            """() => {
              const cell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="base_rate_vpm"]'
              );
              const input = document.querySelector('.inline-table-number-input');
              const wrap = document.querySelector('.inline-table-number-wrap');
              if (!cell || !input) return null;
              for (let i = 0; i < 6; i += 1) {
                cell.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                cell.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
                input.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
              }
              return {
                value: input.value,
                stillOpen: document.body.contains(input),
                extraPad: wrap && cell
                  ? parseFloat(getComputedStyle(wrap).paddingRight)
                    - parseFloat(getComputedStyle(cell).paddingRight)
                  : 0,
              };
            }"""
        )
        assert spinner_guard["stillOpen"] is True
        assert spinner_guard["value"] in ("12.75", "12.750")
        assert 2 <= spinner_guard["extraPad"] <= 4
        editor.press("Enter")
        page.wait_for_function(
            """() => {
              const cell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="base_rate_vpm"]'
              );
              return cell && cell.textContent.includes('12,75')
                && !document.querySelector('.inline-table-number-input');
            }"""
        )

        page.locator(
            '#policy-tariffs-section td[data-inline-field="service_hours"]'
        ).first.dblclick()
        page.locator(".inline-table-number-input").wait_for()
        page.locator(".inline-table-number-input").fill("16")
        page.locator(".inline-table-number-input").press("Enter")
        page.wait_for_function(
            """() => {
              const cell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              );
              return cell && cell.textContent.trim() === '16'
                && !document.querySelector('.inline-table-number-input');
            }"""
        )

        page.locator(
            '#policy-tariffs-section td[data-inline-field="service_days_tkp"]'
        ).first.dblclick()
        page.locator(".inline-table-number-input").wait_for()
        page.locator(".inline-table-number-input").fill("9")
        page.locator(".inline-table-number-input").press("Enter")
        page.wait_for_function(
            """() => {
              const cell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="service_days_tkp"]'
              );
              return cell && cell.textContent.trim() === '9'
                && !document.querySelector('.inline-table-number-input');
            }"""
        )

        bulk = page.evaluate(
            """() => {
              const cells = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              ));
              if (cells.length < 2) return null;
              cells.forEach(function (cell) {
                cell.scrollIntoView({ block: 'nearest', inline: 'nearest' });
              });
              cells[0].dispatchEvent(new PointerEvent('pointerdown', {
                bubbles: true, cancelable: true, button: 0, pointerId: 1, isPrimary: true,
              }));
              cells[1].dispatchEvent(new PointerEvent('pointerdown', {
                bubbles: true, cancelable: true, button: 0, pointerId: 1, isPrimary: true,
                shiftKey: true,
              }));
              const selected = cells.filter(function (cell) {
                return cell.classList.contains('inline-cell-selected');
              });
              const halo = selected.map(function (cell) {
                return getComputedStyle(cell).boxShadow;
              });
              const edges = selected.map(function (cell) {
                const after = getComputedStyle(cell, '::after');
                return {
                  top: after.borderTopWidth,
                  right: after.borderRightWidth,
                  bottom: after.borderBottomWidth,
                  left: after.borderLeftWidth,
                };
              });
              return {
                count: selected.length,
                halo: halo,
                edges: edges,
              };
            }"""
        )
        assert bulk["count"] == 2
        assert all("0.25rem" not in (item or "") for item in bulk["halo"])
        assert bulk["edges"][0]["top"] == "2px"
        assert bulk["edges"][0]["bottom"] == "0px"
        assert bulk["edges"][0]["left"] == "2px"
        assert bulk["edges"][0]["right"] == "2px"
        assert bulk["edges"][1]["top"] == "2px"
        assert bulk["edges"][1]["bottom"] == "2px"

        square = page.evaluate(
            """() => {
              const hours = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              ));
              const days = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_days_tkp"]'
              ));
              if (hours.length < 2 || days.length < 2) return null;
              hours[0].scrollIntoView({ block: 'nearest', inline: 'nearest' });
              days[1].scrollIntoView({ block: 'nearest', inline: 'nearest' });
              hours[0].dispatchEvent(new PointerEvent('pointerdown', {
                bubbles: true, cancelable: true, button: 0, pointerId: 1, isPrimary: true,
              }));
              days[1].dispatchEvent(new PointerEvent('pointerdown', {
                bubbles: true, cancelable: true, button: 0, pointerId: 1, isPrimary: true,
                shiftKey: true,
              }));
              const cells = [hours[0], days[0], hours[1], days[1]];
              const edges = cells.map(function (cell) {
                const after = getComputedStyle(cell, '::after');
                return {
                  selected: cell.classList.contains('inline-cell-selected'),
                  top: after.borderTopWidth,
                  right: after.borderRightWidth,
                  bottom: after.borderBottomWidth,
                  left: after.borderLeftWidth,
                };
              });
              const right = [days[0].getBoundingClientRect(), days[1].getBoundingClientRect()];
              return {
                count: cells.filter(function (cell) {
                  return cell.classList.contains('inline-cell-selected');
                }).length,
                edges: edges,
                rightLeftDelta: Math.abs(right[0].left - right[1].left),
                rightRightDelta: Math.abs(right[0].right - right[1].right),
              };
            }"""
        )
        assert square["count"] == 4
        assert square["edges"][0]["right"] == "0px"
        assert square["edges"][0]["bottom"] == "0px"
        assert square["edges"][1]["left"] == "2px"
        assert square["edges"][1]["bottom"] == "0px"
        assert square["edges"][2]["right"] == "0px"
        assert square["edges"][2]["top"] == "2px"
        assert square["edges"][3]["left"] == "2px"
        assert square["edges"][3]["top"] == "2px"
        assert square["rightLeftDelta"] < 1
        assert square["rightRightDelta"] < 1

        page.evaluate(
            """() => {
              const cells = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              ));
              if (!cells.length) return;
              cells[0].dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
            }"""
        )
        page.locator(".inline-table-number-input").wait_for()
        editing_edges = page.evaluate(
            """() => {
              const hours = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              ));
              const days = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_days_tkp"]'
              ));
              const wrap = document.querySelector('.inline-table-number-wrap');
              const input = document.querySelector('.inline-table-number-input');
              if (hours.length < 2 || days.length < 2 || !wrap || !input) return null;
              const cell = hours[0];
              const afterB = getComputedStyle(days[0], '::after');
              const afterD = getComputedStyle(days[1], '::after');
              const wrapStyle = getComputedStyle(wrap);
              const cellPad = getComputedStyle(cell);
              const right = [days[0].getBoundingClientRect(), days[1].getBoundingClientRect()];
              return {
                editingSelected: cell.classList.contains('inline-cell-selected'),
                neighborTop: getComputedStyle(hours[1], '::after').borderTopWidth,
                neighborBottom: getComputedStyle(hours[1], '::after').borderBottomWidth,
                topRightLeft: afterB.borderLeftWidth,
                bottomRightLeft: afterD.borderLeftWidth,
                wrapBorder: wrapStyle.borderTopWidth,
                wrapOutline: wrapStyle.outlineStyle,
                wrapShadow: wrapStyle.boxShadow,
                padTopDelta: parseFloat(wrapStyle.paddingTop) - parseFloat(cellPad.paddingTop),
                padLeftDelta: parseFloat(wrapStyle.paddingLeft) - parseFloat(cellPad.paddingLeft),
                rightLeftDelta: Math.abs(right[0].left - right[1].left),
                rightRightDelta: Math.abs(right[0].right - right[1].right),
              };
            }"""
        )
        assert editing_edges["editingSelected"] is True
        assert editing_edges["neighborTop"] == "2px"
        assert editing_edges["neighborBottom"] == "2px"
        assert editing_edges["topRightLeft"] == "2px"
        assert editing_edges["bottomRightLeft"] == "2px"
        assert editing_edges["wrapBorder"] == "0px"
        assert editing_edges["wrapOutline"] == "none"
        assert editing_edges["wrapShadow"] in ("none", "")
        assert abs(editing_edges["padTopDelta"]) < 0.5
        assert abs(editing_edges["padLeftDelta"]) < 0.5
        assert editing_edges["rightLeftDelta"] < 1
        assert editing_edges["rightRightDelta"] < 1
        page.wait_for_function(
            """() => {
              const el = document.querySelector('.inline-table-number-input');
              return el && document.activeElement === el;
            }"""
        )
        page.locator(".inline-table-number-input").press("2")
        page.locator(".inline-table-number-input").press("5")
        assert page.locator(".inline-table-number-input").input_value() in ("25", "25.0")
        live_square = page.evaluate(
            """() => {
              const hours = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              ));
              const days = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_days_tkp"]'
              ));
              return {
                hours: hours.slice(1).map(function (cell) { return cell.textContent.trim(); }),
                days: days.map(function (cell) { return cell.textContent.trim(); }),
              };
            }"""
        )
        assert live_square["hours"] == ["25"]
        assert live_square["days"] == ["25", "25"]
        page.locator(".inline-table-number-input").press("Escape")
        page.wait_for_function("() => !document.querySelector('.inline-table-number-input')")
        page.evaluate(
            """() => {
              const cells = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              ));
              if (cells.length < 2) return;
              cells[0].dispatchEvent(new PointerEvent('pointerdown', {
                bubbles: true, cancelable: true, button: 0, pointerId: 1, isPrimary: true,
              }));
              cells[1].dispatchEvent(new PointerEvent('pointerdown', {
                bubbles: true, cancelable: true, button: 0, pointerId: 1, isPrimary: true,
                shiftKey: true,
              }));
              cells[0].dispatchEvent(new KeyboardEvent('keydown', {
                key: '2', bubbles: true, cancelable: true,
              }));
            }"""
        )
        page.locator(".inline-table-number-input").wait_for()
        page.wait_for_function(
            """() => {
              const el = document.querySelector('.inline-table-number-input');
              const cells = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              ));
              return el && el.value === '2'
                && cells.length >= 2
                && cells[1].textContent.trim() === '2';
            }"""
        )
        page.locator(".inline-table-number-input").press("0")
        assert page.locator(".inline-table-number-input").input_value() in ("20", "20.0")
        page.locator(".inline-table-number-input").press("Enter")
        page.wait_for_function(
            """() => {
              const cells = Array.from(document.querySelectorAll(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              ));
              return cells.length >= 2
                && cells.every(function (cell) { return cell.textContent.trim() === '20'; })
                && !document.querySelector('.inline-table-number-input');
            }"""
        )

        opened = False
        for _ in range(3):
            page.evaluate(
                """() => {
                  const cell = document.querySelector(
                    '#policy-tariffs-section td[data-inline-field="section"]'
                  );
                  if (!cell) return;
                  cell.scrollIntoView({ block: 'nearest', inline: 'nearest' });
                  cell.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                }"""
            )
            try:
                page.wait_for_function(
                    """() => {
                      const overlay = document.querySelector('.inline-table-select-editor');
                      return overlay && overlay.dataset.inlineOpen === '1'
                        && !overlay.classList.contains('d-none');
                    }""",
                    timeout=3000,
                )
                opened = True
                break
            except Exception:
                continue
        assert opened, "tariff section select overlay did not open"
        overlay = page.locator(".inline-table-select-editor")
        overlay_labels = overlay.evaluate(
            "el => Array.from(el.options).map(option => option.textContent.trim())"
        )
        assert "TAR-NEW Новый раздел тарифа" in overlay_labels
        overlay.select_option(value=str(target.pk), force=True)
        page.wait_for_function(
            """() => {
              const sectionCell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="section"]'
              );
              const code = document.querySelector(
                '#policy-tariffs-section .typical-section-dsc-code'
              );
              return sectionCell && sectionCell.textContent.includes('Новый раздел тарифа')
                && !sectionCell.textContent.includes('TAR-NEW')
                && code && code.textContent.includes('TAR-NEW');
            }"""
        )

        page.locator("[data-policy-workspace-save-btn]").click()
        page.wait_for_function(
            """() => {
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              const sectionCell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="section"]'
              );
              const rateCell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="base_rate_vpm"]'
              );
              const hoursCell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="service_hours"]'
              );
              const daysCell = document.querySelector(
                '#policy-tariffs-section td[data-inline-field="service_days_tkp"]'
              );
              const code = document.querySelector(
                '#policy-tariffs-section .typical-section-dsc-code'
              );
              return save && save.disabled
                && sectionCell && sectionCell.textContent.includes('Новый раздел тарифа')
                && rateCell && rateCell.textContent.includes('12,75')
                && hoursCell && hoursCell.textContent.trim() === '20'
                && daysCell && daysCell.textContent.trim() === '9'
                && code && code.textContent.includes('TAR-NEW');
            }"""
        )

        context.close()
        browser.close()

    tariff.refresh_from_db()
    tariff2.refresh_from_db()
    assert tariff.section_id == target.pk
    assert str(tariff.base_rate_vpm) == "12.75"
    assert tariff.service_hours == 20
    assert tariff.service_days_tkp == 9
    assert tariff2.service_hours == 20


def test_product_workspace_typical_service_term_inline_edit_saves(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-terms-inline",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-TERM",
        name_en="Term browser product",
        display_name="Term display",
        name_ru="Браузерный продукт сроков",
        position=1,
    )
    term = TypicalServiceTerm.objects.create(
        product=product,
        source_data_weeks="2.0",
        source_data_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
        preliminary_report_months="1.5",
        preliminary_report_term_unit=TypicalServiceTerm.TermUnit.MONTHS,
        final_report_weeks="3.0",
        final_report_term_unit=TypicalServiceTerm.TermUnit.WEEKS,
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-TERM",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator(
            '#policy-typical-service-terms-section[data-policy-inline="1"] table'
        ).wait_for()
        page.wait_for_function(
            """() => {
              const btn = document.querySelector('#typical-service-terms-gantt-edit-btn');
              return btn && !btn.disabled && getComputedStyle(btn).display !== 'none';
            }"""
        )

        chrome = page.evaluate(
            """() => {
              const display = function (el) {
                return el ? getComputedStyle(el).display : '';
              };
              const gantt = document.querySelector('#typical-service-terms-gantt-edit-btn');
              const row = document.querySelector(
                '#policy-typical-service-terms-section tbody tr[data-gantt-url]'
              );
              const value = document.querySelector(
                '#policy-typical-service-terms-section td.typical-service-term-value-col'
              );
              const unit = document.querySelector(
                '#policy-typical-service-terms-section td.typical-service-term-unit-col'
              );
              const header = document.querySelector(
                '#policy-typical-service-terms-section thead th[colspan="2"]'
              );
              let gap = null;
              let headerDelta = null;
              if (value && unit && value.firstChild) {
                const range = document.createRange();
                range.selectNodeContents(value);
                gap = unit.getBoundingClientRect().left - range.getBoundingClientRect().right;
              }
              if (header && value) {
                headerDelta = Math.abs(
                  header.getBoundingClientRect().left - value.getBoundingClientRect().left
                );
              }
              return {
                product: display(document.querySelector(
                  '#policy-typical-service-terms-section .policy-workspace-product-cell'
                )),
                checkbox: display(document.querySelector(
                  '#policy-typical-service-terms-section .policy-workspace-checkbox-cell'
                )),
                csv: display(document.querySelector('#typical-service-terms-csv-download-btn')),
                csvUpload: display(document.querySelector('#typical-service-terms-csv-upload-btn')),
                add: display(document.querySelector(
                  '#policy-typical-service-terms-section button[hx-get*="typical-service-term/create"]'
                )),
                gantt: display(gantt),
                ganttDisabled: gantt ? gantt.disabled : true,
                ganttColor: gantt ? getComputedStyle(gantt).color : '',
                ganttBg: gantt ? getComputedStyle(gantt).backgroundColor : '',
                ganttIconColor: gantt ? getComputedStyle(gantt.querySelector('i') || gantt).color : '',
                rowActive: row ? row.classList.contains('table-active') : true,
                valueAlign: value ? getComputedStyle(value).textAlign : '',
                unitWidth: unit ? parseFloat(getComputedStyle(unit).width) : 0,
                valueWidth: value ? value.getBoundingClientRect().width : 0,
                gap: gap,
                headerDelta: headerDelta,
              };
            }"""
        )
        assert chrome["product"] == "none"
        assert chrome["checkbox"] == "none"
        assert chrome["csv"] == "none"
        assert chrome["csvUpload"] == "none"
        assert chrome["add"] == "none"
        assert chrome["gantt"] != "none"
        assert chrome["ganttDisabled"] is False
        assert chrome["ganttColor"] == "rgb(255, 255, 255)"
        assert chrome["ganttBg"] == "rgb(7, 93, 148)"
        assert chrome["ganttIconColor"] == "rgb(255, 255, 255)"
        assert chrome["rowActive"] is False
        assert chrome["valueAlign"] == "left"
        assert chrome["unitWidth"] > chrome["valueWidth"]
        assert chrome["headerDelta"] is not None and chrome["headerDelta"] < 2

        closed_width = page.evaluate(
            """() => {
              const cell = document.querySelector(
                '#policy-typical-service-terms-section td[data-inline-field="source_data_weeks"]'
              );
              if (cell) cell.scrollIntoView({ block: 'nearest', inline: 'nearest' });
              return cell ? cell.getBoundingClientRect().width : 0;
            }"""
        )
        page.locator(
            '#policy-typical-service-terms-section td[data-inline-field="source_data_weeks"]'
        ).first.dblclick()
        editor = page.locator(".inline-table-number-input")
        editor.wait_for()
        editor_layout = page.evaluate(
            """() => {
              const cell = document.querySelector(
                '#policy-typical-service-terms-section td[data-inline-field="source_data_weeks"]'
              );
              const input = document.querySelector('.inline-table-number-input');
              const unit = document.querySelector(
                '#policy-typical-service-terms-section td[data-inline-field="source_data_term_unit"]'
              );
              if (!cell || !input) return null;
              const cr = cell.getBoundingClientRect();
              const ir = input.getBoundingClientRect();
              const ur = unit ? unit.getBoundingClientRect() : null;
              return {
                width: cr.width,
                overflowRight: ir.right - cr.right,
                overflowLeft: cr.left - ir.left,
                unitGap: ur ? ur.left - ir.right : null,
              };
            }"""
        )
        assert editor_layout is not None
        assert abs(editor_layout["width"] - closed_width) < 1
        assert editor_layout["overflowRight"] <= 1
        assert editor_layout["overflowLeft"] <= 1
        assert editor_layout["unitGap"] is not None and editor_layout["unitGap"] >= -1
        editor_meta = editor.evaluate(
            """el => ({
              type: el.type,
              step: el.step,
              min: el.min,
              lang: el.lang,
            })"""
        )
        assert editor_meta["type"] == "number"
        assert editor_meta["step"] == "0.1"
        assert editor_meta["min"] == "0"
        assert editor_meta["lang"] == "ru"
        editor.fill("4.0")
        editor.press("Enter")
        page.wait_for_function(
            """() => {
              const cell = document.querySelector(
                '#policy-typical-service-terms-section td[data-inline-field="source_data_weeks"]'
              );
              return cell && cell.textContent.trim() === '4,0'
                && !document.querySelector('.inline-table-number-input');
            }"""
        )

        unit_cell = page.locator(
            '#policy-typical-service-terms-section td[data-inline-field="source_data_term_unit"]'
        )
        unit_cell.click()
        overlay = page.locator(".inline-table-select-editor")
        page.wait_for_function(
            """() => {
              const overlay = document.querySelector('.inline-table-select-editor');
              return overlay && overlay.dataset.inlineOpen === '1';
            }"""
        )
        overlay.select_option(value="days", force=True)
        page.wait_for_function(
            """() => {
              const unit = document.querySelector(
                '#policy-typical-service-terms-section td[data-inline-field="source_data_term_unit"]'
              );
              const value = document.querySelector(
                '#policy-typical-service-terms-section td[data-inline-field="source_data_weeks"]'
              );
              return unit && unit.textContent.trim() === 'дн.'
                && value && value.textContent.trim() === '4'
                && value.getAttribute('data-inline-step') === '1';
            }"""
        )

        page.locator("[data-policy-workspace-save-btn]").click()
        page.wait_for_function(
            """() => {
              const save = document.querySelector('[data-policy-workspace-save-btn]');
              const unit = document.querySelector(
                '#policy-typical-service-terms-section td[data-inline-field="source_data_term_unit"]'
              );
              const value = document.querySelector(
                '#policy-typical-service-terms-section td[data-inline-field="source_data_weeks"]'
              );
              return save && save.disabled
                && unit && unit.textContent.trim() === 'дн.'
                && value && value.textContent.trim() === '4';
            }"""
        )

        context.close()
        browser.close()

    term.refresh_from_db()
    assert term.source_data_weeks == Decimal("4")
    assert term.source_data_term_unit == TypicalServiceTerm.TermUnit.DAYS
    assert term.product_id == product.pk


def test_product_workspace_select_dismisses_without_halo_or_jump(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-select-dismiss",
        password="unused",
        is_staff=True,
    )
    direction = ConsultingDirection.objects.create(position=1)
    consulting_type = ConsultingDirectionType.objects.create(
        direction=direction,
        name="Browser consulting",
        position=1,
    )
    service_type = ConsultingServiceType.objects.create(
        direction=direction,
        consulting_type=consulting_type,
        name="Browser service",
        code="BRS",
        position=1,
    )
    other_service = ConsultingServiceType.objects.create(
        direction=direction,
        consulting_type=consulting_type,
        name="Other service",
        code="OTS",
        position=1,
    )
    ConsultingServiceSubtype.objects.create(
        direction=direction,
        service_type=service_type,
        name="Browser subtype",
        position=1,
    )
    Product.objects.create(
        short_name="BR-SEL",
        name_en="Select dismiss product",
        display_name="Select display",
        name_ru="Продукт списка",
        consulting_type_ref=consulting_type,
        service_category_ref=service_type,
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-SEL",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()

        service_cell = page.locator(
            '#policy-products-section td[data-inline-field="service_category_ref"]'
        )
        service_cell.click()
        overlay = page.locator(".inline-table-select-editor")
        page.wait_for_function(
            """() => {
              const overlay = document.querySelector('.inline-table-select-editor');
              return overlay && overlay.dataset.inlineOpen === '1' && !overlay.classList.contains('d-none');
            }"""
        )
        overlap = page.evaluate(
            """() => {
              const cell = document.querySelector('#policy-products-section td[data-inline-field="service_category_ref"]');
              const overlay = document.querySelector('.inline-table-select-editor');
              const code = document.querySelector('#policy-products-section td[data-inline-field="service_code"]');
              if (!cell || !overlay || !code || overlay.classList.contains('d-none')) return null;
              const cellRect = cell.getBoundingClientRect();
              const overlayRect = overlay.getBoundingClientRect();
              const codeRect = code.getBoundingClientRect();
              const style = getComputedStyle(overlay);
              return {
                overlayRight: overlayRect.right,
                overlayWidth: overlayRect.width,
                cellRight: cellRect.right,
                cellWidth: cellRect.width,
                codeLeft: codeRect.left,
                opacity: style.opacity,
                boxShadow: style.boxShadow,
              };
            }"""
        )
        assert overlap, "select overlay should stay open after click"
        assert float(overlap["opacity"]) == 0
        assert overlap["overlayWidth"] > 0
        assert overlap["boxShadow"] in ("none", "none 0px 0px 0px 0px")
        assert overlap["overlayRight"] <= overlap["codeLeft"] + 1
        assert abs(overlap["overlayRight"] - overlap["cellRight"]) <= 1

        page.locator("#policy-workspace-actions").click()
        page.wait_for_function(
            """() => {
              const overlay = document.querySelector('.inline-table-select-editor');
              const cell = document.querySelector('#policy-products-section td[data-inline-field="service_category_ref"]');
              return overlay && overlay.classList.contains('d-none')
                && overlay.dataset.inlineOpen !== '1'
                && cell && !cell.classList.contains('inline-cell-selected')
                && document.activeElement !== overlay;
            }"""
        )
        box_after_first = service_cell.bounding_box()
        page.locator("#policy-workspace-actions").click()
        box_after_second = service_cell.bounding_box()
        assert box_after_first and box_after_second
        assert abs(box_after_first["x"] - box_after_second["x"]) < 1
        assert abs(box_after_first["width"] - box_after_second["width"]) < 1
        assert abs(box_after_first["height"] - box_after_second["height"]) < 1

        service_cell.click()
        page.wait_for_function(
            """() => {
              const overlay = document.querySelector('.inline-table-select-editor');
              return overlay && overlay.dataset.inlineOpen === '1';
            }"""
        )
        overlay.select_option(value=str(other_service.pk), force=True)
        page.wait_for_function(
            """() => {
              const overlay = document.querySelector('.inline-table-select-editor');
              const cell = document.querySelector('#policy-products-section td[data-inline-field="service_category_ref"]');
              return overlay && overlay.classList.contains('d-none')
                && cell && !cell.classList.contains('inline-cell-selected');
            }"""
        )
        after_choice = page.evaluate(
            """() => {
              const cell = document.querySelector('#policy-products-section td[data-inline-field="service_category_ref"]');
              const code = document.querySelector('#policy-products-section td[data-inline-field="service_code"]');
              return {
                cellRight: cell.getBoundingClientRect().right,
                codeLeft: code.getBoundingClientRect().left,
                selected: cell.classList.contains('inline-cell-selected'),
              };
            }"""
        )
        assert not after_choice["selected"]
        assert after_choice["cellRight"] <= after_choice["codeLeft"] + 1

        context.close()
        browser.close()


def test_product_workspace_composition_inline_edit_opens_rich_toolbar(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-compositions-inline",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-CMP",
        name_en="Composition browser product",
        display_name="Composition display",
        name_ru="Браузерный продукт состава",
        position=1,
    )
    section = TypicalSection.objects.create(
        product=product,
        code="CMP-CUR",
        short_name="cmp-cur",
        name_en="Current composition section",
        name_ru="Текущий раздел состава",
        accounting_type="Раздел",
        position=1,
    )
    TypicalSection.objects.create(
        product=product,
        code="CMP-NEW",
        short_name="cmp-new",
        name_en="New composition section",
        name_ru="Новый раздел состава",
        accounting_type="Раздел",
        position=2,
    )
    TypicalServiceComposition.objects.create(
        product=product,
        section=section,
        service_composition="Первая строка\nВторая строка",
        service_composition_editor_state={
            "html": (
                '<ul><li data-list="bullet">Первая строка</li>'
                '<li class="ql-indent-1" data-list="bullet">Вторая строка</li></ul>'
                '<p><br></p>'
            ),
            "plain_text": "Первая строка\nВторая строка",
        },
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator(
            '#policy-products-section tbody tr[data-workspace-url]',
            has_text="BR-CMP",
        ).locator(".product-quick-edit").click()
        page.locator('#policy-pane[data-policy-workspace="1"]').wait_for()
        page.locator(
            '#policy-typical-service-compositions-section[data-policy-inline="1"] table'
        ).wait_for()

        chrome = page.evaluate(
            """() => {
              const display = function (el) {
                return el ? getComputedStyle(el).display : '';
              };
              const code = document.querySelector(
                '#policy-typical-service-compositions-section .typical-section-dsc-code'
              );
              const thead = document.querySelector(
                '#policy-typical-service-compositions-section thead'
              );
              const th = thead && thead.querySelector('th');
              const codeTd = document.querySelector(
                '#policy-typical-service-compositions-section td.typical-section-code-col'
              );
              const codeSpan = codeTd && codeTd.querySelector('.typical-section-dsc-code');
              return {
                product: display(document.querySelector(
                  '#policy-typical-service-compositions-section .policy-workspace-product-cell'
                )),
                csv: display(document.querySelector('#typical-service-compositions-csv-download-btn')),
                docx: display(document.querySelector('#typical-service-compositions-docx-download-btn')),
                actions: display(document.querySelector('#typical-service-compositions-actions')),
                add: display(document.querySelector(
                  '#policy-typical-service-compositions-section button[hx-get*="typical-service-composition/create"]'
                )),
                toolbarHidden: (function () {
                  const slot = document.querySelector(
                    '#policy-typical-service-compositions-section .policy-service-composition-inline-toolbar'
                  );
                  return slot ? getComputedStyle(slot).visibility === 'hidden' : true;
                })(),
                headerHeight: thead ? Math.round(thead.getBoundingClientRect().height) : 0,
                codeColor: code ? getComputedStyle(code).color : '',
                theadSticky: th ? getComputedStyle(th).position : '',
                codeExtra: (codeTd && codeSpan)
                  ? (codeTd.getBoundingClientRect().width - codeSpan.getBoundingClientRect().width)
                  : 999,
              };
            }"""
        )
        assert chrome["product"] == "none"
        assert chrome["csv"] == "none"
        assert chrome["docx"] == "none"
        assert chrome["actions"] == "none"
        assert chrome["add"] != "none"
        assert chrome["toolbarHidden"] is True
        assert chrome["theadSticky"] == "sticky"
        assert "173" in chrome["codeColor"] or chrome["codeColor"] == "rgb(173, 181, 189)"
        assert chrome["codeExtra"] < 40

        display_font = page.evaluate(
            """() => {
              const el = document.querySelector(
                '#policy-typical-service-compositions-section .policy-service-composition-content--rich'
              );
              return el ? getComputedStyle(el).fontSize : '';
            }"""
        )
        page.evaluate(
            """() => {
              const table = document.getElementById('typical-service-compositions-table');
              const toggle = document.getElementById('typical-service-compositions-wrap-toggle');
              if (table) table.classList.remove('clf-truncated');
              if (toggle) toggle.classList.remove('active');
              window.__policyTypicalServiceCompositionWrapActive = false;
            }"""
        )
        bullet_left_before = page.evaluate(
            """() => {
              const root = document.querySelector(
                '#policy-typical-service-compositions-section .policy-service-composition-content--rich'
              );
              const li = root && root.querySelector('li[data-list="bullet"]:not(.ql-indent-1)');
              const nested = root && root.querySelector('li.ql-indent-1[data-list="bullet"]');
              const emptyP = root && Array.from(root.querySelectorAll('p')).find(function (p) {
                return p.textContent.replace(/\\s/g, '') === '';
              });
              const ui = li && li.querySelector('.ql-ui');
              const nestedUi = nested && nested.querySelector('.ql-ui');
              return {
                left: li ? Math.round(li.getBoundingClientRect().left) : 0,
                uiLeft: ui ? Math.round(ui.getBoundingClientRect().left) : 0,
                nestedUiLeft: nestedUi ? Math.round(nestedUi.getBoundingClientRect().left) : 0,
                pad: li ? getComputedStyle(li).paddingLeft : '',
                nestedPad: nested ? getComputedStyle(nested).paddingLeft : '',
                emptyHeight: emptyP ? Math.round(emptyP.getBoundingClientRect().height) : 0,
              };
            }"""
        )

        page.evaluate(
            """() => {
              const table = document.getElementById('typical-service-compositions-table');
              const toggle = document.getElementById('typical-service-compositions-wrap-toggle');
              if (table) table.classList.add('clf-truncated');
              if (toggle) toggle.classList.add('active');
              window.__policyTypicalServiceCompositionWrapActive = true;
            }"""
        )
        code_width_before = page.evaluate(
            """() => {
              const el = document.querySelector(
                '#policy-typical-service-compositions-section td.typical-section-code-col'
              );
              return el ? Math.round(el.getBoundingClientRect().width) : 0;
            }"""
        )
        header_height_before = page.evaluate(
            """() => {
              const thead = document.querySelector(
                '#policy-typical-service-compositions-section thead'
              );
              return thead ? Math.round(thead.getBoundingClientRect().height) : 0;
            }"""
        )
        page.locator(
            '#policy-typical-service-compositions-section td[data-inline-type="rich"]'
        ).first.dblclick()
        page.wait_for_function(
            """() => {
              const wrap = document.querySelector(
                '#policy-typical-service-compositions-section .inline-table-rich-wrap'
              );
              const header = document.querySelector(
                '#policy-typical-service-compositions-section .policy-service-composition-header'
              );
              const table = document.getElementById('typical-service-compositions-table');
              const slot = document.querySelector(
                '#policy-typical-service-compositions-section .policy-service-composition-inline-toolbar'
              );
              const actions = document.querySelector(
                '#policy-typical-service-compositions-section .policy-service-composition-edit-actions'
              );
              return !!(wrap && header && header.classList.contains('is-rich-editing')
                && table && !table.classList.contains('clf-truncated')
                && slot && getComputedStyle(slot).visibility === 'visible'
                && actions && getComputedStyle(actions).visibility === 'visible');
            }"""
        )
        editing = page.evaluate(
            """() => {
              const wrap = document.querySelector(
                '#policy-typical-service-compositions-section .inline-table-rich-wrap'
              );
              const outline = wrap ? getComputedStyle(wrap).outlineColor : '';
              const box = wrap ? getComputedStyle(wrap).boxShadow : '';
              const commit = document.querySelector(
                '#policy-typical-service-compositions-section [data-rich-edit-action="commit"]'
              );
              const cancel = document.querySelector(
                '#policy-typical-service-compositions-section [data-rich-edit-action="cancel"]'
              );
              const actions = document.querySelector(
                '#policy-typical-service-compositions-section .policy-service-composition-edit-actions'
              );
              return {
                outline: outline,
                box: box,
                commitVisible: !!(commit && actions && getComputedStyle(actions).visibility !== 'hidden'),
                cancelVisible: !!(cancel && actions && getComputedStyle(actions).visibility !== 'hidden'),
                headerHeight: (function () {
                  const thead = document.querySelector(
                    '#policy-typical-service-compositions-section thead'
                  );
                  return thead ? Math.round(thead.getBoundingClientRect().height) : 0;
                })(),
              };
            }"""
        )
        assert (
            "13, 110, 253" in editing["outline"]
            or "13, 110, 253" in editing["box"]
            or "7, 93, 148" in editing["outline"]
            or             "7, 93, 148" in editing["box"]
        )
        assert editing["commitVisible"] is True
        assert editing["cancelVisible"] is True
        assert abs(editing["headerHeight"] - header_height_before) <= 2
        page.wait_for_function(
            """() => !!document.querySelector(
              '#policy-typical-service-compositions-section .inline-table-rich-wrap .ql-editor li.ql-indent-1[data-list="bullet"]'
            )"""
        )
        bullet_left_editing = page.evaluate(
            """() => {
              const root = document.querySelector(
                '#policy-typical-service-compositions-section .inline-table-rich-wrap .ql-editor'
              );
              const li = root && root.querySelector('li[data-list="bullet"]:not(.ql-indent-1)');
              const nested = root && root.querySelector('li.ql-indent-1[data-list="bullet"]');
              const emptyP = root && Array.from(root.querySelectorAll('p')).find(function (p) {
                return p.textContent.replace(/\\s/g, '') === '';
              });
              const ui = li && li.querySelector('.ql-ui');
              const nestedUi = nested && nested.querySelector('.ql-ui');
              return {
                left: li ? Math.round(li.getBoundingClientRect().left) : 0,
                uiLeft: ui ? Math.round(ui.getBoundingClientRect().left) : 0,
                nestedUiLeft: nestedUi ? Math.round(nestedUi.getBoundingClientRect().left) : 0,
                pad: li ? getComputedStyle(li).paddingLeft : '',
                nestedPad: nested ? getComputedStyle(nested).paddingLeft : '',
                emptyHeight: emptyP ? Math.round(emptyP.getBoundingClientRect().height) : 0,
              };
            }"""
        )
        assert bullet_left_before["left"] > 0
        assert float(str(bullet_left_before["nestedPad"]).replace("px", "") or "0") > float(
            str(bullet_left_before["pad"]).replace("px", "") or "0"
        )
        assert bullet_left_before["nestedUiLeft"] > bullet_left_before["uiLeft"]
        assert abs(bullet_left_editing["left"] - bullet_left_before["left"]) <= 2
        assert abs(bullet_left_editing["uiLeft"] - bullet_left_before["uiLeft"]) <= 2
        assert abs(bullet_left_editing["nestedUiLeft"] - bullet_left_before["nestedUiLeft"]) <= 2
        assert bullet_left_editing["nestedPad"] == bullet_left_before["nestedPad"]
        assert bullet_left_before["emptyHeight"] > 0
        assert abs(bullet_left_editing["emptyHeight"] - bullet_left_before["emptyHeight"]) <= 2

        layout = page.evaluate(
            """() => {
              const title = document.querySelector(
                '#policy-typical-service-compositions-section .policy-service-composition-header__title'
              );
              const toolbar = document.querySelector(
                '#policy-typical-service-compositions-section .policy-service-composition-inline-toolbar'
              );
              const actions = document.querySelector(
                '#policy-typical-service-compositions-section .policy-service-composition-edit-actions'
              );
              const editor = document.querySelector(
                '#policy-typical-service-compositions-section .inline-table-rich-wrap .ql-editor'
              );
              const titleBox = title ? title.getBoundingClientRect() : null;
              const toolbarBox = toolbar ? toolbar.getBoundingClientRect() : null;
              const actionsBox = actions ? actions.getBoundingClientRect() : null;
              return {
                sameRow: !!(titleBox && toolbarBox && actionsBox
                  && Math.abs(titleBox.top - toolbarBox.top) < 12
                  && Math.abs(titleBox.top - actionsBox.top) < 12),
                toolbarRightOfTitle: !!(titleBox && toolbarBox && toolbarBox.left >= titleBox.right - 4),
                actionsRightOfToolbar: !!(toolbarBox && actionsBox && actionsBox.left >= toolbarBox.left),
                commitInView: !!(actionsBox
                  && actionsBox.right <= window.innerWidth
                  && actionsBox.left >= 0),
                editorFont: editor ? getComputedStyle(editor).fontSize : '',
                codeWidth: (function () {
                  const el = document.querySelector(
                    '#policy-typical-service-compositions-section td.typical-section-code-col'
                  );
                  return el ? Math.round(el.getBoundingClientRect().width) : 0;
                })(),
              };
            }"""
        )
        assert layout["sameRow"] is True
        assert layout["toolbarRightOfTitle"] is True
        assert layout["actionsRightOfToolbar"] is True
        assert layout["commitInView"] is True
        assert layout["editorFont"] == display_font
        assert abs(layout["codeWidth"] - code_width_before) <= 1

        page.locator(
            '#typical-service-composition-inline-toolbar [data-bs-toggle="dropdown"]'
        ).click()
        menu_state = page.evaluate(
            """() => {
              const menu = document.querySelector('.proposal-service-text-toolbar__list-menu');
              return {
                menuShow: !!(menu && menu.classList.contains('show')),
                menuParent: menu && menu.parentElement
                  ? menu.parentElement.tagName
                  : '',
                display: menu ? getComputedStyle(menu).display : null,
                items: menu ? menu.querySelectorAll('.dropdown-item').length : 0
              };
            }"""
        )
        assert menu_state["menuShow"] is True, menu_state
        assert menu_state["items"] >= 6

        page.locator(
            '#typical-service-composition-inline-toolbar [data-color-toggle="color"]'
        ).click()
        color_state = page.evaluate(
            """() => {
              const popover = document.querySelector(
                '[data-color-popover="color"]'
              );
              const toggle = document.querySelector(
                '#typical-service-composition-inline-toolbar [data-color-toggle="color"]'
              );
              const swatch = document.querySelector(
                '#typical-service-composition-inline-toolbar [data-color-preview="color"]'
              );
              const box = popover ? popover.getBoundingClientRect() : null;
              return {
                hidden: popover ? popover.hidden : true,
                parent: popover && popover.parentElement
                  ? popover.parentElement.tagName
                  : '',
                hasSv: !!(popover && popover.querySelector('[data-color-sv="color"]')),
                visible: !!(box && box.width > 80 && box.height > 80),
                swatchVisible: !!(swatch && getComputedStyle(swatch).opacity !== '0'
                  && getComputedStyle(swatch).width !== '0px'),
                toggleExpanded: toggle
                  ? toggle.getAttribute('aria-expanded')
                  : '',
              };
            }"""
        )
        assert color_state["hidden"] is False, color_state
        assert color_state["parent"] == "BODY"
        assert color_state["hasSv"] is True
        assert color_state["visible"] is True
        assert color_state["swatchVisible"] is True
        assert color_state["toggleExpanded"] == "true"

        page.locator(
            '#policy-typical-service-compositions-section .table-section-title'
        ).click()
        page.wait_for_function(
            """() => !document.querySelector(
              '#policy-typical-service-compositions-section .inline-table-rich-wrap'
            )"""
        )
        dirty = page.evaluate(
            """() => {
              const cell = document.querySelector(
                '#policy-typical-service-compositions-section td[data-inline-type="rich"]'
              );
              return !!(cell && cell.classList.contains('inline-cell-dirty'));
            }"""
        )
        assert dirty is False

        page.locator(
            '#policy-typical-service-compositions-section td[data-inline-type="rich"]'
        ).first.dblclick()
        page.wait_for_function(
            """() => !!document.querySelector(
              '#policy-typical-service-compositions-section .inline-table-rich-wrap .ql-editor'
            )"""
        )
        drag = page.evaluate(
            """() => {
              const editor = document.querySelector(
                '#policy-typical-service-compositions-section .inline-table-rich-wrap .ql-editor'
              );
              const cell = document.querySelector(
                '#policy-typical-service-compositions-section td.inline-cell-editing'
              );
              const editorBox = editor.getBoundingClientRect();
              const cellBox = cell.getBoundingClientRect();
              return {
                startX: editorBox.left + 12,
                startY: editorBox.top + Math.min(8, editorBox.height / 2),
                endX: editorBox.left + 12,
                endY: cellBox.bottom + 12,
              };
            }"""
        )
        page.mouse.move(drag["startX"], drag["startY"])
        page.mouse.down()
        page.mouse.move(drag["endX"], drag["endY"], steps=6)
        page.mouse.up()
        assert page.locator(
            '#policy-typical-service-compositions-section .inline-table-rich-wrap'
        ).count() == 1

        page.keyboard.press("Escape")
        page.wait_for_function(
            """() => !document.querySelector(
              '#policy-typical-service-compositions-section .inline-table-rich-wrap'
            )"""
        )

        context.close()
        browser.close()


def test_typical_service_composition_modal_toolbar_starts_inactive(live_server, django_user_model):
    user = django_user_model.objects.create_user(
        username="policy-browser-composition-modal",
        password="unused",
        is_staff=True,
    )
    product = Product.objects.create(
        short_name="BR-MODAL",
        name_en="Composition modal product",
        display_name="Composition modal",
        name_ru="Модалка состава",
        position=1,
    )
    TypicalSection.objects.create(
        product=product,
        code="MOD-SEC",
        short_name="mod-sec",
        name_en="Modal section",
        name_ru="Раздел модалки",
        accounting_type="Раздел",
        position=1,
    )

    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    django_client = Client()
    django_client.force_login(user)
    session_cookie = django_client.cookies[settings.SESSION_COOKIE_NAME]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=os.environ.get("PLAYWRIGHT_CHANNEL") or None
        )
        context = browser.new_context()
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_cookie.value,
                    "url": live_server.url,
                }
            ]
        )
        page = context.new_page()
        page.goto(live_server.url, wait_until="domcontentloaded")
        page.locator('a[href="#policy"]').first.click()
        page.locator('#policy-pane[data-policy-lazy-shell="1"]').wait_for()
        page.locator("#policy-pane #policy-products-section table").wait_for()
        page.locator("#policy-typical-service-compositions-section").scroll_into_view_if_needed()
        page.locator("#policy-typical-service-compositions-section table").wait_for()
        page.locator(
            '#policy-typical-service-compositions-section button[hx-get*="typical-service-composition/create"]'
        ).click()
        page.locator("#policy-modal #typical-service-composition-toolbar").wait_for()
        page.locator("#typical-service-composition-editor .ql-editor").wait_for()

        chrome = page.evaluate(
            """() => {
              const toolbar = document.querySelector(
                '#policy-modal #typical-service-composition-toolbar'
              );
              if (!toolbar) return null;
              const colorOf = function (el) {
                return el ? getComputedStyle(el).color : '';
              };
              const bgOf = function (el) {
                return el ? getComputedStyle(el).backgroundColor : '';
              };
              const formatButtons = Array.from(toolbar.querySelectorAll('button[data-format]'));
              const listButtons = Array.from(
                toolbar.querySelectorAll('button[data-list]:not([data-list-marker-option])')
              );
              const alignButtons = Array.from(toolbar.querySelectorAll('button[data-align]'));
              return {
                formatActive: formatButtons.map(function (btn) {
                  return btn.classList.contains('is-active');
                }),
                listActive: listButtons.map(function (btn) {
                  return btn.classList.contains('is-active');
                }),
                alignActive: alignButtons.map(function (btn) {
                  return {
                    align: btn.dataset.align,
                    active: btn.classList.contains('is-active'),
                  };
                }),
                boldColor: colorOf(toolbar.querySelector('button[data-format="bold"]')),
                boldBg: bgOf(toolbar.querySelector('button[data-format="bold"]')),
                italicColor: colorOf(toolbar.querySelector('button[data-format="italic"]')),
                orderedColor: colorOf(toolbar.querySelector('button[data-list="ordered"]')),
              };
            }"""
        )
        assert chrome is not None
        assert chrome["formatActive"]
        assert all(active is False for active in chrome["formatActive"])
        assert all(active is False for active in chrome["listActive"])
        assert chrome["boldColor"] != "rgb(10, 88, 202)"
        assert chrome["italicColor"] != "rgb(10, 88, 202)"
        assert chrome["orderedColor"] != "rgb(10, 88, 202)"
        assert chrome["boldBg"] in {"rgb(255, 255, 255)", "rgba(0, 0, 0, 0)", "rgb(248, 249, 250)"}

        context.close()
        browser.close()
