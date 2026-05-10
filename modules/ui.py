"""
OmniMapping UI Module
Handles all user interface and display functions for the economic development platform.
"""

import csv
import math
import os
from collections import defaultdict
from pathlib import Path

def load_csv(filename):
    """Load CSV data into a list of dictionaries"""
    with open(filename, newline="") as file:
        return list(csv.DictReader(file))


def validate_csv_file(filename, required_fields=None, numeric_fields=None, allow_blank=None):
    """Validate a single CSV file for malformed rows and field issues."""
    required_fields = required_fields or []
    numeric_fields = numeric_fields or []
    allow_blank = allow_blank or []
    issues = []

    with open(filename, newline="") as file:
        reader = csv.DictReader(file, restkey="__extra__", restval="")
        if not reader.fieldnames or all(str(field).strip() == "" for field in reader.fieldnames):
            issues.append(f"{filename}: missing or invalid header row")
            return issues

        missing_headers = [field for field in required_fields if field not in reader.fieldnames]
        if missing_headers:
            issues.append(f"{filename}: missing required header(s): {', '.join(missing_headers)}")

        line_number = 1
        try:
            for line_number, row in enumerate(reader, start=2):
                if row.get("__extra__"):
                    issues.append(f"{filename}: extra columns on line {line_number}: {row['__extra__']}")

                for field in required_fields:
                    if field not in row:
                        continue
                    value = str(row.get(field, "")).strip()
                    if value == "" and field not in allow_blank:
                        issues.append(f"{filename}: missing required '{field}' on line {line_number}")

                for field in numeric_fields:
                    if field not in row:
                        continue
                    value = str(row.get(field, "")).strip()
                    if value == "":
                        if field not in allow_blank:
                            issues.append(f"{filename}: missing numeric field '{field}' on line {line_number}")
                    else:
                        try:
                            float(value)
                        except ValueError:
                            issues.append(f"{filename}: non-numeric value for '{field}' on line {line_number}: {value}")
        except csv.Error as exc:
            issues.append(f"{filename}: malformed CSV row at line {line_number}: {exc}")

    return issues


def validate_data_files(data_dir="data"):
    """Validate all data CSV files prior to loading."""
    file_specs = {
        "segments.csv": {
            "required_fields": ["segment", "stage", "rail_score", "reason", "omnitrax_angle", "commodity_type"],
            "numeric_fields": ["rail_score"]
        },
        "companies.csv": {
            "required_fields": ["company", "segment", "state", "city", "commodity_type", "rail_fit_score", "industrial_real_estate_score"],
            "numeric_fields": ["rail_fit_score", "industrial_real_estate_score"]
        },
        "industrial_sites.csv": {
            "required_fields": ["site_name", "state", "city", "rail_served", "nearby_class1", "transload_available", "interstate_access", "port_access", "target_industries"],
            "numeric_fields": ["acres"],
            "allow_blank": ["acres"]
        },
        "rail_infrastructure.csv": {
            "required_fields": ["location", "type", "latitude", "longitude", "rail_connections", "capacity_score", "logistics_score"],
            "numeric_fields": ["latitude", "longitude", "rail_connections", "capacity_score", "logistics_score"]
        }
    }

    issues = []
    for filename, spec in file_specs.items():
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            issues.append(f"Missing data file: {filepath}")
            continue
        issues.extend(validate_csv_file(filepath,
                                        required_fields=spec.get("required_fields"),
                                        numeric_fields=spec.get("numeric_fields"),
                                        allow_blank=spec.get("allow_blank")))

    return issues


YES_VALUES = {'yes', 'true', '1', 'y'}

from .scoring import estimate_acreage_need, get_region, calculate_freight_intensity_score
from .data_quality import annotate_rail_quality, annotate_site_quality


def safe_int(value, default=0):
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default


def safe_float(value, default=None):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def normalize_string(value):
    return str(value or '').strip()


def normalize_list_field(value):
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


def parse_boolean_yes_no(value):
    return 'Yes' if str(value or '').strip().lower() in YES_VALUES else 'No'


def normalize_segment_record(segment):
    normalized = {k: normalize_string(v) for k, v in segment.items()}
    normalized['rail_score'] = safe_int(normalized.get('rail_score'), 0)
    return normalized


