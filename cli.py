"""
OmniMapping CLI Interface
Command-line interface for the platform.
"""

from typing import Dict, List

from config import DEFAULT_TOP_LIMIT
from logger import get_logger
from modules.search import (
    filter_by_commodity, filter_by_min_score, filter_by_state, get_companies_by_segment,
    search_companies
)
from modules.export import format_company_location
from modules.ui import (
    display_export_menu, display_geographic_analysis_menu, display_main_menu,
    display_map_menu, get_company_selection,
    get_commodity_filter, get_min_score, get_search_term, get_state_filter,
    get_user_choice, print_company_profile, print_header, print_opportunity_brief
)

logger = get_logger(__name__)

def safe_score(value, default=0):
    """Convert score-like values to integers without breaking search flows."""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default

def handle_search_menu(companies: List[Dict]):
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

def handle_site_matching(companies: List[Dict], sites: List[Dict], segments: List[Dict]):
    """Handle industrial site matching operations"""
    from modules.search import find_best_sites_for_company
    from modules.ui import get_site_recommendation_explanation

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

def handle_opportunity_brief(companies: List[Dict], segments: List[Dict], sites: List[Dict]):
    """Generate opportunity brief for a company"""
    company_idx = get_company_selection(companies, "Select company for opportunity brief")
    company = companies[company_idx]

    segment_data = next((s for s in segments if s["segment"] == company.get("segment")), {})

    # Find best site match
    from modules.search import find_best_sites_for_company
    site_matches = find_best_sites_for_company(company, sites, 1)
    recommended_site = site_matches[0]['site'] if site_matches else None

    print_opportunity_brief(company, segment_data, recommended_site)

def handle_export_menu(companies: List[Dict], sites: List[Dict], segments: List[Dict]):
    """Handle export operations"""
    from modules.export import export_opportunity_briefs, export_to_csv

    while True:
        display_export_menu()
        choice = get_user_choice(1, 6)

        if choice == 1:
            from modules.search import get_top_opportunities
            top_companies = get_top_opportunities(companies, 20)
            export_to_csv(top_companies, "top_20_opportunities.csv")

        elif choice == 2:
            export_to_csv(companies, "all_companies.csv")

        elif choice == 3:
            export_opportunity_briefs(companies, segments, sites)

        elif choice == 4:
            from modules.export import export_company_profiles_json
            export_company_profiles_json(companies)

        elif choice == 5:
            from modules.export import export_site_matching_report
            export_site_matching_report(companies, sites)

        elif choice == 6:
            break

def handle_map_generation(companies: List[Dict], sites: List[Dict]):
    """Handle map generation operations"""
    from modules.geography import generate_company_map, generate_sites_map, generate_top_opportunities_map

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

def handle_geographic_analysis(companies: List[Dict], rail_infrastructure: List[Dict]):
    """Handle geographic intelligence and analysis operations"""
    from modules.geography import (
        analyze_geographic_clusters, generate_geographic_opportunity_map,
        get_multimodal_logistics_profile, print_geographic_intelligence,
        get_geographic_intelligence
    )
    from modules.export import export_geographic_profiles

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
            from config import EXPORTS_DIR
            EXPORTS_DIR.mkdir(exist_ok=True)
            filename = EXPORTS_DIR / "geographic_profiles.csv"
            export_geographic_profiles(companies, rail_infrastructure, filename)
            print(f"Geographic profiles exported to {filename}")

        elif choice == 5:
            # View multimodal logistics analysis
            print_header("Multimodal Logistics Analysis")
            company_idx = get_company_selection(companies, "Select a company")
            company = companies[company_idx]
            logistics_profile = get_multimodal_logistics_profile(company, rail_infrastructure)
            from modules.geography import print_multimodal_profile
            print_multimodal_profile(logistics_profile)

        elif choice == 6:
            break

def print_verification_summary(companies: List[Dict], sites: List[Dict], segments: List[Dict]):
    """Print a summary of verification results"""
    from modules.search import get_top_opportunities

    top_companies = get_top_opportunities(companies, 20)
    print(f"Top opportunity: {top_companies[0].get('company', 'Unknown') if top_companies else 'None'}")

def run_main_interface(segments: List[Dict], companies: List[Dict], sites: List[Dict], rail_infrastructure: List[Dict]):
    """Run the main CLI interface"""
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
            from modules.search import get_top_opportunities
            top_companies = get_top_opportunities(companies, 20)
            print_header("Top 20 Rail Development Opportunities")

            for i, company in enumerate(top_companies, 1):
                print(f"\n{i}. ", end="")
                segment_data = {'segment': company.get('segment')}
                print_company_profile(company, segment_data)
                from modules.search import find_best_sites_for_company
                site_matches = find_best_sites_for_company(company, sites, 1)
                best_site = site_matches[0] if site_matches else None
                from modules.ui import build_why_ranked_explanation
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