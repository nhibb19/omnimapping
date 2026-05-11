#!/usr/bin/env python3
"""Lightweight Flask dashboard for OmniMapping."""

import argparse
import csv
import contextlib
import io
import json
import os
import sys
from datetime import datetime

from flask import Flask, abort, redirect, render_template, request, send_file, url_for

from main import load_data
from modules.export import (
    build_company_profile_basics,
    build_company_report,
    build_site_profile,
    build_site_directory,
    build_site_report,
    export_company_report_json,
    export_site_report_json,
    export_to_csv,
    export_top_companies_json,
    filter_ranked_companies,
    find_company_for_report,
    find_site_for_report,
    format_company_location,
    format_site_location,
    safe_filename_token,
    safe_score,
)
from modules.scoring import calculate_lane_score, calculate_site_compatibility_score
from modules.search import find_best_sites_for_company, get_site_recommendation_explanation
from modules.review import (
    REVIEW_STATUS_LABELS,
    REVIEW_STATUSES,
    build_review_update,
    load_review_store,
    merge_review_records,
    merge_review_record,
    review_status_tone,
    save_review_store,
)
from modules.supply_chains import (
    build_supply_chain_catalog,
    build_supply_chain_detail,
    filter_supply_chains,
)
from modules.ui import (
    format_company_context,
    format_transload_site_angle,
    generate_recommended_next_action,
    get_priority_reasons,
    print_opportunity_brief,
)


def unique_sorted(values):
    """Return sorted, non-blank unique values for dashboard filters."""
    return sorted({str(value).strip() for value in values if str(value or '').strip()})


def parse_min_score(value):
    """Parse an optional minimum score from a dashboard query string."""
    if value is None or str(value).strip() == '':
        return None
    try:
        score = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def parse_limit(value, default=50, maximum=500):
    """Parse a positive row limit for dashboard lists and downloads."""
    try:
        limit = int(float(str(value).strip()))
    except (TypeError, ValueError):
        limit = default
    return max(1, min(maximum, limit))


def get_company_filter_args(args):
    """Collect reusable ranked-company filter arguments from a request."""
    return {
        'query': str(args.get('q', '')).strip() or None,
        'state': str(args.get('state', '')).strip() or None,
        'segment': str(args.get('segment', '')).strip() or None,
        'commodity': str(args.get('commodity', '')).strip() or None,
        'min_score': parse_min_score(args.get('min_score')),
    }


def build_filter_options(companies):
    """Build select-list values from loaded company records."""
    return {
        'states': unique_sorted(company.get('state') for company in companies),
        'segments': unique_sorted(company.get('segment') for company in companies),
        'commodities': unique_sorted(
            company.get('commodity_type') or company.get('commodity')
            for company in companies
        ),
    }


def build_site_filter_options(sites):
    """Build select-list values from loaded industrial site records."""
    return {
        'states': unique_sorted(site.get('state') for site in sites),
        'port_access': unique_sorted(site.get('port_access') for site in sites),
        'transload_available': unique_sorted(site.get('transload_available') for site in sites),
        'source_confidences': unique_sorted(site.get('source_confidence') for site in sites),
        'review_statuses': [
            {'value': status, 'label': REVIEW_STATUS_LABELS[status]}
            for status in REVIEW_STATUSES
        ],
    }


def get_site_filter_args(args):
    """Collect reusable industrial-site filter arguments from a request."""
    return {
        'query': str(args.get('q', '')).strip(),
        'state': str(args.get('state', '')).strip().upper(),
        'port_access': str(args.get('port_access', '')).strip(),
        'transload_available': str(args.get('transload_available', '')).strip(),
        'source_confidence': str(args.get('source_confidence', '')).strip(),
        'needs_confirmation': str(args.get('needs_confirmation', '')).strip(),
        'review_status': str(args.get('review_status', '')).strip(),
    }


