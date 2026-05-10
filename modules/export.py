"""
OmniMapping Export Module
Handles all data export functionality including CSV, JSON, and TXT formats.
"""

import csv
import json
import os
import re
from datetime import datetime

from .ui import get_priority_reasons

EXPORT_FIELDNAMES = [
    'company', 'company_info', 'segment', 'location', 'commodity', 'commodity_type',
    'state', 'city',
    'inbound_materials', 'outbound_products', 'why_target', 'omnitrax_outreach_angle',
    'priority_score', 'score_breakdown', 'score_reasons',
    'best_recommended_site', 'best_recommended_site_location', 'best_recommended_site_score',
    'best_site_name',
    'site_match_quality_label', 'freight_intensity_label', 'infrastructure_dependency',
    'recommended_next_action', 'opportunity_risk',
    'latitude', 'longitude', 'nearest_major_city', 'nearest_port',
    'nearest_class1_railroad', 'estimated_rail_distance'
]

GEOGRAPHIC_FIELDS = [
    'latitude', 'longitude', 'nearest_major_city', 'nearest_port',
    'nearest_class1_railroad', 'estimated_rail_distance'
]


def safe_score(value, default=0):
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def format_score_breakdown_for_export(breakdown):
    if not breakdown:
        return "{}"

    try:
        return json.dumps({k: int(v) for k, v in breakdown.items()}, sort_keys=True)
    except Exception:
        return json.dumps(breakdown, sort_keys=True)


def format_company_location(company):
    city = company.get('city', '')
    state = company.get('state', '')
    if city and state:
        return f"{city}, {state}"
    return city or state


def format_site_location(site):
    if not site:
        return ''

    city = site.get('city', '')
    state = site.get('state', '')
    if city and state:
        return f"{city}, {state}"
    return city or state


def get_best_recommended_site_name(company):
    return company.get('best_recommended_site') or company.get('best_site_name') or ''


def safe_filename_token(value, default="company"):
    """Return a filesystem-safe lowercase token for generated export names."""
    token = re.sub(r'[^A-Za-z0-9]+', '_', str(value or '').strip()).strip('_').lower()
    return token or default


def build_company_export_row(company):
    commodity = company.get('commodity') or company.get('commodity_type', '')
    company_info = company.get('company_info') or company.get('why_target', '')
    best_recommended_site = get_best_recommended_site_name(company)

    row = {
        'company': company.get('company', ''),
        'company_info': company_info,
        'segment': company.get('segment', ''),
        'location': format_company_location(company),
        'commodity': commodity,
        'commodity_type': company.get('commodity_type', ''),
        'state': company.get('state', ''),
        'city': company.get('city', ''),
        'inbound_materials': company.get('inbound_materials', ''),
        'outbound_products': company.get('outbound_products', ''),
        'why_target': company.get('why_target', ''),
        'omnitrax_outreach_angle': company.get('omnitrax_outreach_angle', ''),
        'priority_score': safe_score(company.get('priority_score', 0)),
        'score_breakdown': format_score_breakdown_for_export(company.get('score_breakdown', {})),
        'score_reasons': '; '.join(get_priority_reasons(company)),
        'best_recommended_site': best_recommended_site,
        'best_recommended_site_location': company.get('best_recommended_site_location', ''),
        'best_recommended_site_score': company.get('best_site_match_score', ''),
        'best_site_name': best_recommended_site,
        'site_match_quality_label': company.get('site_match_quality_label', ''),
        'freight_intensity_label': company.get('freight_intensity_label', ''),
        'infrastructure_dependency': company.get('infrastructure_dependency', ''),
        'recommended_next_action': company.get('recommended_next_action', ''),
        'opportunity_risk': company.get('opportunity_risk', ''),
        'latitude': company.get('latitude', ''),
        'longitude': company.get('longitude', ''),
        'nearest_major_city': company.get('nearest_major_city', ''),
        'nearest_port': company.get('nearest_port', ''),
        'nearest_class1_railroad': company.get('nearest_class1_railroad', ''),
        'estimated_rail_distance': company.get('estimated_rail_distance', ''),
    }
    return row


