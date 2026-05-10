#!/usr/bin/env python3
"""
OmniMapping Economic Development Platform
A comprehensive rail opportunity analysis and prospecting tool.
"""

import argparse
import os
import sys

from modules.ui import *
from modules.scoring import *
from modules.search import *
from modules.export import *
from modules.geography import *
from modules.geographic_scoring import *
from modules.data_quality import build_data_quality_report

def safe_score(value, default=0):
    """Convert score-like values to integers without interrupting verification."""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def load_data():
    """Load all data files"""
    try:
        issues = validate_data_files()
        if issues:
            print_header("Data Validation Issues")
            for issue in issues:
                print(f"- {issue}")
            print("Please fix the reported CSV issues before running OmniMapping.")
            sys.exit(1)

        segments = [normalize_segment_record(s) for s in load_csv("data/segments.csv")]
        companies = [normalize_company_record(c) for c in load_csv("data/companies.csv")]
        sites = [normalize_site_record(s) for s in load_csv("data/industrial_sites.csv")]
        rail_infrastructure = [normalize_rail_infrastructure_record(r) for r in load_csv("data/rail_infrastructure.csv")]

        # Enhance companies with geographic intelligence
        companies = enhance_company_geography(companies, rail_infrastructure)

        # Calculate priority scores and derived site fit context for all companies
        for company in companies:
            segment_data = next((s for s in segments if s["segment"] == company.get("segment")), {})
            best_match_score = 0
            best_site_name = None
            best_site_location = ''

            if sites:
                scored_sites = [
                    (site, calculate_site_compatibility_score(company, site))
                    for site in sites
                ]
                best_site, best_match_score = max(scored_sites, key=lambda item: item[1])
                best_site_name = best_site.get('site_name')
                best_site_city = best_site.get('city', '')
                best_site_state = best_site.get('state', '')
                best_site_location = f"{best_site_city}, {best_site_state}" if best_site_city and best_site_state else best_site_city or best_site_state

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

        return segments, companies, sites, rail_infrastructure
    except FileNotFoundError as e:
        print(f"Error loading data files: {e}")
        print("Please ensure all data files are present in the data/ directory.")
        sys.exit(1)


def print_verification_check(name, passed, detail):
    """Print a single verification check with a consistent pass/fail marker."""
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}: {detail}")


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


