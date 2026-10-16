import re
import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://195.19.209.79"

NOISE_WORDS = {
    "фото", "электроника", "недвижимость", "транспорт",
    "требует доработок", "опубликовано", "снято с публикации",
    "забронировано", "продано", "в наличии",
}


def extract_title_from_card(card_text: str) -> str:
    
    lines = [l.strip() for l in card_text.split("\n") if l.strip()]
    price_idx = next((i for i, l in enumerate(lines) if "₽" in l), None)

    if price_idx is not None:
        idx = price_idx - 1
        while idx >= 0 and (lines[idx].lower() in NOISE_WORDS or len(lines[idx]) <= 1):
            idx -= 1
        if idx >= 0:
            return lines[idx]

    for l in lines:
        if l.lower() not in NOISE_WORDS and len(l) > 1:
            return l
    return lines[0] if lines else ""


class TestAdsDesktop:
    def test_search_by_title(self, page: Page):
        """TC-01: поиск по названию."""
        page.goto(f"{BASE_URL}/ads")
        page.wait_for_selector(".ads-page__title")
        page.wait_for_timeout(1500)

        cards = page.locator(".ads-page__grid > div")
        initial_count = cards.count()
        assert initial_count > 0, "На странице нет объявлений — тест невозможен"

        first_title = ""
        for i in range(cards.count()):
            t = extract_title_from_card(cards.nth(i).inner_text())
            if len(t) >= 3:
                first_title = t
                break
        if not first_title:
            first_title = extract_title_from_card(cards.first.inner_text())
        assert first_title, "Не удалось получить название карточки"

        search_input = page.get_by_placeholder("Найти объявление...")

        search_input.click()
        search_input.fill(first_title)
        search_input.press("Enter")
        page.wait_for_timeout(2000)
        filtered_count = page.locator(".ads-page__grid > div").count()
        assert filtered_count > 0, (
            f"По полному названию '{first_title}' ничего не найдено — вероятный баг поиска"
        )
        for i in range(filtered_count):
            card_text = page.locator(".ads-page__grid > div").nth(i).inner_text().lower()
            assert first_title.lower() in card_text, (
                f"Карточка {i} не содержит '{first_title}'"
            )
        search_input.fill("")
        search_input.press("Enter")
        page.wait_for_timeout(600)

        if len(first_title) >= 4:
            partial = first_title[:4]
            search_input.click()
            search_input.fill(partial)
            search_input.press("Enter")
            page.wait_for_timeout(2000)
            pc = page.locator(".ads-page__grid > div").count()
            assert pc > 0, f"По части '{partial}' ничего не найдено"
            search_input.fill("")
            search_input.press("Enter")
            page.wait_for_timeout(600)

        search_input.click()
        search_input.fill("^")
        search_input.press("Enter")
        page.wait_for_timeout(1500)
        assert page.locator(".ads-page__grid > div").count() == 0, (
            "Поиск по '^' вернул результаты"
        )
        search_input.fill("")
        search_input.press("Enter")

    def test_sort_by_date_and_name(self, page: Page):
        """TC-02: сортировка по дате и названию."""
        page.goto(f"{BASE_URL}/ads")
        page.wait_for_selector(".ads-page__title")
        page.wait_for_timeout(800)

        sort_dropdown = page.locator(".ads-page__sort-select")
        cards = page.locator(".ads-page__grid > div")

        def current_titles():
            return [
                extract_title_from_card(cards.nth(i).inner_text()).lower()
                for i in range(cards.count())
            ]

        sort_dropdown.click()
        page.get_by_text("По новизне (сначала старые)", exact=True).last.click()
        page.wait_for_timeout(700)
        expect(sort_dropdown).to_contain_text("сначала старые")
        old_order = current_titles()

        sort_dropdown.click()
        page.get_by_text("По новизне (сначала новые)", exact=True).last.click()
        page.wait_for_timeout(700)
        new_order = current_titles()

        if len(old_order) > 1 and len(set(old_order)) > 1:
            assert old_order != new_order, (
                "Порядок карточек не изменился при смене сортировки по дате"
            )

        sort_dropdown.click()
        page.get_by_text("По названию (А → Я)", exact=True).last.click()
        page.wait_for_timeout(700)
        titles_asc = [t for t in current_titles() if t]
        if len(titles_asc) > 1:
            assert titles_asc == sorted(titles_asc), (
                f"Сортировка А→Я сломана: {titles_asc}"
            )

        sort_dropdown.click()
        page.get_by_text("По названию (Я → А)", exact=True).last.click()
        page.wait_for_timeout(700)
        titles_desc = [t for t in current_titles() if t]
        if len(titles_desc) > 1:
            assert titles_desc == sorted(titles_desc, reverse=True), (
                f"Сортировка Я→А сломана: {titles_desc}"
            )

        sort_dropdown.click()
        page.get_by_text("По новизне (сначала новые)", exact=True).last.click()
        page.wait_for_timeout(500)

    def test_filters_and_reset(self, page: Page):
        """TC-03: переключатель «Только требующие доработок» + сброс."""
        page.goto(f"{BASE_URL}/ads")
        page.wait_for_selector(".ads-page__title")
        page.wait_for_timeout(800)

        revision_toggle = page.locator(".ant-switch")
        revision_toggle.click()
        page.wait_for_timeout(700)
        assert "ant-switch-checked" in (revision_toggle.get_attribute("class") or ""), (
            "Переключатель не включился"
        )

        cards = page.locator(".ads-page__grid > div")
        for i in range(cards.count()):
            text = cards.nth(i).inner_text().lower()
            assert "требует доработок" in text or "доработ" in text, (
                f"Карточка {i} не содержит метку «Требует доработок»"
            )

        page.get_by_role("button", name="Сбросить фильтры").click()
        page.wait_for_timeout(700)
        expect(revision_toggle).not_to_have_class("ant-switch-checked")

    def test_category_filters(self, page: Page):
        """TC-04: фильтрация по категориям."""
        page.goto(f"{BASE_URL}/ads")
        page.wait_for_selector(".ads-page__title")
        page.wait_for_timeout(1000)

        categories = ["Транспорт", "Недвижимость", "Электроника"]

        def cb(name):
            return page.get_by_role("checkbox", name=name)

        def all_cards_contain_any(cats):
            cards = page.locator(".ads-page__grid > div")
            for i in range(cards.count()):
                text = cards.nth(i).inner_text()
                if not any(c in text for c in cats):
                    return False
            return True

        for cat in categories:
            cb(cat).click()
            page.wait_for_timeout(500)
            assert all_cards_contain_any([cat]), f"Фильтр '{cat}' пропускает чужое"
            cb(cat).click()
            page.wait_for_timeout(400)

        for cat in categories[:2]:
            cb(cat).click()
        page.wait_for_timeout(500)
        assert all_cards_contain_any(categories[:2]), "Комбинация фильтров работает неверно"
        for cat in categories[:2]:
            cb(cat).click()
        page.wait_for_timeout(400)

        for cat in categories:
            cb(cat).click()
        page.wait_for_timeout(500)
        assert all_cards_contain_any(categories), "Все три категории работают неверно"

        page.get_by_role("button", name="Сбросить фильтры").click()
        page.wait_for_timeout(500)
        for cat in categories:
            expect(cb(cat)).not_to_be_checked()

    def test_pagination_and_ad_navigation(self, page: Page):
        """TC-05: пагинация + переход в объявление."""
        page.goto(f"{BASE_URL}/ads")
        page.wait_for_selector(".ads-page__title")
        page.wait_for_timeout(700)

        page_two = page.locator(".ads-page__pagination").get_by_text("2").first
        if page_two.count() == 0:
            pytest.skip("Пагинация отсутствует — недостаточно объявлений на стенде")
        page_two.click()
        page.wait_for_timeout(900)

        cards = page.locator(".ads-page__grid > div")
        assert cards.count() > 0, "На второй странице нет карточек"
        cards.first.click(force=True)
        page.wait_for_url(re.compile(r"/ads/\d+"), timeout=10000)

    def test_edit_validation_save_cancel(self, page: Page):
        """TC-06: валидация, сохранение, отмена, восстановление цены."""
        page.goto(f"{BASE_URL}/ads")
        page.wait_for_selector(".ads-page__title")
        page.wait_for_timeout(1200)

        page.locator(".ads-page__grid > div").first.click()
        page.wait_for_url(re.compile(r"/ads/\d+"))
        ad_id = re.search(r"/ads/(\d+)", page.url).group(1)

        page.goto(f"{BASE_URL}/ads/{ad_id}/edit")
        price_input = page.locator(".edit-form .ant-input-number-input")
        original_price = price_input.input_value()

        price_input.fill("")
        page.get_by_role("button", name="Сохранить").click()
        expect(page.locator(".ant-form-item-explain-error")).to_be_visible(timeout=3000)

        price_input.fill("1")
        page.get_by_role("button", name="Сохранить").click()
        page.wait_for_url(re.compile(r"/ads/\d+"), timeout=10000)

        page.goto(f"{BASE_URL}/ads/{ad_id}/edit")
        page.get_by_role("button", name="Отменить").click()
        ok_btn = page.get_by_role("button", name="OK")
        if ok_btn.count() > 0:
            ok_btn.click()
        page.wait_for_url(re.compile(r"/ads/\d+"), timeout=10000)

        page.goto(f"{BASE_URL}/ads/{ad_id}/edit")
        price_input = page.locator(".edit-form .ant-input-number-input")
        price_input.fill(original_price if original_price.strip() else "1")
        page.get_by_role("button", name="Сохранить").click()
        page.wait_for_url(re.compile(r"/ads/\d+"), timeout=10000)

    def test_ai_tools(self, page: Page):
        """TC-07: AI-инструменты. Проверяем появление ВИДИМОГО попоувера."""
        page.goto(f"{BASE_URL}/ads")
        page.wait_for_selector(".ads-page__title")
        page.wait_for_timeout(1200)

        page.locator(".ads-page__grid > div").first.click()
        page.wait_for_url(re.compile(r"/ads/\d+"))
        ad_id = re.search(r"/ads/(\d+)", page.url).group(1)
        page.goto(f"{BASE_URL}/ads/{ad_id}/edit")

        page.get_by_role("button", name="Узнать цену").click()
        visible_price = page.locator(".ant-popover:not(.ant-popover-hidden)").first
        expect(visible_price).to_be_visible(timeout=10000)
        close_btn = page.get_by_role("button", name=re.compile(r"Закрыть"))
        if close_btn.count() > 0:
            close_btn.first.click()
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(800)

        page.get_by_role(
            "button", name=re.compile(r"(Придумать|Улучшить) описание")
        ).click()
        visible_desc = page.locator(".ant-popover:not(.ant-popover-hidden)").first
        expect(visible_desc).to_be_visible(timeout=10000)


class TestAdsMobile:
    def test_theme_switch(self, page: Page):
        """TC-08: переключение темы."""
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{BASE_URL}/ads")
        page.wait_for_selector(".ads-page__title")
        page.wait_for_timeout(800)

        theme_toggle = page.locator(".app-header__theme")
        expect(theme_toggle).to_be_visible()

        app_div = page.locator(".app")
        theme_toggle.click()
        page.wait_for_timeout(600)
        assert "dark" in (app_div.get_attribute("class") or ""), (
            "Класс 'dark' не появился после клика"
        )

        theme_toggle.click()
        page.wait_for_timeout(600)
        assert "dark" not in (app_div.get_attribute("class") or ""), (
            "Класс 'dark' не убрался после второго клика"
        )
