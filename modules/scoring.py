"""
OmniMapping Scoring Module
Contains all scoring algorithms and calculations for the economic development platform.
"""

import math

YES_VALUES = {'yes', 'true', '1'}
REGION_STATES = {
    'South-Central': {'TX', 'OK', 'LA', 'AR'},
    'Midwest': {'IL', 'IN', 'OH', 'MI', 'WI', 'MN', 'IA', 'MO', 'KY', 'TN'},
    'Pacific': {'CA', 'OR', 'WA'},
    'Southeast': {'GA', 'SC', 'NC', 'AL', 'FL', 'VA'},
    'Northeast': {'PA', 'NY', 'NJ', 'MA', 'CT', 'MD', 'DE', 'RI'},
    'Mountain': {'CO', 'UT', 'AZ', 'NM'},
}

HEAVY_SECTORS = {'steel', 'scrap', 'coal', 'ore', 'chemical', 'energy', 'construction', 'automotive'}


def normalize_text(value):
    return str(value or '').strip().lower()


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(str(value).strip())
    except (ValueError, TypeError):
        return default


def is_yes(value):
    return normalize_text(value) in YES_VALUES


def get_region(state):
    state = str(state or '').upper()
    for region, states in REGION_STATES.items():
        if state in states:
            return region
    return 'Unknown'


def estimate_acreage_need(company):
    segment = normalize_text(company.get('segment'))
    ranges = {
        'steel mills': (100, 500),
        'scrap metal': (20, 100),
        'energy': (50, 1000),
        'automotive': (50, 300),
        'construction materials': (30, 200),
        'warehousing/distribution': (50, 500),
        'pipe and tube': (30, 150),
        'chemicals': (30, 250),
        'fabricators': (20, 100),
        'steel service centers': (15, 80),
        'warehousing': (50, 500),
    }
    return ranges.get(segment, (20, 150))


def calculate_acreage_fit(company, site):
    acres_text = normalize_text(site.get('acres'))
    if not acres_text:
        return 5
    try:
        acres_value = float(acres_text)
    except ValueError:
        return 5

    min_need, max_need = estimate_acreage_need(company)
    if acres_value >= max_need:
        return 10
    if acres_value >= min_need:
        return 7
    if acres_value >= min_need * 0.75:
        return 4
    return 0


