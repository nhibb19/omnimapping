"""
OmniMapping Workflows
Contains business logic workflows for scoring, matching, and analysis.
"""

from typing import Dict, List, Tuple

from config import DEFAULT_TOP_LIMIT
from logger import get_logger
from modules.data_quality import build_data_quality_report
from modules.scoring import calculate_priority_score
from modules.search import (
    filter_by_min_score, filter_by_segment, filter_by_state, get_top_opportunities,
    search_companies, find_best_sites_for_company
)

logger = get_logger(__name__)

def safe_score(value, default=0):
    """Convert score-like values to integers without interrupting verification."""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default

def score_in_range(value):
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False
    return 0 <= numeric_value <= 100

def collect_score_range_failures(companies):
    failures = []
    for company in companies:
        company_name = company.get('company', 'Unknown')
        score_fields = {
            'priority_score': company.get('priority_score'),
            'best_site_match_score': company.get('best_site_match_score'),
        }

        for field, value in score_fields.items():
            if not score_in_range(value):
                failures.append(f"{company_name} has {field}={value}")

        breakdown = company.get('score_breakdown', {})
        for field, value in breakdown.items():
            if not score_in_range(value):
                failures.append(f"{company_name} has score_breakdown.{field}={value}")

    return failures

def top_opportunities_are_sorted(top_companies):
    scores = [safe_score(company.get('priority_score', 0)) for company in top_companies]
    return scores == sorted(scores, reverse=True)

def collect_site_match_failures(companies, sites):
    failures = []
    companies_to_check = get_top_opportunities(companies, min(5, len(companies)))

    for company in companies_to_check:
        company_name = company.get('company', 'Unknown')
        matches = find_best_sites_for_company(company, sites, min(3, len(sites)))
        if not matches:
            failures.append(f"{company_name} returned no site matches")
            continue

        scores = [match.get('compatibility_score') for match in matches]
        if any(not score_in_range(score) for score in scores):
            failures.append(f"{company_name} returned out-of-range site match score(s): {scores}")

        if scores != sorted(scores, reverse=True):
            failures.append(f"{company_name} site matches are not sorted descending: {scores}")

        best_match = matches[0]
        if not best_match.get('site') or 'compatibility_score' not in best_match:
            failures.append(f"{company_name} returned an incomplete best site match")

    return failures

def run_verification(segments: List[Dict], companies: List[Dict], sites: List[Dict], rail_infrastructure: List[Dict]) -> int:
    """Run a non-interactive data validation and scoring verification."""
    logger.info("Running OmniMapping verification")

    failures = []

    # Data load validation
    data_loaded = bool(segments and companies and sites and rail_infrastructure)
    if not segments:
        failures.append("No segments loaded")
    if not companies:
        failures.append("No companies loaded")
    if not sites:
        failures.append("No industrial sites loaded")
    if not rail_infrastructure:
        failures.append("No rail infrastructure records loaded")

    logger.info(f"Loaded {len(segments)} segments, {len(companies)} companies, {len(sites)} sites, {len(rail_infrastructure)} rail records")

    # Score validation
    score_failures = collect_score_range_failures(companies)
    failures.extend(score_failures)

    # Top opportunities validation
    top_companies = get_top_opportunities(companies, 20)
    top_sorted = bool(top_companies) and top_opportunities_are_sorted(top_companies)
    if not top_companies:
        failures.append("Top opportunities list is empty")
    elif not top_sorted:
        failures.append("Top opportunities are not sorted by descending priority_score")

    # Site matching validation
    site_match_failures = collect_site_match_failures(companies, sites) if companies and sites else ["Cannot check site matching without companies and sites"]
    failures.extend(site_match_failures)

    # Data quality report
    data_quality = build_data_quality_report(sites, rail_infrastructure)

    if not failures and top_companies:
        sample_company = top_companies[0]
        site_matches = find_best_sites_for_company(sample_company, sites, 1)
        if site_matches:
            best_site = site_matches[0]
            logger.info(f"Sample verification: {sample_company.get('company', 'Unknown')} matched to {best_site['site'].get('site_name', 'Unknown')}")

    if failures:
        logger.error(f"Verification failed with {len(failures)} issue(s)")
        for failure in failures[:10]:
            logger.error(f"- {failure}")
        return 1

    logger.info("Verification completed successfully")
    return 0