def normalize_company_record(company):
    normalized = {k: normalize_string(v) for k, v in company.items()}
    normalized['state'] = normalized.get('state', '').upper()
    normalized['rail_fit_score'] = safe_int(normalized.get('rail_fit_score'), 0)
    normalized['industrial_real_estate_score'] = safe_int(normalized.get('industrial_real_estate_score'), 0)
    normalized['inbound_materials'] = normalized.get('inbound_materials', '')
    normalized['outbound_products'] = normalized.get('outbound_products', '')
    normalized['inbound_materials_list'] = normalize_list_field(normalized.get('inbound_materials'))
    normalized['outbound_products_list'] = normalize_list_field(normalized.get('outbound_products'))
    min_need, max_need = estimate_acreage_need(normalized)
    normalized['estimated_acreage_need_range'] = f"{min_need}-{max_need} acres"
    normalized['freight_intensity_label'] = 'Medium'
    normalized['infrastructure_dependency'] = 'Moderate'
    normalized['where_to_focus'] = ''
    return normalized


def normalize_site_record(site):
    normalized = {k: normalize_string(v) for k, v in site.items()}
    normalized['state'] = normalized.get('state', '').upper()
    normalized['rail_served'] = parse_boolean_yes_no(normalized.get('rail_served'))
    normalized['transload_available'] = parse_boolean_yes_no(normalized.get('transload_available'))
    normalized['interstate_access'] = parse_boolean_yes_no(normalized.get('interstate_access'))
    normalized['port_access'] = parse_boolean_yes_no(normalized.get('port_access'))
    normalized['acres'] = normalize_string(normalized.get('acres'))
    normalized['acres_numeric'] = safe_float(normalized.get('acres'))
    industries = normalize_list_field(normalized.get('target_industries'))
    normalized['target_industries'] = ', '.join(industries)
    normalized['target_industries_list'] = industries
    normalized['site_region'] = get_region(normalized.get('state'))
    return annotate_site_quality(normalized)


def normalize_rail_infrastructure_record(record):
    normalized = {k: normalize_string(v) for k, v in record.items()}
    normalized['latitude'] = safe_float(normalized.get('latitude'))
    normalized['longitude'] = safe_float(normalized.get('longitude'))
    normalized['rail_connections'] = safe_int(normalized.get('rail_connections'))
    normalized['capacity_score'] = safe_int(normalized.get('capacity_score'))
    normalized['logistics_score'] = safe_int(normalized.get('logistics_score'))
    return annotate_rail_quality(normalized)


def site_match_quality_label(score):
    if score >= 90:
        return 'Excellent'
    if score >= 75:
        return 'Strong'
    if score >= 60:
        return 'Good'
    if score >= 40:
        return 'Moderate'
    return 'Limited'


def get_freight_intensity_label(company):
    score = calculate_freight_intensity_score(company)
    if score >= 15:
        return 'High'
    if score >= 8:
        return 'Medium'
    return 'Low'


def generate_infrastructure_dependency(company):
    if company.get('transload_potential', '').lower() == 'high' and company.get('nearest_port'):
        return 'High rail-port-transload dependency'
    if company.get('nearest_port'):
        return 'Moderate port-enabled logistics dependency'
    if company.get('transload_potential', '').lower() == 'medium':
        return 'Moderate transload dependency'
    return 'Rail-dependent industrial logistics'


def generate_recommended_next_action(company, best_site_name=None):
    if best_site_name:
        return (
            f"Begin outreach with a site assessment for {best_site_name}, "
            f"emphasizing acreage, rail access, and transload capability for {company.get('segment', 'the segment')}."
        )

    return (
        f"Identify a rail-served site in {company.get('state', 'the region')} "
        f"with {company.get('estimated_acreage_need_range', 'the right')} for early discussions with the company's real estate team."
    )


def summarize_opportunity_risk(company, match_score):
    if match_score < 50:
        return 'Primary constraint is site fit; confirm acreage and multimodal access before outreach.'
    if company.get('industrial_real_estate_score', 0) <= 2:
        return 'Industrial real estate appetite is moderate; validate market timing and zoning early.'
    return 'Main risk is execution speed; prioritize site control and rail logistics planning.'


