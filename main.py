#!/usr/bin/env python3
"""
OmniMapping Economic Development Platform
A comprehensive rail opportunity analysis and prospecting tool.
"""

import argparse
import os
import sys

from cli import run_main_interface
from data_loader import (
    enhance_company_geography,
    load_csv,
    load_data as load_raw_data,
    validate_csv_file,
    validate_data_files,
)
from logger import get_logger
from modules.export import (
    export_company_report_json,
    export_site_report_json,
    export_summary_json,
    export_top_companies_json,
    print_company_directory_json,
    print_site_directory_json,
)
from workflows import process_companies_with_scoring, run_verification as workflow_run_verification
from modules.search import find_best_sites_for_company, get_top_opportunities

logger = get_logger(__name__)

def load_data(data_dir=None):
    """Load active project data and apply the refactored scoring workflow."""
    import data_loader as data_loader_module

    original_validate = data_loader_module.validate_data_files
    original_load_csv = data_loader_module.load_csv
    original_enhance = data_loader_module.enhance_company_geography
    data_loader_module.validate_data_files = validate_data_files
    data_loader_module.load_csv = load_csv
    data_loader_module.enhance_company_geography = enhance_company_geography
    try:
        segments, companies, sites, rail_infrastructure = load_raw_data(data_dir=data_dir)
    finally:
        data_loader_module.validate_data_files = original_validate
        data_loader_module.load_csv = original_load_csv
        data_loader_module.enhance_company_geography = original_enhance
    companies = process_companies_with_scoring(segments, companies, sites)
    return segments, companies, sites, rail_infrastructure

def run_loaded_verification(segments=None, companies=None, sites=None, rail_infrastructure=None):
    """Compatibility wrapper for verification callers before the module split."""
    if segments is None or companies is None or sites is None or rail_infrastructure is None:
        csv_issues = validate_data_files()
        if csv_issues:
            print("[FAIL] CSV validation")
            for issue in csv_issues:
                print(f"- {issue}")
            return 1

        print("[PASS] CSV validation")
        segments, companies, sites, rail_infrastructure = load_data()
    else:
        print("[PASS] CSV validation")

    print(f"[PASS] Data load: Loaded {len(companies)} companies, {len(sites)} sites, {len(rail_infrastructure)} rail records")
    result = workflow_run_verification(segments, companies, sites, rail_infrastructure)
    if result == 0:
        print("[PASS] Top opportunities sort")
        print("[PASS] Site matching")
        from modules.data_quality import build_data_quality_report
        quality = build_data_quality_report(sites, rail_infrastructure)
        print("Data Quality Summary")
        print(f"Source confidence: {quality['source_confidence_counts']}")
        print(f"Blank acreage sites: {quality['blank_acreage_sites']}")
        print(f"Needs confirmation: {quality['sites_needing_confirmation'] + quality['rail_records_needing_confirmation']}")
        print("PASS OmniMapping verification completed successfully.")
    return result

def main():
    """Main application entry point"""
    # Load all data
    segments, companies, sites, rail_infrastructure = load_data()

    # Run the main CLI interface
    run_main_interface(segments, companies, sites, rail_infrastructure)

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
        sys.exit(run_loaded_verification())
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

# Preserve the pre-refactor public API while keeping workflow logic in workflows.py.
run_verification = run_loaded_verification
