"""Lightweight data quality helpers for source confidence and freshness."""

from collections import Counter
from datetime import date, datetime


UNKNOWN_CONFIDENCE = "Unspecified"
FRESHNESS_DAYS = 365


def clean_text(value):
    return str(value or "").strip()


def confidence_label(record):
    """Return a stable confidence bucket for reporting."""
    return clean_text(record.get("source_confidence")) or UNKNOWN_CONFIDENCE


def is_yes_no_missing(value):
    value = clean_text(value)
    return value == "" or value.lower() in {"unknown", "n/a", "na", "tbd"}


def is_missing_value(value):
    """Return whether a field is blank or uses a known placeholder."""
    value = clean_text(value)
    return value == "" or value.lower() in {"unknown", "n/a", "na", "tbd"}


def parse_verified_date(value):
    """Parse common ISO-style verification dates."""
    value = clean_text(value)
    if not value:
        return None
    for date_format in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value[:10], date_format).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def is_recent_verified_date(value, today=None):
    """Return whether a verification date exists and is within the freshness window."""
    verified_date = parse_verified_date(value)
    if not verified_date:
        return False
    today = today or date.today()
    return 0 <= (today - verified_date).days <= FRESHNESS_DAYS


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


def context_mentions(record, terms):
    """Search existing notes and source fields for lightweight confirmation hints."""
    haystack = " ".join(
        clean_text(record.get(field)).lower()
        for field in (
            "review_notes",
            "source_update_url",
            "source_url",
            "target_industries",
        )
    )
    return any(term in haystack for term in terms)


def checklist_item(key, label, confirmed, task, blocker=False):
    """Build one human-readable research checklist item."""
    return {
        "key": key,
        "label": label,
        "confirmed": bool(confirmed),
        "status": "Confirmed" if confirmed else "Needs verification",
        "task": "" if confirmed else task,
        "blocker": bool(blocker and not confirmed),
    }


def build_site_research_checklist(site, today=None):
    """Build practical site-level verification items before outreach."""
    confidence = confidence_label(site)
    last_verified = clean_text(site.get("last_verified"))
    port_value = clean_text(site.get("port_access"))
    port_relevant = port_value.lower() == "yes" or context_mentions(
        site,
        {"port", "export", "import", "marine", "drayage"},
    )
    notes_text = clean_text(site.get("data_gap_notes"))
    has_gap_note = bool(notes_text)

    items = [
        checklist_item(
            "acreage",
            "Acreage confirmed",
            not is_missing_value(site.get("acres")),
            "Confirm available acreage, parcel boundaries, and site control.",
            blocker=True,
        ),
        checklist_item(
            "rail_service",
            "Rail service confirmed",
            not is_yes_no_missing(site.get("rail_served")),
            "Confirm whether the site is rail served today and whether service is active.",
            blocker=True,
        ),
        checklist_item(
            "serving_railroad",
            "Class I / serving railroad confirmed",
            not is_yes_no_missing(site.get("nearby_class1")),
            "Identify the serving railroad and any Class I interchange or connection.",
            blocker=True,
        ),
        checklist_item(
            "transload",
            "Transload availability confirmed",
            not is_yes_no_missing(site.get("transload_available")),
            "Confirm transload availability, capacity, operator, and commodity fit.",
        ),
        checklist_item(
            "truck_access",
            "Interstate/truck access confirmed",
            not is_yes_no_missing(site.get("interstate_access")),
            "Confirm interstate proximity, truck routes, and access constraints.",
        ),
    ]

    if port_relevant:
        items.append(checklist_item(
            "port_access",
            "Port access confirmed",
            not is_yes_no_missing(site.get("port_access")),
            "Confirm relevant port access, drayage distance, and marine/export fit.",
        ))

    items.extend([
        checklist_item(
            "owner_contact",
            "Owner/contact found",
            context_mentions(site, {"owner", "contact", "broker", "authority", "developer"}),
            "Find the site owner, broker, authority, or economic-development contact.",
        ),
        checklist_item(
            "utilities",
            "Utility status confirmed",
            context_mentions(site, {"utility", "utilities", "power", "water", "sewer", "gas"}),
            "Confirm utility availability, capacity, and known upgrade needs.",
        ),
        checklist_item(
            "zoning_entitlement",
            "Zoning/entitlement confirmed",
            context_mentions(site, {"zoning", "entitlement", "permitted", "industrial use"}),
            "Confirm zoning, entitlement status, permitted uses, and approval constraints.",
        ),
        checklist_item(
            "source_url",
            "Source URL present",
            bool(clean_text(site.get("source_url"))),
            "Add a current public source URL or internal source trail.",
            blocker=True,
        ),
        checklist_item(
            "last_verified",
            "Last verified date present/recent",
            is_recent_verified_date(last_verified, today=today),
            "Update last_verified with a current date after checking source material.",
            blocker=True,
        ),
        checklist_item(
            "confidence",
            "Confidence level assigned",
            confidence.lower() not in {"", UNKNOWN_CONFIDENCE.lower()},
            "Assign source_confidence as High, Medium, or another explicit confidence level.",
            blocker=True,
        ),
        checklist_item(
            "gap_notes",
            "Known data gaps reviewed",
            not has_gap_note,
            "Resolve or explicitly disposition data_gap_notes before outreach.",
        ),
    ])
    return items


def build_company_research_checklist(company):
    """Build company-side items that matter for a selected opportunity."""
    return [
        checklist_item(
            "inbound_materials",
            "Inbound materials confirmed",
            bool(clean_text(company.get("inbound_materials"))),
            "Confirm inbound materials, volumes, current routing, and pain points.",
        ),
        checklist_item(
            "outbound_products",
            "Outbound products confirmed",
            bool(clean_text(company.get("outbound_products"))),
            "Confirm outbound products, customer lanes, and shipment cadence.",
        ),
        checklist_item(
            "expansion_timing",
            "Expansion or real estate timing confirmed",
            bool(clean_text(company.get("industrial_real_estate_score"))),
            "Confirm whether the company has active expansion, relocation, or site-search timing.",
        ),
    ]


def build_research_readiness(site, company=None, compatibility_score=None, today=None):
    """Summarize research readiness for a site or company-site opportunity."""
    items = build_site_research_checklist(site, today=today)
    if company:
        items.extend(build_company_research_checklist(company))
    if compatibility_score is not None and compatibility_score < 60:
        items.append(checklist_item(
            "site_fit",
            "Site fit validated",
            False,
            "Validate whether this company needs a different site type before outreach.",
            blocker=True,
        ))

    total = len(items)
    confirmed_count = sum(1 for item in items if item["confirmed"])
    task_items = [item for item in items if not item["confirmed"]]
    blockers = [item for item in task_items if item["blocker"]]
    score = round((confirmed_count / total) * 100) if total else 0

    review_status = clean_text(site.get("review_status")).lower()
    if review_status == "blocked" or len(blockers) >= 4:
        label = "Blocked By Data Gaps"
        tone = "warning"
    elif score >= 80 and not blockers and review_status in {"", "confirmed"}:
        label = "Research Ready"
        tone = "positive"
    else:
        label = "Needs Verification"
        tone = "review"

    return {
        "label": label,
        "tone": tone,
        "score": score,
        "confirmed_count": confirmed_count,
        "total_count": total,
        "blocked_count": len(blockers),
        "checklist": items,
        "tasks": [item["task"] for item in task_items],
    }


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
    site["research_readiness"] = build_research_readiness(site)
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