def format_score_breakdown(breakdown):
    """Format a numeric score breakdown into a readable summary."""
    if not breakdown:
        return "No score details available."

    ordered_keys = ["rail_fit", "logistics_intensity", "land_intensity", "multimodal_potential", "site_match_quality", "industry_fit", "strategic_fit"]
    labels = {
        "rail_fit": "Rail Fit",
        "logistics_intensity": "Logistics Intensity",
        "land_intensity": "Land Intensity",
        "multimodal_potential": "Multimodal Potential",
        "site_match_quality": "Site Match Quality",
        "industry_fit": "Industry Fit",
        "strategic_fit": "Strategic Fit"
    }

    parts = []
    for key in ordered_keys:
        if key in breakdown:
            parts.append(f"{labels[key]}: {int(breakdown[key])}")

    return ", ".join(parts)


def get_priority_reasons(company):
    """Return plain-English priority reasoning from the score breakdown."""
    breakdown = company.get("score_breakdown", {})
    reasons = []

    if breakdown.get("rail_fit", 0) >= 20:
        reasons.append("Strong rail fit for the company's supply chain segment.")
    if breakdown.get("multimodal_potential", 0) >= 12:
        reasons.append("Good multimodal access to rail hubs, ports, and regional infrastructure.")
    if breakdown.get("logistics_intensity", 0) >= 14:
        reasons.append("The company's inbound/outbound materials indicate high logistics intensity.")
    if breakdown.get("site_match_quality", 0) >= 8:
        reasons.append("Existing site availability is strongly aligned with the company's needs.")
    if breakdown.get("industry_fit", 0) >= 4:
        reasons.append("Industry and commodity profile matches rail-served industrial site requirements.")
    if breakdown.get("land_intensity", 0) >= 10:
        reasons.append("Land intensity is significant, signaling development opportunity.")
    if breakdown.get("strategic_fit", 0) >= 6:
        reasons.append("The opportunity aligns with OmniTRAX strategic positioning.")

    if company.get('nearest_port'):
        reasons.append("Nearby port access improves regional import/export logistics.")
    if company.get('nearest_class1_railroad'):
        reasons.append("Close proximity to a Class 1 railroad enhances rail connectivity.")

    if not reasons:
        reasons.append("Balanced opportunity across rail, logistics, and regional access.")

    return reasons


def build_why_ranked_explanation(company, best_site=None, max_drivers=3):
    """Build a concise explanation of why the company ranks in the top opportunities."""
    reasons = get_priority_reasons(company)
    top_drivers = get_top_score_drivers(company.get('score_breakdown', {}), limit=max_drivers)

    explanation = []
    if reasons:
        explanation.append(reasons[0])

    if top_drivers:
        driver_text = ", ".join(f"{label} ({value})" for label, value in top_drivers)
        explanation.append(f"Key score drivers: {driver_text}.")

    materials = []
    if company.get('inbound_materials'):
        materials.append(f"inbound materials: {company['inbound_materials']}")
    if company.get('outbound_products'):
        materials.append(f"outbound products: {company['outbound_products']}")
    if materials:
        explanation.append(f"Materials profile: {'; '.join(materials)}.")

    geography = []
    if company.get('nearest_class1_railroad'):
        geography.append(f"nearest Class 1 railroad: {company['nearest_class1_railroad']}")
    if company.get('nearest_port'):
        geography.append(f"nearest port: {company['nearest_port']}")
    if company.get('nearest_major_city'):
        geography.append(f"nearest major city: {company['nearest_major_city']}")
    if geography:
        explanation.append(f"Geographic strengths: {'; '.join(geography)}.")

    if best_site and best_site.get('site_name'):
        compatibility_score = best_site.get('compatibility_score', company.get('best_site_match_score', 'N/A'))
        explanation.append(
            f"Best site match: {best_site['site_name']} ({compatibility_score}/100)."
        )

    return explanation or ["Strong rail and logistics ranking with good site potential."]


