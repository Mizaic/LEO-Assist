"""Shared slowapi rate-limiter instance.

Atlas trace:
  DO: DO-19FA25C3
  DI: DI-727C94B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-19FA25C3")

Centralised here to avoid circular imports between main.py and routers.
Import this module in main.py to attach the limiter to the app, and in
individual routers to apply per-endpoint @limiter.limit() decorators.
"""

from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[os.getenv("RATE_LIMIT_DEFAULT", "120/minute")],
)