def export_to_csv(companies, filename="ranked_opportunities.csv", output_dir="exports"):
    """Export company data to CSV file"""
    if not companies:
        print("No companies to export.")
        return None

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    sample_company = companies[0] if companies else {}
    fieldnames = EXPORT_FIELDNAMES.copy()
    if not any(sample_company.get(field) is not None for field in GEOGRAPHIC_FIELDS):
        fieldnames = [f for f in fieldnames if f not in GEOGRAPHIC_FIELDS]

    with open(filepath, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for company in companies:
            row = build_company_export_row(company)
            writer.writerow({k: row[k] for k in fieldnames})

    print(f"Exported {len(companies)} companies to {filepath}")
    return filepath

def export_opportunity_briefs(companies, segments, sites, output_dir="exports"):
    """Export opportunity briefs as text files"""
    os.makedirs(output_dir, exist_ok=True)

    from .search import find_best_sites_for_company
    from .ui import print_opportunity_brief

    briefs_dir = os.path.join(output_dir, "opportunity_briefs")
    os.makedirs(briefs_dir, exist_ok=True)

    for company in companies[:10]:  # Export top 10 for brevity
        segment_data = next((s for s in segments if s["segment"] == company.get("segment")), {})

        # Find best site match
        site_matches = find_best_sites_for_company(company, sites, 1)
        recommended_site = site_matches[0]['site'] if site_matches else None
        if recommended_site:
            company['best_recommended_site'] = recommended_site.get('site_name', '')
            company['best_recommended_site_location'] = format_site_location(recommended_site)
            company['best_site_match_score'] = site_matches[0].get('compatibility_score', company.get('best_site_match_score', ''))

        # Create brief filename
        safe_name = company['company'].replace(' ', '_').replace('.', '').replace('/', '_')
        filename = f"{safe_name}_brief.txt"
        filepath = os.path.join(briefs_dir, filename)

        # Capture the brief output
        import io
        import sys
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()

        print_opportunity_brief(company, segment_data, recommended_site)

        brief_content = buffer.getvalue()
        sys.stdout = old_stdout

        # Write to file
        with open(filepath, 'w') as f:
            f.write(brief_content)

    print(f"Exported {min(10, len(companies))} opportunity briefs to {briefs_dir}")

def export_company_profiles_json(companies, output_dir="exports"):
    """Export company profiles in JSON format"""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"company_profiles_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    serialized_companies = []
    for company in companies:
        company_copy = company.copy()
        export_row = build_company_export_row(company)
        company_copy['company_info'] = export_row['company_info']
        company_copy['location'] = export_row['location']
        company_copy['commodity'] = export_row['commodity']
        company_copy['score_reasons'] = get_priority_reasons(company)
        company_copy['best_recommended_site'] = export_row['best_recommended_site']
        company_copy['best_recommended_site_location'] = export_row['best_recommended_site_location']
        company_copy['best_recommended_site_score'] = export_row['best_recommended_site_score']
        serialized_companies.append(company_copy)

    json_data = {
        "export_info": {
            "timestamp": datetime.now().isoformat(),
            "total_companies": len(companies),
            "description": "OmniMapping company profiles with geographic and logistics data"
        },
        "companies": serialized_companies
    }

    with open(filepath, 'w') as f:
        json.dump(json_data, f, indent=2, default=str)

    print(f"Exported {len(companies)} company profiles to {filepath}")

def export_site_matching_report(companies, sites, output_dir="exports"):
    """Export a comprehensive site matching report"""
    os.makedirs(output_dir, exist_ok=True)

    from .search import find_best_sites_for_company, get_site_recommendation_explanation

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"site_matching_report_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)

    fieldnames = [
        'company', 'company_info', 'segment', 'location', 'commodity', 'commodity_type',
        'company_state', 'company_city',
        'priority_score', 'score_breakdown', 'score_reasons',
        'best_recommended_site', 'best_recommended_site_location',
        'recommended_site', 'site_state', 'compatibility_score',
        'rail_served', 'transload_available', 'port_access',
        'matching_reasons'
    ]

    with open(filepath, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for company in companies[:50]:  # Top 50 companies
            site_matches = find_best_sites_for_company(company, sites, 1)

            if site_matches:
                best_match = site_matches[0]
                site = best_match['site']
                reasons = get_site_recommendation_explanation(company, site)

                row = {
                    'company': company.get('company', ''),
                    'company_info': company.get('company_info') or company.get('why_target', ''),
                    'segment': company.get('segment', ''),
                    'location': format_company_location(company),
                    'commodity': company.get('commodity') or company.get('commodity_type', ''),
                    'commodity_type': company.get('commodity_type', ''),
                    'company_state': company.get('state', ''),
                    'company_city': company.get('city', ''),
                    'priority_score': safe_score(company.get('priority_score', 0)),
                    'score_breakdown': format_score_breakdown_for_export(company.get('score_breakdown', {})),
                    'score_reasons': '; '.join(get_priority_reasons(company)),
                    'best_recommended_site': site.get('site_name', ''),
                    'best_recommended_site_location': format_site_location(site),
                    'recommended_site': site.get('site_name', ''),
                    'site_state': site.get('state', ''),
                    'compatibility_score': best_match['compatibility_score'],
                    'rail_served': site.get('rail_served', ''),
                    'transload_available': site.get('transload_available', ''),
                    'port_access': site.get('port_access', ''),
                    'matching_reasons': '; '.join(reasons)
                }
                writer.writerow(row)

    print(f"Exported site matching report for {min(50, len(companies))} companies to {filepath}")

def export_segment_analysis(companies, segments, output_dir="exports"):
    """Export segment analysis report"""
    os.makedirs(output_dir, exist_ok=True)

    from .search import get_companies_by_segment

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"segment_analysis_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)

    segment_stats = get_companies_by_segment(companies)

    fieldnames = ['segment', 'company_count', 'average_score', 'top_company', 'top_score']

    with open(filepath, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for segment_name, stats in segment_stats.items():
            top_company = max(stats['companies'], key=lambda x: safe_score(x.get('priority_score', 0)))

            row = {
                'segment': segment_name,
                'company_count': stats['count'],
                'average_score': stats['avg_score'],
                'top_company': top_company.get('company', ''),
                'top_score': top_company.get('priority_score', '')
            }
            writer.writerow(row)

    print(f"Exported segment analysis to {filepath}")

def export_geographic_analysis(companies, output_dir="exports"):
    """Export geographic analysis of company locations"""
    os.makedirs(output_dir, exist_ok=True)

    from collections import defaultdict

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"geographic_analysis_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)

    # Analyze by state
    state_stats = defaultdict(list)
    for company in companies:
        state = company.get('state', 'Unknown')
        state_stats[state].append(company)

    fieldnames = ['state', 'company_count', 'average_score', 'rail_served_companies',
                  'port_access_companies', 'transload_potential_companies']

    with open(filepath, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for state, company_list in state_stats.items():
            avg_score = sum(safe_score(c.get('priority_score', 0)) for c in company_list) / len(company_list)

            rail_served = sum(1 for c in company_list if c.get('nearest_class1_railroad'))
            port_access = sum(1 for c in company_list if c.get('nearest_port'))
            transload = sum(1 for c in company_list if c.get('transload_potential', '').lower() in ['high', 'yes'])

            row = {
                'state': state,
                'company_count': len(company_list),
                'average_score': round(avg_score, 1),
                'rail_served_companies': rail_served,
                'port_access_companies': port_access,
                'transload_potential_companies': transload
            }
            writer.writerow(row)

    print(f"Exported geographic analysis to {filepath}")


def find_company_for_report(companies, company_name):
    """Find the best company record for a non-interactive company report."""
    query = str(company_name or '').strip()
    query_lower = query.lower()
    if not query_lower:
        return None, []

    exact_matches = [
        company for company in companies
        if company.get('company', '').strip().lower() == query_lower
    ]
    if exact_matches:
        return exact_matches[0], exact_matches

    partial_matches = [
        company for company in companies
        if query_lower in company.get('company', '').lower()
        or company.get('company', '').lower() in query_lower
    ]
    partial_matches.sort(
        key=lambda company: (
            safe_score(company.get('priority_score', 0)),
            company.get('company', '')
        ),
        reverse=True
    )
    if partial_matches:
        return partial_matches[0], partial_matches

    return None, []


def find_site_for_report(sites, site_name):
    """Find the best site record for a non-interactive site report."""
    query = str(site_name or '').strip()
    query_lower = query.lower()
    if not query_lower:
        return None, []

    exact_matches = [
        site for site in sites
        if site.get('site_name', '').strip().lower() == query_lower
    ]
    if exact_matches:
        return exact_matches[0], exact_matches

    partial_matches = [
        site for site in sites
        if query_lower in site.get('site_name', '').lower()
        or site.get('site_name', '').lower() in query_lower
    ]
    partial_matches.sort(key=lambda site: site.get('site_name', ''))
    if partial_matches:
        return partial_matches[0], partial_matches

    return None, []


def build_site_profile(site):
    """Serialize one industrial site profile for JSON exports."""
    return {
        'site_name': site.get('site_name', ''),
        'location': format_site_location(site),
        'city': site.get('city', ''),
        'state': site.get('state', ''),
        'acres': site.get('acres', ''),
        'rail_served': site.get('rail_served', ''),
        'nearby_class1': site.get('nearby_class1', ''),
        'transload_available': site.get('transload_available', ''),
        'interstate_access': site.get('interstate_access', ''),
        'port_access': site.get('port_access', ''),
        'target_industries': site.get('target_industries', ''),
        'source_url': site.get('source_url', ''),
        'source_confidence': site.get('source_confidence', ''),
        'last_verified': site.get('last_verified', ''),
        'data_gap_notes': site.get('data_gap_notes', ''),
        'data_quality_flags': site.get('data_quality_flags', []),
        'needs_confirmation': bool(site.get('needs_confirmation')),
    }


def build_site_match_export(company, match):
    """Serialize one site match with its fit reasons."""
    from .search import get_site_recommendation_explanation

    site = match.get('site', {})
    return {
        'site_name': site.get('site_name', ''),
        'site_location': format_site_location(site),
        'compatibility_score': safe_score(match.get('compatibility_score', 0)),
        'matching_reasons': get_site_recommendation_explanation(company, site),
        'site_profile': {
            'site_name': site.get('site_name', ''),
            'city': site.get('city', ''),
            'state': site.get('state', ''),
            'acres': site.get('acres', ''),
            'rail_served': site.get('rail_served', ''),
            'nearby_class1': site.get('nearby_class1', ''),
            'transload_available': site.get('transload_available', ''),
            'interstate_access': site.get('interstate_access', ''),
            'port_access': site.get('port_access', ''),
            'target_industries': site.get('target_industries', ''),
            'source_confidence': site.get('source_confidence', ''),
            'last_verified': site.get('last_verified', ''),
            'data_gap_notes': site.get('data_gap_notes', ''),
            'needs_confirmation': bool(site.get('needs_confirmation')),
        },
    }


def build_company_match_for_site_export(company, site):
    """Serialize one company match for a focused site report."""
    from .scoring import calculate_site_compatibility_score
    from .search import get_site_recommendation_explanation

    export_row = build_company_export_row(company)
    return {
        'company': company.get('company', ''),
        'company_location': export_row['location'],
        'segment': company.get('segment', ''),
        'commodity': export_row['commodity'],
        'priority_score': safe_score(company.get('priority_score', 0)),
        'compatibility_score': safe_score(calculate_site_compatibility_score(company, site)),
        'matching_reasons': get_site_recommendation_explanation(company, site),
        'priority_reasons': get_priority_reasons(company),
    }


def build_company_profile_basics(company):
    """Serialize compact company basics shared by ranked JSON exports."""
    export_row = build_company_export_row(company)
    return {
        'company': company.get('company', ''),
        'company_info': export_row['company_info'],
        'location': export_row['location'],
        'city': company.get('city', ''),
        'state': company.get('state', ''),
        'segment': company.get('segment', ''),
        'commodity': export_row['commodity'],
        'commodity_type': company.get('commodity_type', ''),
        'inbound_materials': company.get('inbound_materials', ''),
        'outbound_products': company.get('outbound_products', ''),
        'why_target': company.get('why_target', ''),
        'omnitrax_outreach_angle': company.get('omnitrax_outreach_angle', ''),
    }


def build_best_site_recommendation(company, sites):
    """Return the highest-scored site match for a company in JSON-ready form."""
    from .search import find_best_sites_for_company

    site_matches = find_best_sites_for_company(company, sites, 1)
    if not site_matches:
        return {
            'site_name': get_best_recommended_site_name(company),
            'site_location': company.get('best_recommended_site_location', ''),
            'site_match_score': safe_score(company.get('best_site_match_score', 0)),
            'matching_reasons': [],
            'site_profile': {},
        }

    match = site_matches[0]
    site = match.get('site', {})
    return {
        'site_name': site.get('site_name', ''),
        'site_location': format_site_location(site),
        'site_match_score': safe_score(match.get('compatibility_score', 0)),
        'matching_reasons': build_site_match_export(company, match).get('matching_reasons', []),
        'site_profile': build_site_profile(site),
    }


def filter_ranked_companies(companies, state=None, segment=None, commodity=None, min_score=None):
    """Apply optional ranked-company filters using case-insensitive exact matches."""
    filtered = list(companies)

    if state:
        state_filter = str(state).strip().upper()
        filtered = [company for company in filtered if str(company.get('state', '')).upper() == state_filter]

    if segment:
        segment_filter = str(segment).strip().lower()
        filtered = [company for company in filtered if str(company.get('segment', '')).lower() == segment_filter]

    if commodity:
        commodity_filter = str(commodity).strip().lower()
        filtered = [
            company for company in filtered
            if str(company.get('commodity_type') or company.get('commodity') or '').lower() == commodity_filter
        ]

    if min_score is not None:
        filtered = [company for company in filtered if safe_score(company.get('priority_score', 0)) >= min_score]

    filtered.sort(
        key=lambda company: (
            safe_score(company.get('priority_score', 0)),
            safe_score(company.get('best_site_match_score', 0)),
            company.get('company', '')
        ),
        reverse=True
    )
    return filtered


def build_top_companies_export(companies, sites, limit=20, state=None, segment=None, commodity=None, min_score=None):
    """Build a ranked JSON export of top companies and their best site fit."""
    ranked_companies = filter_ranked_companies(
        companies,
        state=state,
        segment=segment,
        commodity=commodity,
        min_score=min_score,
    )
    limited_companies = ranked_companies[:limit]

    return {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'description': 'Ranked OmniMapping companies with priority scoring and best site recommendation',
            'total_companies': len(companies),
            'filtered_company_count': len(ranked_companies),
            'exported_company_count': len(limited_companies),
            'limit': limit,
            'filters': {
                'state': state,
                'segment': segment,
                'commodity': commodity,
                'min_score': min_score,
            },
        },
        'companies': [
            {
                'rank': index,
                'company_profile': build_company_profile_basics(company),
                'priority_score': safe_score(company.get('priority_score', 0)),
                'score_breakdown': {
                    key: safe_score(value)
                    for key, value in company.get('score_breakdown', {}).items()
                },
                'priority_reasons': get_priority_reasons(company),
                'best_recommended_site': build_best_site_recommendation(company, sites),
            }
            for index, company in enumerate(limited_companies, start=1)
        ],
    }


def export_top_companies_json(companies, sites, output_dir="exports", limit=20, state=None, segment=None, commodity=None, min_score=None):
    """Write ranked company opportunities to JSON and return the file path."""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"top_companies_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    payload = build_top_companies_export(
        companies,
        sites,
        limit=limit,
        state=state,
        segment=segment,
        commodity=commodity,
        min_score=min_score,
    )

    with open(filepath, 'w') as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"Exported top companies to {filepath}")
    return filepath


def build_company_report(company, sites, company_query, all_matches=None):
    """Build a focused JSON-ready report for one matched company."""
    from .search import find_best_sites_for_company

    export_row = build_company_export_row(company)
    site_matches = find_best_sites_for_company(company, sites, 3)
    top_site_matches = [build_site_match_export(company, match) for match in site_matches]

    report_company = company.copy()
    report_company['company_info'] = export_row['company_info']
    report_company['location'] = export_row['location']
    report_company['commodity'] = export_row['commodity']
    report_company['best_recommended_site'] = export_row['best_recommended_site']
    report_company['best_recommended_site_location'] = export_row['best_recommended_site_location']
    report_company['best_recommended_site_score'] = export_row['best_recommended_site_score']

    return {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'description': 'OmniMapping company priority and site matching report',
            'company_query': company_query,
            'matched_company': company.get('company', ''),
            'candidate_match_count': len(all_matches or []),
        },
        'company_profile': report_company,
        'priority': {
            'score': safe_score(company.get('priority_score', 0)),
            'breakdown': {
                key: safe_score(value)
                for key, value in company.get('score_breakdown', {}).items()
            },
            'reasons': get_priority_reasons(company),
            'site_match_quality_label': company.get('site_match_quality_label', ''),
            'freight_intensity_label': company.get('freight_intensity_label', ''),
            'infrastructure_dependency': company.get('infrastructure_dependency', ''),
            'recommended_next_action': company.get('recommended_next_action', ''),
            'opportunity_risk': company.get('opportunity_risk', ''),
        },
        'top_site_matches': top_site_matches,
    }