def run_verification():
    """Run a non-interactive data validation and scoring verification."""
    print_header("OmniMapping Verification")
    failures = []

    csv_issues = validate_data_files()
    if csv_issues:
        failures.extend(csv_issues)
        print_verification_check("CSV validation", False, f"{len(csv_issues)} issue(s) found")
        for issue in csv_issues:
            print(f"  - {issue}")
        print()
        print("FAIL OmniMapping verification failed.")
        return 1

    print_verification_check("CSV validation", True, "all required data files and fields are valid")

    try:
        segments, companies, sites, rail_infrastructure = load_data()
    except SystemExit as exc:
        # load_data already printed the error.
        return exc.code if isinstance(exc.code, int) else 1
    except Exception as exc:
        print(f"Verification failed: {exc}")
        return 1

    print(f"Loaded {len(companies)} companies across {len(set(c.get('segment') for c in companies))} segments")
    print(f"Loaded {len(sites)} industrial sites")
    print(f"Loaded {len(rail_infrastructure)} rail infrastructure records")
    print()

    data_loaded = bool(segments and companies and sites and rail_infrastructure)
    if not segments:
        failures.append("No segments loaded")
    if not companies:
        failures.append("No companies loaded")
    if not sites:
        failures.append("No industrial sites loaded")
    if not rail_infrastructure:
        failures.append("No rail infrastructure records loaded")
    print_verification_check(
        "Data load",
        data_loaded,
        f"{len(segments)} segments, {len(companies)} companies, {len(sites)} sites, {len(rail_infrastructure)} rail records"
    )

    score_failures = collect_score_range_failures(companies)
    failures.extend(score_failures)
    print_verification_check(
        "Score calculation",
        not score_failures and bool(companies),
        "all company priority, breakdown, and site match scores are 0-100" if not score_failures else f"{len(score_failures)} score issue(s) found"
    )
    for issue in score_failures[:10]:
        print(f"  - {issue}")
    if len(score_failures) > 10:
        print(f"  - ... {len(score_failures) - 10} more")

    top_companies = get_top_opportunities(companies, 20)
    top_sorted = bool(top_companies) and top_opportunities_are_sorted(top_companies)
    if not top_companies:
        failures.append("Top opportunities list is empty")
    elif not top_sorted:
        failures.append("Top opportunities are not sorted by descending priority_score")
    print_verification_check(
        "Top opportunities sort",
        top_sorted,
        f"top {len(top_companies)} opportunities sorted descending by priority_score" if top_sorted else "top opportunities are not sorted correctly"
    )

    site_match_failures = collect_site_match_failures(companies, sites) if companies and sites else ["Cannot check site matching without companies and sites"]
    failures.extend(site_match_failures)
    print_verification_check(
        "Site matching",
        not site_match_failures,
        "top company site matches exist, score 0-100, and sort descending" if not site_match_failures else f"{len(site_match_failures)} site matching issue(s) found"
    )
    for issue in site_match_failures[:10]:
        print(f"  - {issue}")
    if len(site_match_failures) > 10:
        print(f"  - ... {len(site_match_failures) - 10} more")

    data_quality = build_data_quality_report(sites, rail_infrastructure)
    print()
    print_header("Data Quality Summary")
    print("Source confidence:")
    for confidence, count in data_quality['source_confidence_counts'].items():
        print(f"  - {confidence}: {count}")
    print(f"Blank acreage sites: {data_quality['blank_acreage_sites']}")
    print(f"Approximate coordinate records: {data_quality['approximate_coordinate_records']}")
    print(f"Missing Class I site details: {data_quality['missing_class1_sites']}")
    print(f"Missing interstate site details: {data_quality['missing_interstate_sites']}")
    print(f"Missing port site details: {data_quality['missing_port_sites']}")
    print(f"Missing transload site details: {data_quality['missing_transload_sites']}")
    print(f"Missing interstate rail details: {data_quality['missing_interstate_rail_records']}")
    print(f"Missing port rail details: {data_quality['missing_port_rail_records']}")
    print(f"Missing transload rail details: {data_quality['missing_transload_rail_records']}")
    print(f"Needs confirmation: {data_quality['sites_needing_confirmation']} sites, {data_quality['rail_records_needing_confirmation']} rail records")

    if not failures and top_companies:
        print()
        print_header("Top 20 Verified Opportunities")
        for i, company in enumerate(top_companies, 1):
            print(f"{i:2}. {company.get('company', 'Unknown')} | Score: {company.get('priority_score', '0')} | Segment: {company.get('segment', 'Unknown')}")

        sample_company = top_companies[0]
        site_matches = find_best_sites_for_company(sample_company, sites, 3)
        best_site = site_matches[0]
        print()
        print_header("Site Matching Verification")
        print(f"Top company: {sample_company.get('company', 'Unknown')}")
        print(f"Matched site: {best_site['site'].get('site_name', 'Unknown')} | Compatibility: {best_site['compatibility_score']}/100")

    print()
    if failures:
        print(f"FAIL OmniMapping verification failed with {len(failures)} issue(s).")
        return 1

    print("PASS OmniMapping verification completed successfully.")
    return 0


def handle_search_menu(companies):
    """Handle search and filtering operations"""
    while True:
        print_header("Search & Filter Menu")
        print("1. Search companies by keyword")
        print("2. Filter by state")
        print("3. Filter by commodity type")
        print("4. Filter by minimum score")
        print("5. Browse by segment")
        print("6. Return to main menu")

        choice = get_user_choice(1, 6)

        if choice == 1:
            query = get_search_term()
            results = search_companies(companies, query)
            results.sort(key=lambda x: safe_score(x.get('priority_score', 0)), reverse=True)

            if results:
                print_header(f"Search Results for '{query}' ({len(results)} found)")
                for company in results[:10]:  # Show top 10
                    segment_data = {'segment': company.get('segment')}
                    print_company_profile(company, segment_data)
            else:
                print(f"No companies found matching '{query}'.")

        elif choice == 2:
            state = get_state_filter()
            results = filter_by_state(companies, state)

            if results:
                results.sort(key=lambda x: safe_score(x.get('priority_score', 0)), reverse=True)
                print_header(f"Companies in {state} ({len(results)} found)")
                for company in results[:10]:
                    segment_data = {'segment': company.get('segment')}
                    print_company_profile(company, segment_data)
            else:
                print(f"No companies found in {state}.")

        elif choice == 3:
            print("Available commodities:", ", ".join(set(c.get('commodity_type', '') for c in companies if c.get('commodity_type'))))
            commodity = get_commodity_filter()
            results = filter_by_commodity(companies, commodity)

            if results:
                results.sort(key=lambda x: safe_score(x.get('priority_score', 0)), reverse=True)
                print_header(f"{commodity} Companies ({len(results)} found)")
                for company in results[:10]:
                    segment_data = {'segment': company.get('segment')}
                    print_company_profile(company, segment_data)
            else:
                print(f"No companies found in {commodity} commodity.")

        elif choice == 4:
            min_score = get_min_score()
            results = filter_by_min_score(companies, min_score)

            if results:
                print_header(f"High-Priority Opportunities (Score ≥ {min_score}) ({len(results)} found)")
                for company in results[:10]:
                    segment_data = {'segment': company.get('segment')}
                    print_company_profile(company, segment_data)
            else:
                print(f"No companies found with score >= {min_score}.")

        elif choice == 5:
            segment_stats = get_companies_by_segment(companies)

            print_header("Supply Chain Segments")
            segment_list = list(segment_stats.keys())
            for i, segment in enumerate(segment_list, 1):
                stats = segment_stats[segment]
                print(f"{i}. {segment} ({stats['count']} companies, avg score: {stats['avg_score']})")

            if segment_list:
                choice = get_user_choice(1, len(segment_list), "Choose segment number")
                selected_segment = segment_list[choice - 1]
                segment_companies = segment_stats[selected_segment]['companies']
                segment_companies.sort(key=lambda x: safe_score(x.get('priority_score', 0)), reverse=True)

                print(f"\nTop companies in {selected_segment}:")
                for company in segment_companies[:10]:
                    segment_data = {'segment': selected_segment}
                    print_company_profile(company, segment_data)

        elif choice == 6:
            break

