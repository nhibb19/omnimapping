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

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for

from config import CITY_COORDINATES
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
from modules.data_quality import build_research_readiness, confidence_label
from modules.supply_chains import (
    SUPPLY_CHAIN_DEFINITIONS,
    build_supply_chain_catalog,
    build_supply_chain_detail,
    filter_supply_chains,
    match_companies_for_definition,
)
from modules.opportunity_readiness import (
    COMPARE_SITES_LABEL,
    QUALIFY_FIT_LABEL,
    READY_LABEL,
    VERIFY_SITE_LABEL,
    annotate_company_opportunity_readiness,
    best_site_name as opportunity_best_site_name,
    build_opportunity_readiness,
    readiness_next_action,
)
from modules.ui import (
    format_company_context,
    format_transload_site_angle,
    generate_recommended_next_action,
    get_priority_reasons,
    print_opportunity_brief,
)
from modules.geographic_scoring import MAJOR_PORTS, calculate_distance, find_nearest_port

STATE_NAMES = {
    'AL': 'Alabama',
    'AK': 'Alaska',
    'AZ': 'Arizona',
    'AR': 'Arkansas',
    'CA': 'California',
    'CO': 'Colorado',
    'CT': 'Connecticut',
    'DE': 'Delaware',
    'FL': 'Florida',
    'GA': 'Georgia',
    'HI': 'Hawaii',
    'ID': 'Idaho',
    'IL': 'Illinois',
    'IN': 'Indiana',
    'IA': 'Iowa',
    'KS': 'Kansas',
    'KY': 'Kentucky',
    'LA': 'Louisiana',
    'ME': 'Maine',
    'MD': 'Maryland',
    'MA': 'Massachusetts',
    'MI': 'Michigan',
    'MN': 'Minnesota',
    'MS': 'Mississippi',
    'MO': 'Missouri',
    'MT': 'Montana',
    'NE': 'Nebraska',
    'NV': 'Nevada',
    'NH': 'New Hampshire',
    'NJ': 'New Jersey',
    'NM': 'New Mexico',
    'NY': 'New York',
    'NC': 'North Carolina',
    'ND': 'North Dakota',
    'OH': 'Ohio',
    'OK': 'Oklahoma',
    'OR': 'Oregon',
    'PA': 'Pennsylvania',
    'RI': 'Rhode Island',
    'SC': 'South Carolina',
    'SD': 'South Dakota',
    'TN': 'Tennessee',
    'TX': 'Texas',
    'UT': 'Utah',
    'VT': 'Vermont',
    'VA': 'Virginia',
    'WA': 'Washington',
    'WV': 'West Virginia',
    'WI': 'Wisconsin',
    'WY': 'Wyoming',
    'DC': 'District of Columbia',
}

MAP_NODE_TYPES = ('company', 'site', 'rail', 'port')
DEFAULT_MAP_NODE_TYPES = ('company', 'site')


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


def normalized_key(value):
    """Normalize a name for lightweight geography lookups."""
    return str(value or '').strip().lower()


def parse_float(value):
    """Parse a float value, returning None for blanks or invalid values."""
    try:
        if value is None or str(value).strip() == '':
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def yes_no_value(value):
    """Normalize yes/no-ish dashboard fields for comparisons."""
    return str(value or '').strip().lower() in {'yes', 'true', '1'}


def get_company_filter_args(args):
    """Collect reusable ranked-company filter arguments from a request."""
    return {
        'query': str(args.get('q', '')).strip() or None,
        'state': str(args.get('state', '')).strip() or None,
        'segment': str(args.get('segment', '')).strip() or None,
        'commodity': str(args.get('commodity', '')).strip() or None,
        'min_score': parse_min_score(args.get('min_score')),
        'readiness': str(args.get('readiness', '')).strip() or None,
    }


def build_dashboard_export_context(filters, total_count, filtered_count, exported_count):
    """Describe the dashboard view that produced an export."""
    return {
        'source': 'dashboard',
        'view': 'ranked_companies',
        'applied_filters': {
            'query': filters.get('query'),
            'state': filters.get('state'),
            'segment': filters.get('segment'),
            'commodity': filters.get('commodity'),
            'min_score': filters.get('min_score'),
            'readiness': filters.get('readiness'),
        },
        'source_company_count': total_count,
        'dashboard_filtered_company_count': filtered_count,
        'dashboard_exported_company_count': exported_count,
        'review_overlay_applied': True,
        'filter_note': (
            'Counts reflect the dashboard view after search, readiness, score, '
            'state, segment, and commodity filters are applied.'
        ),
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
        'readinesses': [
            READY_LABEL,
            VERIFY_SITE_LABEL,
            COMPARE_SITES_LABEL,
            QUALIFY_FIT_LABEL,
        ],
    }


def build_company_view_presets():
    """Return one-click dashboard presets for common company review queues."""
    return [
        {
            'label': 'Ready outreach',
            'description': 'High-priority companies with a site ready enough to start outreach.',
            'params': {'readiness': READY_LABEL, 'min_score': 70},
        },
        {
            'label': 'Verify site first',
            'description': 'Strong prospects blocked by site source or data confirmation work.',
            'params': {'readiness': VERIFY_SITE_LABEL},
        },
        {
            'label': 'Compare sites',
            'description': 'Companies that need a better first-choice site decision.',
            'params': {'readiness': COMPARE_SITES_LABEL},
        },
        {
            'label': 'Qualified fit review',
            'description': 'Prospects that need a human check before outreach.',
            'params': {'readiness': QUALIFY_FIT_LABEL},
        },
    ]


def build_site_view_presets():
    """Return one-click dashboard presets for common site review queues."""
    return [
        {
            'label': 'Research ready',
            'description': 'Confirmed site records ready for opportunity matching.',
            'params': {'review_status': 'confirmed'},
        },
        {
            'label': 'Site verification',
            'description': 'Sites that still need validation or review follow-up.',
            'params': {'review_status': 'needs_review'},
        },
        {
            'label': 'Needs confirmation',
            'description': 'Records with acreage, source, or logistics details to confirm.',
            'params': {'needs_confirmation': 'yes'},
        },
        {
            'label': 'Transload sites',
            'description': 'Sites with transload availability visible in the current data.',
            'params': {'transload_available': 'Yes'},
        },
    ]


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
    filtered = filter_ranked_companies(
        filtered,
        state=filters.get('state'),
        segment=filters.get('segment'),
        commodity=filters.get('commodity'),
        min_score=filters.get('min_score'),
    )
    if filters.get('readiness'):
        filtered = [
            company for company in filtered
            if (
                company.get('readiness_label')
                or (company.get('opportunity_readiness') or build_opportunity_readiness(company)).get('label')
            ) == filters['readiness']
        ]
    return filtered


def build_company_scan_summary(companies):
    """Build compact counts that help economic developers scan the company list."""
    readiness_labels = {
        company.get('company', ''): (
            company.get('opportunity_readiness')
            or build_opportunity_readiness(company)
        ).get('label')
        for company in companies
    }
    ready_for_outreach = [
        company for company in companies
        if readiness_labels.get(company.get('company', '')) == READY_LABEL
    ]
    missing_best_site = [
        company for company in companies
        if readiness_labels.get(company.get('company', '')) == COMPARE_SITES_LABEL
        or not (company.get('best_site_name') or company.get('best_recommended_site'))
    ]
    verify_site = [
        company for company in companies
        if readiness_labels.get(company.get('company', '')) == VERIFY_SITE_LABEL
    ]
    qualify_fit = [
        company for company in companies
        if readiness_labels.get(company.get('company', '')) == QUALIFY_FIT_LABEL
    ]
    external_review_required = [
        company for company in companies
        if (company.get('external_use') or {}).get('human_review_required')
    ]
    outreach_usable = [
        company for company in companies
        if (company.get('external_use') or {}).get('outreach_usable')
    ]
    return {
        'ready_for_outreach': len(ready_for_outreach),
        'outreach_usable': len(outreach_usable),
        'external_review_required': len(external_review_required),
        'verify_site_first': len(verify_site),
        'needs_site_review': len(missing_best_site),
        'qualify_fit': len(qualify_fit),
        'average_priority': round(
            sum(safe_score(company.get('priority_score', 0)) for company in companies) / len(companies),
            1,
        ) if companies else 0,
    }


def build_site_lookup(sites, review_store_path=None):
    """Return reviewed site rows indexed by site name."""
    site_rows = merge_review_records(
        build_site_directory(sites),
        load_review_store(review_store_path) if review_store_path else {},
    )
    return {
        site.get('site_name', ''): site
        for site in site_rows
        if site.get('site_name')
    }


def annotate_companies_with_readiness(companies, sites, review_store_path=None):
    """Attach unified opportunity readiness to ranked companies."""
    sites_by_name = build_site_lookup(sites, review_store_path=review_store_path)
    annotated = []
    for company in companies:
        site_name = company_best_site_name(company)
        site = sites_by_name.get(site_name) if site_name else None
        annotated_company = annotate_company_opportunity_readiness(
            company,
            site=site,
        )
        if site:
            research_readiness = build_research_readiness(
                site,
                company=company,
                compatibility_score=safe_score(company.get('best_site_match_score', 0)),
            )
            verification_tasks = research_readiness.get('tasks', [])
        else:
            verification_tasks = []
        annotated_company['external_use'] = build_workspace_external_use_guardrail(
            company,
            annotated_company.get('opportunity_readiness', {}),
            verification_tasks,
        )
        annotated.append(annotated_company)
    return annotated


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


PIPELINE_STAGES = [
    {
        'key': 'outreach_ready',
        'label': 'Outreach ready',
        'readiness': READY_LABEL,
        'tone': 'positive',
        'description': 'Company, site, lane, and research signals are aligned.',
    },
    {
        'key': 'site_verification',
        'label': 'Site verification',
        'readiness': VERIFY_SITE_LABEL,
        'tone': 'review',
        'description': 'Strong prospects waiting on site source or data confirmation.',
    },
    {
        'key': 'site_selection',
        'label': 'Site selection',
        'readiness': COMPARE_SITES_LABEL,
        'tone': 'warning',
        'description': 'Prospects that need a clearer first-choice site.',
    },
    {
        'key': 'qualification',
        'label': 'Qualification',
        'readiness': QUALIFY_FIT_LABEL,
        'tone': 'review',
        'description': 'Promising fits that need a human check on timing, lane, or need.',
    },
    {
        'key': 'monitor',
        'label': 'Monitor',
        'readiness': 'Monitor',
        'tone': 'neutral',
        'description': 'Lower-signal records to revisit later.',
    },
]


def pipeline_stage_for_readiness(readiness_label):
    """Return the display stage for a readiness label."""
    return next(
        (stage for stage in PIPELINE_STAGES if stage['readiness'] == readiness_label),
        PIPELINE_STAGES[-1],
    )