def get_top_score_drivers(breakdown, limit=3):
    """Return the top score drivers from the score breakdown."""
    if not breakdown:
        return []

    labels = {
        "rail_fit": "Rail Fit",
        "logistics_intensity": "Logistics Intensity",
        "land_intensity": "Land Intensity",
        "multimodal_potential": "Multimodal Potential",
        "site_match_quality": "Site Match Quality",
        "industry_fit": "Industry Fit",
        "strategic_fit": "Strategic Fit"
    }

    top_items = sorted(breakdown.items(), key=lambda item: item[1], reverse=True)
    return [(labels.get(key, key.replace("_", " ").title()), int(value)) for key, value in top_items[:limit]]


def format_rail_logistics_rationale(company):
    rationale = []
    rail_fit_score = company.get('rail_fit_score')
    if rail_fit_score is not None and str(rail_fit_score).strip() != '':
        rationale.append(f"Rail fit score: {rail_fit_score}/5.")

    if company.get('freight_intensity_label'):
        rationale.append(f"Freight intensity: {company['freight_intensity_label']}.")

    if company.get('site_match_quality_label'):
        rationale.append(f"Site match quality: {company['site_match_quality_label']}.")

    if company.get('nearest_class1_railroad'):
        rationale.append(f"Nearest Class 1 railroad: {company['nearest_class1_railroad']}." )

    if company.get('nearest_port'):
        rationale.append(f"Nearest port: {company['nearest_port']}." )

    if company.get('omnitrax_outreach_angle'):
        rationale.append(company['omnitrax_outreach_angle'])

    return rationale or ["Rail and logistics rationale not available from current data."]


def format_company_context(company, segment_data):
    """Summarize company context from loaded company and segment records."""
    context = []

    if company.get('why_target'):
        context.append(company['why_target'])

    materials = []
    if company.get('inbound_materials'):
        materials.append(f"inbound materials: {company['inbound_materials']}")
    if company.get('outbound_products'):
        materials.append(f"outbound products: {company['outbound_products']}")
    if materials:
        context.append(f"Materials flow includes {'; '.join(materials)}.")

    if segment_data.get('reason'):
        context.append(f"Segment rationale: {segment_data['reason']}")

    return context or ["No additional company context available in current data."]


def format_site_fit_summary(company, recommended_site):
    """Summarize the recommended site fit using existing site attributes."""
    if not recommended_site:
        return ["No recommended site is available from current site data."]

    fit = []
    score = company.get('best_site_match_score', 'N/A')
    fit.append(
        f"{recommended_site.get('site_name', 'Unknown')} is the recommended fit at "
        f"{score}/100 site compatibility."
    )

    site_details = []
    location_parts = [recommended_site.get('city'), recommended_site.get('state')]
    location = ', '.join(part for part in location_parts if part)
    if location:
        site_details.append(f"location: {location}")
    if recommended_site.get('acres'):
        site_details.append(f"acres: {recommended_site.get('acres')}")
    if company.get('estimated_acreage_need_range'):
        site_details.append(f"estimated company need: {company.get('estimated_acreage_need_range')}")
    if recommended_site.get('target_industries'):
        site_details.append(f"target industries: {recommended_site.get('target_industries')}")
    if site_details:
        fit.append("; ".join(site_details) + ".")

    access = []
    for label, field in [
        ("rail served", "rail_served"),
        ("transload", "transload_available"),
        ("interstate", "interstate_access"),
        ("port", "port_access"),
    ]:
        if recommended_site.get(field):
            access.append(f"{label}: {recommended_site.get(field)}")
    if access:
        fit.append("Site access profile: " + "; ".join(access) + ".")

    return fit


def format_transload_site_angle(company, recommended_site):
    """Build a transload and site-development angle from current data."""
    angle = []

    if recommended_site:
        transload = recommended_site.get('transload_available', 'No')
        rail_served = recommended_site.get('rail_served', 'No')
        angle.append(
            f"Position the site around rail-served access ({rail_served}) and "
            f"transload availability ({transload})."
        )

        if recommended_site.get('port_access'):
            angle.append(f"Port access in site data: {recommended_site.get('port_access')}.")

    if company.get('transload_potential'):
        angle.append(f"Company transload potential: {company.get('transload_potential')}.")

    if company.get('omnitrax_outreach_angle'):
        angle.append(f"Outreach angle: {company.get('omnitrax_outreach_angle')}")

    return angle or ["No transload or site angle is available from current data."]


