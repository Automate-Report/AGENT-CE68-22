from playwright.async_api import Page
import re

class ParameterExtractor:
    def __init__(self, logger):
        self.logger = logger

    async def extract_from_dom(self, page: Page) -> dict:
        """
        Extract HTTP-sendable parameters from visible form inputs.

        Rule:
          - HTTP param key  = `name` attribute  (this is what the server receives)
          - `placeholder`, `id`, `aria-label` are display hints — NOT param keys.
            They are stored as metadata so DOM scanner can locate the element,
            but are NOT used as keys when fuzzing HTTP requests.
          - Inputs without a `name` attribute are skipped (they are not submitted
            as part of the form payload and are not exploitable via HTTP).
        """
        params = {}
        selector = "input:visible:not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']), textarea:visible, select:visible"
        elements = await page.locator(selector).all()

        for i, el in enumerate(elements):
            try:
                # ── HTTP param key: ONLY use the `name` attribute ────────────
                name_attr = await el.get_attribute("name")
                if not name_attr or not name_attr.strip():
                    # No name → element is not submitted via normal form POST/GET
                    # Skip it for HTTP fuzzing purposes
                    continue

                # Sanitise: replace non-alphanumeric chars with _
                param_key = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name_attr.strip())

                # ── Metadata: collect display hints for reference / logging ──
                placeholder = await el.get_attribute("placeholder") or ""
                el_id       = await el.get_attribute("id")          or ""
                el_type     = await el.get_attribute("type")        or "text"

                params[param_key] = {
                    "value":       "",          # empty placeholder for fuzzing
                    "type":        el_type,
                    "placeholder": placeholder,
                    "id":          el_id,
                }

                self.logger.debug(
                    f"[ParamExtractor] Found param: name='{param_key}' "
                    f"type='{el_type}' placeholder='{placeholder}'"
                )

            except Exception:
                continue

        return params