def build_opportunity_explanation(company, site=None):
    """Build a compact plain-English explanation for an opportunity."""
    readiness = company.get('opportunity_readiness') or build_opportunity_readiness(
        company,
        site=site,
    )
    priority_reasons = get_priority_reasons(company)[:3]
    site_name = company_best_site_name(company)
    reasons = list(priority_reasons)
    if site_name:
        reasons.append(f"Best current site match: {site_name}.")
    if site:
        research = site.get('research_readiness') or build_research_readiness(site, company=company)
        reasons.append(
            f"Site research status: {research.get('label', 'Needs review')} "
            f"({safe_score(research.get('score', 0))}/100)."
        )
    blocker = readiness.get('reason') or 'Review the opportunity before taking action.'
    return {
        'headline': readiness.get('next_action') or 'Review the opportunity before taking action.',
        'why': reasons or ['Priority score, site match, and lane fit should be reviewed together.'],
        'blocker': blocker,
    }


def pipeline_stage_advancement(readiness_label):
    """Return the concrete thing that moves one pipeline stage forward."""
    return {
        READY_LABEL: 'Prepare the selected company-site workspace and export the outreach brief.',
        VERIFY_SITE_LABEL: 'Clear the site blocker in Site Verification or the Site Detail review form.',
        COMPARE_SITES_LABEL: 'Choose a defensible first-choice site from the comparison view.',
        QUALIFY_FIT_LABEL: 'Confirm company timing, material flow, and lane assumptions in the workspace.',
        'Monitor': 'Wait for stronger project, site, or lane signals before active outreach.',
    }.get(readiness_label, 'Review the record and choose the next workflow step.')


def choose_pipeline_item_actions(readiness_label, urls):
    """Choose one primary workflow action and a short secondary set for a pipeline card."""
    if readiness_label == READY_LABEL and urls.get('workspace_url'):
        primary = {'label': 'Open Workspace', 'url': urls['workspace_url']}
        secondary = [
            {'label': 'Review Company', 'url': urls.get('company_url')},
            {'label': 'Review Site', 'url': urls.get('site_url')},
        ]
    elif readiness_label == VERIFY_SITE_LABEL and urls.get('site_url'):
        primary = {'label': 'Review Site', 'url': urls['site_url']}
        secondary = [
            {'label': 'Open Workspace', 'url': urls.get('workspace_url')},
            {'label': 'Compare Sites', 'url': urls.get('compare_url')},
        ]
    elif readiness_label == COMPARE_SITES_LABEL and urls.get('compare_url'):
        primary = {'label': 'Compare Sites', 'url': urls['compare_url']}
        secondary = [
            {'label': 'Review Company', 'url': urls.get('company_url')},
            {'label': 'Review Site', 'url': urls.get('site_url')},
        ]
    elif readiness_label == QUALIFY_FIT_LABEL and urls.get('workspace_url'):
        primary = {'label': 'Open Workspace', 'url': urls['workspace_url']}
        secondary = [
            {'label': 'Compare Sites', 'url': urls.get('compare_url')},
            {'label': 'Review Company', 'url': urls.get('company_url')},
        ]
    else:
        primary = {'label': 'Review Company', 'url': urls.get('company_url')}
        secondary = [
            {'label': 'Compare Sites', 'url': urls.get('compare_url')},
            {'label': 'Review Site', 'url': urls.get('site_url')},
        ]

    return {
        'primary': primary if primary.get('url') else None,
        'secondary': [action for action in secondary if action.get('url') and action.get('url') != primary.get('url')],
    }


def build_opportunity_pipeline(companies, sites, review_store_path=None, limit_per_stage=12, filters=None):
    """Build a practical company-site pipeline from existing readiness signals."""
    annotated_companies = annotate_companies_with_readiness(
        companies,
        sites,
        review_store_path=review_store_path,
    )
    filters = filters or {}
    filtered_companies = filter_companies_for_dashboard(annotated_companies, filters)
    sites_by_name = build_site_lookup(sites, review_store_path=review_store_path)
    stages = [
        {
            **stage,
            'items': [],
            'count': 0,
        }
        for stage in PIPELINE_STAGES
    ]
    stage_by_readiness = {stage['readiness']: stage for stage in stages}

    for company in filtered_companies:
        stage = stage_by_readiness.get(
            company.get('readiness_label'),
            stages[-1],
        )
        site_name = company_best_site_name(company)
        site = sites_by_name.get(site_name) if site_name else None
        explanation = build_opportunity_explanation(company, site=site)
        external_use = company.get('external_use') or build_workspace_external_use_guardrail(
            company,
            company.get('opportunity_readiness') or build_opportunity_readiness(company, site=site),
            (site.get('research_readiness') or build_research_readiness(site)).get('tasks', []) if site else [],
        )
        urls = {
            'company_url': url_for('company_detail', company_name=company.get('company', '')),
            'compare_url': url_for('company_site_comparison', company_name=company.get('company', '')),
            'workspace_url': url_for('opportunity_workspace', company=company.get('company', ''), site=site_name) if site_name else '',
            'site_url': url_for('site_detail', site_name=site_name) if site_name else '',
        }
        actions = choose_pipeline_item_actions(company.get('readiness_label'), urls)
        item = {
            'company': company.get('company', ''),
            'state': company.get('state', ''),
            'segment': company.get('segment', ''),
            'commodity': company.get('commodity_type') or company.get('commodity') or '',
            'priority_score': safe_score(company.get('priority_score', 0)),
            'site_name': site_name,
            'site_match_score': safe_score(company.get('best_site_match_score', 0)),
            'lane_score': safe_score(company.get('best_lane_score', 0)),
            'readiness_label': company.get('readiness_label', ''),
            'readiness_tone': company.get('readiness_tone', ''),
            'next_action': company.get('readiness_next_action') or readiness_next_action(company.get('readiness_label')),
            'advance_action': pipeline_stage_advancement(company.get('readiness_label')),
            'explanation': explanation,
            'external_use': external_use,
            **urls,
            'primary_action': actions['primary'],
            'secondary_actions': actions['secondary'],
        }
        stage['items'].append(item)

    for stage in stages:
        stage['items'].sort(
            key=lambda item: (
                item['priority_score'],
                item['site_match_score'],
                item['lane_score'],
            ),
            reverse=True,
        )
        stage['count'] = len(stage['items'])
        stage['items'] = stage['items'][:limit_per_stage]

    return {
        'stages': stages,
        'total': len(filtered_companies),
        'unfiltered_total': len(annotated_companies),
        'filters': filters,
        'summary': {
            'outreach_ready': stage_by_readiness.get(READY_LABEL, {}).get('count', 0),
            'site_verification': stage_by_readiness.get(VERIFY_SITE_LABEL, {}).get('count', 0),
            'site_selection': stage_by_readiness.get(COMPARE_SITES_LABEL, {}).get('count', 0),
            'qualification': stage_by_readiness.get(QUALIFY_FIT_LABEL, {}).get('count', 0),
            'monitor': stage_by_readiness.get('Monitor', {}).get('count', 0),
        },
    }


def build_verification_queue(sites, companies, review_store_path=None, limit=30):
    """Build the site data-confidence work queue."""
    site_rows = merge_review_records(
        build_site_directory(sites),
        load_review_store(review_store_path) if review_store_path else {},
    )
    queue = []
    for site in site_rows:
        readiness = site.get('research_readiness') or build_research_readiness(site)
        tasks = readiness.get('tasks', [])
        if not tasks and not site.get('needs_confirmation') and site.get('review_status') == 'confirmed':
            continue
        blocked_count = safe_score(readiness.get('blocked_count', 0))
        is_blocked = site.get('review_status') == 'blocked' or readiness.get('label') == 'Blocked By Data Gaps'
        if site.get('review_status') == 'confirmed' and tasks:
            queue_note = (
                f"Review saved, but outreach is still blocked by "
                f"{blocked_count} blocker{'s' if blocked_count != 1 else ''}."
            )
        elif is_blocked:
            queue_note = 'Highest-friction record: clear blocking source or logistics gaps before outreach.'
        else:
            queue_note = 'Incomplete record: finish the remaining verification checklist before outreach.'
        top_company = ''
        top_company_score = 0
        affected_company_count = 0
        for company in companies:
            score = calculate_site_compatibility_score(company, site)
            if score >= 50:
                affected_company_count += 1
            if score > top_company_score:
                top_company = company.get('company', '')
                top_company_score = score
        unlocks_outreach = bool(
            not site.get('ready_for_outreach')
            and top_company
            and top_company_score >= 60
            and (blocked_count or tasks or site.get('needs_confirmation') or is_blocked)
        )
        queue.append({
            'site_name': site.get('site_name', ''),
            'location': site.get('location') or format_site_location(site),
            'state': site.get('state', ''),
            'review_status': site.get('review_status', ''),
            'review_status_label': site.get('review_status_label', status_label(site.get('review_status'))),
            'review_status_tone': site.get('review_status_tone', review_status_tone(site.get('review_status'))),
            'readiness': readiness,
            'confidence': confidence_label(site),
            'needs_confirmation': site.get('needs_confirmation'),
            'flags': site.get('data_quality_flags', []),
            'tasks': tasks[:5],
            'top_blocker': tasks[0] if tasks else 'Review source confidence and site details.',
            'blocked_count': blocked_count,
            'task_count': len(tasks),
            'is_blocked': is_blocked,
            'queue_note': queue_note,
            'top_company': top_company,
            'top_company_score': top_company_score,
            'affected_company_count': affected_company_count,
            'unlocks_outreach': unlocks_outreach,
            'unlock_note': (
                'Fixing this site can unlock outreach for the best-fit company.'
                if unlocks_outreach
                else 'Fixing this site improves downstream matching, workspace, comparison, and export quality.'
            ),
            'site_url': url_for('site_detail', site_name=site.get('site_name', '')),
            'company_url': url_for('company_detail', company_name=top_company) if top_company else '',
            'workspace_url': url_for('opportunity_workspace', company=top_company, site=site.get('site_name', '')) if top_company else '',
        })

    queue.sort(
        key=lambda item: (
            0 if item['is_blocked'] else 1,
            -item['blocked_count'],
            item['readiness'].get('score', 0),
            item['site_name'],
        )
    )
    return {
        'items': queue[:limit],
        'total': len(queue),
        'summary': {
            'blocked': sum(1 for item in queue if item['readiness'].get('label') == 'Blocked By Data Gaps'),
            'needs_confirmation': sum(1 for item in queue if item['needs_confirmation']),
            'missing_sources': sum(
                1 for item in queue
                if any('source' in task.lower() for task in item['tasks'])
            ),
            'average_readiness': round(
                sum(safe_score(item['readiness'].get('score', 0)) for item in queue) / len(queue),
                1,
            ) if queue else 0,
        },
    }


