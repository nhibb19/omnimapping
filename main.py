#!/usr/bin/env python3
"""
OmniMapping Economic Development Platform
A comprehensive rail opportunity analysis and prospecting tool.
"""

import argparse
import os
import sys

from cli import run_main_interface
from data_loader import load_data
from logger import get_logger
from modules.export import (
    export_company_report_json,
    export_site_report_json,
    export_summary_json,
    export_top_companies_json,
    print_company_directory_json,
    print_site_directory_json,
)
from workflows import process_companies_with_scoring, run_verification

logger = get_logger(__name__)

def main():
    """Main application entry point"""
    # Load all data
    segments, companies, sites, rail_infrastructure = load_data()

    # Process companies with scoring and site matching
    companies = process_companies_with_scoring(segments, companies, sites)

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
        segments, companies, sites, rail_infrastructure = load_data()
        companies = process_companies_with_scoring(segments, companies, sites)
        sys.exit(run_verification(segments, companies, sites, rail_infrastructure))
    if args.export_summary:
        segments, companies, sites, rail_infrastructure = load_data()
        companies = process_companies_with_scoring(segments, companies, sites)
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
        companies = process_companies_with_scoring(segments, companies, sites)
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
        companies = process_companies_with_scoring(segments, companies, sites)
        try:
            export_company_report_json(args.company_report, companies, sites)
        except ValueError as exc:
            print(exc)
            sys.exit(1)
        sys.exit(0)
    if args.site_report:
        segments, companies, sites, rail_infrastructure = load_data()
        companies = process_companies_with_scoring(segments, companies, sites)
        try:
            export_site_report_json(args.site_report, sites, companies)
        except ValueError as exc:
            print(exc)
            sys.exit(1)
        sys.exit(0)
    if args.list_companies:
        segments, companies, sites, rail_infrastructure = load_data()
        companies = process_companies_with_scoring(segments, companies, sites)
        print_company_directory_json(companies)
        sys.exit(0)
    if args.list_sites:
        segments, companies, sites, rail_infrastructure = load_data()
        print_site_directory_json(sites)
        sys.exit(0)
    main()
