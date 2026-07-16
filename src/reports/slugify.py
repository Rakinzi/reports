"""Convert a free-text client name into a filesystem/DB-safe report slug."""

import re


def slugify_client_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "custom_report"
