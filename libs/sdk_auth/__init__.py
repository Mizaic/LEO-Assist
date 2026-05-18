"""LEO widget SDK auth helpers.

Atlas trace:
  DO: DO-5C88CA8F
  DI: DI-A1206416
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-5C88CA8F")

Mints and verifies short-lived widget tokens used by the embeddable
SBAR widget (services/widget-sdk). Tokens are HS256 JWTs with
audience "leo-widget", a hard 15-minute TTL ceiling, and a
per-assessment scope claim. The widget never sees the signing key;
only the LEO API does.
"""

from libs.sdk_auth.widget_token import (
    WIDGET_AUDIENCE,
    WIDGET_TOKEN_MAX_TTL_SECONDS,
    WidgetClaims,
    WidgetTokenError,
    WidgetTokenResult,
    mint_widget_token,
    verify_widget_token,
)

__all__ = [
    "WIDGET_AUDIENCE",
    "WIDGET_TOKEN_MAX_TTL_SECONDS",
    "WidgetClaims",
    "WidgetTokenError",
    "WidgetTokenResult",
    "mint_widget_token",
    "verify_widget_token",
]
