---
name: contract-first-client
description: Use whenever B-line frontend or extension code builds or changes an interaction with a backend API.
---

# Contract-first client

1. Base every request and response on an approved OpenAPI document or JSON Schema.
2. Use a clearly labelled Mock while an endpoint is unavailable; never guess fields in a page.
3. Map backend error codes through one shared client mapping.
4. Record compatibility and migration behavior before consuming a contract change.

Do not directly modify A-line or C-line backend code.
