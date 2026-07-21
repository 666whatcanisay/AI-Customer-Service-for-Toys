---
name: browser-adapter-builder
description: Use when creating or changing a browser-platform adapter, selector set, page parser, or manual-input fallback.
---

# Browser adapter builder

1. Keep platform adapters separate from core client logic and manage selectors centrally.
2. Fail safely when the page changes; fall back to manual input after automatic reading fails.
3. Limit the first delivery to one platform.

Never read or store cookies, passwords, or tokens, and never send a message automatically.