def filter_site_directory(site_rows, filters):
    """Filter site directory rows without changing scoring or matching behavior."""
    filtered = list(site_rows)
    if filters.get('query'):
        query = filters['query'].lower()
        searchable_fields = ['site_name', 'location', 'target_industries', 'data_gap_notes']
        filtered = [
            site for site in filtered
            if any(query in str(site.get(field, '')).lower() for field in searchable_fields)
        ]
    if filters.get('state'):
        filtered = [site for site in filtered if site.get('state', '').upper() == filters['state']]
    if filters.get('port_access'):
        filtered = [site for site in filtered if site.get('port_access', '') == filters['port_access']]
    if filters.get('transload_available'):
        filtered = [site for site in filtered if site.get('transload_available', '') == filters['transload_available']]
    if filters.get('source_confidence'):
        filtered = [site for site in filtered if site.get('source_confidence', '') == filters['source_confidence']]
    if filters.get('needs_confirmation'):
        wants_confirmation = filters['needs_confirmation'] == 'yes'
        filtered = [site for site in filtered if bool(site.get('needs_confirmation')) == wants_confirmation]
    if filters.get('review_status'):
        filtered = [site for site in filtered if site.get('review_status') == filters['review_status']]
    return filtered


def company_matches_query(company, query):
    """Return whether a company matches dashboard quick-search text."""
    if not query:
        return True
    query_lower = str(query).strip().lower()
    searchable_fields = [
        'company',
        'city',
        'state',
        'segment',
        'commodity_type',
        'commodity',
        'inbound_materials',
        'outbound_products',
        'why_target',
        'omnitrax_outreach_angle',
        'best_site_name',
        'best_recommended_site',
    ]
    return any(query_lower in str(company.get(field, '')).lower() for field in searchable_fields)


def filter_companies_for_dashboard(companies, filters):
    """Apply dashboard-only search, then reuse ranked-company filters."""
    query = filters.get('query')
    filtered = [company for company in companies if company_matches_query(company, query)]
    return filter_ranked_companies(
        filtered,
        state=filters.get('state'),
        segment=filters.get('segment'),
        commodity=filters.get('commodity'),
        min_score=filters.get('min_score'),
    )


def build_company_scan_summary(companies):
    """Build compact counts that help economic developers scan the company list."""
    ready_for_outreach = [
        company for company in companies
        if safe_score(company.get('priority_score', 0)) >= 70
        and safe_score(company.get('best_site_match_score', 0)) >= 60
    ]
    missing_best_site = [
        company for company in companies
        if not (company.get('best_site_name') or company.get('best_recommended_site'))
    ]
    return {
        'ready_for_outreach': len(ready_for_outreach),
        'needs_site_review': len(missing_best_site),
        'average_priority': round(
            sum(safe_score(company.get('priority_score', 0)) for company in companies) / len(companies),
            1,
        ) if companies else 0,
    }


def build_site_scan_summary(sites):
    """Build compact counts that help economic developers scan the site list."""
    confirmation_sites = [site for site in sites if site.get('needs_confirmation')]
    confirmed_sites = [site for site in sites if site.get('review_status') == 'confirmed']
    review_queue_sites = [
        site for site in sites
        if site.get('review_status') in {'needs_review', 'in_review'}
    ]
    blocked_sites = [site for site in sites if site.get('review_status') == 'blocked']
    rail_transload_sites = [
        site for site in sites
        if str(site.get('rail_served', '')).lower() == 'yes'
        and str(site.get('transload_available', '')).lower() == 'yes'
    ]
    high_confidence_sites = [
        site for site in sites
        if str(site.get('source_confidence', '')).lower() == 'high'
    ]
    return {
        'ready_sites': len(confirmed_sites) if any('review_status' in site for site in sites) else max(0, len(sites) - len(confirmation_sites)),
        'needs_confirmation': len(confirmation_sites),
        'review_queue': len(review_queue_sites),
        'blocked': len(blocked_sites),
        'rail_transload': len(rail_transload_sites),
        'high_confidence': len(high_confidence_sites),
    }


def build_supply_chain_scan_summary(chains):
    """Build overview counts for the supply-chain dashboard."""
    return {
        'chain_count': len(chains),
        'company_matches': sum(chain.get('count', 0) for chain in chains),
        'strong_prospects': sum(chain.get('strong_count', 0) for chain in chains),
        'rail_possible': sum(chain.get('possible_count', 0) for chain in chains),
        'ready_for_outreach': sum(chain.get('ready_count', 0) for chain in chains),
        'needs_site_review': sum(chain.get('site_review_count', 0) for chain in chains),
    }