def handle_site_matching(companies, sites, segments):
    """Handle industrial site matching operations"""
    print_header("Industrial Site Matching")

    # Show available sites
    print("Available Industrial Sites:")
    for i, site in enumerate(sites[:10], 1):
        print(f"{i}. {site.get('site_name', 'Unknown')} ({site.get('city', 'Unknown')}, {site.get('state', 'Unknown')}) - Rail: {site.get('rail_served', 'No')}")

    if len(sites) > 10:
        print(f"... and {len(sites) - 10} more sites")

    # Get company selection
    company_idx = get_company_selection(companies, "Select company for site matching")
    company = companies[company_idx]

    # Find best site matches
    site_matches = find_best_sites_for_company(company, sites, 5)

    print_header(f"Site Recommendations for {company.get('company')}")

    for i, match in enumerate(site_matches, 1):
        site = match['site']
        compatibility = match['compatibility_score']
        reasons = get_site_recommendation_explanation(company, site)

        print(f"\n{i}. {site.get('site_name')} - Compatibility: {compatibility}/100")
        print(f"   Location: {site.get('city')}, {site.get('state')}")
        print(f"   Rail Served: {site.get('rail_served')} | Transload: {site.get('transload_available')} | Port: {site.get('port_access')}")
        print(f"   Why it fits:")
        for reason in reasons:
            print(f"   • {reason}")

def handle_opportunity_brief(companies, segments, sites):
    """Generate opportunity brief for a company"""
    company_idx = get_company_selection(companies, "Select company for opportunity brief")
    company = companies[company_idx]

    segment_data = next((s for s in segments if s["segment"] == company.get("segment")), {})

    # Find best site match
    site_matches = find_best_sites_for_company(company, sites, 1)
    recommended_site = site_matches[0]['site'] if site_matches else None

    print_opportunity_brief(company, segment_data, recommended_site)

def handle_export_menu(companies, sites, segments):
    """Handle export operations"""
    while True:
        display_export_menu()
        choice = get_user_choice(1, 6)

        if choice == 1:
            top_companies = get_top_opportunities(companies, 20)
            export_to_csv(top_companies, "top_20_opportunities.csv")

        elif choice == 2:
            export_to_csv(companies, "all_companies.csv")

        elif choice == 3:
            export_opportunity_briefs(companies, segments, sites)

        elif choice == 4:
            export_company_profiles_json(companies)

        elif choice == 5:
            export_site_matching_report(companies, sites)

        elif choice == 6:
            break

def handle_map_generation(companies, sites):
    """Handle map generation operations"""
    while True:
        display_map_menu()
        choice = get_user_choice(1, 4)

        if choice == 1:
            generate_company_map(companies)

        elif choice == 2:
            generate_sites_map(sites)

        elif choice == 3:
            limit = int(input("How many top opportunities to map? (default 20): ") or "20")
            generate_top_opportunities_map(companies, limit)

        elif choice == 4:
            break

