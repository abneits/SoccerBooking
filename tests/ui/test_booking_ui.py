"""
UI tests — Booking flow (Playwright)

Uses ui_set_time() / ui_reset_time() to control the app clock via
POST /internal/set-time (requires TESTING=true on the app).

Every test that depends on slot state sets the time explicitly so results
are deterministic regardless of when the suite is run.
"""

import pytest
from tests.helpers import (
    db_create_user,
    db_create_slot,
    db_create_booking,
    db_fill_slot,
    db_count_bookings,
    ui_login,
    ui_set_time,
    ui_reset_time,
    TEST_WEDNESDAY,
    OPEN_TIME,
    CLOSED_TIME,
    FROZEN_TIME,
    PRE_OPEN_TIME,
)


async def _setup_open(page, db_pool, username="alice"):
    """Create user + slot and set clock to OPEN state."""
    user = await db_create_user(db_pool, username, pin="1234")
    slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
    await ui_set_time(page, OPEN_TIME)
    await ui_login(page, username, "1234")
    return user, slot


class TestSlotStateUI:
    async def test_open_state_badge_visible(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await ui_set_time(page, OPEN_TIME)
        await ui_login(page, "alice", "1234")
        badge = page.locator(".state-badge")
        text = await badge.inner_text()
        assert "OPEN" in text.upper()
        await ui_reset_time(page)

    async def test_closed_state_badge_visible(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await ui_set_time(page, CLOSED_TIME)
        await ui_login(page, "alice", "1234")
        badge = page.locator(".state-badge")
        text = await badge.inner_text()
        assert "CLOSED" in text.upper()
        await ui_reset_time(page)

    async def test_frozen_state_badge_visible(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await ui_set_time(page, FROZEN_TIME)
        await ui_login(page, "alice", "1234")
        badge = page.locator(".state-badge")
        text = await badge.inner_text()
        assert "FROZEN" in text.upper()
        await ui_reset_time(page)

    async def test_no_slot_before_monday_noon(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_set_time(page, PRE_OPEN_TIME)
        await ui_login(page, "alice", "1234")
        content = await page.content()
        assert "lundi" in content.lower() or "pas encore" in content.lower()
        await ui_reset_time(page)

    async def test_cancelled_slot_shows_banner(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY, status="cancelled", cancelled_reason="Pluie")
        await ui_set_time(page, OPEN_TIME)
        await ui_login(page, "alice", "1234")
        content = await page.content()
        assert "ANNUL" in content.upper()
        assert "Pluie" in content
        await ui_reset_time(page)


class TestBookButtonUI:
    async def test_book_button_visible_during_open(self, page, db_pool):
        user, slot = await _setup_open(page, db_pool)
        book_btn = page.locator('button:has-text("Réserver ma place")')
        assert await book_btn.is_visible()
        await ui_reset_time(page)

    async def test_book_button_absent_during_closed(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await ui_set_time(page, CLOSED_TIME)
        await ui_login(page, "alice", "1234")
        count = await page.locator('button:has-text("Réserver ma place")').count()
        assert count == 0
        await ui_reset_time(page)

    async def test_book_button_absent_during_frozen(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await ui_set_time(page, FROZEN_TIME)
        await ui_login(page, "alice", "1234")
        count = await page.locator('button:has-text("Réserver ma place")').count()
        assert count == 0
        await ui_reset_time(page)

    async def test_guest_form_visible_during_open(self, page, db_pool):
        user, slot = await _setup_open(page, db_pool)
        guest_input = page.locator('input[name="guest_name"]')
        assert await guest_input.is_visible()
        await ui_reset_time(page)

    async def test_readonly_message_shown_during_closed(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await ui_set_time(page, CLOSED_TIME)
        await ui_login(page, "alice", "1234")
        content = await page.content()
        assert "bientôt" in content.lower() or "fermées" in content.lower()
        await ui_reset_time(page)

    async def test_readonly_message_shown_during_frozen(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await ui_set_time(page, FROZEN_TIME)
        await ui_login(page, "alice", "1234")
        content = await page.content()
        assert "verrouill" in content.lower() or "résultats" in content.lower()
        await ui_reset_time(page)


class TestHTMXBookingFlow:
    async def test_click_book_adds_player_to_list(self, page, db_pool):
        """Click 'Réserver ma place' → alice appears in the list via HTMX swap."""
        user, slot = await _setup_open(page, db_pool)
        await page.click('button:has-text("Réserver ma place")')
        # HTMX swaps #slot-panel → wait for alice to appear
        await page.wait_for_selector('ol.player-list li:has-text("alice")', timeout=5000)
        content = await page.content()
        assert "alice" in content
        await ui_reset_time(page)

    async def test_book_replaces_book_button_with_cancel_button(self, page, db_pool):
        """After booking, the book button is replaced by a cancel button."""
        user, slot = await _setup_open(page, db_pool)
        await page.click('button:has-text("Réserver ma place")')
        await page.wait_for_selector('button:has-text("Annuler ma place")', timeout=5000)
        assert await page.locator('button:has-text("Réserver ma place")').count() == 0
        await ui_reset_time(page)

    async def test_click_cancel_removes_player_from_list(self, page, db_pool):
        """Book, then cancel → alice disappears from the list."""
        user, slot = await _setup_open(page, db_pool)
        # Book
        await page.click('button:has-text("Réserver ma place")')
        await page.wait_for_selector('button:has-text("Annuler ma place")', timeout=5000)
        # Cancel
        await page.click('button:has-text("Annuler ma place")')
        await page.wait_for_selector('button:has-text("Réserver ma place")', timeout=5000)
        # alice should no longer be in the player list items (they show '—')
        player_items = page.locator('ol.player-list li')
        count = await player_items.count()
        assert count == 10
        texts = [await player_items.nth(i).inner_text() for i in range(count)]
        assert all("alice" not in t for t in texts)
        await ui_reset_time(page)

    async def test_add_guest_appears_in_list(self, page, db_pool):
        """Fill guest name and click 'Ajouter un invité' → guest appears via HTMX."""
        user, slot = await _setup_open(page, db_pool)
        await page.fill('input[name="guest_name"]', "Bob Invite")
        await page.click('button:has-text("Ajouter un invité")')
        await page.wait_for_selector(
            'ol.player-list li:has-text("Bob Invite")', timeout=5000
        )
        content = await page.content()
        assert "Bob Invite" in content
        assert "invité" in content.lower()
        await ui_reset_time(page)

    async def test_slot_panel_updates_without_full_page_reload(self, page, db_pool):
        """HTMX swap must not reload the full page (no full navigation)."""
        user, slot = await _setup_open(page, db_pool)
        navigation_events = []
        page.on("framenavigated", lambda f: navigation_events.append(f.url))
        initial_url = page.url
        await page.click('button:has-text("Réserver ma place")')
        await page.wait_for_selector('button:has-text("Annuler ma place")', timeout=5000)
        # URL should not have changed (no page navigation)
        assert page.url == initial_url
        await ui_reset_time(page)

    async def test_confirmed_count_increments_after_booking(self, page, db_pool):
        user, slot = await _setup_open(page, db_pool)
        # Initial count: 0 / 10
        initial = await page.locator(".confirmed-count").inner_text()
        assert "0" in initial
        await page.click('button:has-text("Réserver ma place")')
        await page.wait_for_selector('.confirmed-count:has-text("1")', timeout=5000)
        updated = await page.locator(".confirmed-count").inner_text()
        assert "1" in updated
        await ui_reset_time(page)

    async def test_11th_player_shown_in_waitlist(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        slot = await db_create_slot(db_pool, TEST_WEDNESDAY)
        await db_fill_slot(db_pool, slot["id"], confirmed=10)
        await ui_set_time(page, OPEN_TIME)
        await ui_login(page, "alice", "1234")
        await page.click('button:has-text("Réserver ma place")')
        await page.wait_for_selector('.waitlist', timeout=5000)
        content = await page.content()
        assert "alice" in content
        assert "attente" in content.lower()
        await ui_reset_time(page)

    async def test_cancel_guest_removes_guest_from_list(self, page, db_pool):
        user, slot = await _setup_open(page, db_pool)
        await page.fill('input[name="guest_name"]', "Claire Invite")
        await page.click('button:has-text("Ajouter un invité")')
        await page.wait_for_selector('button:has-text("Annuler mon invité")', timeout=5000)
        await page.click('button:has-text("Annuler mon invité")')
        await page.wait_for_selector('button:has-text("Ajouter un invité")', timeout=5000)
        content = await page.content()
        assert "Claire Invite" not in content
        await ui_reset_time(page)


class TestHTMXLoaded:
    async def test_htmx_is_defined_globally(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await ui_login(page, "alice", "1234")
        is_defined = await page.evaluate("typeof htmx !== 'undefined'")
        assert is_defined is True

    async def test_no_js_errors_on_page_load(self, page, db_pool):
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await ui_set_time(page, OPEN_TIME)
        await ui_login(page, "alice", "1234")
        await page.wait_for_load_state("networkidle")
        assert errors == [], f"JS errors: {errors}"
        await ui_reset_time(page)

    async def test_slot_panel_div_exists(self, page, db_pool):
        await db_create_user(db_pool, "alice", pin="1234")
        await db_create_slot(db_pool, TEST_WEDNESDAY)
        await ui_login(page, "alice", "1234")
        panel = page.locator("#slot-panel")
        assert await panel.count() > 0