def print_verification_summary(companies, sites, segments, limit=20):
    """Print a concise verification summary of the top opportunity companies and their best site matches."""
    from .search import get_top_opportunities, find_best_sites_for_company

    top_companies = get_top_opportunities(companies, limit)
    print_header("Verification Summary: Top 20 Opportunities")

    for index, company in enumerate(top_companies, start=1):
        score = safe_int(company.get('priority_score', 0))
        summary = format_score_breakdown(company.get('score_breakdown', {}))
        reasons = get_priority_reasons(company)
        site_match = find_best_sites_for_company(company, sites, 1)
        best_site = site_match[0] if site_match else None

        print(f"\n{index}. {company.get('company', 'Unknown')} ({company.get('state', 'Unknown')}) - Score {score}/100")
        print(f"   Breakdown: {summary}")
        print(f"   Primary priority reason: {reasons[0] if reasons else 'Strong rail and logistics alignment.'}")

        if best_site:
            site = best_site['site']
            print(f"   Top site match: {site.get('site_name', 'Unknown')} ({best_site['compatibility_score']}/100)")

    print(f"\nLoaded {len(companies)} companies, {len(sites)} sites, {len(segments)} segments.")


def print_header(title):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def print_company_profile(company, segment_data, show_details=False):
    """Print formatted company information"""
    rail_fit = int(company.get('rail_fit_score', 0))
    industrial_real_estate_fit = int(company.get('industrial_real_estate_score', 0))
    priority_score = safe_int(company.get('priority_score', 0))
    breakdown = company.get('score_breakdown', {})
    breakdown_summary = format_score_breakdown(breakdown)

    print(f"""
{company['company']} ({company.get('state', 'Unknown')})
   Location: {company.get('city', 'Unknown')}, {company.get('state', 'Unknown')}
   Segment: {company.get('segment', 'Unknown')}
   Commodity: {company.get('commodity_type', 'Unknown')}

   Priority Score: {priority_score}/100
   Breakdown: {breakdown_summary}
   Freight Intensity: {company.get('freight_intensity_label', 'Medium')}
   Estimated Land Need: {company.get('estimated_acreage_need_range', 'Unknown')}
   Best Site Match: {company.get('best_site_name', 'TBD')} ({company.get('best_site_match_score', 0)}/100)
   Site Match Quality: {company.get('site_match_quality_label', 'Unknown')}
   Infrastructure Dependency: {company.get('infrastructure_dependency', 'Moderate')}""")

    if show_details:
        reasons = get_priority_reasons(company)
        print(f"""
   Inbound Materials: {company.get('inbound_materials', 'N/A')}
   Outbound Products: {company.get('outbound_products', 'N/A')}
   Why Target: {company.get('why_target', 'N/A')}
   OmniTRAX Angle: {company.get('omnitrax_outreach_angle', 'N/A')}""")
        print("\n   Why this opportunity is prioritized:")
        for reason in reasons:
            print(f"   • {reason}")

    # Add geographic information if available
    if 'latitude' in company and 'longitude' in company:
        print(f"   Coordinates: {company['latitude']}, {company['longitude']}")

    if 'nearest_major_city' in company:
        print(f"   Nearest Major City: {company['nearest_major_city']}")

    if 'nearest_port' in company:
        print(f"   Nearest Port: {company['nearest_port']}")

    if 'nearest_class1_railroad' in company:
        print(f"   Nearest Class 1 Railroad: {company['nearest_class1_railroad']}")

    print(f"   {'─'*50}")

def print_site_profile(site, show_details=False):
    """Print formatted industrial site information"""
    print(f"""
{site['site_name']} ({site.get('state', 'Unknown')})
   Location: {site.get('city', 'Unknown')}, {site.get('state', 'Unknown')}
   Rail Served: {site.get('rail_served', 'No')}
   Acres Available: {site.get('acres', 'Unknown')}
   Nearby Class 1: {site.get('nearby_class1', 'Unknown')}
   Transload Available: {site.get('transload_available', 'No')}
   Interstate Access: {site.get('interstate_access', 'No')}
   Port Access: {site.get('port_access', 'No')}""")

    if show_details and 'target_industries' in site:
        print(f"   Target Industries: {site['target_industries']}")

    print(f"   {'─'*50}")