def handle_geographic_analysis(companies, rail_infrastructure):
    """Handle geographic intelligence and analysis operations"""
    while True:
        display_geographic_analysis_menu()
        choice = get_user_choice(1, 6)

        if choice == 1:
            # View geographic profiles
            print_header("Geographic Intelligence Profiles")
            company_idx = get_company_selection(companies, "Select a company")
            company = companies[company_idx]
            geo_intel = get_geographic_intelligence(company, rail_infrastructure)
            print_geographic_intelligence(geo_intel)

        elif choice == 2:
            # Analyze geographic clustering
            print_header("Geographic Clustering Analysis by State")
            clusters = analyze_geographic_clusters(companies)
            
            for state, cluster_data in sorted(clusters.items()):
                print(f"""
{state} Region:
   • Companies: {cluster_data['company_count']}
   • Cluster Centroid: ({cluster_data['centroid_lat']:.4f}, {cluster_data['centroid_lon']:.4f})
   • Average Distance Between Companies: {cluster_data['avg_distance_between_companies']} miles
   • Top Company: {cluster_data['companies'][0].get('company', 'Unknown')} (Score: {cluster_data['companies'][0].get('priority_score', 0)})""")

        elif choice == 3:
            # Generate geographic opportunity map
            print_header("Generating Geographic Opportunity Map...")
            generate_geographic_opportunity_map(companies, rail_infrastructure)

        elif choice == 4:
            # Export geographic profiles
            os.makedirs("exports", exist_ok=True)
            filename = os.path.join("exports", "geographic_profiles.csv")
            export_geographic_profiles(companies, rail_infrastructure, filename)
            print(f"Geographic profiles exported to {filename}")

        elif choice == 5:
            # View multimodal logistics analysis
            print_header("Multimodal Logistics Analysis")
            company_idx = get_company_selection(companies, "Select a company")
            company = companies[company_idx]
            logistics_profile = get_multimodal_logistics_profile(company, rail_infrastructure)
            print_multimodal_profile(logistics_profile)

        elif choice == 6:
            break

def main():
    """Main application entry point"""
    # Load all data
    segments, companies, sites, rail_infrastructure = load_data()

    print_header("OmniMapping Economic Development Platform")
    print("Rail Opportunity Analysis & Prospecting Tool")
    print(f"Loaded {len(companies)} companies across {len(set(c.get('segment') for c in companies))} segments")
    print(f"Loaded {len(sites)} industrial sites")
    print()

    print_verification_summary(companies, sites, segments)

    while True:
        display_main_menu()
        choice = get_user_choice(1, 13)

        if choice == 1:
            # Search companies
            query = get_search_term()
            results = search_companies(companies, query)
            results.sort(key=lambda x: safe_score(x.get('priority_score', 0)), reverse=True)

            if results:
                print_header(f"Search Results for '{query}' ({len(results)} found)")
                for company in results[:10]:
                    segment_data = {'segment': company.get('segment')}
                    print_company_profile(company, segment_data)
            else:
                print(f"No companies found matching '{query}'.")

        elif choice == 2:
            # Browse segments
            handle_search_menu(companies)

        elif choice == 3:
            # Filter by state
            state = get_state_filter()
            results = filter_by_state(companies, state)
            results.sort(key=lambda x: safe_score(x.get('priority_score', 0)), reverse=True)

            if results:
                print_header(f"Companies in {state} ({len(results)} found)")
                for company in results[:15]:
                    segment_data = {'segment': company.get('segment')}
                    print_company_profile(company, segment_data)
            else:
                print(f"No companies found in {state}.")

        elif choice == 4:
            # Filter by commodity
            print("Available commodities:", ", ".join(set(c.get('commodity_type', '') for c in companies if c.get('commodity_type'))))
            commodity = get_commodity_filter()
            results = filter_by_commodity(companies, commodity)
            results.sort(key=lambda x: safe_score(x.get('priority_score', 0)), reverse=True)

            if results:
                print_header(f"{commodity} Companies ({len(results)} found)")
                for company in results[:15]:
                    segment_data = {'segment': company.get('segment')}
                    print_company_profile(company, segment_data)
            else:
                print(f"No companies found in {commodity} commodity.")

        elif choice == 5:
            # Filter by minimum score
            min_score = get_min_score()
            results = filter_by_min_score(companies, min_score)
            results.sort(key=lambda x: safe_score(x.get('priority_score', 0)), reverse=True)

            if results:
                print_header(f"High-Priority Opportunities (Score ≥ {min_score}) ({len(results)} found)")
                for company in results:
                    segment_data = {'segment': company.get('segment')}
                    print_company_profile(company, segment_data)
            else:
                print(f"No companies found with score >= {min_score}.")

        elif choice == 6:
            # View top 20 opportunities
            top_companies = get_top_opportunities(companies, 20)
            print_header("Top 20 Rail Development Opportunities")

            for i, company in enumerate(top_companies, 1):
                print(f"\n{i}. ", end="")
                segment_data = {'segment': company.get('segment')}
                print_company_profile(company, segment_data)
                site_matches = find_best_sites_for_company(company, sites, 1)
                best_site = site_matches[0] if site_matches else None
                ranked_explanation = build_why_ranked_explanation(company, best_site)
                print("   WHY RANKED HERE:")
                for line in ranked_explanation[:2]:
                    print(f"      • {line}")

        elif choice == 7:
            # View company detail profile
            company_idx = get_company_selection(companies)
            company = companies[company_idx]
            segment_data = {'segment': company.get('segment')}
            print_company_profile(company, segment_data, show_details=True)

        elif choice == 8:
            # Generate opportunity brief
            handle_opportunity_brief(companies, segments, sites)

        elif choice == 9:
            # Industrial site matching
            handle_site_matching(companies, sites, segments)

        elif choice == 10:
            # Export data
            handle_export_menu(companies, sites, segments)

        elif choice == 11:
            # Generate maps
            handle_map_generation(companies, sites)

        elif choice == 12:
            # Geographic intelligence and analysis
            handle_geographic_analysis(companies, rail_infrastructure)

        elif choice == 13:
            # Exit
            print("\nThank you for using OmniMapping!")
            print("Economic development through rail opportunity analysis.")
            break