def build_site_report(site, companies, site_query, all_matches=None, top_limit=10):
    """Build a focused JSON-ready report for one matched industrial site."""
    top_company_matches = [
        build_company_match_for_site_export(company, site)
        for company in companies
    ]
    top_company_matches.sort(
        key=lambda match: (
            match['compatibility_score'],
            match['priority_score'],
            match['company']
        ),
        reverse=True
    )

    return {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'description': 'OmniMapping site profile and company compatibility report',
            'site_query': site_query,
            'matched_site': site.get('site_name', ''),
            'candidate_match_count': len(all_matches or []),
            'top_company_limit': top_limit,
        },
        'site_profile': build_site_profile(site),
        'top_matched_companies': top_company_matches[:top_limit],
    }


def build_company_directory(companies):
    """Build a compact JSON-ready list of available company report targets."""
    directory = []
    for company in companies:
        export_row = build_company_export_row(company)
        directory.append({
            'company': company.get('company', ''),
            'location': export_row['location'],
            'segment': company.get('segment', ''),
            'commodity': export_row['commodity'],
            'priority_score': safe_score(company.get('priority_score', 0)),
            'best_recommended_site': get_best_recommended_site_name(company),
            'best_site_match_score': safe_score(company.get('best_site_match_score', 0)),
        })

    directory.sort(
        key=lambda item: (
            item['priority_score'],
            item['company']
        ),
        reverse=True
    )
    return directory


