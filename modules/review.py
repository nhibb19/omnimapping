"""Local review workflow helpers for industrial site records."""

import json
import os
from datetime import datetime

from .data_quality import build_research_readiness, site_gap_flags


REVIEW_STATUSES = ("needs_review", "in_review", "confirmed", "blocked")

REVIEW_STATUS_LABELS = {
    "needs_review": "Needs review",
    "in_review": "In review",
    "confirmed": "Confirmed",
    "blocked": "Blocked",
}


def clean_review_text(value):
    """Return a trimmed string for persisted review fields."""
    return str(value or "").strip()


def default_review_status(site):
    """Derive the default review state from existing site confirmation flags."""
    return "needs_review" if site.get("needs_confirmation") else "confirmed"


def validate_review_status(status):
    """Return a valid review status or raise ValueError."""
    status = clean_review_text(status)
    if status not in REVIEW_STATUSES:
        raise ValueError(f"Invalid review status: {status}")
    return status


def review_status_label(status):
    """Return display text for a review status."""
    return REVIEW_STATUS_LABELS.get(status, REVIEW_STATUS_LABELS["needs_review"])


def review_status_tone(status):
    """Return the dashboard color tone for a review status."""
    if status == "confirmed":
        return "positive"
    if status == "blocked":
        return "warning"
    if status in {"needs_review", "in_review"}:
        return "review"
    return "neutral"


def normalize_review_record(record):
    """Return a safe review record shape from persisted JSON."""
    if not isinstance(record, dict):
        record = {}

    status = clean_review_text(record.get("review_status"))
    if status not in REVIEW_STATUSES:
        status = ""

    return {
        "review_status": status,
        "review_notes": clean_review_text(record.get("review_notes")),
        "reviewed_by": clean_review_text(record.get("reviewed_by")),
        "reviewed_at": clean_review_text(record.get("reviewed_at")),
        "source_update_url": clean_review_text(record.get("source_update_url")),
        "source_confidence": clean_review_text(record.get("source_confidence")),
        "last_verified": clean_review_text(record.get("last_verified")),
        "data_gap_notes": clean_review_text(record.get("data_gap_notes")),
        "owner_contact": clean_review_text(record.get("owner_contact")),
        "utilities": clean_review_text(record.get("utilities")),
        "zoning_entitlement": clean_review_text(record.get("zoning_entitlement")),
        "acres": clean_review_text(record.get("acres")),
        "rail_served": clean_review_text(record.get("rail_served")),
        "nearby_class1": clean_review_text(record.get("nearby_class1")),
        "transload_available": clean_review_text(record.get("transload_available")),
        "interstate_access": clean_review_text(record.get("interstate_access")),
        "port_access": clean_review_text(record.get("port_access")),
    }


def load_review_store(filepath):
    """Load persisted review records, falling back to an empty store safely."""
    if not filepath or not os.path.exists(filepath):
        return {}

    try:
        with open(filepath) as review_file:
            data = json.load(review_file)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    return {
        clean_review_text(site_name): normalize_review_record(record)
        for site_name, record in data.items()
        if clean_review_text(site_name)
    }


def save_review_store(filepath, review_store):
    """Persist review records as stable local JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    normalized_store = {
        clean_review_text(site_name): normalize_review_record(record)
        for site_name, record in review_store.items()
        if clean_review_text(site_name)
    }

    temp_filepath = f"{filepath}.tmp"
    with open(temp_filepath, "w") as review_file:
        json.dump(normalized_store, review_file, indent=2, sort_keys=True)
        review_file.write("\n")
    os.replace(temp_filepath, filepath)
    return normalized_store


def merge_review_record(site, review_store):
    """Attach review workflow fields to one site row without mutating source data."""
    merged = site.copy()
    raw_persisted = review_store.get(site.get("site_name", ""))
    has_persisted_review = isinstance(raw_persisted, dict)
    persisted = normalize_review_record(raw_persisted or {})
    status = persisted.get("review_status") or default_review_status(site)
    if has_persisted_review:
        for field in (
            "source_confidence",
            "last_verified",
            "data_gap_notes",
            "owner_contact",
            "utilities",
            "zoning_entitlement",
            "acres",
            "rail_served",
            "nearby_class1",
            "transload_available",
            "interstate_access",
            "port_access",
        ):
            merged[field] = persisted[field]
        if persisted.get("source_update_url"):
            merged["source_url"] = persisted["source_update_url"]
    for field in (
        "review_status",
        "review_notes",
        "reviewed_by",
        "reviewed_at",
        "source_update_url",
    ):
        merged[field] = persisted[field]
    merged["review_status"] = status
    merged["review_status_label"] = review_status_label(status)
    merged["review_status_tone"] = review_status_tone(status)
    merged["data_quality_flags"] = site_gap_flags(merged)
    merged["needs_confirmation"] = bool(merged["data_quality_flags"])
    merged["research_readiness"] = build_research_readiness(merged)
    merged["ready_for_outreach"] = (
        status == "confirmed"
        and merged["research_readiness"].get("label") == "Research Ready"
    )
    return merged


def merge_review_records(sites, review_store):
    """Attach review workflow fields to site rows."""
    return [merge_review_record(site, review_store) for site in sites]


def build_review_update(
    existing_record,
    status,
    notes="",
    reviewed_by="",
    source_update_url="",
    reviewed_at=None,
    source_confidence="",
    last_verified="",
    data_gap_notes="",
    owner_contact="",
    utilities="",
    zoning_entitlement="",
    acres="",
    rail_served="",
    nearby_class1="",
    transload_available="",
    interstate_access="",
    port_access="",
):
    """Build a validated review update record from form input."""
    existing = normalize_review_record(existing_record)
    status = validate_review_status(status)
    existing.update({
        "review_status": status,
        "review_notes": clean_review_text(notes),
        "reviewed_by": clean_review_text(reviewed_by),
        "reviewed_at": reviewed_at or datetime.now().isoformat(timespec="seconds"),
        "source_update_url": clean_review_text(source_update_url),
        "source_confidence": clean_review_text(source_confidence),
        "last_verified": clean_review_text(last_verified),
        "data_gap_notes": clean_review_text(data_gap_notes),
        "owner_contact": clean_review_text(owner_contact),
        "utilities": clean_review_text(utilities),
        "zoning_entitlement": clean_review_text(zoning_entitlement),
        "acres": clean_review_text(acres),
        "rail_served": clean_review_text(rail_served),
        "nearby_class1": clean_review_text(nearby_class1),
        "transload_available": clean_review_text(transload_available),
        "interstate_access": clean_review_text(interstate_access),
        "port_access": clean_review_text(port_access),
    })
    return existing