def clamp_score(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def calculate_rail_fit_score(company):
    rail_fit = safe_int(company.get('rail_fit_score', 0), 0)
    distance = safe_float(company.get('estimated_rail_distance', 100), 100)

    score = (rail_fit / 5) * 20
    if distance < 20:
        score += 5
    elif distance > 60:
        score -= 3

    return clamp_score(round(score), 0, 25)


def calculate_freight_intensity_score(company):
    inbound = normalize_text(company.get('inbound_materials'))
    outbound = normalize_text(company.get('outbound_products'))
    score = 6
    heavy_materials = ['steel', 'scrap', 'coal', 'ore', 'chemical', 'aggregate', 'cement', 'lumber', 'grain', 'automotive', 'oil', 'gas']

    for material in heavy_materials:
        if material in inbound or material in outbound:
            score += 3

    segment_name = normalize_text(company.get('segment'))
    if segment_name in HEAVY_SECTORS:
        score += 3
    if 'distribution' in segment_name or 'logistics' in segment_name:
        score += 2

    return clamp_score(score, 0, 20)


def calculate_land_intensity_score(company):
    real_estate = safe_int(company.get('industrial_real_estate_score', 0), 0)
    return clamp_score(round((real_estate / 5) * 15), 0, 15)


def calculate_multimodal_potential_score(company):
    return clamp_score(round(calculate_geography_score(company) * 0.15), 0, 15)


def calculate_site_match_quality_score(match_score):
    if match_score >= 90:
        return 10
    if match_score >= 75:
        return 8
    if match_score >= 60:
        return 6
    if match_score >= 40:
        return 4
    if match_score >= 20:
        return 2
    return 0


def calculate_industry_fit_score(company, segment_data):
    commodity = normalize_text(company.get('commodity_type'))
    segment_name = normalize_text(segment_data.get('segment'))

    if any(term in commodity for term in HEAVY_SECTORS) or any(term in segment_name for term in HEAVY_SECTORS):
        return 5
    if segment_name:
        return 4
    return 3


def calculate_strategic_fit_score(company, segment_data):
    score = 4
    outreach = normalize_text(company.get('omnitrax_outreach_angle'))
    segment_name = normalize_text(segment_data.get('segment'))

    if 'industrial' in outreach:
        score += 3
    if 'rail' in outreach:
        score += 2
    if 'logistics' in outreach:
        score += 1
    if segment_name in ['steel mills', 'energy', 'chemicals', 'automotive']:
        score += 2

    return clamp_score(score, 0, 10)


def calculate_priority_score(company, segment_data, best_site_match_score=0):
    """Calculate a weighted 1-100 priority score with breakout details."""
    breakdown = {
        'rail_fit': calculate_rail_fit_score(company),
        'logistics_intensity': calculate_freight_intensity_score(company),
        'land_intensity': calculate_land_intensity_score(company),
        'multimodal_potential': calculate_multimodal_potential_score(company),
        'site_match_quality': calculate_site_match_quality_score(best_site_match_score),
        'industry_fit': calculate_industry_fit_score(company, segment_data),
        'strategic_fit': calculate_strategic_fit_score(company, segment_data),
    }

    final_score = clamp_score(sum(breakdown.values()), 0, 100)
    return final_score, breakdown


def calculate_geography_score(company):
    """
    Calculate geographic intelligence score based on logistics factors.
    Returns a score from 0-100 based on multimodal potential.
    """
    score = 50  # Base score

    # Port proximity bonus
    if company.get('nearest_port'):
        score += 10

    # Class 1 railroad proximity bonus
    if company.get('nearest_class1_railroad'):
        score += 10

    # Low estimated rail distance bonus
    rail_distance = safe_float(company.get('estimated_rail_distance', 100), 100)
    if rail_distance < 10:
        score += 15
    elif rail_distance < 50:
        score += 10
    elif rail_distance < 100:
        score += 5

    # Transload potential bonus
    if normalize_text(company.get('transload_potential')) in ['high', 'yes']:
        score += 10

    # Port to consumer score bonus
    port_score = safe_int(company.get('port_to_consumer_score', 0), 0)
    score += port_score // 2  # Add up to 50 points

    return clamp_score(score, 0, 100)

def calculate_site_compatibility_score(company, site):
    """
    Calculate how well an industrial site matches a company's needs.
    Returns a compatibility score from 0-100.
    """
    score = 0

    if is_yes(site.get('rail_served')):
        score += 30

    if is_yes(site.get('transload_available')):
        score += 20

    if is_yes(site.get('port_access')):
        score += 7

    if is_yes(site.get('interstate_access')):
        score += 6

    site_industries = normalize_text(site.get('target_industries'))
    company_segment = normalize_text(company.get('segment'))
    company_commodity = normalize_text(company.get('commodity_type'))

    if company_segment in site_industries or company_commodity in site_industries:
        score += 15

    if normalize_text(company.get('state')) == normalize_text(site.get('state')):
        score += 8
    elif get_region(company.get('state')) == get_region(site.get('state')):
        score += 4

    score += calculate_acreage_fit(company, site)

    return clamp_score(score, 0, 100)

def calculate_overall_opportunity_score(company, segment_data):
    """
    Calculate the overall opportunity score using weighted categories.
    This is the advanced scoring system for Phase 7.
    """
    weights = {
        'rail_fit': 0.25,
        'logistics_intensity': 0.20,
        'land_intensity': 0.15,
        'multimodal_potential': 0.15,
        'industrial_outdoor_storage': 0.10,
        'supply_chain_criticality': 0.10,
        'expansion_likelihood': 0.03,
        'omnitrax_strategic_fit': 0.02
    }

    scores = {}

    # Rail fit score (1-5 scale, convert to 0-100)
    rail_fit = safe_int(company.get('rail_fit_score', 0), 0)
    scores['rail_fit'] = clamp_score((rail_fit / 5) * 100, 0, 100)

    # Logistics intensity (based on inbound/outbound materials)
    logistics_score = 50  # Base
    inbound = normalize_text(company.get('inbound_materials'))
    outbound = normalize_text(company.get('outbound_products'))

    heavy_materials = ['steel', 'scrap', 'coal', 'ore', 'chemical', 'aggregate']
    for material in heavy_materials:
        if material in inbound or material in outbound:
            logistics_score += 10

    scores['logistics_intensity'] = clamp_score(min(100, logistics_score), 0, 100)

    # Land intensity (based on industrial real estate score)
    land_score = safe_int(company.get('industrial_real_estate_score', 0), 0)
    scores['land_intensity'] = clamp_score((land_score / 5) * 100, 0, 100)

    # Multimodal potential (geography score)
    scores['multimodal_potential'] = calculate_geography_score(company)

    # Industrial outdoor storage potential
    storage_score = 30  # Base
    segment = normalize_text(segment_data.get('segment'))
    if segment in ['steel mills', 'scrap metal', 'construction materials', 'energy']:
        storage_score += 40
    elif segment in ['warehousing/distribution', 'pipe and tube']:
        storage_score += 30

    scores['industrial_outdoor_storage'] = clamp_score(min(100, storage_score), 0, 100)

    # Supply chain criticality
    criticality_score = 50  # Base
    if segment in ['steel mills', 'energy', 'chemicals']:
        criticality_score += 30
    elif segment in ['automotive', 'construction materials']:
        criticality_score += 20

    scores['supply_chain_criticality'] = clamp_score(min(100, criticality_score), 0, 100)

    # Expansion likelihood (based on company size indicators)
    expansion_score = 40  # Base
    company_name = company.get('company', '')
    large_companies = ['Nucor', 'U.S. Steel', 'ArcelorMittal', 'ExxonMobil', 'Chevron']
    if company_name in large_companies:
        expansion_score += 40
    elif 'global' in normalize_text(company.get('why_target')):
        expansion_score += 20

    scores['expansion_likelihood'] = clamp_score(min(100, expansion_score), 0, 100)

    # OmniTRAX strategic fit
    omnitrax_score = 50  # Base
    outreach = normalize_text(company.get('omnitrax_outreach_angle'))
    if 'industrial' in outreach:
        omnitrax_score += 30
    elif 'rail' in outreach:
        omnitrax_score += 20

    scores['omnitrax_strategic_fit'] = clamp_score(min(100, omnitrax_score), 0, 100)

    # Calculate weighted composite score
    overall_score = 0
    for category, weight in weights.items():
        overall_score += scores[category] * weight

    return clamp_score(round(overall_score), 0, 100), scores

def rank_companies_by_score(companies, segments):
    """Rank all companies by their priority scores"""
    ranked_companies = []

    for company in companies:
        segment_data = next((s for s in segments if s["segment"] == company.get("segment")), {})
        score, breakdown = calculate_priority_score(company, segment_data)
        company['priority_score'] = score
        company['score_breakdown'] = breakdown
        ranked_companies.append(company)

    # Sort by priority score descending
    ranked_companies.sort(key=lambda x: safe_int(x.get('priority_score', 0)), reverse=True)
    return ranked_companies