def build_site_directory(sites):
    """Build a compact JSON-ready list of available site report targets."""
    directory = []
    for site in sites:
        directory.append({
            'site_name': site.get('site_name', ''),
            'location': format_site_location(site),
            'city': site.get('city', ''),
            'state': site.get('state', ''),
            'acres': site.get('acres', ''),
            'rail_served': site.get('rail_served', ''),
            'transload_available': site.get('transload_available', ''),
            'port_access': site.get('port_access', ''),
            'target_industries': site.get('target_industries', ''),
            'source_confidence': site.get('source_confidence', ''),
            'last_verified': site.get('last_verified', ''),
            'data_gap_notes': site.get('data_gap_notes', ''),
            'data_quality_flags': site.get('data_quality_flags', []),
            'needs_confirmation': bool(site.get('needs_confirmation')),
        })

    directory.sort(key=lambda item: item['site_name'])
    return directory


def print_company_directory_json(companies):
    """Print available companies as JSON for non-interactive CLI discovery."""
    payload = {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'description': 'Available OmniMapping companies for --company-report',
            'total_companies': len(companies),
        },
        'companies': build_company_directory(companies),
    }
    print(json.dumps(payload, indent=2, default=str))


def print_site_directory_json(sites):
    """Print available industrial sites as JSON for non-interactive CLI discovery."""
    payload = {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'description': 'Available OmniMapping sites for --site-report',
            'total_sites': len(sites),
        },
        'sites': build_site_directory(sites),
    }
    print(json.dumps(payload, indent=2, default=str))