def build_supply_chain_filter_options(chains):
    """Build select-list values from configured supply-chain groups."""
    return {
        'groups': unique_sorted(chain.get('group') for chain in chains),
        'opportunities': ['Strong rail prospect', 'Rail-service possible', 'Monitor'],
        'readinesses': ['Ready for outreach', 'Qualify fit', 'Needs site review', 'Monitor'],
        'sorts': [
            {'value': 'strong', 'label': 'Strong rail prospects'},
            {'value': 'ready', 'label': 'Ready for outreach'},
            {'value': 'priority', 'label': 'Average priority'},
            {'value': 'site_fit', 'label': 'Average site fit'},
            {'value': 'matches', 'label': 'Company matches'},
        ],
    }


def score_tone(score):
    """Return a visual status tone for a 0-100 score."""
    score = safe_score(score)
    if score >= 80:
        return 'positive'
    if score >= 60:
        return 'review'
    return 'warning'


def priority_label(score):
    """Return a short working label for a company priority score."""
    score = safe_score(score)
    if score >= 80:
        return 'High priority'
    if score >= 70:
        return 'Qualified'
    if score >= 50:
        return 'Review fit'
    return 'Low priority'


def match_label(score):
    """Return a short working label for a site-match score."""
    score = safe_score(score)
    if score >= 80:
        return 'Strong match'
    if score >= 60:
        return 'Workable match'
    if score > 0:
        return 'Needs review'
    return 'Unmatched'


def yes_no_tone(value):
    """Return a visual tone for yes/no capability fields."""
    normalized = str(value or '').strip().lower()
    if normalized == 'yes':
        return 'positive'
    if normalized == 'no':
        return 'neutral'
    return 'review'


def confidence_tone(value):
    """Return a visual tone for source-confidence labels."""
    normalized = str(value or '').strip().lower()
    if normalized == 'high':
        return 'positive'
    if normalized in {'medium', 'unspecified', ''}:
        return 'review'
    return 'neutral'


def status_label(status):
    """Return display text for a local site review status."""
    return REVIEW_STATUS_LABELS.get(status, REVIEW_STATUS_LABELS['needs_review'])


def find_segment_for_company(segments, company):
    """Find the segment row that belongs to a company."""
    return next((segment for segment in segments if segment.get('segment') == company.get('segment')), {})


def build_workspace_data_gaps(company, site, compatibility_score=None):
    """Call out practical confirmation items for a company-site opportunity."""
    gaps = []
    required_company_fields = [
        ('inbound_materials', 'Confirm inbound material volumes and routing.'),
        ('outbound_products', 'Confirm outbound product flows and customer lanes.'),
        ('industrial_real_estate_score', 'Confirm active real estate or expansion timing.'),
    ]
    for field, message in required_company_fields:
        if not str(company.get(field, '')).strip():
            gaps.append(message)

    required_site_fields = [
        ('acres', 'Confirm available acreage and parcel control.'),
        ('rail_served', 'Confirm rail service status and serving railroad.'),
        ('transload_available', 'Confirm transload capacity and operating model.'),
        ('interstate_access', 'Confirm highway access and truck route constraints.'),
    ]
    for field, message in required_site_fields:
        if not str(site.get(field, '')).strip():
            gaps.append(message)

    pair_score = compatibility_score if compatibility_score is not None else safe_score(company.get('best_site_match_score', 0))
    if pair_score < 60:
        gaps.append('Validate whether the company needs a different site type before outreach.')

    lane = calculate_lane_score(company, site)
    if lane['lane_score'] < 55:
        gaps.append('Validate inbound and outbound lane assumptions against site rail, transload, highway, and port access.')

    if not gaps:
        gaps.append('Confirm acreage, rail service details, utility readiness, and company timing before outreach.')

    return gaps


def build_workspace_talking_points(company, site, segment_data):
    """Build concise outreach talking points from existing company/site context."""
    talking_points = []
    talking_points.extend(format_transload_site_angle(company, site)[:2])

    if company.get('omnitrax_outreach_angle'):
        talking_points.append(company.get('omnitrax_outreach_angle'))
    if segment_data.get('reason'):
        talking_points.append(segment_data.get('reason'))
    if site.get('target_industries'):
        talking_points.append(f"Position {site.get('site_name')} around target industries: {site.get('target_industries')}.")

    seen = set()
    unique_points = []
    for point in talking_points:
        if point and point not in seen:
            unique_points.append(point)
            seen.add(point)

    return unique_points or ['Lead with rail-served site fit, logistics efficiency, and speed to evaluate development readiness.']


