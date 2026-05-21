"""Unified opportunity readiness labels for company-site workflows."""

from .data_quality import build_research_readiness
from .scoring import safe_int


READY_LABEL = "Ready for outreach"
VERIFY_SITE_LABEL = "Verify site first"
COMPARE_SITES_LABEL = "Compare sites"
QUALIFY_FIT_LABEL = "Qualify fit"
MONITOR_LABEL = "Monitor"


def best_site_name(company):
    """Return the best available site name from ranked company data."""
    return company.get("best_site_name") or company.get("best_recommended_site") or ""


def readiness_rank(label):
    """Return a stable sort rank for readiness labels."""
    return {
        READY_LABEL: 4,
        VERIFY_SITE_LABEL: 3,
        COMPARE_SITES_LABEL: 2,
        QUALIFY_FIT_LABEL: 1,
        MONITOR_LABEL: 0,
    }.get(label, 0)


def readiness_tone(label):
    """Return the dashboard tone for a readiness label."""
    return {
        READY_LABEL: "positive",
        VERIFY_SITE_LABEL: "review",
        COMPARE_SITES_LABEL: "warning",
        QUALIFY_FIT_LABEL: "review",
        MONITOR_LABEL: "neutral",
    }.get(label, "neutral")


def readiness_next_action(label):
    """Return an action-oriented instruction for a readiness label."""
    return {
        READY_LABEL: "Open opportunity workspace and confirm outreach timing.",
        VERIFY_SITE_LABEL: "Verify the matched site before outreach.",
        COMPARE_SITES_LABEL: "Compare industrial sites and choose a usable first-choice location.",
        QUALIFY_FIT_LABEL: "Validate material volumes, lane fit, and site requirements.",
        MONITOR_LABEL: "Monitor as a market category and revisit when project signals improve.",
    }.get(label, "Review the opportunity before taking action.")


def build_opportunity_readiness(company, site=None, compatibility_score=None, lane=None, research_readiness=None):
    """Build a single readiness model for a company-site opportunity."""
    priority_score = safe_int(company.get("priority_score"), 0)
    site_match_score = safe_int(
        compatibility_score if compatibility_score is not None else company.get("best_site_match_score"),
        0,
    )
    lane_score = safe_int(
        lane.get("lane_score") if isinstance(lane, dict) else company.get("best_lane_score"),
        0,
    )
    selected_site_name = site.get("site_name", "") if site else best_site_name(company)
    has_best_site = bool(selected_site_name)
    has_usable_site = bool(site) or has_best_site
    review_status = str((site or {}).get("review_status", "")).strip().lower()

    readiness = research_readiness
    if readiness is None and site:
        readiness = build_research_readiness(
            site,
            company=company,
            compatibility_score=site_match_score,
        )
    readiness = readiness or {}
    readiness_label = readiness.get("label", "")
    readiness_score = safe_int(readiness.get("score"), 0)
    blocked_count = safe_int(readiness.get("blocked_count"), 0)
    blocked_by_gaps = (
        review_status == "blocked"
        or readiness_label == "Blocked By Data Gaps"
        or blocked_count > 0
    )
    site_ready = (
        has_usable_site
        and not blocked_by_gaps
        and review_status == "confirmed"
        and readiness_label == "Research Ready"
    )

    if not has_usable_site:
        label = COMPARE_SITES_LABEL if priority_score >= 55 else MONITOR_LABEL
        reason = "No usable best site is selected."
    elif blocked_by_gaps or not site_ready:
        label = VERIFY_SITE_LABEL if priority_score >= 60 or site_match_score >= 50 else MONITOR_LABEL
        reason = "Matched site needs verification before outreach."
    elif priority_score >= 70 and site_match_score >= 60 and lane_score >= 55:
        label = READY_LABEL
        reason = "Priority, site fit, lane fit, and site readiness are aligned."
    elif priority_score >= 60 or site_match_score >= 50 or lane_score >= 50:
        label = QUALIFY_FIT_LABEL
        reason = "Core fit is promising, but the opportunity needs qualification."
    else:
        label = MONITOR_LABEL
        reason = "Signals are not yet strong enough for active outreach."

    return {
        "label": label,
        "tone": readiness_tone(label),
        "rank": readiness_rank(label),
        "next_action": readiness_next_action(label),
        "reason": reason,
        "priority_score": priority_score,
        "site_match_score": site_match_score,
        "lane_score": lane_score,
        "site_name": selected_site_name,
        "has_best_site": has_best_site,
        "has_usable_site": has_usable_site,
        "site_ready": site_ready,
        "review_status": review_status,
        "site_readiness_label": readiness_label,
        "site_readiness_score": readiness_score,
        "blocked_count": blocked_count,
        "blocked_by_gaps": blocked_by_gaps,
        "actionable": label == READY_LABEL,
    }


def annotate_company_opportunity_readiness(company, site=None, compatibility_score=None, lane=None, research_readiness=None):
    """Return a company copy with unified readiness display fields attached."""
    readiness = build_opportunity_readiness(
        company,
        site=site,
        compatibility_score=compatibility_score,
        lane=lane,
        research_readiness=research_readiness,
    )
    annotated = company.copy()
    annotated["opportunity_readiness"] = readiness
    annotated["readiness_label"] = readiness["label"]
    annotated["readiness_tone"] = readiness["tone"]
    annotated["readiness_rank"] = readiness["rank"]
    annotated["readiness_next_action"] = readiness["next_action"]
    return annotated
