"""The number formats an admin can choose for BitNet, each with an estimate of what it takes, and whether this machine can
run it. Both formats use the same downloaded weights (about 1.2 GB); only the memory and the speed differ. CPU only.

The memory figures are the ones this service's README and `dtype` setting already give: about 5 GB unpacked as
`bfloat16`, and about 1.6 times that as `float32`. They are not measured here, and the page says so.

shortcut: free memory is read when the page is opened; two services starting at once can both see the same free memory."""

from __future__ import annotations

from typing import Any

DISK_MB = 1200
# (dtype, estimated memory in MB, note)
FORMATS = (
    ("bfloat16", 5000, "The default: the least memory."),
    ("float32", 8000, "Faster on CPUs without native bfloat16 maths; about 1.6 times the memory."),
)
FREE_SHARE = 0.85  # keep some memory for the rest of the machine


def fit(need_mb: int, hardware: dict[str, Any]) -> tuple[bool | None, str]:
    """(fits, reason). `None` = the free memory could not be read, so nothing is claimed."""
    free = hardware.get("ram_available_mb")
    if free is None:
        return None, "Free memory could not be read."
    ok = need_mb <= free * FREE_SHARE
    return ok, "" if ok else f"Needs about {need_mb} MB of memory; {free} MB is free."


def listing(hardware: dict[str, Any], current: str, downloaded: bool) -> list[dict[str, Any]]:
    """Every format, smallest first. `current` is the dtype in use; it always fits, because the memory it holds
    already counts as used. `downloaded` is whether the weights are on disk (the same for both formats)."""
    rows = []
    for dtype, need, note in FORMATS:
        in_use = dtype == current
        fits, reason = (True, "") if in_use else fit(need, hardware)
        rows.append({"title": f"{dtype} · CPU",
                     "detail": f"about {need} MB memory · {DISK_MB} MB download{' · downloaded' if downloaded else ''} · {note}",
                     "id": dtype, "name": dtype, "dtype": dtype, "estimated_mb": need, "disk_mb": DISK_MB,
                     "fits": fits, "reason": reason, "downloaded": downloaded, "current": in_use, "note": note})
    return sorted(rows, key=lambda row: row["estimated_mb"])


def find(rows: list[dict[str, Any]], variant_id: str) -> dict[str, Any] | None:
    return next((row for row in rows if row["id"] == variant_id), None)
