"""Lightweight data quality helpers for source confidence and freshness."""

from collections import Counter


UNKNOWN_CONFIDENCE = "Unspecified"


def clean_text(value):
    return str(value or "").strip()


def confidence_label(record):
    """Return a stable confidence bucket for reporting."""
    return clean_text(record.get("source_confidence")) or UNKNOWN_CONFIDENCE


def is_yes_no_missing(value):
    value = clean_text(value)
    return value == "" or value.lower() in {"unknown", "n/a", "na", "tbd"}


def note_mentions_approximate(record):
    note = clean_text(record.get("data_gap_notes")).lower()
    return "approx" in note or "city-center" in note or "service-area" in note


def site_gap_flags(site):
    """Flag practical site fields that should be confirmed before outreach."""
    flags = []
    if not clean_text(site.get("acres")):
        flags.append("blank acreage")
    if is_yes_no_missing(site.get("nearby_class1")):
        flags.append("missing Class I detail")
    if is_yes_no_missing(site.get("interstate_access")):
        flags.append("missing interstate detail")
    if is_yes_no_missing(site.get("port_access")):
        flags.append("missing port detail")
    if is_yes_no_missing(site.get("transload_available")):
        flags.append("missing transload detail")
    if clean_text(site.get("data_gap_notes")):
        flags.append("data gap note")
    return flags


def rail_gap_flags(record):
    """Flag practical rail infrastructure fields that should be confirmed."""
    flags = []
    if note_mentions_approximate(record):
        flags.append("approximate coordinates")
    if is_yes_no_missing(record.get("port_nearby")):
        flags.append("missing port detail")
    if is_yes_no_missing(record.get("interstate_access")):
        flags.append("missing interstate detail")
    if is_yes_no_missing(record.get("transload_hub")):
        flags.append("missing transload detail")
    if clean_text(record.get("data_gap_notes")):
        flags.append("data gap note")
    return flags


def annotate_site_quality(site):
    """Attach display-friendly data quality fields to a site record."""
    flags = site_gap_flags(site)
    site["data_quality_flags"] = flags
    site["needs_confirmation"] = bool(flags)
    site["source_confidence"] = confidence_label(site)
    site["source_url"] = clean_text(site.get("source_url"))
    site["last_verified"] = clean_text(site.get("last_verified"))
    site["data_gap_notes"] = clean_text(site.get("data_gap_notes"))
    return site


def annotate_rail_quality(record):
    """Attach display-friendly data quality fields to a rail record."""
    flags = rail_gap_flags(record)
    record["data_quality_flags"] = flags
    record["needs_confirmation"] = bool(flags)
    record["source_confidence"] = confidence_label(record)
    record["source_url"] = clean_text(record.get("source_url"))
    record["last_verified"] = clean_text(record.get("last_verified"))
    record["data_gap_notes"] = clean_text(record.get("data_gap_notes"))
    return record


def build_data_quality_report(sites, rail_infrastructure):
    """Build concise quality counts for verification and dashboards."""
    confidence_counts = Counter()
    for record in list(sites) + list(rail_infrastructure):
        confidence_counts[confidence_label(record)] += 1

    site_flags = [flag for site in sites for flag in site_gap_flags(site)]
    rail_flags = [flag for record in rail_infrastructure for flag in rail_gap_flags(record)]

    return {
        "source_confidence_counts": dict(sorted(confidence_counts.items())),
        "blank_acreage_sites": sum(1 for site in sites if not clean_text(site.get("acres"))),
        "approximate_coordinate_records": sum(1 for record in rail_infrastructure if note_mentions_approximate(record)),
        "missing_class1_sites": sum(1 for site in sites if is_yes_no_missing(site.get("nearby_class1"))),
        "missing_interstate_sites": sum(1 for site in sites if is_yes_no_missing(site.get("interstate_access"))),
        "missing_port_sites": sum(1 for site in sites if is_yes_no_missing(site.get("port_access"))),
        "missing_transload_sites": sum(1 for site in sites if is_yes_no_missing(site.get("transload_available"))),
        "missing_interstate_rail_records": sum(1 for record in rail_infrastructure if is_yes_no_missing(record.get("interstate_access"))),
        "missing_port_rail_records": sum(1 for record in rail_infrastructure if is_yes_no_missing(record.get("port_nearby"))),
        "missing_transload_rail_records": sum(1 for record in rail_infrastructure if is_yes_no_missing(record.get("transload_hub"))),
        "sites_needing_confirmation": sum(1 for site in sites if site_gap_flags(site)),
        "rail_records_needing_confirmation": sum(1 for record in rail_infrastructure if rail_gap_flags(record)),
        "site_flag_counts": dict(sorted(Counter(site_flags).items())),
        "rail_flag_counts": dict(sorted(Counter(rail_flags).items())),
    }