def build_company_site_comparison(company, sites, segments, limit=5):
    """Build a decision-ready comparison of top compatible sites for one company."""
    site_matches = find_best_sites_for_company(company, sites, limit)
    compared_sites = []

    for index, match in enumerate(site_matches, start=1):
        site = match.get('site', {})
        compatibility_score = safe_score(match.get('compatibility_score', 0))
        compared_sites.append({
            'rank': index,
            'site': build_site_profile(site),
            'compatibility_score': compatibility_score,
            'pair_score': safe_score(match.get('pair_score', 0)),
            'lane_score': safe_score(match.get('lane_score', 0)),
            'lane_readiness_label': match.get('lane_readiness_label', ''),
            'lane_reasons': match.get('lane_reasons', []),
            'matching_reasons': get_site_recommendation_explanation(company, site),
            'risks_or_confirmation_items': build_workspace_data_gaps(
                company,
                site,
                compatibility_score=compatibility_score,
            ),
        })

    first_choice = compared_sites[0] if compared_sites else None
    first_choice_summary = None
    if first_choice:
        first_choice_summary = {
            'site_name': first_choice['site'].get('site_name', ''),
            'compatibility_score': first_choice['compatibility_score'],
            'lane_score': first_choice['lane_score'],
            'lane_readiness_label': first_choice['lane_readiness_label'],
            'why': first_choice['matching_reasons'][:3],
        }

    return {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'description': 'OmniMapping company site comparison',
            'company': company.get('company', ''),
            'site_count': len(compared_sites),
            'limit': limit,
        },
        'company': build_company_profile_basics(company),
        'priority': {
            'score': safe_score(company.get('priority_score', 0)),
            'breakdown': {
                key: safe_score(value)
                for key, value in company.get('score_breakdown', {}).items()
            },
            'reasons': get_priority_reasons(company),
            'risk': company.get('opportunity_risk', ''),
        },
        'recommended_first_choice': first_choice_summary,
        'compared_sites': compared_sites,
    }


def build_opportunity_workspace(company, site, segments):
    """Build a JSON-ready selected company-site workspace payload."""
    segment_data = find_segment_for_company(segments, company)
    compatibility_score = safe_score(calculate_site_compatibility_score(company, site))
    lane = calculate_lane_score(company, site)
    company_copy = company.copy()
    company_copy['best_recommended_site'] = site.get('site_name', '')
    company_copy['best_site_name'] = site.get('site_name', '')
    company_copy['best_recommended_site_location'] = format_site_location(site)
    company_copy['best_site_match_score'] = compatibility_score

    return {
        'export_info': {
            'timestamp': datetime.now().isoformat(),
            'description': 'OmniMapping opportunity workspace for one company-site pair',
            'company': company.get('company', ''),
            'site': site.get('site_name', ''),
        },
        'company': build_company_profile_basics(company),
        'site': build_site_profile(site),
        'priority': {
            'score': safe_score(company.get('priority_score', 0)),
            'breakdown': {
                key: safe_score(value)
                for key, value in company.get('score_breakdown', {}).items()
            },
            'reasons': get_priority_reasons(company),
            'risk': company.get('opportunity_risk', ''),
            'next_action': generate_recommended_next_action(company, site.get('site_name')),
        },
        'site_match': {
            'compatibility_score': compatibility_score,
            'matching_reasons': get_site_recommendation_explanation(company, site),
        },
        'lane': lane,
        'company_context': format_company_context(company, segment_data),
        'risks_or_data_gaps': build_workspace_data_gaps(company, site, compatibility_score=compatibility_score),
        'talking_points': build_workspace_talking_points(company, site, segment_data),
    }


