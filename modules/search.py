"""
OmniMapping Search Module
Contains all search, filtering, and data retrieval functions.
"""

from .scoring import calculate_lane_score, calculate_site_compatibility_score, calculate_acreage_fit, get_region


def safe_score(value, default=0):
    """Convert score-like values to integers without breaking search flows."""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default

def search_companies(companies, query):
    """Search companies by name, segment, state, city, or commodity"""
    results = []
    query_lower = query.lower()

    for company in companies:
        searchable_text = f"{company.get('company', '')} {company.get('segment', '')} {company.get('state', '')} {company.get('city', '')} {company.get('commodity_type', '')}".lower()

        if query_lower in searchable_text:
            results.append(company)

    return results

def filter_by_state(companies, state):
    """Filter companies by state"""
    return [c for c in companies if c.get('state', '').upper() == state.upper()]

def filter_by_commodity(companies, commodity):
    """Filter companies by commodity type"""
    return [c for c in companies if c.get('commodity_type', '').lower() == commodity.lower()]

def filter_by_min_score(companies, min_score):
    """Filter companies by minimum priority score"""
    return [c for c in companies if safe_score(c.get('priority_score', 0)) >= min_score]

def filter_by_segment(companies, segment):
    """Filter companies by supply chain segment"""
    return [c for c in companies if c.get('segment', '').lower() == segment.lower()]

def get_top_opportunities(companies, limit=20):
    """Get top-ranked opportunities by priority score"""
    return sorted(companies, key=lambda x: safe_score(x.get('priority_score', 0)), reverse=True)[:limit]

def get_companies_by_segment(companies):
    """Group companies by segment and return statistics"""
    from collections import defaultdict

    segment_stats = defaultdict(list)

    for company in companies:
        segment = company.get('segment', 'Unknown')
        segment_stats[segment].append(company)

    # Calculate stats for each segment
    results = {}
    for segment, company_list in segment_stats.items():
        avg_score = sum(safe_score(c.get('priority_score', 0)) for c in company_list) / len(company_list)
        results[segment] = {
            'companies': company_list,
            'count': len(company_list),
            'avg_score': round(avg_score, 1)
        }

    return results

def find_best_sites_for_company(company, sites, limit=3):
    """Find the best industrial sites for a specific company"""
    site_matches = []

    for site in sites:
        compatibility_score = calculate_site_compatibility_score(company, site)
        lane = calculate_lane_score(company, site)
        pair_score = round((compatibility_score * 0.7) + (lane['lane_score'] * 0.3))
        site_matches.append({
            'site': site,
            'compatibility_score': compatibility_score,
            'pair_score': pair_score,
            **lane,
        })

    # Sort by blended site and lane fit so recommended sites reflect route viability.
    site_matches.sort(
        key=lambda x: (x['pair_score'], x['compatibility_score'], x['lane_score']),
        reverse=True,
    )

    return site_matches[:limit]

def get_site_recommendation_explanation(company, site):
    """Generate an explanation of why a site fits a company"""
    reasons = []

    # Rail served
    if site.get('rail_served', '').lower() in ['yes', 'true', '1']:
        reasons.append("Rail-served location provides direct rail access")

    # Transload
    if site.get('transload_available', '').lower() in ['yes', 'true', '1']:
        reasons.append("Transload facilities available for multimodal operations")

    # Port access
    if site.get('port_access', '').lower() in ['yes', 'true', '1']:
        reasons.append("Port access enables import/export capabilities")

    # Interstate access
    if site.get('interstate_access', '').lower() in ['yes', 'true', '1']:
        reasons.append("Interstate access provides highway connectivity")

    # Industry targeting
    site_industries = site.get('target_industries', '').lower()
    company_segment = company.get('segment', '').lower()
    company_commodity = company.get('commodity_type', '').lower()

    if company_segment in site_industries or company_commodity in site_industries:
        reasons.append(f"Site specifically targets {company_segment} industry")

    # Location proximity
    company_state = company.get('state', '')
    site_state = site.get('state', '')
    if company_state == site_state:
        reasons.append(f"Located in same state ({company_state}) as company")
    elif get_region(company_state) == get_region(site_state):
        reasons.append(f"Located in the same region ({get_region(company_state)}) as company")

    # Acreage fit
    acreage_fit = calculate_acreage_fit(company, site)
    if acreage_fit >= 7:
        reasons.append("Site acreage is a good match for the company's industrial land needs")
    elif acreage_fit >= 4:
        reasons.append("Site acreage may be workable for the company's anticipated growth")

    lane = calculate_lane_score(company, site)
    if lane['lane_score'] >= 75:
        reasons.append(f"{lane['lane_readiness_label']}: likely lane has strong logistics support")
    elif lane['lane_score'] >= 55:
        reasons.append(f"{lane['lane_readiness_label']}: lane appears workable with follow-up validation")

    if not reasons:
        reasons.append("General industrial site with development potential")

    return reasons

def search_sites(sites, query):
    """Search industrial sites by name, state, city, or target industries"""
    results = []
    query_lower = query.lower()

    for site in sites:
        searchable_text = f"{site.get('site_name', '')} {site.get('state', '')} {site.get('city', '')} {site.get('target_industries', '')}".lower()

        if query_lower in searchable_text:
            results.append(site)

    return results

def filter_sites_by_state(sites, state):
    """Filter industrial sites by state"""
    return [s for s in sites if s.get('state', '').upper() == state.upper()]

def filter_sites_by_rail_served(sites):
    """Filter sites that are rail served"""
    return [s for s in sites if s.get('rail_served', '').lower() in ['yes', 'true', '1']]

def filter_sites_by_transload(sites):
    """Filter sites with transload facilities"""
    return [s for s in sites if s.get('transload_available', '').lower() in ['yes', 'true', '1']]

def filter_sites_by_port_access(sites):
    """Filter sites with port access"""
    return [s for s in sites if s.get('port_access', '').lower() in ['yes', 'true', '1']]

def get_sites_by_target_industry(sites, industry):
    """Find sites that target a specific industry"""
    results = []
    industry_lower = industry.lower()

    for site in sites:
        target_industries = site.get('target_industries', '').lower()
        if industry_lower in target_industries:
            results.append(site)

    return results