def print_opportunity_brief(company, segment_data, recommended_site=None):
    """Print a concise economic-development business-development memo."""
    print_header("OPPORTUNITY BRIEF")

    company_name = company.get('company', 'Unknown')
    location = f"{company.get('city', 'Unknown')}, {company.get('state', 'Unknown')}"
    commodity = company.get('commodity') or company.get('commodity_type', 'Unknown')
    top_drivers = get_top_score_drivers(company.get('score_breakdown', {}))
    rail_rationale = format_rail_logistics_rationale(company)
    company_context = format_company_context(company, segment_data)
    site_fit = format_site_fit_summary(company, recommended_site)
    transload_angle = format_transload_site_angle(company, recommended_site)

    print(f"COMPANY: {company_name}")
    print(f"LOCATION: {location}")
    print(f"SEGMENT: {company.get('segment', 'Unknown')}")
    print(f"COMMODITY: {commodity}")
    print(f"PRIORITY SCORE: {company.get('priority_score', '0')}/100")
    print(f"FREIGHT INTENSITY: {company.get('freight_intensity_label', 'Unknown')}")
    print(f"SITE MATCH QUALITY: {company.get('site_match_quality_label', 'Unknown')} ({company.get('best_site_match_score', 0)}/100)")
    print(f"INFRASTRUCTURE DEPENDENCY: {company.get('infrastructure_dependency', 'Unknown')}")

    print("\n1. COMPANY CONTEXT:")
    for line in company_context:
        print(f"   - {line}")

    print("\n2. TOP SCORE DRIVERS:")
    if top_drivers:
        for label, value in top_drivers:
            print(f"   - {label}: {value}")
    else:
        print("   - No score drivers available from current data.")

    print("\n3. RAIL / LOGISTICS RATIONALE:")
    for line in rail_rationale:
        print(f"   - {line}")

    print("\n4. RECOMMENDED SITE FIT:")
    for line in site_fit:
        print(f"   - {line}")

    print("\n5. BEST RECOMMENDED INDUSTRIAL SITE:")
    if recommended_site:
        print(f"   {recommended_site.get('site_name', 'Unknown')} ({recommended_site.get('city', 'Unknown')}, {recommended_site.get('state', 'Unknown')})")
        print(f"   - Rail Served: {recommended_site.get('rail_served', 'No')}")
        print(f"   - Transload: {recommended_site.get('transload_available', 'No')}")
        print(f"   - Port Access: {recommended_site.get('port_access', 'No')}")
        print(f"   - Acres: {recommended_site.get('acres', 'Unknown')}")
        print(f"   - Target Industries: {recommended_site.get('target_industries', 'Unknown')}")
    else:
        print("   No specific site recommendation available from current data.")

    print("\n6. TRANSLOAD / SITE ANGLE:")
    for line in transload_angle:
        print(f"   - {line}")

    if company.get('opportunity_risk'):
        print("\n7. KEY RISK OR CONSTRAINT:")
        print(f"   {company['opportunity_risk']}")

    print("\n8. NEXT ACTION:")
    print(f"   {company.get('recommended_next_action', 'Confirm site fit and engage the company for a rail/real estate review.')}")

def display_main_menu():
    """Display the main menu options"""
    print("""
OmniMapping Economic Development Platform - Main Menu:
1. Search companies
2. Browse supply chain segments
3. Filter by state
4. Filter by commodity
5. Filter by minimum score
6. View top 20 opportunities
7. View company detail profile
8. Generate opportunity brief
9. Industrial site matching
10. Export ranked opportunities to CSV
11. Generate maps
12. Geographic intelligence & analysis
13. Exit

Scoring: Companies ranked 1-100 based on rail fit, bulk potential, and development opportunity""")

def display_map_menu():
    """Display the map generation menu"""
    print("""
Map Generation Options:
1. Generate company locations map
2. Generate industrial sites map
3. Generate top opportunities map
4. Return to main menu""")

def display_export_menu():
    """Display the export options menu"""
    print("""
Export Options:
1. Export top 20 opportunities (CSV)
2. Export all companies (CSV)
3. Export opportunity briefs (TXT)
4. Export company profiles (JSON)
5. Export site matching report (CSV)
6. Return to main menu""")

