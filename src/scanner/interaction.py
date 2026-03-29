"""
InteractionEngine — Deep Behavioral Exploration
Phases (run in order to maximise API call coverage):
  0. Dismiss modals / cookie banners
  1. Scroll to trigger lazy-load
  2. Click navigation / menu items (reveals sub-pages & their API calls)
  3. Click tabs, accordions, dropdowns (reveals more content/API calls)
  4. Fill & submit forms (search, filters, comments) — triggers backend calls
  5. Click action buttons (Save, Send, Add, etc.)
Each phase waits for network to settle so the API collector in crawler can capture all resulting requests.
"""
from playwright.async_api import Page
from src.core.logger import setup_logger
from urllib.parse import urlparse

# ── Scope guard: domains that are NEVER part of the target application ─────────
# Clicking links to these would send the browser outside the scan scope.
_EXTERNAL_DOMAINS = {
    # Social media
    "facebook.com", "fb.com", "twitter.com", "x.com", "instagram.com",
    "linkedin.com", "tiktok.com", "youtube.com", "pinterest.com",
    "reddit.com", "discord.com", "telegram.org", "t.me",
    "snapchat.com", "whatsapp.com", "line.me", "weibo.com",
    # Search / ad engines
    "google.com", "google.co.th", "bing.com", "yahoo.com", "baidu.com",
    "duckduckgo.com", "yandex.com",
    # Analytics & tracking
    "analytics.google.com", "googletagmanager.com", "googleadservices.com",
    "doubleclick.net", "hotjar.com", "mixpanel.com", "segment.io",
    "amplitude.com", "clarity.ms", "fullstory.com",
    # CDN / infra (no user data)
    "cloudflare.com", "fastly.com", "akamaihd.net", "cdn.jsdelivr.net",
    "unpkg.com", "cdnjs.cloudflare.com",
    # Payment / identity (never scan these)
    "paypal.com", "stripe.com", "omise.co", "auth0.com", "okta.com",
    "accounts.google.com", "login.microsoftonline.com",
    # Maps
    "maps.googleapis.com", "maps.google.com", "openstreetmap.org",
}

# Selectors that would navigate away / log the user out — skip these
_DANGEROUS_TEXT = ("log out", "logout", "sign out", "signout", "delete account",
                   "register", "sign up", "create account", "exit", "quit")

_NAV_SELECTORS = (
    "nav a:visible",
    "[role='navigation'] a:visible",
    "header a:visible",
    ".navbar a:visible",
    ".sidebar a:visible",
    ".menu a:visible",
    "[role='menuitem']:visible",
    "[role='tab']:visible",
)

_TAB_SELECTORS = (
    "[role='tab']:visible",
    ".tab:visible",
    ".tabs li:visible",
    "button[data-tab]:visible",
    ".accordion-header:visible",
    "summary:visible",          # <details><summary> pattern
)

_FORM_SELECTORS = "input:visible:not([type='hidden']):not([type='submit']):not([type='radio']):not([type='checkbox']), textarea:visible"

_ACTION_BUTTON_SELECTORS = (
    "button:visible",
    "[role='button']:visible",
    "input[type='submit']:visible",
    "input[type='button']:visible",
)

_ACTION_TEXT_WHITELIST = ("search", "find", "filter", "apply", "show", "load",
                          "submit", "send", "save", "add", "create", "post",
                          "go", "ok", "confirm", "next", "get", "fetch", "view")

_CLOSE_TEXT_TRIGGERS = ("close", "dismiss", "accept", "got it", "okay", "agree",
                        "accept all", "allow", "continue", ">", "×", "✕")