def write_company_site_comparison_json(comparison, output_dir="exports"):
    """Write a company site comparison JSON export."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    company_token = safe_filename_token(comparison['company'].get('company'), default='company')
    filename = f"site_comparison_{company_token}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w') as export_file:
        json.dump(comparison, export_file, indent=2, default=str)
    return filepath


def write_company_site_comparison_csv(comparison, output_dir="exports"):
    """Write a company site comparison table CSV export."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    company_token = safe_filename_token(comparison['company'].get('company'), default='company')
    filename = f"site_comparison_{company_token}_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)
    fieldnames = [
        'rank',
        'site_name',
        'compatibility_score',
        'location',
        'acres',
        'rail_served',
        'nearby_class1',
        'transload_available',
        'interstate_access',
        'port_access',
        'target_industries',
        'lane_score',
        'lane_readiness_label',
        'lane_reasons',
        'matching_reasons',
        'risks_or_confirmation_items',
    ]
    with open(filepath, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for compared_site in comparison.get('compared_sites', []):
            site = compared_site.get('site', {})
            writer.writerow({
                'rank': compared_site.get('rank', ''),
                'site_name': site.get('site_name', ''),
                'compatibility_score': compared_site.get('compatibility_score', ''),
                'location': site.get('location', ''),
                'acres': site.get('acres', ''),
                'rail_served': site.get('rail_served', ''),
                'nearby_class1': site.get('nearby_class1', ''),
                'transload_available': site.get('transload_available', ''),
                'interstate_access': site.get('interstate_access', ''),
                'port_access': site.get('port_access', ''),
                'target_industries': site.get('target_industries', ''),
                'lane_score': compared_site.get('lane_score', ''),
                'lane_readiness_label': compared_site.get('lane_readiness_label', ''),
                'lane_reasons': '; '.join(compared_site.get('lane_reasons', [])),
                'matching_reasons': '; '.join(compared_site.get('matching_reasons', [])),
                'risks_or_confirmation_items': '; '.join(compared_site.get('risks_or_confirmation_items', [])),
            })
    return filepath


def write_workspace_json(workspace, output_dir="exports"):
    """Write a selected opportunity workspace JSON export."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    company_token = safe_filename_token(workspace['company'].get('company'), default='company')
    site_token = safe_filename_token(workspace['site'].get('site_name'), default='site')
    filename = f"opportunity_workspace_{company_token}_{site_token}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w') as export_file:
        json.dump(workspace, export_file, indent=2, default=str)
    return filepath


def write_workspace_brief_txt(company, site, segments, output_dir="exports"):
    """Write a selected opportunity brief TXT export using the existing brief printer."""
    os.makedirs(output_dir, exist_ok=True)
    segment_data = find_segment_for_company(segments, company)
    compatibility_score = safe_score(calculate_site_compatibility_score(company, site))
    company_copy = company.copy()
    company_copy['best_recommended_site'] = site.get('site_name', '')
    company_copy['best_site_name'] = site.get('site_name', '')
    company_copy['best_recommended_site_location'] = format_site_location(site)
    company_copy['best_site_match_score'] = compatibility_score
    company_copy['recommended_next_action'] = generate_recommended_next_action(company, site.get('site_name'))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    company_token = safe_filename_token(company.get('company'), default='company')
    site_token = safe_filename_token(site.get('site_name'), default='site')
    filename = f"opportunity_brief_{company_token}_{site_token}_{timestamp}.txt"
    filepath = os.path.join(output_dir, filename)

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        print_opportunity_brief(company_copy, segment_data, recommended_site=site)

    with open(filepath, 'w') as brief_file:
        brief_file.write(buffer.getvalue())
    return filepath


def create_app(data_loader=load_data, export_dir="exports", review_store_path=None):
    """Create the dashboard app with injectable data loading for tests."""
    app = Flask(__name__)
    app.config['OMNIMAPPING_DATA_LOADER'] = data_loader
    app.config['OMNIMAPPING_EXPORT_DIR'] = export_dir
    app.config['OMNIMAPPING_REVIEW_STORE'] = review_store_path or os.path.join('data', 'review_status.json')

    def get_data():
        if 'OMNIMAPPING_DATA' not in app.config:
            app.config['OMNIMAPPING_DATA'] = app.config['OMNIMAPPING_DATA_LOADER']()
        segments, companies, sites, rail_infrastructure = app.config['OMNIMAPPING_DATA']
        return segments, companies, sites, rail_infrastructure

    @app.context_processor
    def inject_helpers():
        return {
            'format_company_location': format_company_location,
            'format_site_location': format_site_location,
            'safe_score': safe_score,
            'score_tone': score_tone,
            'priority_label': priority_label,
            'match_label': match_label,
            'yes_no_tone': yes_no_tone,
            'confidence_tone': confidence_tone,
            'review_status_tone': review_status_tone,
            'status_label': status_label,
            'review_status_options': [
                {'value': status, 'label': REVIEW_STATUS_LABELS[status]}
                for status in REVIEW_STATUSES
            ],
        }

    @app.route('/')
    def index():
        return redirect(url_for('companies'))

    @app.route('/companies')
    def companies():
        _, all_companies, sites, _ = get_data()
        filters = get_company_filter_args(request.args)
        limit = parse_limit(request.args.get('limit'), default=50)
        ranked_companies = filter_companies_for_dashboard(all_companies, filters)
        visible_companies = ranked_companies[:limit]

        return render_template(
            'companies.html',
            companies=visible_companies,
            total_count=len(all_companies),
            filtered_count=len(ranked_companies),
            filters=filters,
            filter_options=build_filter_options(all_companies),
            limit=limit,
            sites=sites,
            scan_summary=build_company_scan_summary(ranked_companies),
        )

    @app.route('/companies/<path:company_name>')
    def company_detail(company_name):
        _, all_companies, sites, _ = get_data()
        company, matches = find_company_for_report(all_companies, company_name)
        if not company:
            abort(404)

        report = build_company_report(company, sites, company_name, all_matches=matches)
        return render_template('company_detail.html', report=report)

    @app.route('/companies/<path:company_name>/site-comparison')
    def company_site_comparison(company_name):
        segments, all_companies, sites, _ = get_data()
        company, _ = find_company_for_report(all_companies, company_name)
        if not company:
            abort(404)

        limit = parse_limit(request.args.get('limit'), default=5, maximum=10)
        comparison = build_company_site_comparison(company, sites, segments, limit=limit)
        return render_template('company_site_comparison.html', comparison=comparison, limit=limit)

    @app.route('/sites')
    def sites():
        _, companies, all_sites, _ = get_data()
        filters = get_site_filter_args(request.args)
        site_rows = build_site_directory(all_sites)
        site_rows = merge_review_records(site_rows, load_review_store(app.config['OMNIMAPPING_REVIEW_STORE']))
        site_rows = filter_site_directory(site_rows, filters)

        return render_template(
            'sites.html',
            sites=site_rows,
            total_count=len(all_sites),
            filtered_count=len(site_rows),
            filter_options=build_site_filter_options(all_sites),
            filters=filters,
            company_count=len(companies),
            scan_summary=build_site_scan_summary(site_rows),
        )

    @app.route('/sites/<path:site_name>')
    def site_detail(site_name):
        _, companies, all_sites, _ = get_data()
        site, matches = find_site_for_report(all_sites, site_name)
        if not site:
            abort(404)

        report = build_site_report(site, companies, site_name, all_matches=matches, top_limit=15)
        report['site_profile'] = merge_review_record(
            report['site_profile'],
            load_review_store(app.config['OMNIMAPPING_REVIEW_STORE']),
        )
        return render_template('site_detail.html', report=report)

    @app.route('/supply-chains')
    def supply_chains():
        _, companies, _, _ = get_data()
        all_chains = build_supply_chain_catalog(companies)
        filters = {
            'group': str(request.args.get('group', '')).strip(),
            'query': str(request.args.get('q', '')).strip(),
            'min_priority': parse_min_score(request.args.get('min_priority')),
            'opportunity': str(request.args.get('opportunity', '')).strip(),
            'readiness': str(request.args.get('readiness', '')).strip(),
            'sort': str(request.args.get('sort', 'strong')).strip() or 'strong',
        }
        visible_chains = filter_supply_chains(
            all_chains,
            group=filters['group'] or None,
            query=filters['query'] or None,
            min_priority=filters['min_priority'],
            opportunity=filters['opportunity'] or None,
            readiness=filters['readiness'] or None,
            sort=filters['sort'],
        )

        return render_template(
            'supply_chains.html',
            chains=visible_chains,
            total_count=len(all_chains),
            filtered_count=len(visible_chains),
            filters=filters,
            filter_options=build_supply_chain_filter_options(all_chains),
            scan_summary=build_supply_chain_scan_summary(visible_chains),
        )

    @app.route('/supply-chains/<slug>')
    def supply_chain_detail(slug):
        _, companies, _, _ = get_data()
        chain = build_supply_chain_detail(slug, companies)
        if not chain:
            abort(404)

        return render_template('supply_chain_detail.html', chain=chain)

    @app.route('/sites/<path:site_name>/review', methods=['POST'])
    def update_site_review(site_name):
        _, _, all_sites, _ = get_data()
        site, _ = find_site_for_report(all_sites, site_name)
        if not site:
            abort(404)

        status = request.form.get('review_status', '')
        try:
            review_store = load_review_store(app.config['OMNIMAPPING_REVIEW_STORE'])
            review_store[site.get('site_name', '')] = build_review_update(
                review_store.get(site.get('site_name', ''), {}),
                status,
                notes=request.form.get('review_notes', ''),
                reviewed_by=request.form.get('reviewed_by', ''),
                source_update_url=request.form.get('source_update_url', ''),
            )
            save_review_store(app.config['OMNIMAPPING_REVIEW_STORE'], review_store)
        except ValueError:
            abort(400)

        return redirect(url_for('site_detail', site_name=site.get('site_name', '')))

    @app.route('/workspace')
    def opportunity_workspace():
        segments, companies, sites, _ = get_data()
        company_name = request.args.get('company', '')
        site_name = request.args.get('site', '')
        company, _ = find_company_for_report(companies, company_name)
        site, _ = find_site_for_report(sites, site_name)
        if not company or not site:
            abort(404)

        workspace = build_opportunity_workspace(company, site, segments)
        return render_template('opportunity_workspace.html', workspace=workspace)

    @app.route('/downloads/top-companies.csv')
    def download_top_companies_csv():
        _, all_companies, _, _ = get_data()
        filters = get_company_filter_args(request.args)
        limit = parse_limit(request.args.get('limit'), default=50)
        ranked_companies = filter_companies_for_dashboard(all_companies, filters)[:limit]
        filename = "dashboard_top_companies.csv"
        filepath = export_to_csv(ranked_companies, filename=filename, output_dir=app.config['OMNIMAPPING_EXPORT_DIR'])
        if not filepath:
            abort(404)
        return send_file(os.path.abspath(filepath), as_attachment=True, download_name=filename)

    @app.route('/downloads/top-companies.json')
    def download_top_companies_json():
        _, all_companies, sites, _ = get_data()
        filters = get_company_filter_args(request.args)
        limit = parse_limit(request.args.get('limit'), default=50)
        ranked_companies = filter_companies_for_dashboard(all_companies, filters)
        export_filters = {key: value for key, value in filters.items() if key != 'query'}
        filepath = export_top_companies_json(
            ranked_companies,
            sites,
            output_dir=app.config['OMNIMAPPING_EXPORT_DIR'],
            limit=limit,
            **export_filters,
        )
        return send_file(os.path.abspath(filepath), as_attachment=True, download_name=os.path.basename(filepath))

    @app.route('/downloads/company/<path:company_name>.json')
    def download_company_report(company_name):
        _, all_companies, sites, _ = get_data()
        try:
            filepath = export_company_report_json(
                company_name,
                all_companies,
                sites,
                output_dir=app.config['OMNIMAPPING_EXPORT_DIR'],
            )
        except ValueError:
            abort(404)
        return send_file(os.path.abspath(filepath), as_attachment=True, download_name=os.path.basename(filepath))

    @app.route('/downloads/site/<path:site_name>.json')
    def download_site_report(site_name):
        _, companies, all_sites, _ = get_data()
        try:
            filepath = export_site_report_json(
                site_name,
                all_sites,
                companies,
                output_dir=app.config['OMNIMAPPING_EXPORT_DIR'],
            )
        except ValueError:
            abort(404)
        return send_file(os.path.abspath(filepath), as_attachment=True, download_name=os.path.basename(filepath))

    @app.route('/downloads/workspace.json')
    def download_workspace_json():
        segments, companies, sites, _ = get_data()
        company, _ = find_company_for_report(companies, request.args.get('company', ''))
        site, _ = find_site_for_report(sites, request.args.get('site', ''))
        if not company or not site:
            abort(404)

        workspace = build_opportunity_workspace(company, site, segments)
        filepath = write_workspace_json(workspace, output_dir=app.config['OMNIMAPPING_EXPORT_DIR'])
        return send_file(os.path.abspath(filepath), as_attachment=True, download_name=os.path.basename(filepath))

    @app.route('/downloads/company-site-comparison/<path:company_name>.json')
    def download_company_site_comparison_json(company_name):
        segments, companies, sites, _ = get_data()
        company, _ = find_company_for_report(companies, company_name)
        if not company:
            abort(404)

        limit = parse_limit(request.args.get('limit'), default=5, maximum=10)
        comparison = build_company_site_comparison(company, sites, segments, limit=limit)
        filepath = write_company_site_comparison_json(
            comparison,
            output_dir=app.config['OMNIMAPPING_EXPORT_DIR'],
        )
        return send_file(os.path.abspath(filepath), as_attachment=True, download_name=os.path.basename(filepath))

    @app.route('/downloads/company-site-comparison/<path:company_name>.csv')
    def download_company_site_comparison_csv(company_name):
        segments, companies, sites, _ = get_data()
        company, _ = find_company_for_report(companies, company_name)
        if not company:
            abort(404)

        limit = parse_limit(request.args.get('limit'), default=5, maximum=10)
        comparison = build_company_site_comparison(company, sites, segments, limit=limit)
        filepath = write_company_site_comparison_csv(
            comparison,
            output_dir=app.config['OMNIMAPPING_EXPORT_DIR'],
        )
        return send_file(os.path.abspath(filepath), as_attachment=True, download_name=os.path.basename(filepath))

    @app.route('/downloads/workspace.txt')
    def download_workspace_txt():
        segments, companies, sites, _ = get_data()
        company, _ = find_company_for_report(companies, request.args.get('company', ''))
        site, _ = find_site_for_report(sites, request.args.get('site', ''))
        if not company or not site:
            abort(404)

        filepath = write_workspace_brief_txt(
            company,
            site,
            segments,
            output_dir=app.config['OMNIMAPPING_EXPORT_DIR'],
        )
        return send_file(os.path.abspath(filepath), as_attachment=True, download_name=os.path.basename(filepath))

    @app.route('/health')
    def health():
        segments, companies, sites, rail_infrastructure = get_data()
        return {
            'status': 'ok',
            'segments': len(segments),
            'companies': len(companies),
            'sites': len(sites),
            'rail_infrastructure': len(rail_infrastructure),
        }

    return app


def run_smoke_test():
    """Exercise the dashboard routes without starting a server."""
    app = create_app()
    app.config['TESTING'] = True
    client = app.test_client()

    checks = [
        ('/health', 200),
        ('/companies', 200),
        ('/companies?state=TX&min_score=1', 200),
        ('/sites', 200),
        ('/supply-chains', 200),
        ('/supply-chains/steel', 200),
        ('/workspace?company=Nucor&site=Savannah%20Gateway%20Industrial%20Hub', 200),
        ('/companies/Nucor/site-comparison', 200),
    ]
    for path, expected_status in checks:
        response = client.get(path)
        try:
            if response.status_code != expected_status:
                print(f"[FAIL] {path}: expected {expected_status}, got {response.status_code}")
                return 1
            print(f"[PASS] {path}: {response.status_code}")
        finally:
            response.close()

    print("PASS dashboard smoke test completed successfully.")
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="OmniMapping local web dashboard")
    parser.add_argument('--host', default='127.0.0.1', help='Dashboard host address.')
    parser.add_argument('--port', type=int, default=5000, help='Dashboard port.')
    parser.add_argument('--debug', action='store_true', help='Run Flask in debug mode.')
    parser.add_argument('--smoke-test', action='store_true', help='Run a local dashboard route smoke test.')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    if args.smoke_test:
        sys.exit(run_smoke_test())

    dashboard_app = create_app()
    dashboard_app.run(host=args.host, port=args.port, debug=args.debug)