def build_command_center_today_work(pipeline, verification, limit=7):
    """Build a compact, prioritized daily triage list across core workflows."""
    stage_lookup = {stage['readiness']: stage for stage in pipeline['stages']}
    work = []
    seen = set()
    seen_action_urls = set()

    def add_item(key, rank, title, subtitle, why, primary_action, tone='review', pills=None):
        if not primary_action or not primary_action.get('url') or key in seen:
            return
        if primary_action['url'] in seen_action_urls:
            return
        seen.add(key)
        seen_action_urls.add(primary_action['url'])
        work.append({
            'rank': rank,
            'title': title,
            'subtitle': subtitle,
            'why': why,
            'primary_action': primary_action,
            'tone': tone,
            'pills': [pill for pill in (pills or []) if pill],
        })

    for item in stage_lookup.get(VERIFY_SITE_LABEL, {}).get('items', [])[:4]:
        add_item(
            ('verify-opportunity', item['company'], item['site_name']),
            10 - item['priority_score'] / 100,
            item['site_name'] or item['company'],
            f"{item['company']} is blocked before outreach.",
            item['explanation']['blocker'],
            item['primary_action'],
            tone=item['readiness_tone'],
            pills=[
                f"{item['priority_score']}/100 priority",
                item['readiness_label'],
            ],
        )

    for item in stage_lookup.get(READY_LABEL, {}).get('items', [])[:3]:
        external_use = item.get('external_use', {})
        add_item(
            ('ready', item['company'], item['site_name']),
            20 - item['priority_score'] / 100,
            item['company'],
            f"{item['site_name']} is ready enough for workspace prep.",
            external_use.get('note') or item['explanation']['blocker'],
            item['primary_action'],
            tone=item['readiness_tone'],
            pills=[
                f"{item['priority_score']}/100 priority",
                item['readiness_label'],
                external_use.get('status'),
            ],
        )

    for item in verification['items'][:5]:
        add_item(
            ('site-verification', item['site_name']),
            30 - item['blocked_count'],
            item['site_name'],
            item['unlock_note'],
            item['top_blocker'],
            {'label': 'Review Site', 'url': item['site_url']},
            tone='warning' if item['is_blocked'] else 'review',
            pills=[
                item['review_status_label'],
                f"{item['blocked_count']} blockers",
            ],
        )

    for item in stage_lookup.get(COMPARE_SITES_LABEL, {}).get('items', [])[:2]:
        add_item(
            ('compare', item['company']),
            40 - item['priority_score'] / 100,
            item['company'],
            'This prospect needs a first-choice site before outreach can be trusted.',
            item['advance_action'],
            item['primary_action'],
            tone=item['readiness_tone'],
            pills=[
                f"{item['priority_score']}/100 priority",
                item['readiness_label'],
            ],
        )

    for item in stage_lookup.get(QUALIFY_FIT_LABEL, {}).get('items', [])[:2]:
        add_item(
            ('qualify', item['company'], item['site_name']),
            50 - item['priority_score'] / 100,
            item['company'],
            'The fit is promising, but needs a human check before outreach.',
            item['advance_action'],
            item['primary_action'],
            tone=item['readiness_tone'],
            pills=[
                f"{item['priority_score']}/100 priority",
                item['readiness_label'],
            ],
        )

    work.sort(key=lambda item: item['rank'])
    return work[:limit]


def build_saved_views():
    """Return useful saved view shortcuts across core dashboard workflows."""
    return [
        {
            'label': 'Today: site verification',
            'description': 'Open the highest-impact source and data confirmation queue.',
            'url': url_for('verification_queue'),
        },
        {
            'label': 'High-score site blockers',
            'description': 'Companies with enough priority to matter, blocked by site verification.',
            'url': url_for('companies', readiness=VERIFY_SITE_LABEL, min_score=70),
        },
        {
            'label': 'Texas chemical prospects',
            'description': 'A practical market slice for chemical and bulk liquid targets.',
            'url': url_for('companies', state='TX', segment='Chemicals', min_score=60),
        },
        {
            'label': 'Transload-ready sites',
            'description': 'Industrial sites with transload availability in the source data.',
            'url': url_for('sites', transload_available='Yes'),
        },
        {
            'label': 'Steel supply chain map',
            'description': 'Geographic view focused on the steel supply-chain play.',
            'url': url_for('opportunity_map', supply_chain='steel'),
        },
        {
            'label': 'Opportunity pipeline',
            'description': 'Review all companies by action stage.',
            'url': url_for('opportunity_pipeline'),
        },
    ]


def build_command_center(companies, sites, rail_infrastructure, review_store_path=None):
    """Build the dashboard landing-page operating summary."""
    pipeline = build_opportunity_pipeline(
        companies,
        sites,
        review_store_path=review_store_path,
        limit_per_stage=6,
    )
    verification = build_verification_queue(
        sites,
        companies,
        review_store_path=review_store_path,
        limit=8,
    )
    map_filters = {
        'query': '',
        'state': '',
        'segment': '',
        'commodity': '',
        'min_score': 60,
        'min_site_fit': None,
        'site_readiness': '',
        'source_confidence': '',
        'supply_chain': '',
        'node_types': ['company', 'site'],
    }
    map_data = build_opportunity_map(
        companies,
        sites,
        rail_infrastructure,
        map_filters,
        review_store_path=review_store_path,
    )
    ready_stage = next(
        (stage for stage in pipeline['stages'] if stage['readiness'] == READY_LABEL),
        {'items': []},
    )
    verify_stage = next(
        (stage for stage in pipeline['stages'] if stage['readiness'] == VERIFY_SITE_LABEL),
        {'items': []},
    )
    return {
        'pipeline': pipeline,
        'verification': verification,
        'today_work': build_command_center_today_work(pipeline, verification),
        'saved_views': build_saved_views(),
        'ready_opportunities': ready_stage['items'],
        'site_blockers': verify_stage['items'],
        'territory_plays': map_data.get('territory_plays', [])[:4],
        'summary': {
            'companies': len(companies),
            'sites': len(sites),
            'rail_records': len(rail_infrastructure),
            'territory_count': len(map_data.get('territory_plays', [])),
        },
    }


def render_command_center_packet(center):
    """Render a plain-text business packet for sharing outside the dashboard."""
    lines = [
        'OmniMapping Opportunity Packet',
        'Internal triage artifact: confirm source facts, contact owner, timing, and human review status before external use.',
        f"Companies: {center['summary']['companies']}",
        f"Sites: {center['summary']['sites']}",
        '',
        'Pipeline',
    ]
    for stage in center['pipeline']['stages']:
        lines.append(f"- {stage['label']}: {stage['count']}")
    lines.extend(['', 'Top Site Verification Items'])
    for item in center['verification']['items'][:10]:
        first_task = item['tasks'][0] if item['tasks'] else 'Review source confidence and site details.'
        lines.append(
            f"- {item['site_name']} ({item['location']}): "
            f"{item['readiness'].get('label')} - {first_task}"
        )
    lines.extend(['', 'Outreach Prep Candidates'])
    ready_items = center['ready_opportunities'][:10]
    if ready_items:
        for item in ready_items:
            external_use = item.get('external_use', {})
            lines.append(
                f"- {item['company']} + {item['site_name']}: "
                f"{external_use.get('status', 'Review before external use')} - "
                f"{external_use.get('note', 'Confirm human review before sharing externally.')}"
            )
    else:
        lines.append('- None currently queued.')
    lines.extend(['', 'Territory Plays'])
    for play in center['territory_plays']:
        lines.append(f"- {play.get('title')}: {play.get('reason')}")
    return "\n".join(lines) + "\n"


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
        'readinesses': [READY_LABEL, VERIFY_SITE_LABEL, COMPARE_SITES_LABEL, QUALIFY_FIT_LABEL, 'Monitor'],
        'sorts': [
            {'value': 'strong', 'label': 'Strong rail prospects'},
            {'value': 'ready', 'label': 'Ready for outreach'},
            {'value': 'priority', 'label': 'Average priority'},
            {'value': 'site_fit', 'label': 'Average site fit'},
            {'value': 'matches', 'label': 'Company matches'},
        ],
    }


def build_rail_coordinate_index(rail_infrastructure):
    """Index rail records by asset and city names for derived map coordinates."""
    index = {}
    for rail in rail_infrastructure:
        lat = parse_float(rail.get('latitude'))
        lon = parse_float(rail.get('longitude'))
        if lat is None or lon is None:
            continue
        coordinate = (lat, lon)
        for key in [rail.get('location'), rail.get('major_city')]:
            if normalized_key(key) and normalized_key(key) not in index:
                index[normalized_key(key)] = coordinate
    return index


def derive_map_coordinates(record, rail_coordinate_index=None):
    """Return coordinates from explicit fields, rail matches, or known city coordinates."""
    lat = parse_float(record.get('latitude'))
    lon = parse_float(record.get('longitude'))
    if lat is not None and lon is not None:
        return lat, lon, 'record coordinates'

    rail_coordinate_index = rail_coordinate_index or {}
    lookup_keys = [
        record.get('site_name'),
        record.get('location'),
        record.get('city'),
        record.get('major_city'),
    ]
    for key in lookup_keys:
        coordinate = rail_coordinate_index.get(normalized_key(key))
        if coordinate:
            return coordinate[0], coordinate[1], 'rail infrastructure match'

    city = str(record.get('city') or record.get('major_city') or '').strip()
    if not city and record.get('location'):
        city = str(record.get('location') or '').split(',')[0].strip()
    if city in CITY_COORDINATES:
        lat, lon = CITY_COORDINATES[city]
        return lat, lon, 'city coordinates'

    return None, None, ''


def get_map_filter_args(args):
    """Collect opportunity-map filters from the query string."""
    requested_node_types = args.getlist('node_type')
    node_types = [
        node_type for node_type in requested_node_types
        if node_type in MAP_NODE_TYPES
    ]
    if args.get('layers_submitted') and not node_types:
        selected_node_types = []
    else:
        selected_node_types = node_types or list(DEFAULT_MAP_NODE_TYPES)
    return {
        'query': str(args.get('q', '')).strip(),
        'state': str(args.get('state', '')).strip().upper(),
        'segment': str(args.get('segment', '')).strip(),
        'commodity': str(args.get('commodity', '')).strip(),
        'min_score': parse_min_score(args.get('min_score')),
        'min_site_fit': parse_min_score(args.get('min_site_fit')),
        'site_readiness': str(args.get('site_readiness', '')).strip(),
        'source_confidence': str(args.get('source_confidence', '')).strip(),
        'supply_chain': str(args.get('supply_chain', '')).strip(),
        'node_types': selected_node_types,
    }


def build_map_filter_options(companies, sites, chains, rail_infrastructure=None, review_store_path=None):
    """Build select values for the map view."""
    rail_infrastructure = rail_infrastructure or []
    site_rows = merge_review_records(
        build_site_directory(sites),
        load_review_store(review_store_path) if review_store_path else {},
    )
    return {
        **build_filter_options(companies),
        'site_readinesses': unique_sorted(
            site.get('research_readiness', {}).get('label')
            for site in site_rows
        ),
        'source_confidences': unique_sorted(
            list(confidence_label(site) for site in site_rows)
            + list(confidence_label(rail) for rail in rail_infrastructure)
        ),
        'supply_chains': [
            {'value': chain['slug'], 'label': chain['name']}
            for chain in chains
        ],
        'node_types': [
            {'value': 'company', 'label': 'Companies'},
            {'value': 'site', 'label': 'Sites'},
            {'value': 'rail', 'label': 'Rail context'},
            {'value': 'port', 'label': 'Port context'},
        ],
    }


def record_matches_query(record, query, fields):
    """Return whether a record matches free-text map search."""
    if not query:
        return True
    query_lower = query.lower()
    return any(query_lower in str(record.get(field, '')).lower() for field in fields)