def get_user_choice(min_val, max_val, prompt="Enter your choice"):
    """Get validated user input for menu choices"""
    while True:
        try:
            choice = int(input(f"\n{prompt} ({min_val}-{max_val}): ").strip())
            if min_val <= choice <= max_val:
                return choice
            else:
                print(f"Please enter a number between {min_val} and {max_val}.")
        except ValueError:
            print("Please enter a valid number.")

def get_search_term():
    """Get search term from user"""
    return input("Enter search term (company name, segment, state, city, or commodity): ").strip()

def get_state_filter():
    """Get state filter from user"""
    return input("Enter state abbreviation (e.g., TX, CA, IL): ").strip().upper()

def get_commodity_filter():
    """Get commodity filter from user"""
    return input("Enter commodity type: ").strip()

def get_min_score():
    """Get minimum score filter from user"""
    while True:
        try:
            score = int(input("Enter minimum priority score (1-100): "))
            if 1 <= score <= 100:
                return score
            else:
                print("Please enter a score between 1 and 100.")
        except ValueError:
            print("Please enter a valid number.")

def get_company_selection(companies, prompt="Select a company"):
    """Get company selection from user"""
    print(f"\nAvailable Companies (showing first 20):")
    for i, company in enumerate(companies[:20], 1):
        print(f"{i}. {company['company']} ({company.get('city', 'Unknown')}, {company.get('state', 'Unknown')}) - Score: {company.get('priority_score', '0')}")

    if len(companies) > 20:
        print(f"... and {len(companies) - 20} more companies")

    return get_user_choice(1, len(companies), f"{prompt} (1-{len(companies)})") - 1

def print_geographic_intelligence(geo_intel):
    """Display comprehensive geographic intelligence profile"""
    print(f"""
Company: {geo_intel.get('company', 'Unknown')}
Location: {geo_intel.get('city', 'Unknown')}, {geo_intel.get('state', 'Unknown')}

═══════════════════════════════════════════════════════════════
GEOGRAPHIC INTELLIGENCE PROFILE
═══════════════════════════════════════════════════════════════

📍 RAIL INFRASTRUCTURE ACCESS:
   • Nearest Hub: {geo_intel.get('nearest_rail_hub', 'Unknown')}
   • Distance: {geo_intel.get('rail_distance_miles', 'Unknown')} miles
   • Rail Connections: {geo_intel.get('rail_connections', 0)}
   • Rail Logistics Score: {geo_intel.get('rail_logistics_score', 0)}/10
   • Transload Hub: {geo_intel.get('transload_hub_available', 'No')}

⚓ MARITIME ACCESS:
   • Nearest Port: {geo_intel.get('nearest_port', 'Not accessible')}
   • Distance: {geo_intel.get('port_distance_miles', 'Unknown')} miles
   • Port Accessible: {'Yes' if geo_intel.get('port_accessible') else 'No'}

🏙️  CONSUMER MARKET ACCESS:
   • Nearest Major City: {geo_intel.get('nearest_major_city', 'Unknown')}
   • Region: {geo_intel.get('region', 'Unknown')}
   • Distance: {geo_intel.get('city_distance_miles', 'Unknown')} miles
   • Consumer Market Access: {'Strong' if geo_intel.get('consumer_market_access') else 'Limited'}

📊 LOGISTICS SCORING:
   • Multimodal Logistics Score: {int(geo_intel.get('multimodal_logistics_score', 0))}/100
   • Geographic Opportunity Score: {int(geo_intel.get('geographic_opportunity_score', 0))}/100

🏭 INDUSTRIAL LAND REQUIREMENTS:
   • Minimum Acres: {geo_intel.get('industrial_land_minimum_acres', 'Unknown')}
   • Average Acres: {geo_intel.get('industrial_land_average_acres', 'Unknown')}
   • Maximum Acres: {geo_intel.get('industrial_land_maximum_acres', 'Unknown')}
""")