def process_companies_with_scoring(segments: List[Dict], companies: List[Dict], sites: List[Dict]) -> List[Dict]:
    """Process companies with priority scoring and site matching"""
    logger.info("Processing companies with scoring and site matching")

    for company in companies:
        segment_data = next((s for s in segments if s["segment"] == company.get("segment")), {})
        best_match_score = 0
        best_site_name = None
        best_site_location = ''

        if sites:
            site_matches = find_best_sites_for_company(company, sites, 1)
            best_match = site_matches[0]
            best_site = best_match.get('site', {})
            best_match_score = best_match.get('compatibility_score', 0)
            best_site_name = best_site.get('site_name')
            best_site_city = best_site.get('city', '')
            best_site_state = best_site.get('state', '')
            best_site_location = f"{best_site_city}, {best_site_state}" if best_site_city and best_site_state else best_site_city or best_site_state
            company['best_lane_score'] = best_match.get('lane_score', 0)
            company['best_lane_readiness_label'] = best_match.get('lane_readiness_label', '')
            company['best_lane_reasons'] = best_match.get('lane_reasons', [])
            company['best_pair_score'] = best_match.get('pair_score', best_match_score)

        company['best_site_match_score'] = best_match_score
        company['best_site_name'] = best_site_name
        company['best_recommended_site'] = best_site_name
        company['best_recommended_site_location'] = best_site_location
        company['site_match_quality_label'] = site_match_quality_label(best_match_score)
        company['freight_intensity_label'] = get_freight_intensity_label(company)
        company['infrastructure_dependency'] = generate_infrastructure_dependency(company)
        score, breakdown = calculate_priority_score(company, segment_data, best_match_score)
        company['priority_score'] = score
        company['score_breakdown'] = breakdown
        company['recommended_next_action'] = generate_recommended_next_action(company, best_site_name)
        company['opportunity_risk'] = summarize_opportunity_risk(company, best_match_score)

    logger.info(f"Processed {len(companies)} companies with scoring")
    return companies

def site_match_quality_label(score):
    """Convert site match score to quality label"""
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Strong"
    elif score >= 60:
        return "Good"
    elif score >= 40:
        return "Fair"
    else:
        return "Poor"

def get_freight_intensity_label(company):
    """Generate freight intensity label"""
    inbound = str(company.get('inbound_materials', '')).lower()
    outbound = str(company.get('outbound_products', '')).lower()
    heavy_keywords = ['steel', 'scrap', 'coal', 'ore', 'chemical', 'aggregate', 'cement', 'lumber', 'grain']

    heavy_count = sum(1 for keyword in heavy_keywords if keyword in inbound or keyword in outbound)
    if heavy_count >= 3:
        return "Very High"
    elif heavy_count >= 2:
        return "High"
    elif heavy_count >= 1:
        return "Medium"
    else:
        return "Low"

def generate_infrastructure_dependency(company):
    """Generate infrastructure dependency assessment"""
    score = safe_score(company.get('rail_fit_score', 0))
    if score >= 80:
        return "Rail Critical"
    elif score >= 60:
        return "Rail Preferred"
    elif score >= 40:
        return "Rail Beneficial"
    else:
        return "Rail Optional"

def generate_recommended_next_action(company, best_site_name):
    """Generate recommended next action"""
    score = safe_score(company.get('priority_score', 0))
    if score >= 80 and best_site_name:
        return "Immediate Outreach"
    elif score >= 60:
        return "Research & Outreach"
    elif score >= 40:
        return "Monitor & Research"
    else:
        return "Low Priority"

def summarize_opportunity_risk(company, site_match_score):
    """Summarize opportunity risk factors"""
    risks = []
    score = safe_score(company.get('priority_score', 0))

    if score < 50:
        risks.append("Low priority score")
    if site_match_score < 50:
        risks.append("Weak site match")
    if not company.get('best_site_name'):
        risks.append("No suitable sites")

    return "; ".join(risks) if risks else "Low Risk"