def company_matches_supply_chain(company, supply_chain_slug):
    """Return whether a company belongs to the selected supply-chain definition."""
    if not supply_chain_slug:
        return True
    definition = next(
        (item for item in SUPPLY_CHAIN_DEFINITIONS if item.get('slug') == supply_chain_slug),
        None,
    )
    if not definition:
        return True
    return company in match_companies_for_definition(definition, [company])


def map_marker_tone(score):
    """Return a marker tone from a 0-100 opportunity score."""
    score = safe_score(score)
    if score >= 80:
        return 'strong'
    if score >= 60:
        return 'workable'
    return 'watch'


def map_marker_tone_label(tone):
    """Return a short readable label for map marker tones."""
    return {
        'strong': 'Strong signal',
        'workable': 'Workable signal',
        'watch': 'Watch list',
        'infrastructure': 'Infrastructure',
        'neutral': 'Context',
        'port': 'Port access',
    }.get(tone, 'Mapped node')


def has_map_opportunity_filters(filters):
    """Return whether map filters should narrow infrastructure context."""
    return any([
        filters.get('state'),
        filters.get('segment'),
        filters.get('commodity'),
        filters.get('min_score') is not None,
        filters.get('min_site_fit') is not None,
        filters.get('site_readiness'),
        filters.get('supply_chain'),
    ])


def company_best_site_name(company):
    """Return the best available site name for a company."""
    return company.get('best_site_name') or company.get('best_recommended_site') or ''


def map_company_marker_id(company):
    """Return the DOM marker id used for a company on the opportunity map."""
    return f"company-{safe_filename_token(company.get('company'), default='company')}"


def build_play_link(label, endpoint, **values):
    """Build one workflow link for a territory play."""
    return {'label': label, 'url': url_for(endpoint, **values)}


def territory_company_watch_item(company, matched_site, visible_node_types):
    """Return the plain-English watch item for one company in a territory play."""
    best_site = company_best_site_name(company)
    if not best_site:
        return 'No visible site option'
    if not matched_site and 'site' not in visible_node_types:
        return 'No visible site option'
    readiness = company.get('opportunity_readiness', {})
    if readiness.get('label'):
        return readiness.get('reason') or readiness.get('label')
    site_match_score = safe_score(company.get('best_site_match_score', 0))
    if not best_site:
        return 'No visible site option'
    if not matched_site:
        return 'Missing site data' if 'site' in visible_node_types else 'No visible site option'

    readiness = matched_site.get('research_readiness') or build_research_readiness(matched_site)
    readiness_score = safe_score(readiness.get('score', 0))
    readiness_label = readiness.get('label', '')
    if readiness_label == 'Blocked By Data Gaps' or readiness_score < 60:
        return 'Site readiness needs review'
    if site_match_score < 60:
        return 'Company is strong but needs site comparison'
    if confidence_label(matched_site) == 'Unspecified':
        return 'Confidence needs confirmation'
    return 'Ready for workspace review'


def build_territory_company_detail(company, sites_by_name, visible_node_types):
    """Build compact work-queue context for one ranked company in a territory play."""
    company_name = company.get('company', '')
    best_site = company_best_site_name(company)
    matched_site = sites_by_name.get(best_site) if best_site else None
    readiness = matched_site.get('research_readiness') if matched_site else {}
    opportunity_readiness = company.get('opportunity_readiness') or build_opportunity_readiness(
        company,
        site=matched_site,
    )
    priority_score = safe_score(company.get('priority_score', 0))
    site_match_score = safe_score(company.get('best_site_match_score', 0))
    links = [
        build_play_link('View Company', 'company_detail', company_name=company_name),
        build_play_link('Compare Sites', 'company_site_comparison', company_name=company_name),
    ]
    if best_site:
        links.append(build_play_link('Open Workspace', 'opportunity_workspace', company=company_name, site=best_site))
    if matched_site:
        links.append(build_play_link('Review Site', 'site_detail', site_name=matched_site.get('site_name', '')))

    return {
        'company': company_name,
        'marker_id': map_company_marker_id(company),
        'priority_score': priority_score,
        'priority_label': priority_label(priority_score),
        'matched_site': best_site,
        'site_match_score': site_match_score,
        'site_match_label': match_label(site_match_score),
        'site_readiness_score': safe_score(readiness.get('score', 0)) if readiness else None,
        'site_readiness_label': readiness.get('label', 'Not visible on this map') if readiness else 'Not visible on this map',
        'readiness_label': opportunity_readiness.get('label', ''),
        'readiness_tone': opportunity_readiness.get('tone', ''),
        'readiness_actionable': opportunity_readiness.get('actionable', False),
        'confidence': confidence_label(matched_site) if matched_site else '',
        'watch_item': territory_company_watch_item(company, matched_site, visible_node_types),
        'links': links,
    }


def build_territory_site_detail(site):
    """Build compact readiness context for one visible site in a territory play."""
    readiness = site.get('research_readiness') or build_research_readiness(site)
    readiness_score = safe_score(readiness.get('score', 0))
    if readiness.get('label') == 'Blocked By Data Gaps' or readiness_score < 60:
        watch_item = 'Site readiness needs review'
    elif confidence_label(site) == 'Unspecified':
        watch_item = 'Confidence needs confirmation'
    else:
        watch_item = 'Ready site option'
    return {
        'site_name': site.get('site_name', ''),
        'readiness_score': readiness_score,
        'readiness_label': readiness.get('label', 'Needs review'),
        'confidence': confidence_label(site),
        'watch_item': watch_item,
        'url': url_for('site_detail', site_name=site.get('site_name', '')),
    }


def choose_territory_primary_action(top_company_detail, top_site_detail, visible_node_types):
    """Choose the most useful first workflow for a territory play."""
    if top_company_detail:
        company_name = top_company_detail['company']
        matched_site = top_company_detail.get('matched_site')
        readiness_score = top_company_detail.get('site_readiness_score')
        readiness_label = top_company_detail.get('site_readiness_label')
        if matched_site and readiness_score is not None:
            if top_company_detail.get('readiness_actionable') is False:
                return build_play_link('Review Site', 'site_detail', site_name=matched_site)
            if readiness_label == 'Blocked By Data Gaps':
                return build_play_link('Review Site', 'site_detail', site_name=matched_site)
            return build_play_link('Open Workspace', 'opportunity_workspace', company=company_name, site=matched_site)
        if 'site' in visible_node_types:
            return build_play_link('Compare Sites', 'company_site_comparison', company_name=company_name)
        return build_play_link('View Company', 'company_detail', company_name=company_name)
    if top_site_detail:
        return build_play_link('Review Site', 'site_detail', site_name=top_site_detail['site_name'])
    return None


def build_territory_action_plan(mapped_companies, mapped_sites, visible_node_types):
    """Build practical state-level plays from the currently visible opportunity set."""
    territories = {}

    if 'company' in visible_node_types:
        for company in mapped_companies:
            state = str(company.get('state') or 'Unknown').upper()
            territory = territories.setdefault(state, {'companies': [], 'sites': []})
            territory['companies'].append(company)

    if 'site' in visible_node_types:
        for site in mapped_sites:
            state = str(site.get('state') or 'Unknown').upper()
            territory = territories.setdefault(state, {'companies': [], 'sites': []})
            territory['sites'].append(site)

    plays = []
    for state, territory in territories.items():
        companies = sorted(
            territory['companies'],
            key=lambda item: (-safe_score(item.get('priority_score', 0)), item.get('company', '')),
        )
        sites = sorted(
            territory['sites'],
            key=lambda item: (-safe_score(item.get('research_readiness', {}).get('score', 0)), item.get('site_name', '')),
        )
        top_company = companies[0] if companies else None
        top_site = sites[0] if sites else None
        top_company_score = safe_score(top_company.get('priority_score', 0)) if top_company else 0
        top_site_score = safe_score(top_site.get('research_readiness', {}).get('score', 0)) if top_site else 0
        best_site_name = company_best_site_name(top_company) if top_company else ''
        best_site_label = best_site_name or (top_site.get('site_name', '') if top_site else '')
        sites_by_name = {
            site.get('site_name', ''): site
            for site in sites
            if site.get('site_name')
        }
        company_details = [
            build_territory_company_detail(company, sites_by_name, visible_node_types)
            for company in companies[:5]
        ]
        site_details = [build_territory_site_detail(site) for site in sites[:3]]
        top_company_detail = company_details[0] if company_details else None
        top_site_detail = site_details[0] if site_details else None
        primary_action = choose_territory_primary_action(top_company_detail, top_site_detail, visible_node_types)
        blocking_issue = (
            top_company_detail.get('watch_item') if top_company_detail
            else top_site_detail.get('watch_item') if top_site_detail
            else ''
        )
        avg_company_score = round(
            sum(safe_score(company.get('priority_score', 0)) for company in companies) / len(companies)
        ) if companies else 0
        avg_site_score = round(
            sum(safe_score(site.get('research_readiness', {}).get('score', 0)) for site in sites) / len(sites)
        ) if sites else 0
        territory_score = max(top_company_score, top_site_score, round((avg_company_score + avg_site_score) / 2))
        territory_label = STATE_NAMES.get(state, state)
        links = []

        if top_company:
            company_name = top_company.get('company', '')
            links.extend([
                build_play_link('View Company', 'company_detail', company_name=company_name),
                build_play_link('Compare Sites', 'company_site_comparison', company_name=company_name),
            ])
            if best_site_label:
                links.append(build_play_link('Open Workspace', 'opportunity_workspace', company=company_name, site=best_site_label))
        if top_site:
            links.append(build_play_link('Review Site', 'site_detail', site_name=top_site.get('site_name', '')))

        if top_company and best_site_label:
            title = f"Move {top_company.get('company', '')} toward {best_site_label}"
            reason = (
                f"{territory_label} has the strongest visible company at {top_company_score}/100 "
                f"with {len(companies)} company target{'s' if len(companies) != 1 else ''}"
            )
            if top_site:
                reason += f" and {len(sites)} site option{'s' if len(sites) != 1 else ''} in view."
            else:
                reason += "."
            next_action = generate_recommended_next_action(top_company, best_site_label)
        elif top_company:
            title = f"Qualify {top_company.get('company', '')} first"
            reason = (
                f"{territory_label} has {len(companies)} visible company target"
                f"{'s' if len(companies) != 1 else ''}; the top priority is {top_company_score}/100."
            )
            next_action = 'Open the company workflow and compare sites before outreach.'
        elif top_site:
            readiness = top_site.get('research_readiness', {})
            title = f"Review {top_site.get('site_name', '')}"
            reason = (
                f"{territory_label} has {len(sites)} visible site option"
                f"{'s' if len(sites) != 1 else ''}; the top readiness signal is "
                f"{top_site_score}/100 ({readiness.get('label', 'Needs review')})."
            )
            next_action = 'Review site readiness, fill data gaps, and confirm whether it can support target companies.'
        else:
            continue

        plays.append({
            'territory': state,
            'territory_label': territory_label,
            'title': title,
            'reason': reason,
            'company_count': len(companies),
            'site_count': len(sites),
            'top_company': top_company.get('company', '') if top_company else '',
            'top_site': top_site.get('site_name', '') if top_site else best_site_name,
            'next_action': next_action,
            'score': territory_score,
            'signal': priority_label(top_company_score) if top_company else top_site.get('research_readiness', {}).get('label', 'Needs review'),
            'primary_action': primary_action,
            'blocking_issue': blocking_issue,
            'company_details': company_details,
            'site_details': site_details,
            'top_marker_id': top_company_detail.get('marker_id') if top_company_detail else '',
            'links': links[:4],
        })

    return sorted(
        plays,
        key=lambda item: (-item['score'], -item['company_count'], -item['site_count'], item['territory']),
    )[:4]