def print_multimodal_profile(logistics_profile):
    """Display multimodal logistics profile"""
    print(f"""
═══════════════════════════════════════════════════════════════
MULTIMODAL LOGISTICS PROFILE
═══════════════════════════════════════════════════════════════

Company: {logistics_profile.get('company', 'Unknown')}
Location: {logistics_profile.get('city', 'Unknown')}, {logistics_profile.get('state', 'Unknown')}

🚆 RAIL ACCESS SCORE: {int(logistics_profile.get('multimodal_logistics_score', 0))}/100

📍 Rail Infrastructure:
   • Nearest Hub: {logistics_profile.get('rail_hub', 'Unknown')}
   • Distance: {logistics_profile.get('rail_distance_miles', 'Unknown')} miles
   • Connections: {logistics_profile.get('rail_connections', 0)}
   • Capacity: {logistics_profile.get('rail_capacity_score', 0)}/5
   • Transload Available: {logistics_profile.get('transload_available', 'No')}

⚓ Maritime Logistics:
   • Nearest Port: {logistics_profile.get('nearest_port', 'Not accessible')}
   • Distance: {logistics_profile.get('port_distance_miles', 'Unknown')} miles
   • Accessible: {'Yes' if logistics_profile.get('port_accessible') else 'No'}

🏙️  Market Proximity:
   • Nearest City: {logistics_profile.get('nearest_major_city', 'Unknown')}
   • Region: {logistics_profile.get('city_region', 'Unknown')}

💡 Multimodal Logistics Score: {int(logistics_profile.get('multimodal_logistics_score', 0))}/100
""")

def print_regional_opportunity(regional_analysis):
    """Display regional economic opportunity analysis"""
    print(f"""
═══════════════════════════════════════════════════════════════
REGIONAL OPPORTUNITY ANALYSIS
═══════════════════════════════════════════════════════════════

Company: {regional_analysis.get('company', 'Unknown')}
State: {regional_analysis.get('state', 'Unknown')}
Region: {regional_analysis.get('region', 'Unknown')}

🌍 REGIONAL OPPORTUNITY SCORE: {int(regional_analysis.get('regional_opportunity_score', 0))}/100

Strategic Regional Position:
   • Nearest Major Hub: {regional_analysis.get('nearest_major_hub', 'Unknown')}
   • Distance to Hub: {regional_analysis.get('hub_distance_miles', 'Unknown')} miles
   • Hub Type: {regional_analysis.get('hub_type', 'Unknown')}
   • Hub Logistics Rating: {regional_analysis.get('logistics_rating', 0)}/10

Economic Development Potential:
   This company operates in a {regional_analysis.get('region', 'Unknown')} region,
   which offers significant economic development opportunities through
   rail infrastructure alignment and multimodal logistics connectivity.
""")

def display_geographic_analysis_menu():
    """Display geographic analysis menu"""
    print(f"""
Geographic Intelligence & Analysis Menu:
1. View geographic profiles for all companies
2. Analyze geographic clustering by state
3. Generate geographic opportunity map
4. Export geographic profiles to CSV
5. View multimodal logistics analysis
6. Return to main menu""")

def get_companies_by_segment(companies):
    """Get companies grouped by segment with statistics"""
    segment_stats = defaultdict(lambda: {'count': 0, 'avg_score': 0, 'companies': []})
    
    for company in companies:
        segment = company.get('segment', 'Unknown')
        score = safe_int(company.get('priority_score', 0))
        segment_stats[segment]['companies'].append(company)
        segment_stats[segment]['count'] += 1
        segment_stats[segment]['avg_score'] += score
    
    # Calculate averages
    for segment in segment_stats:
        if segment_stats[segment]['count'] > 0:
            segment_stats[segment]['avg_score'] /= segment_stats[segment]['count']
            segment_stats[segment]['avg_score'] = round(segment_stats[segment]['avg_score'], 1)
    
    return segment_stats

def filter_by_state(companies, state):
    """Filter companies by state"""
    return [c for c in companies if c.get('state', '').upper() == state.upper()]

def filter_by_commodity(companies, commodity):
    """Filter companies by commodity type"""
    return [c for c in companies if c.get('commodity_type', '').lower() == commodity.lower()]

def filter_by_min_score(companies, min_score):
    """Filter companies by minimum priority score"""
    return [c for c in companies if safe_int(c.get('priority_score', 0)) >= min_score]

def get_top_opportunities(companies, limit=20):
    """Get top-ranked opportunities by priority score"""
    return sorted(companies, key=lambda x: safe_int(x.get('priority_score', 0)), reverse=True)[:limit]