def parse_cli_args():
    parser = argparse.ArgumentParser(description="OmniMapping Economic Development Platform")
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Run non-interactive verification of data, scoring, and site matching.'
    )
    parser.add_argument(
        '--export-summary',
        action='store_true',
        help='Load data and write a compact JSON summary to exports/.'
    )
    parser.add_argument(
        '--top-companies',
        action='store_true',
        help='Load data and write ranked company opportunities as JSON to exports/.'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=20,
        help='Limit ranked company exports. Used with --top-companies.'
    )
    parser.add_argument(
        '--state',
        help='Filter ranked company exports by two-letter state. Used with --top-companies.'
    )
    parser.add_argument(
        '--segment',
        help='Filter ranked company exports by supply chain segment. Used with --top-companies.'
    )
    parser.add_argument(
        '--commodity',
        help='Filter ranked company exports by commodity type. Used with --top-companies.'
    )
    parser.add_argument(
        '--min-score',
        type=int,
        help='Filter ranked company exports by minimum priority score. Used with --top-companies.'
    )
    parser.add_argument(
        '--company-report',
        metavar='COMPANY_NAME',
        help='Load data and write a focused JSON company report to exports/.'
    )
    parser.add_argument(
        '--site-report',
        metavar='SITE_NAME',
        help='Load data and write a focused JSON site report with top company matches to exports/.'
    )
    parser.add_argument(
        '--list-companies',
        action='store_true',
        help='Print available companies as JSON for non-interactive report discovery.'
    )
    parser.add_argument(
        '--list-sites',
        action='store_true',
        help='Print available industrial sites as JSON for non-interactive report discovery.'
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_cli_args()
    if args.verify:
        sys.exit(run_verification())
    if args.export_summary:
        segments, companies, sites, rail_infrastructure = load_data()
        export_summary_json(companies, segments, sites, rail_infrastructure)
        sys.exit(0)
    if args.top_companies:
        if args.limit < 1:
            print("--limit must be at least 1")
            sys.exit(1)
        if args.min_score is not None and not 0 <= args.min_score <= 100:
            print("--min-score must be between 0 and 100")
            sys.exit(1)
        segments, companies, sites, rail_infrastructure = load_data()
        export_top_companies_json(
            companies,
            sites,
            limit=args.limit,
            state=args.state,
            segment=args.segment,
            commodity=args.commodity,
            min_score=args.min_score,
        )
        sys.exit(0)
    if args.company_report:
        segments, companies, sites, rail_infrastructure = load_data()
        try:
            export_company_report_json(args.company_report, companies, sites)
        except ValueError as exc:
            print(exc)
            sys.exit(1)
        sys.exit(0)
    if args.site_report:
        segments, companies, sites, rail_infrastructure = load_data()
        try:
            export_site_report_json(args.site_report, sites, companies)
        except ValueError as exc:
            print(exc)
            sys.exit(1)
        sys.exit(0)
    if args.list_companies:
        segments, companies, sites, rail_infrastructure = load_data()
        print_company_directory_json(companies)
        sys.exit(0)
    if args.list_sites:
        segments, companies, sites, rail_infrastructure = load_data()
        print_site_directory_json(sites)
        sys.exit(0)
    main()