def build_map_active_filter_labels(filters):
    """Return concise labels for filters that should explain the current map set."""
    labels = []
    if filters.get('query'):
        labels.append(f"Search: {filters['query']}")
    if filters.get('state'):
        labels.append(f"State: {filters['state']}")
    if filters.get('segment'):
        labels.append(f"Segment: {filters['segment']}")
    if filters.get('commodity'):
        labels.append(f"Commodity: {filters['commodity']}")
    if filters.get('supply_chain'):
        chain = next(
            (item for item in SUPPLY_CHAIN_DEFINITIONS if item.get('slug') == filters['supply_chain']),
            None,
        )
        labels.append(f"Supply chain: {chain.get('name') if chain else filters['supply_chain']}")
    if filters.get('min_score') is not None:
        labels.append(f"Company priority >= {filters['min_score']}")
    if filters.get('min_site_fit') is not None:
        labels.append(f"Company site fit >= {filters['min_site_fit']}")
    if filters.get('site_readiness'):
        labels.append(f"Site readiness: {filters['site_readiness']}")
    if filters.get('source_confidence'):
        labels.append(f"Site/rail confidence: {filters['source_confidence']}")
    node_types = filters.get('node_types') or []
    if set(node_types) != set(DEFAULT_MAP_NODE_TYPES):
        readable_layers = {
            'company': 'companies',
            'site': 'sites',
            'rail': 'rail context',
            'port': 'port context',
        }
        labels.append(
            f"Layers: {', '.join(readable_layers.get(node_type, node_type) for node_type in node_types) if node_types else 'none'}"
        )
    return labels


def is_near_any_coordinate(lat, lon, coordinates, max_miles=250):
    """Return whether a coordinate is near any visible opportunity anchor."""
    for anchor_lat, anchor_lon in coordinates:
        distance = calculate_distance(lat, lon, anchor_lat, anchor_lon)
        if distance is not None and distance <= max_miles:
            return True
    return False


