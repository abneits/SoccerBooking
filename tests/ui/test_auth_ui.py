"""
UI tests — Authentication (Playwright)
Exercises the real browser: form rendering, validation feedback, redirects.
"""

import pytest
from tests.helpers import db_create_user, ui_login
from tests.conftest import APP_URL


class TestLoginPageUI:
    async def test_login_page_loads(self, page):
        await page.goto("/login")
        assert "login" in page.url.lower() or await page.title() != ""

    async def test_login_page_has_username_input(self, page):
        await page.goto("/login")
        assert await page.locator('input[name="username"]').is_visible()

    async def test_login_page_has_pin_input(self, page):
        await page.goto("/login")
        pin = page.locator('input[name="pin"]')
        assert await pin.is_visible()
        pin_type = await pin.get_attribute("type")
        assert pin_type == "password"

    async def test_login_page_has_submit_button(self, page):
        await page.goto("/login")
        assert await page.locator('button[type="submit"]').is_visible()

    async def test_login_page_has_register_link(self, page):
        await page.goto("/login")
        link = page.locator('a[href="/register"]')
        assert await link.is_visible()

    async def test_bad_credentials_shows_error_inline(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await page.goto("/login")
        await page.fill('input[name="username"]', "alice")
        await page.fill('input[name="pin"]', "9999")
        await page.click('button[type="submit"]')
        # Stays on login, shows error
        await page.wait_for_load_state("networkidle")
        assert "/login" in page.url
        body = await page.content()
        assert any(word in body.lower() for word in ["invalid", "incorrect", "error", "invalide"])

    async def test_unknown_user_shows_error(self, page):
        await page.goto("/login")
        await page.fill('input[name="username"]', "nobody_xyz")
        await page.fill('input[name="pin"]', "1234")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        assert "/login" in page.url

    async def test_successful_login_redirects_to_home(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        assert page.url.rstrip("/") == APP_URL or page.url.endswith("/")

    async def test_home_visible_after_login(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        content = await page.content()
        # Home page has the slot panel or the "no slot" message
        assert "slot" in content.lower() or "créneau" in content.lower() or "lundi" in content.lower()

    async def test_logout_link_visible_after_login(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        logout = page.locator('a[href="/logout"]')
        assert await logout.is_visible()

    async def test_clicking_logout_redirects_to_login(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        await page.click('a[href="/logout"]')
        await page.wait_for_url("**/login**", timeout=5000)
        assert "/login" in page.url

    async def test_after_logout_home_redirects_to_login(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        await page.goto("/logout")
        await page.goto("/")
        await page.wait_for_url("**/login**", timeout=5000)
        assert "/login" in page.url


class TestRegisterPageUI:
    async def test_register_page_loads(self, page):
        await page.goto("/register")
        assert await page.locator('input[name="username"]').is_visible()
        assert await page.locator('input[name="pin"]').is_visible()

    async def test_register_page_has_login_link(self, page):
        await page.goto("/register")
        link = page.locator('a[href="/login"]')
        assert await link.is_visible()

    async def test_register_with_short_pin_shows_error(self, page):
        await page.goto("/register")
        await page.fill('input[name="username"]', "newuser")
        await page.fill('input[name="pin"]', "12")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        assert "/register" in page.url
        body = await page.content()
        assert any(word in body.lower() for word in ["pin", "chiffre", "digit", "error"])

    async def test_register_with_non_numeric_pin_shows_error(self, page):
        await page.goto("/register")
        await page.fill('input[name="username"]', "newuser")
        await page.fill('input[name="pin"]', "abcd")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        assert "/register" in page.url

    async def test_register_with_empty_username_shows_error(self, page):
        await page.goto("/register")
        await page.fill('input[name="pin"]', "1234")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        assert "/register" in page.url

    async def test_successful_registration_redirects_to_login(self, page):
        await page.goto("/register")
        await page.fill('input[name="username"]', "brandnewuser")
        await page.fill('input[name="pin"]', "4321")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/login**", timeout=5000)
        assert "/login" in page.url

    async def test_duplicate_username_shows_error(self, page, db_pool):
        await db_create_user(db_pool, "existinguser")
        await page.goto("/register")
        await page.fill('input[name="username"]', "existinguser")
        await page.fill('input[name="pin"]', "5678")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        assert "/register" in page.url
        body = await page.content()
        assert any(word in body.lower() for word in ["taken", "pris", "already", "exist", "error"])

    async def test_can_login_after_registering(self, page):
        await page.goto("/register")
        await page.fill('input[name="username"]', "freshuser")
        await page.fill('input[name="pin"]', "7777")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/login**", timeout=5000)
        await page.fill('input[name="username"]', "freshuser")
        await page.fill('input[name="pin"]', "7777")
        await page.click('button[type="submit"]')
        await page.wait_for_url("**/", timeout=5000)
        assert page.url.rstrip("/") == APP_URL or page.url.endswith("/")


class TestProfilePageUI:
    async def test_profile_page_shows_username(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        await page.goto("/profile")
        content = await page.content()
        assert "alice" in content

    async def test_profile_shows_admin_badge(self, page, db_pool):
        await db_create_user(db_pool, "boss", pin="1234", role="admin")
        await ui_login(page, "boss", "1234")
        await page.goto("/profile")
        content = await page.content()
        assert "admin" in content.lower()

    async def test_pin_change_form_is_present(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        await page.goto("/profile")
        assert await page.locator('input[name="current_pin"]').is_visible()
        assert await page.locator('input[name="new_pin"]').is_visible()
        assert await page.locator('input[name="confirm_pin"]').is_visible()

    async def test_pin_change_success_shows_message(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        await page.goto("/profile")
        await page.fill('input[name="current_pin"]', "1234")
        await page.fill('input[name="new_pin"]', "5678")
        await page.fill('input[name="confirm_pin"]', "5678")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        content = await page.content()
        assert any(word in content.lower() for word in ["success", "updated", "mis à jour", "ok"])

    async def test_pin_change_wrong_current_shows_error(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        await page.goto("/profile")
        await page.fill('input[name="current_pin"]', "9999")
        await page.fill('input[name="new_pin"]', "5678")
        await page.fill('input[name="confirm_pin"]', "5678")
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        content = await page.content()
        assert any(word in content.lower() for word in ["incorrect", "error", "wrong", "invalide"])