class InteractionEngine:
    def __init__(self, logger=None):
        self.logger = logger or setup_logger("Crawler")
        self._target_origin: str = ""  # set from _process_url before each page

    # ── Scope-guard helpers ────────────────────────────────────────────────────
    def _is_external_href(self, href: str) -> bool:
        """Return True if href points to a known external/social domain."""
        if not href:
            return False
        try:
            parsed = urlparse(href if href.startswith("http") else "http://" + href)
            host = parsed.netloc.lower().lstrip("www.")
            # Exact or subdomain match
            return any(
                host == d or host.endswith("." + d)
                for d in _EXTERNAL_DOMAINS
            )
        except:
            return False

    async def _guard_origin(self, page: Page) -> bool:
        """
        If the page has navigated outside the target origin, go back.
        Returns True if we had to recover (i.e. the click took us away).
        """
        if not self._target_origin:
            return False
        try:
            current = page.url
            if not current.startswith(self._target_origin):
                self.logger.warning(
                    f"    [⚠️ Scope Guard] Left target scope! ({current[:60]}) → going back"
                )
                await page.go_back(timeout=4000)
                await page.wait_for_load_state("networkidle", timeout=3000)
                return True
        except: pass
        return False

    async def trigger_smart_interaction(self, page: Page):
        self.logger.info("    [..] Executing behavioral exploration...")

        # Phase 0 — Dismiss obstacles (modals, cookie banners)
        await self._dismiss_obstacles(page)

        # Phase 1 — Scroll to trigger lazy-loading
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(800)
            await page.evaluate("window.scrollTo(0, 0)")
        except: pass

        # Phase 2 — Click navigation / menu items
        await self._click_nav_items(page)

        # Phase 3 — Click tabs, accordions, dropdowns
        await self._click_tabs_and_drops(page)

        # Phase 4 — Fill and submit forms (triggers backend search/filter APIs)
        await self._fill_and_submit_forms(page)

        # Phase 5 — Click action buttons (Save, Send, Add, etc.)
        await self._click_action_buttons(page)

    # ── Phase 0 ────────────────────────────────────────────────────────────────
    async def _dismiss_obstacles(self, page: Page):
        """Click any visible close/accept buttons on modals or cookie banners."""
        try:
            selector = ", ".join(
                f"button:has-text('{t}')" for t in _CLOSE_TEXT_TRIGGERS
            ) + ", [aria-label='Close']:visible, .modal-close:visible, .cookie-accept:visible"
            elements = await page.locator(selector).all()
            for el in elements[:5]:
                try:
                    if await el.is_visible():
                        await el.click(timeout=800)
                        await page.wait_for_timeout(400)
                except: continue
        except: pass

    # ── Phase 2 ────────────────────────────────────────────────────────────────
    async def _click_nav_items(self, page: Page):
        """Click navigation links that stay within the target origin."""
        seen_hrefs: set = set()

        for sel in _NAV_SELECTORS:
            try:
                elements = await page.locator(sel).all()
                for el in elements[:8]:
                    try:
                        text = (await el.inner_text()).strip().lower()
                        if any(d in text for d in _DANGEROUS_TEXT):
                            continue

                        href = await el.get_attribute("href") or ""

                        # Block known external domains by href
                        if self._is_external_href(href):
                            self.logger.debug(f"    [Scope] Blocked external nav href: {href[:60]}")
                            continue

                        # Block absolute links that leave the target origin
                        if href.startswith("http") and self._target_origin:
                            if not href.startswith(self._target_origin):
                                continue

                        if href in seen_hrefs:
                            continue
                        seen_hrefs.add(href)

                        await el.click(timeout=1200)
                        await page.wait_for_load_state("networkidle", timeout=3000)
                        await self._guard_origin(page)   # recover if we left the scope
                        await page.keyboard.press("Escape")
                        self.logger.debug(f"    [Nav] Clicked: {text[:40]!r}")
                    except: continue
            except: continue

    # ── Phase 3 ────────────────────────────────────────────────────────────────
    async def _click_tabs_and_drops(self, page: Page):
        """Click tabs, accordions, and dropdown triggers."""
        for sel in _TAB_SELECTORS:
            try:
                elements = await page.locator(sel).all()
                for el in elements[:6]:
                    try:
                        if not await el.is_visible():
                            continue
                        text = (await el.inner_text()).strip().lower()
                        if any(d in text for d in _DANGEROUS_TEXT):
                            continue
                        href = await el.get_attribute("href") or ""
                        if self._is_external_href(href):
                            continue
                        await el.click(timeout=1200)
                        await page.wait_for_timeout(800)
                        await self._guard_origin(page)
                        await page.keyboard.press("Escape")
                        self.logger.debug(f"    [Tab] Clicked: {text[:40]!r}")
                    except: continue
            except: continue

    # ── Phase 4 ────────────────────────────────────────────────────────────────
    async def _fill_and_submit_forms(self, page: Page):
        """Fill visible form inputs with probe values and submit to trigger API calls."""
        # Re-evaluate after nav clicks might have changed the DOM
        try:
            inputs = await page.locator(_FORM_SELECTORS).all()
        except:
            return

        for i, inp in enumerate(inputs[:6]):
            try:
                if not await inp.is_editable():
                    continue

                el_type = (await inp.get_attribute("type") or "text").lower()
                name    = (await inp.get_attribute("name") or
                           await inp.get_attribute("placeholder") or f"field_{i}")

                # Choose a probe value appropriate for the field type
                if el_type in ("email",):
                    probe = "test@example.com"
                elif el_type in ("number", "tel"):
                    probe = "12345"
                elif el_type in ("password",):
                    probe = "T3st!pass"
                elif el_type in ("url",):
                    probe = "http://example.com"
                else:
                    probe = f"test_probe_{i}"

                await inp.fill(probe)
                self.logger.info(f"    [Form] Filled '{name}' with '{probe}'")

                # Press Enter to submit (most common trigger for search/filter)
                await inp.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=3000)
                await page.keyboard.press("Escape")

            except: continue

    # ── Phase 5 ────────────────────────────────────────────────────────────────
    async def _click_action_buttons(self, page: Page):
        """Click buttons whose text suggests they trigger a backend action."""
        for sel in _ACTION_BUTTON_SELECTORS:
            try:
                elements = await page.locator(sel).all()
                for el in elements[:12]:
                    try:
                        if not await el.is_visible():
                            continue
                        text = (await el.inner_text()).strip().lower()
                        if any(d in text for d in _DANGEROUS_TEXT):
                            continue
                        if not any(w in text for w in _ACTION_TEXT_WHITELIST):
                            continue
                        # Check the button's href / action target if any
                        href = await el.get_attribute("href") or ""
                        if self._is_external_href(href):
                            self.logger.debug(f"    [Scope] Blocked external button href: {href[:60]}")
                            continue

                        await el.click(timeout=1200)
                        await page.wait_for_load_state("networkidle", timeout=3000)
                        await self._guard_origin(page)
                        await page.keyboard.press("Escape")
                        self.logger.info(f"    [Action] Clicked button: {text[:40]!r}")

                    except: continue
            except: continue