def build_opportunity_map(companies, sites, rail_infrastructure, filters, review_store_path=None):
    """Build a JSON-ready map model from existing dashboard opportunity data."""
    rail_coordinate_index = build_rail_coordinate_index(rail_infrastructure)
    markers = []
    visible_node_types = set(filters.get('node_types') or [])
    active_filters = build_map_active_filter_labels(filters)
    mapped_companies = []
    mapped_sites = []

    filtered_companies = filter_companies_for_dashboard(companies, {
        'query': filters.get('query') or None,
        'state': filters.get('state') or None,
        'segment': filters.get('segment') or None,
        'commodity': filters.get('commodity') or None,
        'min_score': filters.get('min_score'),
    })
    if filters.get('min_site_fit') is not None:
        filtered_companies = [
            company for company in filtered_companies
            if safe_score(company.get('best_site_match_score', 0)) >= filters['min_site_fit']
        ]
    filtered_companies = [
        company for company in filtered_companies
        if company_matches_supply_chain(company, filters.get('supply_chain'))
    ]
    site_rows = merge_review_records(
        build_site_directory(sites),
        load_review_store(review_store_path) if review_store_path else {},
    )
    sites_by_name = {
        site.get('site_name', ''): site
        for site in site_rows
        if site.get('site_name')
    }
    filtered_companies = [
        annotate_company_opportunity_readiness(
            company,
            site=sites_by_name.get(company_best_site_name(company)),
        )
        for company in filtered_companies
    ]
    unmapped_companies = []
    if 'company' in visible_node_types:
        for company in filtered_companies:
            lat, lon, coordinate_source = derive_map_coordinates(company, rail_coordinate_index)
            if lat is None or lon is None:
                unmapped_companies.append({
                    'type': 'company',
                    'label': company.get('company', ''),
                    'state': str(company.get('state') or '').upper(),
                    'reason': 'Missing coordinates',
                })
                continue
            priority_score = safe_score(company.get('priority_score', 0))
            opportunity_readiness = company.get('opportunity_readiness', {})
            tone = 'strong' if opportunity_readiness.get('label') == READY_LABEL else map_marker_tone(priority_score)
            best_site = company.get('best_site_name') or company.get('best_recommended_site') or ''
            details = [
                f"Priority {priority_score}/100 ({priority_label(priority_score)})",
                f"Best site fit {safe_score(company.get('best_site_match_score', 0))}/100",
                f"Readiness: {opportunity_readiness.get('label', '')}",
                f"Coordinates: {coordinate_source}",
            ]
            if company.get('nearest_class1_railroad'):
                details.append(f"Nearest rail {company.get('nearest_class1_railroad')}")
            if company.get('nearest_port'):
                details.append(f"Nearest port {company.get('nearest_port')}")
            markers.append({
                'id': f"company-{safe_filename_token(company.get('company'), default='company')}",
                'type': 'company',
                'label': company.get('company', ''),
                'subtitle': format_company_location(company),
                'lat': lat,
                'lon': lon,
                'state': str(company.get('state') or '').upper(),
                'tone': tone,
                'tone_label': map_marker_tone_label(tone),
                'score': priority_score,
                'size': 16 + min(24, priority_score * 0.22),
                'segment': company.get('segment', ''),
                'commodity': company.get('commodity_type') or company.get('commodity', ''),
                'next_step': opportunity_readiness.get('next_action') or company.get('recommended_next_action') or 'Open the workspace to qualify outreach and site fit.',
                'details': details,
                'links': [
                    {'label': 'Company', 'url': url_for('company_detail', company_name=company.get('company', ''))},
                    {'label': 'Compare Sites', 'url': url_for('company_site_comparison', company_name=company.get('company', ''))},
                ] + (
                    [{'label': 'Workspace', 'url': url_for('opportunity_workspace', company=company.get('company', ''), site=best_site)}]
                    if best_site else []
                ),
            })
            mapped_companies.append(company)

    filtered_company_site_names = {
        company.get('best_site_name') or company.get('best_recommended_site')
        for company in filtered_companies
        if company.get('best_site_name') or company.get('best_recommended_site')
    }
    filtered_sites = []
    for site_row in site_rows:
        readiness = site_row.get('research_readiness') or build_research_readiness(site_row)
        if filters.get('query') and not record_matches_query(
            site_row,
            filters['query'],
            ['site_name', 'location', 'target_industries', 'data_gap_notes'],
        ):
            continue
        if filters.get('state') and site_row.get('state', '').upper() != filters['state']:
            continue
        if filters.get('segment') and site_row.get('site_name') not in filtered_company_site_names:
            continue
        if filters.get('commodity') and filters['commodity'].lower() not in str(site_row.get('target_industries', '')).lower():
            continue
        if filters.get('site_readiness') and readiness.get('label') != filters['site_readiness']:
            continue
        if filters.get('source_confidence') and confidence_label(site_row) != filters['source_confidence']:
            continue
        site_row = {**site_row, 'research_readiness': readiness}
        filtered_sites.append(site_row)

    anchor_coordinates = []
    for record in list(filtered_companies) + list(filtered_sites):
        lat, lon, _ = derive_map_coordinates(record, rail_coordinate_index)
        if lat is not None and lon is not None:
            anchor_coordinates.append((lat, lon))

    if 'site' in visible_node_types:
        unmapped_sites = []
        for site in filtered_sites:
            lat, lon, coordinate_source = derive_map_coordinates(site, rail_coordinate_index)
            if lat is None or lon is None:
                unmapped_sites.append({
                    'type': 'site',
                    'label': site.get('site_name', ''),
                    'state': str(site.get('state') or '').upper(),
                    'reason': 'Missing coordinates',
                })
                continue
            readiness = site.get('research_readiness') or build_research_readiness(site)
            score = safe_score(readiness.get('score', 0))
            tone = map_marker_tone(score)
            markers.append({
                'id': f"site-{safe_filename_token(site.get('site_name'), default='site')}",
                'type': 'site',
                'label': site.get('site_name', ''),
                'subtitle': site.get('location') or format_site_location(site),
                'lat': lat,
                'lon': lon,
                'state': str(site.get('state') or '').upper(),
                'tone': tone,
                'tone_label': map_marker_tone_label(tone),
                'score': score,
                'size': 14 + min(22, score * 0.2),
                'segment': site.get('target_industries', ''),
                'commodity': site.get('target_industries', ''),
                'next_step': 'Open the site profile to review readiness, gaps, and compatible companies.',
                'details': [
                    f"Research {score}/100 ({readiness.get('label', '')})",
                    f"Rail served: {site.get('rail_served') or 'Confirm'}",
                    f"Transload: {site.get('transload_available') or 'Confirm'}",
                    f"Port access: {site.get('port_access') or 'Confirm'}",
                    f"Confidence: {confidence_label(site)}",
                    f"Coordinates: {coordinate_source}",
                ],
                'links': [
                    {'label': 'Site', 'url': url_for('site_detail', site_name=site.get('site_name', ''))},
                ],
            })
            mapped_sites.append(site)
    else:
        unmapped_sites = []

    if 'rail' in visible_node_types:
        for rail in rail_infrastructure:
            if has_map_opportunity_filters(filters) and not anchor_coordinates:
                continue
            if filters.get('query') and not record_matches_query(
                rail,
                filters['query'],
                ['location', 'type', 'major_city', 'region', 'interstate_access'],
            ):
                continue
            if filters.get('source_confidence') and confidence_label(rail) != filters['source_confidence']:
                continue
            lat, lon, coordinate_source = derive_map_coordinates(rail, rail_coordinate_index)
            if lat is None or lon is None:
                continue
            if (
                has_map_opportunity_filters(filters)
                and not filters.get('query')
                and not is_near_any_coordinate(lat, lon, anchor_coordinates)
            ):
                continue
            logistics_score = safe_score(int(parse_float(rail.get('logistics_score')) or 0) * 10)
            tone = 'infrastructure' if yes_no_value(rail.get('transload_hub')) else 'neutral'
            markers.append({
                'id': f"rail-{safe_filename_token(rail.get('location'), default='rail')}",
                'type': 'rail',
                'label': rail.get('location', ''),
                'subtitle': rail.get('type', ''),
                'lat': lat,
                'lon': lon,
                'state': '',
                'tone': tone,
                'tone_label': map_marker_tone_label(tone),
                'score': logistics_score,
                'size': 13 + min(17, logistics_score * 0.15),
                'segment': rail.get('type', ''),
                'commodity': '',
                'next_step': 'Use this infrastructure node as nearby context for visible companies and sites.',
                'details': [
                    f"Logistics {rail.get('logistics_score', '')}/10",
                    f"Rail connections {rail.get('rail_connections', '')}",
                    f"Transload hub: {rail.get('transload_hub') or 'Confirm'}",
                    f"Port nearby: {rail.get('port_nearby') or 'Confirm'}",
                    f"Confidence: {confidence_label(rail)}",
                    f"Coordinates: {coordinate_source}",
                ],
                'links': [],
            })

    if 'company' in visible_node_types and 'port' in visible_node_types and mapped_companies:
        visible_ports = {}
        for company in mapped_companies:
            port_info = find_nearest_port(company)
            if port_info and port_info.get('port_name') in MAJOR_PORTS:
                visible_ports[port_info['port_name']] = port_info
        for port_name, port_info in sorted(visible_ports.items()):
            if filters.get('query') and filters['query'].lower() not in port_name.lower():
                continue
            lat, lon = MAJOR_PORTS[port_name]
            markers.append({
                'id': f"port-{safe_filename_token(port_name, default='port')}",
                'type': 'port',
                'label': port_name,
                'subtitle': 'Nearest port for visible opportunities',
                'lat': lat,
                'lon': lon,
                'state': '',
                'tone': 'port',
                'tone_label': map_marker_tone_label('port'),
                'score': 70 if port_info.get('port_accessible') else 45,
                'size': 18,
                'segment': 'Port',
                'commodity': '',
                'next_step': 'Use this port node to qualify multimodal optionality for the visible company set.',
                'details': [
                    'Port node derived from visible company geography',
                    f"Last matched distance: {port_info.get('distance_miles')} miles",
                    f"Within 300 miles: {'Yes' if port_info.get('port_accessible') else 'No'}",
                ],
                'links': [],
            })

    state_counts = {}
    state_profiles = {}
    if 'company' in visible_node_types:
        for company in mapped_companies:
            state = str(company.get('state') or 'Unknown').upper()
            profile = state_profiles.setdefault(state, {
                'state': state,
                'name': STATE_NAMES.get(state, state),
                'companies': 0,
                'sites': 0,
                'ready_sites': 0,
                'high_priority': 0,
                'priority_total': 0,
                'top_score': 0,
                'top_label': '',
            })
            score = safe_score(company.get('priority_score', 0))
            profile['companies'] += 1
            profile['priority_total'] += score
            if score >= 80:
                profile['high_priority'] += 1
            if score > profile['top_score']:
                profile['top_score'] = score
                profile['top_label'] = company.get('company', '')

    if 'site' in visible_node_types:
        for site in mapped_sites:
            state = str(site.get('state') or 'Unknown').upper()
            profile = state_profiles.setdefault(state, {
                'state': state,
                'name': STATE_NAMES.get(state, state),
                'companies': 0,
                'sites': 0,
                'ready_sites': 0,
                'high_priority': 0,
                'priority_total': 0,
                'top_score': 0,
                'top_label': '',
            })
            readiness_score = safe_score(site.get('research_readiness', {}).get('score', 0))
            profile['sites'] += 1
            if readiness_score >= 70:
                profile['ready_sites'] += 1
            if readiness_score > profile['top_score']:
                profile['top_score'] = readiness_score
            if not profile['top_label']:
                profile['top_label'] = site.get('site_name', '')

    for profile in state_profiles.values():
        profile['avg_priority'] = round(profile['priority_total'] / profile['companies']) if profile['companies'] else 0
        profile['activity'] = profile['companies'] + profile['sites']
        profile['readiness'] = round((profile['ready_sites'] / profile['sites']) * 100) if profile['sites'] else 0
        state_counts[profile['state']] = profile['activity']

    markers.sort(key=lambda marker: (marker['type'] != 'company', -safe_score(marker.get('score', 0)), marker['label']))
    type_counts = {}
    for marker in markers:
        type_counts[marker['type']] = type_counts.get(marker['type'], 0) + 1
    type_counts = {
        node_type: type_counts.get(node_type, 0)
        for node_type in MAP_NODE_TYPES
    }
    top_opportunities = [
        marker for marker in markers
        if marker.get('type') == 'company'
    ][:5]
    top_states = [
        {
            'state': profile['state'],
            'count': profile['activity'],
            'companies': profile['companies'],
            'sites': profile['sites'],
        }
        for profile in sorted(
            state_profiles.values(),
            key=lambda item: (-item['activity'], item['state']),
        )[:6]
    ]
    return {
        'markers': markers,
        'summary': {
            'companies': len(mapped_companies),
            'sites': len(mapped_sites),
            'markers': len(markers),
            'unmapped_companies': len(unmapped_companies),
            'unmapped_sites': len(unmapped_sites),
            'unmapped_nodes': len(unmapped_companies) + len(unmapped_sites),
            'filtered_companies': len(filtered_companies) if 'company' in visible_node_types else 0,
            'filtered_sites': len(filtered_sites) if 'site' in visible_node_types else 0,
            'high_priority': len([
                company for company in mapped_companies
                if safe_score(company.get('priority_score', 0)) >= 80
            ]),
            'ready_sites': len([
                site for site in mapped_sites
                if site.get('research_readiness', {}).get('score', 0) >= 70
            ]),
            'states': len(state_counts),
            'baseline_companies': len(companies),
            'baseline_sites': len(sites),
            'baseline_nodes': len(companies) + len(sites),
            'active_filters': len(active_filters),
        },
        'filter_context': {
            'active_labels': active_filters,
            'has_filters': bool(active_filters),
            'state': filters.get('state') or '',
            'node_types': sorted(visible_node_types),
        },
        'state_profiles': state_profiles,
        'state_counts': dict(sorted(state_counts.items())),
        'top_states': top_states,
        'type_counts': type_counts,
        'top_opportunities': top_opportunities,
        'unmapped_nodes': (unmapped_companies + unmapped_sites)[:20],
        'territory_plays': build_territory_action_plan(mapped_companies, mapped_sites, visible_node_types),
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

    readiness = build_research_readiness(site, company=company, compatibility_score=pair_score)
    for task in readiness.get('tasks', []):
        if task not in gaps:
            gaps.append(task)

    if not gaps:
        gaps.append('Confirm acreage, rail service details, utility readiness, and company timing before outreach.')

    return gaps


def build_workspace_qualification_checklist(company, site, lane, research_readiness):
    """Translate qualification language into concrete user actions."""
    return [
        {
            'label': 'Material volumes',
            'action': (
                'Confirm what moves inbound and outbound, estimated annual volume, '
                'handling mode, and whether rail or transload is actually needed.'
            ),
        },
        {
            'label': 'Lane fit',
            'action': (
                'Check origin and destination lanes against this site rail access, '
                'truck access, port optionality, and the serving railroad.'
            ),
        },
        {
            'label': 'Site requirements',
            'action': (
                'Confirm acreage, parcel control, utilities, zoning, transload capacity, '
                'and timing before outreach.'
            ),
        },
        {
            'label': 'Evidence to capture',
            'action': (
                (research_readiness.get('tasks') or ['No open blockers. Capture source links, owner contact, utilities, zoning, and timing notes.'])[0]
            ),
        },
    ]


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


def build_workspace_external_use_guardrail(company, opportunity_readiness, verification_tasks):
    """Explain whether a selected opportunity is usable outside the dashboard."""
    company_text = " ".join([
        str(company.get('company_info', '')),
        str(company.get('why_target', '')),
        str(company.get('opportunity_risk', '')),
    ]).lower()
    has_speculative_context = 'speculative' in company_text
    blockers = list(verification_tasks or [])
    actionable = bool(opportunity_readiness.get('actionable'))

    if blockers:
        status = 'Hold for verification'
        tone = 'review'
        note = 'Resolve the open research blocker before using this brief for outreach.'
    elif has_speculative_context:
        status = 'Internal review first'
        tone = 'review'
        note = 'The company opportunity language is speculative, so confirm live need, decision maker, and timing before external outreach.'
    elif actionable:
        status = 'Ready for outreach prep'
        tone = 'positive'
        note = 'No research blockers remain. Confirm timing and contact owner before sending externally.'
    else:
        status = 'Hold for qualification'
        tone = 'review'
        note = 'The pair still needs qualification before outreach prep.'

    return {
        'status': status,
        'tone': tone,
        'note': note,
        'has_speculative_context': has_speculative_context,
        'human_review_required': bool(blockers or has_speculative_context or not actionable),
        'outreach_usable': bool(actionable and not blockers and not has_speculative_context),
        'send_checklist': [
            'Confirm public-source facts and remove unsupported claims.',
            'Confirm contact target, outreach timing, and why this message matters now.',
            'Keep speculative prospect language internal unless a human reviewer validates it.',
        ],
    }


def build_company_site_comparison(company, sites, segments, limit=5):
    """Build a decision-ready comparison of top compatible sites for one company."""
    site_matches = find_best_sites_for_company(company, sites, limit)
    compared_sites = []

    for index, match in enumerate(site_matches, start=1):
        site = match.get('site', {})
        compatibility_score = safe_score(match.get('compatibility_score', 0))
        research_readiness = build_research_readiness(
            site,
            company=company,
            compatibility_score=compatibility_score,
        )
        lane = {
            'lane_score': safe_score(match.get('lane_score', 0)),
            'lane_readiness_label': match.get('lane_readiness_label', ''),
            'lane_reasons': match.get('lane_reasons', []),
        }
        opportunity_readiness = build_opportunity_readiness(
            company,
            site=site,
            compatibility_score=compatibility_score,
            lane=lane,
            research_readiness=research_readiness,
        )
        compared_sites.append({
            'rank': index,
            'site': build_site_profile(site),
            'compatibility_score': compatibility_score,
            'pair_score': safe_score(match.get('pair_score', 0)),
            'lane_score': lane['lane_score'],
            'lane_readiness_label': lane['lane_readiness_label'],
            'lane_reasons': lane['lane_reasons'],
            'research_readiness': research_readiness,
            'opportunity_readiness': opportunity_readiness,
            'actionable': opportunity_readiness['actionable'],
            'verification_tasks': research_readiness.get('tasks', []),
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
            'research_readiness_label': first_choice['research_readiness']['label'],
            'readiness_label': first_choice['opportunity_readiness']['label'],
            'actionable': first_choice['actionable'],
            'next_action': first_choice['opportunity_readiness'].get('next_action', ''),
            'reason': first_choice['opportunity_readiness'].get('reason', ''),
            'blocked_count': first_choice['research_readiness'].get('blocked_count', 0),
            'verification_tasks': first_choice.get('verification_tasks', [])[:3],
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
    research_readiness = build_research_readiness(
        site,
        company=company,
        compatibility_score=compatibility_score,
    )
    opportunity_readiness = build_opportunity_readiness(
        company,
        site=site,
        compatibility_score=compatibility_score,
        lane=lane,
        research_readiness=research_readiness,
    )
    company_copy = company.copy()
    company_copy['best_recommended_site'] = site.get('site_name', '')
    company_copy['best_site_name'] = site.get('site_name', '')
    company_copy['best_recommended_site_location'] = format_site_location(site)
    company_copy['best_site_match_score'] = compatibility_score
    verification_tasks = research_readiness.get('tasks', [])
    qualification_checklist = build_workspace_qualification_checklist(
        company,
        site,
        lane,
        research_readiness,
    )
    external_use = build_workspace_external_use_guardrail(
        company,
        opportunity_readiness,
        verification_tasks,
    )

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
        'research_readiness': research_readiness,
        'opportunity_readiness': opportunity_readiness,
        'external_use': external_use,
        'verification_tasks': verification_tasks,
        'qualification_checklist': qualification_checklist,
        'company_context': format_company_context(company, segment_data),
        'risks_or_data_gaps': build_workspace_data_gaps(company, site, compatibility_score=compatibility_score),
        'talking_points': build_workspace_talking_points(company, site, segment_data),
    }


def build_workspace_brief_handoff(workspace, export_filename):
    """Build the user-facing handoff model for a workspace brief page."""
    company = workspace.get('company', {})
    site = workspace.get('site', {})
    priority = workspace.get('priority', {})
    site_match = workspace.get('site_match', {})
    lane = workspace.get('lane', {})
    research = workspace.get('research_readiness', {})
    readiness = workspace.get('opportunity_readiness', {})
    external_use = workspace.get('external_use') or build_workspace_external_use_guardrail(
        company,
        readiness,
        workspace.get('verification_tasks', []),
    )
    talking_points = workspace.get('talking_points', [])
    blockers = workspace.get('verification_tasks', [])

    lead_angle = talking_points[0] if talking_points else readiness.get('reason', '')
    executive_summary = (
        f"{company.get('company')} is a {safe_score(priority.get('score', 0))}/100 "
        f"{company.get('segment', 'prospect')} opportunity matched to "
        f"{site.get('site_name')} at {safe_score(site_match.get('compatibility_score', 0))}/100 site fit. "
        f"{lead_angle}"
    ).strip()

    return {
        'file_name': export_filename,
        'external_status': external_use.get('status', 'Hold for qualification'),
        'external_tone': external_use.get('tone', 'review'),
        'external_note': external_use.get('note', ''),
        'has_speculative_context': external_use.get('has_speculative_context', False),
        'human_review_required': external_use.get('human_review_required', True),
        'outreach_usable': external_use.get('outreach_usable', False),
        'executive_summary': executive_summary,
        'decision_gates': [
            {
                'label': 'Company priority',
                'value': f"{safe_score(priority.get('score', 0))}/100",
                'status': priority_label(priority.get('score', 0)),
                'tone': score_tone(priority.get('score', 0)),
            },
            {
                'label': 'Site fit',
                'value': f"{safe_score(site_match.get('compatibility_score', 0))}/100",
                'status': match_label(site_match.get('compatibility_score', 0)),
                'tone': score_tone(site_match.get('compatibility_score', 0)),
            },
            {
                'label': 'Lane readiness',
                'value': f"{safe_score(lane.get('lane_score', 0))}/100",
                'status': lane.get('lane_readiness_label', 'Needs review'),
                'tone': score_tone(lane.get('lane_score', 0)),
            },
            {
                'label': 'Research readiness',
                'value': f"{safe_score(research.get('score', 0))}/100",
                'status': research.get('label', 'Needs review'),
                'tone': research.get('tone', 'review'),
            },
            {
                'label': 'External use',
                'value': external_use.get('status', 'Hold for qualification'),
                'status': 'Human review required' if external_use.get('human_review_required', True) else 'Prep-ready',
                'tone': external_use.get('tone', 'review'),
            },
        ],
        'evidence': [
            {'label': 'Source confidence', 'value': site.get('source_confidence') or 'Unspecified'},
            {'label': 'Last verified', 'value': site.get('last_verified') or 'Unknown'},
            {'label': 'Acreage', 'value': site.get('acres') or 'Confirm'},
            {'label': 'Rail served', 'value': site.get('rail_served') or 'Confirm'},
            {'label': 'Transload', 'value': site.get('transload_available') or 'Confirm'},
            {'label': 'Port access', 'value': site.get('port_access') or 'Confirm'},
        ],
        'questions': [
            'Is there a current expansion, relocation, sourcing, or logistics event behind this prospect?',
            'What annual inbound and outbound volumes are realistic, and which lanes matter most?',
            'Does the company need direct rail, transload, port optionality, or mainly industrial real estate?',
            'Who owns the decision, and what proof would make this site credible to them?',
        ],
        'send_checklist': external_use.get('send_checklist', []),
    }


def render_workspace_brief_text(company, site, segments):
    """Build the selected opportunity TXT brief body."""
    segment_data = find_segment_for_company(segments, company)
    compatibility_score = safe_score(calculate_site_compatibility_score(company, site))
    workspace = build_opportunity_workspace(company, site, segments)
    company_copy = company.copy()
    company_copy['best_recommended_site'] = site.get('site_name', '')
    company_copy['best_site_name'] = site.get('site_name', '')
    company_copy['best_recommended_site_location'] = format_site_location(site)
    company_copy['best_site_match_score'] = compatibility_score
    company_copy['recommended_next_action'] = workspace['opportunity_readiness'].get(
        'next_action',
        generate_recommended_next_action(company, site.get('site_name')),
    )

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        print_opportunity_brief(company_copy, segment_data, recommended_site=site)
        print("\n9. REVIEWED READINESS CONTEXT:")
        print(
            "   - Opportunity readiness: "
            f"{workspace['opportunity_readiness'].get('label', 'Needs review')}"
        )
        print(
            "   - Research readiness: "
            f"{workspace['research_readiness'].get('label', 'Needs review')} "
            f"({workspace['research_readiness'].get('score', 0)}/100)"
        )
        print(
            "   - Outreach usable: "
            f"{'Yes' if workspace['external_use'].get('outreach_usable') else 'No'}"
        )
        print(
            "   - External use status: "
            f"{workspace['external_use'].get('status', 'Hold for qualification')}"
        )
        print(
            "   - Human review required: "
            f"{'Yes' if workspace['external_use'].get('human_review_required') else 'No'}"
        )
        print(
            "   - External use note: "
            f"{workspace['external_use'].get('note', 'Review before external use.')}"
        )
        print(
            "   - Next action: "
            f"{workspace['opportunity_readiness'].get('next_action', 'Review this pair before outreach.')}"
        )
        print(
            "   - Why this action: "
            f"{workspace['opportunity_readiness'].get('reason', 'No readiness explanation available.')}"
        )
        if workspace['verification_tasks']:
            print("   - Blockers:")
            for task in workspace['verification_tasks']:
                print(f"     * {task}")
            print("   - Verification tasks:")
            for task in workspace['verification_tasks']:
                print(f"     * {task}")
        else:
            print("   - Blockers: none open in the current checklist.")
            print("   - Verification tasks: none open in the current checklist.")

    return buffer.getvalue()


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
        'opportunity_readiness_label',
        'research_readiness_label',
        'research_readiness_score',
        'review_status',
        'source_confidence',
        'last_verified',
        'blocked_count',
        'lane_reasons',
        'verification_tasks',
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
                'opportunity_readiness_label': compared_site.get('opportunity_readiness', {}).get('label', ''),
                'research_readiness_label': compared_site.get('research_readiness', {}).get('label', ''),
                'research_readiness_score': compared_site.get('research_readiness', {}).get('score', ''),
                'review_status': site.get('review_status_label') or site.get('review_status', ''),
                'source_confidence': site.get('source_confidence', ''),
                'last_verified': site.get('last_verified', ''),
                'blocked_count': compared_site.get('research_readiness', {}).get('blocked_count', ''),
                'lane_reasons': '; '.join(compared_site.get('lane_reasons', [])),
                'verification_tasks': '; '.join(compared_site.get('verification_tasks', [])),
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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    company_token = safe_filename_token(company.get('company'), default='company')
    site_token = safe_filename_token(site.get('site_name'), default='site')
    filename = f"opportunity_brief_{company_token}_{site_token}_{timestamp}.txt"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w') as brief_file:
        brief_file.write(render_workspace_brief_text(company, site, segments))
    return filepath


def build_site_review_next_steps(site, companies):
    """Build visible next-step guidance after a site review save."""
    readiness = site.get('research_readiness') or build_research_readiness(site)
    site_name = site.get('site_name', '')
    matches = []
    for company in companies:
        compatibility_score = safe_score(calculate_site_compatibility_score(company, site))
        if compatibility_score <= 0:
            continue
        opportunity_readiness = build_opportunity_readiness(
            company,
            site=site,
            compatibility_score=compatibility_score,
            research_readiness=build_research_readiness(
                site,
                company=company,
                compatibility_score=compatibility_score,
            ),
        )
        matches.append({
            'company': company.get('company', ''),
            'compatibility_score': compatibility_score,
            'opportunity_readiness': opportunity_readiness,
            'workspace_url': url_for('opportunity_workspace', company=company.get('company', ''), site=site_name),
            'compare_url': url_for('company_site_comparison', company_name=company.get('company', '')),
        })
    matches.sort(key=lambda item: item['compatibility_score'], reverse=True)
    top_match = matches[0] if matches else None

    if readiness.get('label') == 'Research Ready':
        headline = 'Research Ready: this site now flows downstream.'
        description = (
            f"{site_name} drops out of Site Verification and becomes usable in Pipeline, "
            "Workspace, comparisons, and exports."
        )
        primary = (
            {'label': 'Open Workspace', 'url': top_match['workspace_url']}
            if top_match else {'label': 'Open Pipeline', 'url': url_for('opportunity_pipeline')}
        )
        secondary = [
            {'label': 'Check Pipeline', 'url': url_for('opportunity_pipeline')},
        ]
        if top_match:
            secondary.append({'label': 'Compare Sites', 'url': top_match['compare_url']})
    elif readiness.get('tasks'):
        headline = 'Review saved, but this site still needs verification.'
        description = (
            f"{readiness.get('blocked_count', 0)} blocker"
            f"{'s' if readiness.get('blocked_count', 0) != 1 else ''} remain before outreach."
        )
        primary = {'label': 'Continue Site Verification', 'url': url_for('verification_queue')}
        secondary = [{'label': 'Check Pipeline', 'url': url_for('opportunity_pipeline')}]
        if top_match:
            secondary.append({'label': 'Open Workspace', 'url': top_match['workspace_url']})
    else:
        headline = 'Review saved.'
        description = 'Use Pipeline to choose the next active opportunity.'
        primary = {'label': 'Check Pipeline', 'url': url_for('opportunity_pipeline')}
        secondary = [{'label': 'Site Verification', 'url': url_for('verification_queue')}]

    return {
        'headline': headline,
        'description': description,
        'readiness_label': readiness.get('label', 'Needs Verification'),
        'blocked_count': safe_score(readiness.get('blocked_count', 0)),
        'tasks': readiness.get('tasks', [])[:4],
        'primary_action': primary,
        'secondary_actions': secondary,
        'unlocked_opportunities': matches[:3] if readiness.get('label') == 'Research Ready' else [],
    }


def create_app(data_loader=load_data, export_dir="exports", review_store_path=None):
    """Create the dashboard app with injectable data loading for tests."""
    app = Flask(__name__)
    app.secret_key = os.environ.get('OMNIMAPPING_SECRET_KEY', 'omnimapping-local-dashboard')
    app.config['OMNIMAPPING_DATA_LOADER'] = data_loader
    app.config['OMNIMAPPING_EXPORT_DIR'] = export_dir
    app.config['OMNIMAPPING_REVIEW_STORE'] = review_store_path or os.path.join('data', 'review_status.json')

    def get_data():
        if 'OMNIMAPPING_DATA' not in app.config:
            app.config['OMNIMAPPING_DATA'] = app.config['OMNIMAPPING_DATA_LOADER']()
        segments, companies, sites, rail_infrastructure = app.config['OMNIMAPPING_DATA']
        return segments, companies, sites, rail_infrastructure

    def get_reviewed_sites(sites):
        """Apply local review overlays consistently for pages and downloads."""
        return merge_review_records(
            sites,
            load_review_store(app.config['OMNIMAPPING_REVIEW_STORE']),
        )

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
        _, companies, sites, rail_infrastructure = get_data()
        center = build_command_center(
            companies,
            sites,
            rail_infrastructure,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
        )
        return render_template('command_center.html', center=center)

    @app.route('/pipeline')
    def opportunity_pipeline():
        _, companies, sites, _ = get_data()
        filters = get_company_filter_args(request.args)
        pipeline = build_opportunity_pipeline(
            companies,
            sites,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
            limit_per_stage=25,
            filters=filters,
        )
        return render_template(
            'opportunity_pipeline.html',
            pipeline=pipeline,
            saved_views=build_saved_views(),
            filter_options=build_filter_options(companies),
            filters=filters,
        )

    @app.route('/verification')
    def verification_queue():
        _, companies, sites, _ = get_data()
        queue = build_verification_queue(
            sites,
            companies,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
            limit=60,
        )
        return render_template('verification_queue.html', queue=queue, saved_views=build_saved_views())

    @app.route('/companies')
    def companies():
        _, all_companies, sites, _ = get_data()
        filters = get_company_filter_args(request.args)
        limit = parse_limit(request.args.get('limit'), default=50)
        readiness_companies = annotate_companies_with_readiness(
            all_companies,
            sites,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
        )
        ranked_companies = filter_companies_for_dashboard(readiness_companies, filters)
        visible_companies = ranked_companies[:limit]

        return render_template(
            'companies.html',
            companies=visible_companies,
            total_count=len(all_companies),
            filtered_count=len(ranked_companies),
            filters=filters,
            filter_options=build_filter_options(all_companies),
            view_presets=build_company_view_presets(),
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

        report = build_company_report(company, get_reviewed_sites(sites), company_name, all_matches=matches)
        return render_template('company_detail.html', report=report)

    @app.route('/companies/<path:company_name>/site-comparison')
    def company_site_comparison(company_name):
        segments, all_companies, sites, _ = get_data()
        company, _ = find_company_for_report(all_companies, company_name)
        if not company:
            abort(404)

        limit = parse_limit(request.args.get('limit'), default=5, maximum=10)
        comparison = build_company_site_comparison(company, get_reviewed_sites(sites), segments, limit=limit)
        return render_template('company_site_comparison.html', comparison=comparison, limit=limit)

    @app.route('/map')
    def opportunity_map():
        _, companies, sites, rail_infrastructure = get_data()
        chains = build_supply_chain_catalog(companies)
        filters = get_map_filter_args(request.args)
        map_data = build_opportunity_map(
            companies,
            sites,
            rail_infrastructure,
            filters,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
        )
        return render_template(
            'opportunity_map.html',
            map_data=map_data,
            filters=filters,
            filter_options=build_map_filter_options(
                companies,
                sites,
                chains,
                rail_infrastructure=rail_infrastructure,
                review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
            ),
        )

    @app.route('/downloads/opportunity-packet.txt')
    def download_opportunity_packet():
        _, companies, sites, rail_infrastructure = get_data()
        center = build_command_center(
            companies,
            sites,
            rail_infrastructure,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
        )
        packet = render_command_center_packet(center)
        buffer = io.BytesIO(packet.encode('utf-8'))
        return send_file(
            buffer,
            as_attachment=True,
            download_name='omnimapping_opportunity_packet.txt',
            mimetype='text/plain',
        )

    @app.route('/sites')
    def sites():
        _, companies, all_sites, _ = get_data()
        filters = get_site_filter_args(request.args)
        reviewed_sites = get_reviewed_sites(all_sites)
        site_rows = build_site_directory(reviewed_sites)
        site_rows = filter_site_directory(site_rows, filters)

        return render_template(
            'sites.html',
            sites=site_rows,
            total_count=len(all_sites),
            filtered_count=len(site_rows),
            filter_options=build_site_filter_options(reviewed_sites),
            view_presets=build_site_view_presets(),
            filters=filters,
            company_count=len(companies),
            scan_summary=build_site_scan_summary(site_rows),
        )

    @app.route('/sites/<path:site_name>')
    def site_detail(site_name):
        _, companies, all_sites, _ = get_data()
        reviewed_sites = get_reviewed_sites(all_sites)
        site, matches = find_site_for_report(reviewed_sites, site_name)
        if not site:
            abort(404)

        report = build_site_report(site, companies, site_name, all_matches=matches, top_limit=15)
        if request.args.get('review_saved'):
            report['review_outcome'] = build_site_review_next_steps(site, companies)
        return render_template('site_detail.html', report=report)

    @app.route('/supply-chains')
    def supply_chains():
        _, companies, sites, _ = get_data()
        readiness_companies = annotate_companies_with_readiness(
            companies,
            sites,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
        )
        all_chains = build_supply_chain_catalog(readiness_companies)
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
        _, companies, sites, _ = get_data()
        readiness_companies = annotate_companies_with_readiness(
            companies,
            sites,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
        )
        chain = build_supply_chain_detail(slug, readiness_companies)
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
                source_confidence=request.form.get('source_confidence', ''),
                last_verified=request.form.get('last_verified', ''),
                data_gap_notes=request.form.get('data_gap_notes', ''),
                owner_contact=request.form.get('owner_contact', ''),
                utilities=request.form.get('utilities', ''),
                zoning_entitlement=request.form.get('zoning_entitlement', ''),
                acres=request.form.get('acres', ''),
                rail_served=request.form.get('rail_served', ''),
                nearby_class1=request.form.get('nearby_class1', ''),
                transload_available=request.form.get('transload_available', ''),
                interstate_access=request.form.get('interstate_access', ''),
                port_access=request.form.get('port_access', ''),
            )
            save_review_store(app.config['OMNIMAPPING_REVIEW_STORE'], review_store)
        except ValueError:
            abort(400)

        updated_site = merge_review_record(
            site,
            load_review_store(app.config['OMNIMAPPING_REVIEW_STORE']),
        )
        readiness = updated_site.get('research_readiness', {})
        blocked_count = safe_score(readiness.get('blocked_count', 0))
        outreach_label = 'usable for outreach' if updated_site.get('ready_for_outreach') else 'not usable for outreach yet'
        flash(
            "Review saved for {site}. Status: {status}. Research readiness: {research}. "
            "Remaining blocker count: {blocked}. Site is {outreach}.".format(
                site=updated_site.get('site_name', ''),
                status=updated_site.get('review_status_label', ''),
                research=readiness.get('label', 'Needs Verification'),
                blocked=blocked_count,
                outreach=outreach_label,
            ),
            'success',
        )

        return redirect(url_for('site_detail', site_name=site.get('site_name', ''), review_saved=1))

    @app.route('/workspace')
    def opportunity_workspace():
        segments, companies, sites, _ = get_data()
        company_name = request.args.get('company', '')
        site_name = request.args.get('site', '')
        company, _ = find_company_for_report(companies, company_name)
        site, _ = find_site_for_report(sites, site_name)
        if not company or not site:
            abort(404)

        site = merge_review_record(site, load_review_store(app.config['OMNIMAPPING_REVIEW_STORE']))
        workspace = build_opportunity_workspace(company, site, segments)
        return render_template('opportunity_workspace.html', workspace=workspace)

    @app.route('/workspace/brief')
    def workspace_brief_preview():
        segments, companies, sites, _ = get_data()
        company, _ = find_company_for_report(companies, request.args.get('company', ''))
        site, _ = find_site_for_report(get_reviewed_sites(sites), request.args.get('site', ''))
        if not company or not site:
            abort(404)

        workspace = build_opportunity_workspace(company, site, segments)
        filepath = write_workspace_brief_txt(
            company,
            site,
            segments,
            output_dir=app.config['OMNIMAPPING_EXPORT_DIR'],
        )
        with open(filepath) as brief_file:
            brief_text = brief_file.read()
        return render_template(
            'workspace_brief.html',
            workspace=workspace,
            handoff=build_workspace_brief_handoff(workspace, os.path.basename(filepath)),
            brief_text=brief_text,
            export_filename=os.path.basename(filepath),
            export_path=os.path.abspath(filepath),
        )

    @app.route('/downloads/top-companies.csv')
    def download_top_companies_csv():
        _, all_companies, sites, _ = get_data()
        filters = get_company_filter_args(request.args)
        limit = parse_limit(request.args.get('limit'), default=50)
        readiness_companies = annotate_companies_with_readiness(
            all_companies,
            sites,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
        )
        ranked_companies = filter_companies_for_dashboard(readiness_companies, filters)[:limit]
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
        readiness_companies = annotate_companies_with_readiness(
            all_companies,
            sites,
            review_store_path=app.config['OMNIMAPPING_REVIEW_STORE'],
        )
        ranked_companies = filter_companies_for_dashboard(readiness_companies, filters)
        export_filters = {
            key: value
            for key, value in filters.items()
            if key not in {'query', 'readiness'}
        }
        filepath = export_top_companies_json(
            ranked_companies,
            get_reviewed_sites(sites),
            output_dir=app.config['OMNIMAPPING_EXPORT_DIR'],
            limit=limit,
            export_context=build_dashboard_export_context(
                filters,
                total_count=len(all_companies),
                filtered_count=len(ranked_companies),
                exported_count=len(ranked_companies[:limit]),
            ),
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
                get_reviewed_sites(sites),
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
                get_reviewed_sites(all_sites),
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
        site, _ = find_site_for_report(get_reviewed_sites(sites), request.args.get('site', ''))
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
        comparison = build_company_site_comparison(company, get_reviewed_sites(sites), segments, limit=limit)
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
        comparison = build_company_site_comparison(company, get_reviewed_sites(sites), segments, limit=limit)
        filepath = write_company_site_comparison_csv(
            comparison,
            output_dir=app.config['OMNIMAPPING_EXPORT_DIR'],
        )
        return send_file(os.path.abspath(filepath), as_attachment=True, download_name=os.path.basename(filepath))

    @app.route('/downloads/workspace.txt')
    def download_workspace_txt():
        segments, companies, sites, _ = get_data()
        company, _ = find_company_for_report(companies, request.args.get('company', ''))
        site, _ = find_site_for_report(get_reviewed_sites(sites), request.args.get('site', ''))
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
        ('/', 200),
        ('/pipeline', 200),
        ('/verification', 200),
        ('/companies', 200),
        ('/companies?state=TX&min_score=1', 200),
        ('/map', 200),
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
