"""
UI tests — Admin panel (Playwright)
Exercises the admin dashboard: access control, slot management,
booking management, user management.
"""

import pytest
from tests.helpers import (
    db_create_user,
    db_create_slot,
    db_create_booking,
    db_count_bookings,
    db_get_user,
    db_get_slot,
    decode_data,
    ui_login,
)

SLOT_PAST = "2020-03-25"


async def ui_login_admin(page, db_pool):
    """Create and log in as testadmin."""
    # admin_client fixture already creates testadmin, but for UI tests we need page login
    await db_create_user(db_pool, "uiadmin", pin="0000", role="admin")
    await ui_login(page, "uiadmin", "0000")
    await page.goto("/admin")


class TestAdminAccessUI:
    async def test_unauthenticated_redirected_to_login(self, page):
        await page.goto("/admin")
        await page.wait_for_url("**/login**", timeout=5000)
        assert "/login" in page.url

    async def test_player_redirected_to_home(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234", role="player")
        await ui_login(page, "alice", "1234")
        await page.goto("/admin")
        await page.wait_for_url("**/", timeout=5000)
        assert "/admin" not in page.url

    async def test_admin_can_access_panel(self, page, db_pool):
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "administration" in content.lower() or "admin" in content.lower()

    async def test_admin_panel_shows_user_section(self, page, db_pool):
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "utilisateur" in content.lower() or "user" in content.lower()

    async def test_admin_panel_shows_slot_section(self, page, db_pool):
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "créneau" in content.lower() or "slot" in content.lower()

    async def test_admin_panel_shows_all_users(self, page, db_pool):
        await db_create_user(db_pool, "visible_bob", pin="1234")
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "visible_bob" in content

    async def test_admin_panel_shows_slot_dates(self, page, db_pool):
        await db_create_slot(db_pool, "2020-03-25")
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "2020-03-25" in content

    async def test_admin_has_back_to_home_link(self, page, db_pool):
        await ui_login_admin(page, db_pool)
        link = page.locator('a[href="/"]')
        assert await link.count() > 0

    async def test_admin_has_logout_link(self, page, db_pool):
        await ui_login_admin(page, db_pool)
        link = page.locator('a[href="/logout"]')
        assert await link.is_visible()


class TestSlotManagementUI:
    async def test_pre_cancel_slot_form_present(self, page, db_pool):
        await ui_login_admin(page, db_pool)
        date_input = page.locator('input[name="date"]')
        assert await date_input.is_visible()

    async def test_pre_cancel_slot_by_date(self, page, db_pool):
        await ui_login_admin(page, db_pool)
        await page.fill('input[name="date"]', "2099-07-02")
        await page.fill('input[name="reason"]', "Test UI cancel")
        await page.click('button:has-text("Annuler / Pré-annuler")')
        await page.wait_for_url("**/admin**", timeout=5000)
        row = await db_pool.fetchrow(
            "SELECT data FROM slots WHERE data->>'date' = '2099-07-02'"
        )
        assert row is not None
        assert decode_data(row)["status"] == "cancelled"

    async def test_current_slot_displayed_when_exists(self, page, db_pool):
        await db_create_slot(db_pool, "2099-03-25")
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "2099-03-25" in content

    async def test_cancel_current_slot_button_present_for_non_cancelled(self, page, db_pool):
        await db_create_slot(db_pool, "2099-03-25")
        await ui_login_admin(page, db_pool)
        cancel_btn = page.locator('button.danger:has-text("Annuler ce créneau")')
        assert await cancel_btn.count() > 0

    async def test_cancel_current_slot_by_button(self, page, db_pool):
        slot = await db_create_slot(db_pool, "2099-03-25")
        await ui_login_admin(page, db_pool)
        # Fill reason and click cancel
        reason_inputs = page.locator('input[name="reason"]')
        # The second reason input is for the current slot cancel form
        await reason_inputs.last.fill("UI test cancel")
        await page.click('button.danger:has-text("Annuler ce créneau")')
        await page.wait_for_url("**/admin**", timeout=5000)
        updated = await db_get_slot(db_pool, slot["id"])
        assert updated["status"] == "cancelled"

    async def test_already_cancelled_slot_hides_cancel_button(self, page, db_pool):
        await db_create_slot(db_pool, "2099-03-25", status="cancelled")
        await ui_login_admin(page, db_pool)
        content = await page.content()
        # The cancel-this-slot button should not render for already-cancelled slots
        cancel_btns = await page.locator('button.danger:has-text("Annuler ce créneau")').count()
        assert cancel_btns == 0


class TestBookingManagementUI:
    async def test_booking_list_shown_for_active_slot(self, page, db_pool):
        await db_create_slot(db_pool, "2099-03-25")
        await ui_login_admin(page, db_pool)
        content = await page.content()
        # Booking management section should appear
        assert "réservation" in content.lower() or "booking" in content.lower()

    async def test_empty_booking_list_shows_message(self, page, db_pool):
        await db_create_slot(db_pool, "2099-03-25")
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "aucune réservation" in content.lower() or "no booking" in content.lower()

    async def test_booking_appears_in_list(self, page, db_pool):
        user = await db_create_user(db_pool, "bob_player", pin="1234")
        slot = await db_create_slot(db_pool, SLOT_PAST)
        await db_create_booking(db_pool, slot["id"], user["id"], user["id"])
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "bob_player" in content

    async def test_guest_booking_shown_with_guest_name(self, page, db_pool):
        user = await db_create_user(db_pool, "alice", pin="1234")
        slot = await db_create_slot(db_pool, SLOT_PAST)
        await db_create_booking(
            db_pool, slot["id"], None, user["id"], booking_type="guest", guest_name="Jean Invite"
        )
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "Jean Invite" in content

    async def test_cancel_button_absent_for_frozen_slot(self, page, db_pool):
        """FROZEN slot: admin cancel buttons should NOT appear."""
        user = await db_create_user(db_pool, "bob_player", pin="1234")
        slot = await db_create_slot(db_pool, SLOT_PAST)  # FROZEN
        await db_create_booking(db_pool, slot["id"], user["id"], user["id"])
        await ui_login_admin(page, db_pool)
        # The ✕ cancel buttons are only shown for open/closed state
        cancel_x = page.locator('button.danger.small')
        count = await cancel_x.count()
        assert count == 0


class TestUserManagementUI:
    async def test_user_list_shows_all_users(self, page, db_pool):
        await db_create_user(db_pool, "player1", pin="1234")
        await db_create_user(db_pool, "player2", pin="1234")
        await ui_login_admin(page, db_pool)
        content = await page.content()
        assert "player1" in content
        assert "player2" in content

    async def test_user_row_shows_role_badge(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234", role="player")
        await ui_login_admin(page, db_pool)
        badge = page.locator(".role-badge").first
        assert await badge.is_visible()

    async def test_reset_pin_form_present(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login_admin(page, db_pool)
        pin_inputs = page.locator('input[name="new_pin"]')
        assert await pin_inputs.count() > 0

    async def test_pin_input_is_type_password(self, page, db_pool):
        """TMPL-4 fix: new_pin field must be type=password."""
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login_admin(page, db_pool)
        pin_input = page.locator('input[name="new_pin"]').first
        input_type = await pin_input.get_attribute("type")
        assert input_type == "password"

    async def test_reset_pin_via_ui(self, page, db_pool):
        bob = await db_create_user(db_pool, "bob_pin_test", pin="1234")
        await ui_login_admin(page, db_pool)
        # Find bob's row and fill PIN reset
        # Use the hidden user_id input to locate the right form
        row_form = page.locator(
            f'form[action="/admin/user/reset-pin"] input[value="{bob["id"]}"]'
        ).locator("xpath=../..") # parent form
        await row_form.locator('input[name="new_pin"]').fill("8888")
        await row_form.locator('button[type="submit"]').click()
        await page.wait_for_url("**/admin**", timeout=5000)
        updated = await db_get_user(db_pool, bob["id"])
        assert updated["pin"] == "8888"

    async def test_role_select_present(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login_admin(page, db_pool)
        role_select = page.locator('select[name="role"]').first
        assert await role_select.is_visible()

    async def test_change_role_via_ui(self, page, db_pool):
        bob = await db_create_user(db_pool, "bob_role_test", pin="1234", role="player")
        await ui_login_admin(page, db_pool)
        role_form = page.locator(
            f'form[action="/admin/user/set-role"] input[value="{bob["id"]}"]'
        ).locator("xpath=../..") # parent form
        await role_form.locator('select[name="role"]').select_option("admin")
        await role_form.locator('button[type="submit"]').click()
        await page.wait_for_url("**/admin**", timeout=5000)
        updated = await db_get_user(db_pool, bob["id"])
        assert updated["role"] == "admin"

    async def test_delete_button_present(self, page, db_pool):
        await db_create_user(db_pool, "deleteable", pin="1234")
        await ui_login_admin(page, db_pool)
        delete_btns = page.locator('form[action="/admin/user/delete"] button')
        assert await delete_btns.count() > 0

    async def test_delete_user_confirm_dialog_fired(self, page, db_pool):
        """Clicking delete triggers a JS confirm dialog."""
        await db_create_user(db_pool, "to_delete", pin="1234")
        await ui_login_admin(page, db_pool)

        dialog_fired = []

        def handle_dialog(dialog):
            dialog_fired.append(dialog.message)
            # Dismiss the dialog (cancel the delete)
            import asyncio
            asyncio.ensure_future(dialog.dismiss())

        page.on("dialog", handle_dialog)

        delete_btn = page.locator(
            'form[action="/admin/user/delete"] button'
        ).first
        await delete_btn.click()

        await page.wait_for_timeout(500)
        assert len(dialog_fired) > 0

    async def test_confirm_dialog_contains_username(self, page, db_pool):
        await db_create_user(db_pool, "named_user", pin="1234")
        await ui_login_admin(page, db_pool)

        dialog_messages = []

        def handle_dialog(dialog):
            dialog_messages.append(dialog.message)
            import asyncio
            asyncio.ensure_future(dialog.dismiss())

        page.on("dialog", handle_dialog)

        delete_btn = page.locator(
            'form[action="/admin/user/delete"] button:has-text("Supprimer")'
        ).first
        await delete_btn.click()
        await page.wait_for_timeout(500)
        assert any("named_user" in msg for msg in dialog_messages)

    async def test_dismiss_confirm_does_not_delete_user(self, page, db_pool):
        bob = await db_create_user(db_pool, "safe_bob", pin="1234")
        await ui_login_admin(page, db_pool)

        def handle_dialog(dialog):
            import asyncio
            asyncio.ensure_future(dialog.dismiss())

        page.on("dialog", handle_dialog)

        delete_btn = page.locator(
            f'form[action="/admin/user/delete"] input[value="{bob["id"]}"]'
        ).locator("xpath=../..").locator('button[type="submit"]')
        await delete_btn.click()
        await page.wait_for_timeout(500)
        row = await db_get_user(db_pool, bob["id"])
        assert row is not None

    async def test_accept_confirm_deletes_user(self, page, db_pool):
        bob = await db_create_user(db_pool, "bye_bob", pin="1234")
        await ui_login_admin(page, db_pool)

        def handle_dialog(dialog):
            import asyncio
            asyncio.ensure_future(dialog.accept())

        page.on("dialog", handle_dialog)

        delete_btn = page.locator(
            f'form[action="/admin/user/delete"] input[value="{bob["id"]}"]'
        ).locator("xpath=../..").locator('button[type="submit"]')
        await delete_btn.click()
        await page.wait_for_url("**/admin**", timeout=5000)
        row = await db_get_user(db_pool, bob["id"])
        assert row is None