def export_company_report_json(company_name, companies, sites, output_dir="exports"):
    """Write a focused company report JSON file and return its path."""
    os.makedirs(output_dir, exist_ok=True)

    company, matches = find_company_for_report(companies, company_name)
    if not company:
        raise ValueError(f"No company found matching '{company_name}'.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_company_name = safe_filename_token(company.get('company'))
    filename = f"company_report_{safe_company_name}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    report = build_company_report(company, sites, company_name, all_matches=matches)

    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Exported company report to {filepath}")
    return filepath


def export_site_report_json(site_name, sites, companies, output_dir="exports", top_limit=10):
    """Write a focused site report JSON file and return its path."""
    os.makedirs(output_dir, exist_ok=True)

    site, matches = find_site_for_report(sites, site_name)
    if not site:
        raise ValueError(f"No site found matching '{site_name}'.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_site_name = safe_filename_token(site.get('site_name'), default='site')
    filename = f"site_report_{safe_site_name}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    report = build_site_report(site, companies, site_name, all_matches=matches, top_limit=top_limit)

    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Exported site report to {filepath}")
    return filepath


def build_export_summary(companies, segments, sites, rail_infrastructure, top_limit=20):
    """Build a compact operational summary for non-interactive export."""
    from .search import get_companies_by_segment, get_top_opportunities, find_best_sites_for_company

    top_companies = get_top_opportunities(companies, top_limit)
    segment_stats = get_companies_by_segment(companies)

    state_counts = {}
    for company in companies:
        state = company.get('state') or 'Unknown'
        state_counts[state] = state_counts.get(state, 0) + 1

    segment_averages = [
        {
            'segment': segment_name,
            'company_count': stats['count'],
            'average_score': stats['avg_score'],
        }
        for segment_name, stats in segment_stats.items()
    ]
    segment_averages.sort(key=lambda item: (-item['average_score'], item['segment']))

    best_site_matches = []
    for company in top_companies:
        matches = find_best_sites_for_company(company, sites, 1)
        if matches:
            match = matches[0]
            site = match['site']
            best_site_matches.append({
                'company': company.get('company', ''),
                'priority_score': safe_score(company.get('priority_score', 0)),
                'site_name': site.get('site_name', ''),
                'site_location': format_site_location(site),
                'compatibility_score': safe_score(match.get('compatibility_score', 0)),
            })
        else:
            best_site_matches.append({
                'company': company.get('company', ''),
                'priority_score': safe_score(company.get('priority_score', 0)),
                'site_name': '',
                'site_location': '',
                'compatibility_score': 0,
            })

    top_opportunities = [
        {
            'rank': index,
            'company': company.get('company', ''),
            'priority_score': safe_score(company.get('priority_score', 0)),
            'segment': company.get('segment', ''),
            'location': format_company_location(company),
            'commodity': company.get('commodity') or company.get('commodity_type', ''),
            'best_recommended_site': get_best_recommended_site_name(company),
            'best_site_match_score': safe_score(company.get('best_site_match_score', 0)),
        }
        for index, company in enumerate(top_companies, start=1)
    ]

    return {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'description': 'Compact OmniMapping opportunity summary',
            'top_limit': top_limit,
        },
        'counts': {
            'companies': len(companies),
            'segments': len(segments),
            'industrial_sites': len(sites),
            'rail_infrastructure_records': len(rail_infrastructure),
        },
        'top_opportunities': top_opportunities,
        'segment_averages': segment_averages,
        'state_counts': dict(sorted(state_counts.items())),
        'best_site_matches': best_site_matches,
    }


def export_summary_json(companies, segments, sites, rail_infrastructure, output_dir="exports", top_limit=20):
    """Write a compact JSON summary of loaded opportunity data."""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"summary_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    summary = build_export_summary(companies, segments, sites, rail_infrastructure, top_limit=top_limit)

    with open(filepath, 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"Exported summary to {filepath}")
    return filepath


def create_export_summary(companies, sites, output_dir="exports"):
    """Print a brief description of available export commands."""
    summary = {
        'companies': len(companies),
        'industrial_sites': len(sites),
        'export_directory': output_dir,
        'available_exports': [
            'ranked opportunities CSV',
            'site matching CSV',
            'segment analysis CSV',
            'geographic analysis CSV',
            'company profiles JSON',
            'opportunity briefs TXT',
            'compact summary JSON via --export-summary',
        ],
    }
    print(json.dumps(summary, indent=2))
