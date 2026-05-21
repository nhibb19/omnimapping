"""Tests for the OmniMapping Flask dashboard."""

import contextlib
import csv
import html
import io
import json
import os
import re
import sys
import tempfile
import unittest
from urllib.parse import urlsplit

from flask import request

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT_DIR)

import main
from dashboard import (
    build_company_site_comparison,
    build_company_scan_summary,
    build_opportunity_workspace,
    build_opportunity_map,
    build_map_filter_options,
    build_site_scan_summary,
    build_company_view_presets,
    build_site_view_presets,
    annotate_companies_with_readiness,
    build_command_center,
    build_opportunity_pipeline,
    build_verification_queue,
    build_supply_chain_filter_options,
    build_supply_chain_scan_summary,
    create_app,
    filter_companies_for_dashboard,
    filter_site_directory,
    get_map_filter_args,
    parse_limit,
    parse_min_score,
    unique_sorted,
)
from modules.data_quality import build_research_readiness
from modules.opportunity_readiness import (
    READY_LABEL,
    VERIFY_SITE_LABEL,
    build_opportunity_readiness,
)
from modules.export import build_site_directory
from modules.review import (
    build_review_update,
    load_review_store,
    merge_review_records,
    save_review_store,
)
from modules.supply_chains import (
    SUPPLY_CHAIN_DEFINITIONS,
    build_supply_chain_catalog,
    build_supply_chain_detail,
    filter_supply_chains,
)


class TestOmniMappingDashboard(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

        self.write_sample_data_dir(self.tempdir.name)

        previous_cwd = os.getcwd()
        try:
            os.chdir(self.tempdir.name)
            with contextlib.redirect_stdout(io.StringIO()):
                self.loaded_data = main.load_data()
        finally:
            os.chdir(previous_cwd)

        self.app = create_app(
            data_loader=lambda: self.loaded_data,
            export_dir=os.path.join(self.tempdir.name, 'exports'),
            review_store_path=os.path.join(self.tempdir.name, 'data', 'review_status.json'),
        )
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.review_store_path = self.app.config['OMNIMAPPING_REVIEW_STORE']

    def write_csv(self, filepath, rows):
        import csv

        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def write_sample_data_dir(self, root_dir):
        data_dir = os.path.join(root_dir, 'data')
        os.makedirs(data_dir, exist_ok=True)
        self.write_csv(os.path.join(data_dir, 'segments.csv'), [
            {
                'segment': 'Chemicals',
                'stage': 'active',
                'rail_score': '5',
                'reason': 'Chemical producers require rail and port access',
                'omnitrax_angle': 'rail transload',
                'commodity_type': 'chemicals',
            },
            {
                'segment': 'Warehousing',
                'stage': 'active',
                'rail_score': '3',
                'reason': 'Distribution users benefit from multimodal optionality',
                'omnitrax_angle': 'industrial real estate',
                'commodity_type': 'steel',
            },
        ])
        self.write_csv(os.path.join(data_dir, 'companies.csv'), [
            {
                'company': 'Acme Chemicals',
                'segment': 'Chemicals',
                'state': 'TX',
                'city': 'Houston',
                'commodity_type': 'chemicals',
                'rail_fit_score': '5',
                'industrial_real_estate_score': '4',
                'omnitrax_outreach_angle': 'rail transload',
                'inbound_materials': 'chemical inputs',
                'outbound_products': 'industrial chemicals',
                'why_target': 'Regional chemical production prospect',
            },
            {
                'company': 'Front Range Logistics',
                'segment': 'Warehousing',
                'state': 'CO',
                'city': 'Denver',
                'commodity_type': 'steel',
                'rail_fit_score': '3',
                'industrial_real_estate_score': '5',
                'omnitrax_outreach_angle': 'industrial real estate',
                'inbound_materials': 'steel',
                'outbound_products': 'finished goods',
                'why_target': 'Distribution user with land needs',
            },
        ])
        self.write_csv(os.path.join(data_dir, 'industrial_sites.csv'), [
            {
                'site_name': 'Houston Rail Park',
                'state': 'TX',
                'city': 'Houston',
                'rail_served': 'yes',
                'nearby_class1': 'yes',
                'transload_available': 'yes',
                'interstate_access': 'yes',
                'port_access': 'yes',
                'target_industries': 'chemicals, logistics',
                'acres': '250',
            },
            {
                'site_name': 'Denver Industrial Yard',
                'state': 'CO',
                'city': 'Denver',
                'rail_served': 'yes',
                'nearby_class1': 'yes',
                'transload_available': 'no',
                'interstate_access': 'yes',
                'port_access': 'no',
                'target_industries': 'warehousing, steel',
                'acres': '',
            },
        ])
        self.write_csv(os.path.join(data_dir, 'rail_infrastructure.csv'), [
            {
                'location': 'Houston Hub',
                'type': 'Yard',
                'latitude': '29.7604',
                'longitude': '-95.3698',
                'rail_connections': '5',
                'capacity_score': '8',
                'logistics_score': '7',
            },
            {
                'location': 'Denver Hub',
                'type': 'Intermodal',
                'latitude': '39.7392',
                'longitude': '-104.9903',
                'rail_connections': '3',
                'capacity_score': '6',
                'logistics_score': '6',
            },
        ])

    def test_dashboard_helper_parsing_is_stable(self):
        self.assertEqual(unique_sorted(['TX', '', 'CO', 'TX', None]), ['CO', 'TX'])
        self.assertIsNone(parse_min_score(''))
        self.assertIsNone(parse_min_score('not-a-score'))
        self.assertEqual(parse_min_score('-10'), 0)
        self.assertEqual(parse_min_score('120'), 100)
        self.assertEqual(parse_limit('bad', default=25), 25)
        self.assertEqual(parse_limit('0'), 1)

    def test_ranked_companies_page_filters_and_links_to_detail(self):
        response = self.client.get('/companies?state=TX&segment=Chemicals&commodity=chemicals&min_score=1')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Ranked Companies', body)
        self.assertIn('Acme Chemicals', body)
        self.assertNotIn('Front Range Logistics', body)
        self.assertIn('Human review', body)
        self.assertIn('Hold for verification', body)
        self.assertIn('/companies/Acme%20Chemicals', body)
        self.assertIn('/downloads/top-companies.csv', body)
        self.assertIn('/downloads/top-companies.json', body)
        self.assertIn('Ready for outreach', body)
        self.assertIn('Apply Filters', body)
        self.assertIn('Workspace', body)
        self.assertIn('Ready outreach', body)
        self.assertIn('Verify site first', body)
        self.assertIn('name="readiness"', body)

    def test_ranked_companies_quick_search_filters_exported_rows(self):
        response = self.client.get('/companies?q=Front%20Range')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Front Range Logistics', body)
        self.assertNotIn('Acme Chemicals', body)

        _, companies, sites, _ = self.loaded_data
        self.assertTrue(all('best_lane_score' in company for company in companies))
        filtered = filter_companies_for_dashboard(companies, {'query': 'chemical inputs'})
        self.assertEqual([company['company'] for company in filtered], ['Acme Chemicals'])

        summary = build_company_scan_summary(filtered)
        self.assertEqual(summary['ready_for_outreach'], 0)
        self.assertEqual(summary['external_review_required'], 0)
        self.assertEqual(summary['verify_site_first'], 1)

        readiness_companies = annotate_companies_with_readiness(companies, sites)
        readiness_filtered = filter_companies_for_dashboard(
            readiness_companies,
            {'query': '', 'readiness': VERIFY_SITE_LABEL, 'min_score': 70},
        )
        self.assertEqual([company['company'] for company in readiness_filtered], ['Acme Chemicals'])

    def test_dashboard_view_presets_link_to_supported_filters(self):
        company_presets = build_company_view_presets()
        site_presets = build_site_view_presets()

        self.assertTrue(any(
            preset['params'].get('readiness') == VERIFY_SITE_LABEL
            for preset in company_presets
        ))
        self.assertTrue(any(
            preset['params'].get('needs_confirmation') == 'yes'
            for preset in site_presets
        ))

    def test_opportunity_map_payload_derives_nodes_and_filters(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        with self.app.test_request_context('/map?state=TX&node_type=company&node_type=site'):
            map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': 'TX',
                    'segment': '',
                    'commodity': '',
                    'min_score': 1,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['company', 'site'],
                },
                review_store_path=self.review_store_path,
            )

        labels = {marker['label'] for marker in map_data['markers']}
        self.assertIn('Acme Chemicals', labels)
        self.assertIn('Houston Rail Park', labels)
        self.assertNotIn('Front Range Logistics', labels)
        self.assertTrue(all(marker['type'] in {'company', 'site'} for marker in map_data['markers']))
        self.assertTrue(all('lat' in marker and 'lon' in marker for marker in map_data['markers']))
        self.assertEqual(map_data['summary']['companies'], 1)
        self.assertEqual(map_data['type_counts']['company'], 1)
        self.assertEqual(map_data['top_opportunities'][0]['label'], 'Acme Chemicals')
        self.assertEqual(map_data['top_states'][0]['state'], 'TX')
        self.assertEqual(map_data['top_states'][0]['count'], 2)
        self.assertEqual(map_data['territory_plays'][0]['territory'], 'TX')
        self.assertEqual(map_data['territory_plays'][0]['top_company'], 'Acme Chemicals')
        self.assertEqual(map_data['territory_plays'][0]['top_site'], 'Houston Rail Park')
        self.assertEqual(map_data['territory_plays'][0]['company_details'][0]['company'], 'Acme Chemicals')
        self.assertEqual(map_data['territory_plays'][0]['company_details'][0]['matched_site'], 'Houston Rail Park')
        self.assertIn('State: TX', map_data['filter_context']['active_labels'])

    def test_opportunity_map_action_plan_includes_workflow_links(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        ready_sites = [
            {
                **site,
                'source_url': 'https://example.com/owner-utilities-zoning',
                'source_confidence': 'High',
                'last_verified': '2026-05-09',
                'data_gap_notes': '',
            }
            for site in sites
        ]
        with self.app.test_request_context('/map?node_type=company&node_type=site'):
            map_data = build_opportunity_map(
                companies,
                ready_sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': '',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['company', 'site'],
                },
                review_store_path=self.review_store_path,
            )

        plays_by_state = {play['territory']: play for play in map_data['territory_plays']}
        tx_play = plays_by_state['TX']
        self.assertIn('Acme Chemicals', tx_play['title'])
        self.assertIn('Texas', tx_play['reason'])
        self.assertEqual(tx_play['company_count'], 1)
        self.assertEqual(tx_play['site_count'], 1)
        self.assertGreater(tx_play['score'], 0)
        self.assertEqual(tx_play['primary_action']['label'], 'Open Workspace')
        self.assertEqual(tx_play['blocking_issue'], 'Priority, site fit, lane fit, and site readiness are aligned.')
        self.assertEqual(tx_play['company_details'][0]['company'], 'Acme Chemicals')
        self.assertEqual(tx_play['company_details'][0]['site_match_label'], 'Strong match')
        self.assertIn(tx_play['company_details'][0]['site_readiness_label'], {'Research Ready', 'Needs Verification'})
        self.assertEqual(tx_play['site_details'][0]['site_name'], 'Houston Rail Park')
        link_labels = {link['label'] for link in tx_play['links']}
        self.assertIn('View Company', link_labels)
        self.assertIn('Compare Sites', link_labels)
        self.assertIn('Open Workspace', link_labels)
        self.assertIn('Review Site', link_labels)
        link_urls = ' '.join(link['url'] for link in tx_play['links'])
        self.assertIn('/companies/Acme%20Chemicals', link_urls)
        self.assertIn('/companies/Acme%20Chemicals/site-comparison', link_urls)
        self.assertIn('/workspace?company=Acme+Chemicals', link_urls)
        self.assertIn('/sites/Houston%20Rail%20Park', link_urls)

    def test_opportunity_map_action_plan_primary_action_changes_by_visible_layers(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        with self.app.test_request_context('/map?node_type=company'):
            company_map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': 'TX',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['company'],
                },
                review_store_path=self.review_store_path,
            )

        company_play = company_map_data['territory_plays'][0]
        self.assertEqual(company_play['primary_action']['label'], 'View Company')
        self.assertEqual(company_play['blocking_issue'], 'No visible site option')

        with self.app.test_request_context('/map?node_type=site'):
            site_map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': 'TX',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['site'],
                },
                review_store_path=self.review_store_path,
            )

        site_play = site_map_data['territory_plays'][0]
        self.assertEqual(site_play['primary_action']['label'], 'Review Site')
        self.assertEqual(site_play['blocking_issue'], 'Site readiness needs review')

    def test_opportunity_map_action_plan_uses_compare_sites_when_site_choice_needs_review(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        unmatched_companies = [
            {**company, 'best_site_name': '', 'best_recommended_site': ''}
            if company['company'] == 'Acme Chemicals' else company
            for company in companies
        ]

        with self.app.test_request_context('/map?state=TX&node_type=company&node_type=site'):
            map_data = build_opportunity_map(
                unmatched_companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': 'TX',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['company', 'site'],
                },
                review_store_path=self.review_store_path,
            )

        tx_play = map_data['territory_plays'][0]
        self.assertEqual(tx_play['primary_action']['label'], 'Compare Sites')
        self.assertEqual(tx_play['company_details'][0]['watch_item'], 'No visible site option')

    def test_opportunity_map_segment_and_confidence_filters_apply_to_all_layers(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        with self.app.test_request_context('/map?segment=Chemicals&source_confidence=Unspecified&node_type=company&node_type=site'):
            map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': '',
                    'segment': 'Chemicals',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': 'Unspecified',
                    'supply_chain': '',
                    'node_types': ['company', 'site'],
                },
                review_store_path=self.review_store_path,
            )

        labels = {marker['label'] for marker in map_data['markers']}
        self.assertIn('Acme Chemicals', labels)
        self.assertNotIn('Front Range Logistics', labels)
        self.assertIn('Houston Rail Park', labels)
        self.assertNotIn('Denver Industrial Yard', labels)
        self.assertIn('Segment: Chemicals', map_data['filter_context']['active_labels'])
        self.assertIn('Site/rail confidence: Unspecified', map_data['filter_context']['active_labels'])
        self.assertEqual([play['territory'] for play in map_data['territory_plays']], ['TX'])
        self.assertEqual([detail['company'] for detail in map_data['territory_plays'][0]['company_details']], ['Acme Chemicals'])
        self.assertEqual([detail['site_name'] for detail in map_data['territory_plays'][0]['site_details']], ['Houston Rail Park'])

        with self.app.test_request_context('/map?commodity=chemicals&node_type=company&node_type=site'):
            commodity_map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': '',
                    'segment': '',
                    'commodity': 'chemicals',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['company', 'site'],
                },
                review_store_path=self.review_store_path,
            )

        commodity_labels = {marker['label'] for marker in commodity_map_data['markers']}
        self.assertIn('Acme Chemicals', commodity_labels)
        self.assertIn('Houston Rail Park', commodity_labels)
        self.assertNotIn('Front Range Logistics', commodity_labels)
        self.assertNotIn('Denver Industrial Yard', commodity_labels)
        self.assertIn('Commodity: chemicals', commodity_map_data['filter_context']['active_labels'])

    def test_opportunity_map_confidence_filter_keeps_companies_without_confidence(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        confident_sites = [
            {**site, 'source_confidence': 'High' if site['site_name'] == 'Houston Rail Park' else 'Medium'}
            for site in sites
        ]
        confident_rail = [
            {**rail, 'source_confidence': 'High' if rail['location'] == 'Houston Hub' else 'Medium'}
            for rail in rail_infrastructure
        ]

        with self.app.test_request_context('/map?source_confidence=High&node_type=company&node_type=site&node_type=rail'):
            map_data = build_opportunity_map(
                companies,
                confident_sites,
                confident_rail,
                {
                    'query': '',
                    'state': '',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': 'High',
                    'supply_chain': '',
                    'node_types': ['company', 'site', 'rail'],
                },
                review_store_path=self.review_store_path,
            )

        labels = {marker['label'] for marker in map_data['markers']}
        self.assertIn('Acme Chemicals', labels)
        self.assertIn('Front Range Logistics', labels)
        self.assertIn('Houston Rail Park', labels)
        self.assertIn('Houston Hub', labels)
        self.assertNotIn('Denver Industrial Yard', labels)
        self.assertNotIn('Denver Hub', labels)
        self.assertEqual(map_data['type_counts']['company'], 2)
        self.assertEqual(map_data['type_counts']['site'], 1)
        self.assertEqual(map_data['type_counts']['rail'], 1)

    def test_opportunity_map_readiness_filter_uses_persisted_review_status(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        reviewable_sites = [
            {
                **site,
                'acres': site.get('acres') or '75',
                'source_url': 'https://example.com/site',
                'source_confidence': 'High',
                'last_verified': '2026-05-09',
                'data_gap_notes': '',
            }
            for site in sites
        ]
        save_review_store(self.review_store_path, {
            'Houston Rail Park': build_review_update(
                {},
                'blocked',
                notes='Blocked until the site owner confirms availability.',
            ),
        })

        with self.app.test_request_context('/map?site_readiness=Blocked%20By%20Data%20Gaps&node_type=site'):
            map_data = build_opportunity_map(
                companies,
                reviewable_sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': '',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': 'Blocked By Data Gaps',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['site'],
                },
                review_store_path=self.review_store_path,
            )
            filter_options = build_map_filter_options(
                companies,
                reviewable_sites,
                [],
                rail_infrastructure=rail_infrastructure,
                review_store_path=self.review_store_path,
            )

        labels = {marker['label'] for marker in map_data['markers']}
        self.assertEqual(labels, {'Houston Rail Park'})
        self.assertEqual(map_data['type_counts']['site'], 1)
        self.assertIn('Site readiness: Blocked By Data Gaps', map_data['filter_context']['active_labels'])
        self.assertTrue(any(
            detail.endswith('(Blocked By Data Gaps)')
            for detail in map_data['markers'][0]['details']
        ))
        self.assertIn('Blocked By Data Gaps', filter_options['site_readinesses'])

    def test_opportunity_map_layer_selection_controls_counts_and_state_shading(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        with self.app.test_request_context('/map?node_type=site'):
            site_map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': '',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['site'],
                },
                review_store_path=self.review_store_path,
            )

        self.assertEqual(site_map_data['type_counts']['company'], 0)
        self.assertEqual(site_map_data['type_counts']['site'], 2)
        self.assertEqual(site_map_data['summary']['companies'], 0)
        self.assertEqual(site_map_data['summary']['sites'], 2)
        self.assertEqual(site_map_data['summary']['high_priority'], 0)
        self.assertEqual(site_map_data['summary']['states'], 2)
        self.assertTrue(all(profile['companies'] == 0 for profile in site_map_data['state_profiles'].values()))
        self.assertTrue(all(profile['top_score'] > 0 for profile in site_map_data['state_profiles'].values()))
        self.assertIn('Layers: sites', site_map_data['filter_context']['active_labels'])

        with self.app.test_request_context('/map?node_type=company'):
            company_map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': '',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['company'],
                },
                review_store_path=self.review_store_path,
            )

        self.assertEqual(company_map_data['type_counts']['company'], 2)
        self.assertEqual(company_map_data['type_counts']['site'], 0)
        self.assertEqual(company_map_data['summary']['companies'], 2)
        self.assertEqual(company_map_data['summary']['sites'], 0)
        self.assertEqual(company_map_data['summary']['ready_sites'], 0)
        self.assertTrue(all(profile['sites'] == 0 for profile in company_map_data['state_profiles'].values()))
        self.assertIn('Layers: companies', company_map_data['filter_context']['active_labels'])

    def test_opportunity_map_confidence_filter_treats_blank_source_as_unspecified(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        blank_confidence_sites = [
            {**site, 'source_confidence': ''}
            for site in sites
        ]
        blank_confidence_rail = [
            {**rail, 'source_confidence': ''}
            for rail in rail_infrastructure
        ]

        with self.app.test_request_context('/map?source_confidence=Unspecified&node_type=site&node_type=rail'):
            map_data = build_opportunity_map(
                companies,
                blank_confidence_sites,
                blank_confidence_rail,
                {
                    'query': '',
                    'state': '',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': 'Unspecified',
                    'supply_chain': '',
                    'node_types': ['site', 'rail'],
                },
                review_store_path=self.review_store_path,
            )
            filter_options = build_map_filter_options(
                companies,
                blank_confidence_sites,
                [],
                rail_infrastructure=blank_confidence_rail,
                review_store_path=self.review_store_path,
            )

        labels = {marker['label'] for marker in map_data['markers']}
        self.assertIn('Houston Rail Park', labels)
        self.assertIn('Denver Industrial Yard', labels)
        self.assertIn('Houston Hub', labels)
        self.assertIn('Denver Hub', labels)
        self.assertIn('Unspecified', filter_options['source_confidences'])
        self.assertIn('Site/rail confidence: Unspecified', map_data['filter_context']['active_labels'])

    def test_opportunity_map_preserves_intentionally_empty_layer_selection(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        with self.app.test_request_context('/map?layers_submitted=1'):
            filters = get_map_filter_args(request.args)
            map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                filters,
                review_store_path=self.review_store_path,
            )

        self.assertEqual(filters['node_types'], [])
        self.assertEqual(map_data['markers'], [])
        self.assertEqual(map_data['summary']['markers'], 0)
        self.assertEqual(map_data['type_counts']['company'], 0)
        self.assertEqual(map_data['type_counts']['site'], 0)
        self.assertEqual(map_data['territory_plays'], [])
        self.assertIn('Layers: none', map_data['filter_context']['active_labels'])

    def test_opportunity_map_port_context_requires_visible_company_layer(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        with self.app.test_request_context('/map?node_type=site&node_type=port'):
            site_port_map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': '',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['site', 'port'],
                },
                review_store_path=self.review_store_path,
            )

        self.assertEqual(site_port_map_data['type_counts']['site'], 2)
        self.assertEqual(site_port_map_data['type_counts']['port'], 0)

        with self.app.test_request_context('/map?node_type=company&node_type=port'):
            company_port_map_data = build_opportunity_map(
                companies,
                sites,
                rail_infrastructure,
                {
                    'query': '',
                    'state': '',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['company', 'port'],
                },
                review_store_path=self.review_store_path,
            )

        self.assertEqual(company_port_map_data['type_counts']['company'], 2)
        self.assertGreater(company_port_map_data['type_counts']['port'], 0)

    def test_opportunity_map_route_shows_filters_markers_and_workflow_links(self):
        response = self.client.get('/map?state=TX&segment=Chemicals&commodity=chemicals&min_score=1')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('<h1>Map</h1>', body)
        self.assertNotIn('Opportunity Map', body)
        self.assertIn('Filters', body)
        self.assertIn('Layers', body)
        self.assertIn('Action Plan', body)
        self.assertIn('Best territory plays from the current map view.', body)
        self.assertIn('<details class="territory-play">', body)
        self.assertIn('Top companies', body)
        self.assertIn('Site readiness', body)
        self.assertIn('Watch:', body)
        self.assertIn('Primary: Review Site', body)
        self.assertIn('Focus company', body)
        self.assertIn('Insights', body)
        self.assertIn('Top mapped opportunities', body)
        self.assertIn('Inspect', body)
        self.assertIn('Filtered Result', body)
        self.assertIn('Fit Results', body)
        self.assertIn('Cluster', body)
        self.assertIn('Acme Chemicals', body)
        self.assertIn('Houston Rail Park', body)
        self.assertNotIn('Houston Hub', body)
        self.assertIn('Supply chain', body)
        self.assertIn('Site/rail confidence', body)
        self.assertIn('Min site fit', body)
        self.assertIn('Rail context', body)
        self.assertIn('/companies/Acme%20Chemicals/site-comparison', body)
        self.assertIn('/workspace?company=Acme+Chemicals', body)
        self.assertIn('Review Site', body)
        self.assertIn('site=Houston+Rail+Park', body)

    def test_home_renders_command_center(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Command Center', body)
        self.assertIn('Daily Workbench', body)

    def test_opportunity_map_apply_filters_query_changes_result_summary(self):
        response = self.client.get('/map?layers_submitted=1&state=TX&node_type=company&node_type=site')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('State: TX', body)
        self.assertIn('2 mapped nodes across 1 states', body)
        self.assertIn('Visible layers show 1 company markers and 1 site markers', body)
        self.assertIn('Coverage: 1 of 1 filtered companies mapped, and 1 of 1 filtered sites mapped.', body)
        self.assertIn('value="TX" selected', body)
        self.assertIn('value="company" checked', body)
        self.assertIn('value="site" checked', body)
        self.assertNotIn('Front Range Logistics', body)

    def test_opportunity_map_route_empty_action_plan_renders_helpful_state(self):
        response = self.client.get('/map?layers_submitted=1')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('No action plan yet.', body)
        self.assertIn('Turn on company or site layers, or broaden filters, to see territory plays.', body)

    def test_company_detail_page_shows_priority_site_and_next_action(self):
        response = self.client.get('/companies/Acme%20Chemicals')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Acme Chemicals', body)
        self.assertIn('Priority score', body)
        self.assertIn('Score Breakdown', body)
        self.assertIn('Priority Reasons', body)
        self.assertIn('Houston Rail Park', body)
        self.assertIn('Next Action', body)
        self.assertIn('Company Data Gaps', body)
        self.assertIn('Best site fit', body)
        self.assertIn('/downloads/company/Acme%20Chemicals.json', body)
        self.assertIn('/workspace?company=Acme+Chemicals&amp;site=Houston+Rail+Park', body)
        self.assertIn('/companies/Acme%20Chemicals/site-comparison', body)

    def test_sites_page_and_site_detail_show_compatible_companies(self):
        sites_response = self.client.get('/sites?state=TX&port_access=Yes&transload_available=Yes&source_confidence=Unspecified')
        detail_response = self.client.get('/sites/Houston%20Rail%20Park')

        self.assertEqual(sites_response.status_code, 200)
        self.assertIn('Houston Rail Park', sites_response.get_data(as_text=True))
        self.assertNotIn('Denver Industrial Yard', sites_response.get_data(as_text=True))

        self.assertEqual(detail_response.status_code, 200)
        detail_body = detail_response.get_data(as_text=True)
        self.assertIn('Site Details', detail_body)
        self.assertIn('Top Compatible Companies', detail_body)
        self.assertIn('Review Status', detail_body)
        self.assertIn('Save Review', detail_body)
        self.assertIn('Confirmed', detail_body)
        self.assertIn('Data Confidence', detail_body)
        self.assertIn('Research Checklist', detail_body)
        self.assertIn('Research readiness', detail_body)
        self.assertIn('Verification Tasks', detail_body)
        self.assertIn('Back to Site Verification', detail_body)
        self.assertIn('Check Pipeline', detail_body)
        self.assertIn('Source URL present', detail_body)
        self.assertIn('Source confidence', detail_body)
        self.assertIn('Last verified', detail_body)
        self.assertIn('Data gaps', detail_body)
        self.assertIn('Matched companies', detail_body)
        self.assertIn('Acme Chemicals', detail_body)
        self.assertIn('/downloads/site/Houston%20Rail%20Park.json', detail_body)
        self.assertIn('/workspace?company=Acme+Chemicals&amp;site=Houston+Rail+Park', detail_body)

    def test_site_filters_work_for_state_port_transload_and_confidence(self):
        _, _, sites, _ = self.loaded_data
        directory = merge_review_records(build_site_directory(sites), {})

        filtered = filter_site_directory(directory, {
            'state': 'TX',
            'port_access': 'Yes',
            'transload_available': 'Yes',
            'source_confidence': 'Unspecified',
            'review_status': '',
        })

        self.assertEqual([site['site_name'] for site in filtered], ['Houston Rail Park'])

        confirmation_filtered = filter_site_directory(directory, {
            'query': 'Denver',
            'state': '',
            'port_access': '',
            'transload_available': '',
            'source_confidence': '',
            'needs_confirmation': 'yes',
            'review_status': '',
        })
        self.assertEqual([site['site_name'] for site in confirmation_filtered], ['Denver Industrial Yard'])

        summary = build_site_scan_summary(directory)
        self.assertEqual(summary['needs_confirmation'], 1)
        self.assertEqual(summary['review_queue'], 1)

    def test_research_readiness_builds_tasks_from_existing_site_fields(self):
        _, companies, sites, _ = self.loaded_data
        readiness = build_research_readiness(
            sites[0],
            company=companies[0],
            compatibility_score=85,
        )

        self.assertEqual(readiness['label'], 'Needs Verification')
        self.assertGreater(readiness['score'], 0)
        self.assertIn('Add a current public source URL or internal source trail.', readiness['tasks'])
        self.assertIn('Assign source_confidence as High, Medium, or another explicit confidence level.', readiness['tasks'])
        self.assertTrue(any(
            item['label'] == 'Acreage confirmed' and item['confirmed']
            for item in readiness['checklist']
        ))

    def test_unified_readiness_blocks_high_score_unverified_site(self):
        _, companies, sites, _ = self.loaded_data
        company = {**companies[0], 'priority_score': 95, 'best_site_match_score': 90, 'best_lane_score': 80}
        readiness = build_opportunity_readiness(company, site=sites[0])

        self.assertEqual(readiness['label'], VERIFY_SITE_LABEL)
        self.assertFalse(readiness['actionable'])
        self.assertFalse(readiness['site_ready'])

    def test_unified_readiness_allows_confirmed_research_ready_site(self):
        _, companies, sites, _ = self.loaded_data
        site = {
            **sites[0],
            'source_url': 'https://example.com/site',
            'source_confidence': 'High',
            'last_verified': '2026-05-09',
            'data_gap_notes': '',
            'review_status': 'confirmed',
            'review_notes': 'owner utilities zoning',
        }
        company = {**companies[0], 'priority_score': 95, 'best_site_match_score': 90, 'best_lane_score': 80}
        readiness = build_opportunity_readiness(company, site=site)

        self.assertEqual(readiness['label'], READY_LABEL)
        self.assertTrue(readiness['actionable'])
        self.assertTrue(readiness['site_ready'])

    def test_unified_readiness_requires_confirmed_and_research_ready_site(self):
        _, companies, sites, _ = self.loaded_data
        confirmed_incomplete_site = {
            **sites[0],
            'review_status': 'confirmed',
        }
        company = {**companies[0], 'priority_score': 95, 'best_site_match_score': 90, 'best_lane_score': 80}
        readiness = build_opportunity_readiness(company, site=confirmed_incomplete_site)

        self.assertEqual(readiness['label'], VERIFY_SITE_LABEL)
        self.assertFalse(readiness['actionable'])
        self.assertFalse(readiness['site_ready'])

    def test_opportunity_map_payload_reports_unmapped_records(self):
        _, companies, sites, rail_infrastructure = self.loaded_data
        unmapped_company = {
            **companies[0],
            'company': 'Remote Unknown Works',
            'city': 'No Such City',
            'state': 'ZZ',
            'latitude': '',
            'longitude': '',
        }
        unmapped_site = {
            **sites[0],
            'site_name': 'Unmapped Industrial Site',
            'city': 'No Such City',
            'state': 'ZZ',
            'latitude': '',
            'longitude': '',
        }

        with self.app.test_request_context('/map?state=ZZ&node_type=company&node_type=site'):
            map_data = build_opportunity_map(
                [unmapped_company],
                [unmapped_site],
                rail_infrastructure,
                {
                    'query': '',
                    'state': 'ZZ',
                    'segment': '',
                    'commodity': '',
                    'min_score': None,
                    'min_site_fit': None,
                    'site_readiness': '',
                    'source_confidence': '',
                    'supply_chain': '',
                    'node_types': ['company', 'site'],
                },
                review_store_path=self.review_store_path,
            )

        self.assertEqual(map_data['summary']['unmapped_companies'], 1)
        self.assertEqual(map_data['summary']['unmapped_sites'], 1)
        self.assertEqual(map_data['summary']['unmapped_nodes'], 2)
        self.assertEqual(map_data['markers'], [])

    def test_default_review_status_derives_from_confirmation_flag(self):
        _, _, sites, _ = self.loaded_data
        directory = merge_review_records(build_site_directory(sites), {})
        statuses = {site['site_name']: site['review_status'] for site in directory}

        self.assertEqual(statuses['Houston Rail Park'], 'confirmed')
        self.assertEqual(statuses['Denver Industrial Yard'], 'needs_review')

    def test_review_store_load_save_and_malformed_fallback(self):
        record = build_review_update(
            {},
            'in_review',
            notes='Confirm acreage with county source.',
            reviewed_by='Alex',
            source_update_url='https://example.com/source',
            reviewed_at='2026-05-09T20:00:00',
            owner_contact='City economic development contact listed.',
            utilities='Electric, water, sewer available per listing.',
            zoning_entitlement='Industrial use permitted.',
        )
        saved = save_review_store(self.review_store_path, {'Denver Industrial Yard': record})
        loaded = load_review_store(self.review_store_path)

        self.assertEqual(saved, loaded)
        self.assertEqual(loaded['Denver Industrial Yard']['review_status'], 'in_review')
        self.assertEqual(loaded['Denver Industrial Yard']['reviewed_by'], 'Alex')
        self.assertEqual(loaded['Denver Industrial Yard']['owner_contact'], 'City economic development contact listed.')
        self.assertEqual(loaded['Denver Industrial Yard']['utilities'], 'Electric, water, sewer available per listing.')
        self.assertEqual(loaded['Denver Industrial Yard']['zoning_entitlement'], 'Industrial use permitted.')

        with open(self.review_store_path, 'w') as review_file:
            review_file.write('{not-json')

        self.assertEqual(load_review_store(self.review_store_path), {})

    def test_sites_page_filters_by_review_status(self):
        save_review_store(self.review_store_path, {
            'Denver Industrial Yard': build_review_update(
                {},
                'blocked',
                notes='Waiting on parcel control source.',
                reviewed_by='Maya',
                reviewed_at='2026-05-09T20:05:00',
            ),
        })

        response = self.client.get('/sites?review_status=blocked')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Denver Industrial Yard', body)
        self.assertIn('Blocked', body)
        self.assertNotIn('Houston Rail Park', body)

    def test_site_review_update_route_persists_and_redirects(self):
        response = self.client.post('/sites/Denver%20Industrial%20Yard/review', data={
            'review_status': 'confirmed',
            'review_notes': 'Acreage, owner contact, utilities, and zoning confirmed from public listing.',
            'reviewed_by': 'Jordan',
            'source_update_url': 'https://example.com/denver-yard',
            'source_confidence': 'High',
            'last_verified': '2026-05-19',
            'acres': '75',
            'rail_served': 'Yes',
            'nearby_class1': 'Yes',
            'transload_available': 'No',
            'interstate_access': 'Yes',
            'port_access': 'No',
            'data_gap_notes': '',
            'owner_contact': 'Broker listed on public site sheet.',
            'utilities': 'Power, water, and sewer shown as available.',
            'zoning_entitlement': 'Industrial zoning shown as permitted use.',
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn('/sites/Denver%20Industrial%20Yard', response.headers['Location'])

        loaded = load_review_store(self.review_store_path)
        self.assertEqual(loaded['Denver Industrial Yard']['review_status'], 'confirmed')
        self.assertEqual(loaded['Denver Industrial Yard']['reviewed_by'], 'Jordan')
        self.assertEqual(loaded['Denver Industrial Yard']['source_confidence'], 'High')
        self.assertEqual(loaded['Denver Industrial Yard']['last_verified'], '2026-05-19')
        self.assertEqual(loaded['Denver Industrial Yard']['acres'], '75')
        self.assertTrue(loaded['Denver Industrial Yard']['reviewed_at'])

        _, _, sites, _ = self.loaded_data
        reviewed_sites = merge_review_records(build_site_directory(sites), loaded)
        denver_site = next(site for site in reviewed_sites if site['site_name'] == 'Denver Industrial Yard')
        self.assertEqual(denver_site['research_readiness']['label'], 'Research Ready')
        self.assertFalse(denver_site['research_readiness']['tasks'])

        detail_response = self.client.get('/sites/Denver%20Industrial%20Yard')
        detail_body = detail_response.get_data(as_text=True)
        self.assertIn('Acreage, owner contact, utilities, and zoning confirmed from public listing.', detail_body)
        self.assertIn('Broker listed on public site sheet.', detail_body)
        self.assertIn('Power, water, and sewer shown as available.', detail_body)
        self.assertIn('Industrial zoning shown as permitted use.', detail_body)
        self.assertIn('Jordan', detail_body)
        self.assertIn('Research Ready', detail_body)
        self.assertIn('Ready to use', detail_body)

    def test_site_review_save_redirect_shows_practical_feedback(self):
        response = self.client.post('/sites/Houston%20Rail%20Park/review', data={
            'review_status': 'confirmed',
            'review_notes': 'Source URL checked but date and confidence still need a second pass.',
            'reviewed_by': 'Jordan',
            'source_update_url': 'https://example.com/houston-rail-park',
            'source_confidence': '',
            'last_verified': '',
            'acres': '250',
            'rail_served': 'Yes',
            'nearby_class1': 'Yes',
            'transload_available': 'Yes',
            'interstate_access': 'Yes',
            'port_access': 'Yes',
            'data_gap_notes': '',
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Review saved for Houston Rail Park', body)
        self.assertIn('Status: Confirmed', body)
        self.assertIn('Research readiness: Needs Verification', body)
        self.assertIn('Remaining blocker count: 2', body)
        self.assertIn('not usable for outreach yet', body)
        self.assertIn('Review saved, but outreach is still blocked', body)
        self.assertIn('data/review_status.json', body)
        self.assertIn('Review Saved: Next Step', body)
        self.assertIn('Continue Site Verification', body)
        self.assertIn('Check Pipeline', body)

    def test_verified_site_updates_pipeline_stage_and_exports(self):
        response = self.client.post('/sites/Houston%20Rail%20Park/review', data={
            'review_status': 'confirmed',
            'review_notes': 'Owner contact, utilities, and zoning confirmed for outreach.',
            'reviewed_by': 'Jordan',
            'source_update_url': 'https://example.com/houston-rail-park',
            'source_confidence': 'High',
            'last_verified': '2026-05-19',
            'acres': '250',
            'rail_served': 'Yes',
            'nearby_class1': 'Yes',
            'transload_available': 'Yes',
            'interstate_access': 'Yes',
            'port_access': 'Yes',
            'data_gap_notes': '',
        })
        self.assertEqual(response.status_code, 302)

        _, companies, sites, _ = self.loaded_data
        with self.app.test_request_context('/pipeline'):
            pipeline = build_opportunity_pipeline(
                companies,
                sites,
                review_store_path=self.review_store_path,
            )

        ready_stage = next(stage for stage in pipeline['stages'] if stage['label'] == 'Outreach ready')
        ready_items = {item['company']: item for item in ready_stage['items']}
        self.assertIn('Acme Chemicals', ready_items)
        self.assertEqual(ready_items['Acme Chemicals']['primary_action']['label'], 'Open Workspace')

        with self.app.test_request_context('/verification'):
            verification = build_verification_queue(
                sites,
                companies,
                review_store_path=self.review_store_path,
            )
        self.assertNotIn(
            'Houston Rail Park',
            {item['site_name'] for item in verification['items']},
        )

        detail_response = self.client.get('/sites/Houston%20Rail%20Park?review_saved=1')
        detail_body = detail_response.get_data(as_text=True)
        self.assertIn('Research Ready: this site now flows downstream.', detail_body)
        self.assertIn('Unlocked Opportunities', detail_body)
        self.assertIn('Open Workspace', detail_body)
        self.assertIn('/workspace?company=Acme+Chemicals&amp;site=Houston+Rail+Park', detail_body)

        workspace_response = self.client.get('/downloads/workspace.json?company=Acme%20Chemicals&site=Houston%20Rail%20Park')
        try:
            self.assertEqual(workspace_response.status_code, 200)
            workspace_body = workspace_response.get_data(as_text=True)
            self.assertIn('"label": "Research Ready"', workspace_body)
            self.assertIn('"verification_tasks": []', workspace_body)
        finally:
            detail_response.close()
            workspace_response.close()

    def test_confirmed_but_incomplete_site_remains_in_verification_queue_with_blockers(self):
        response = self.client.post('/sites/Houston%20Rail%20Park/review', data={
            'review_status': 'confirmed',
            'review_notes': 'Source URL checked but confidence and verification date are still open.',
            'reviewed_by': 'Jordan',
            'source_update_url': 'https://example.com/houston-rail-park',
            'source_confidence': '',
            'last_verified': '',
            'acres': '250',
            'rail_served': 'Yes',
            'nearby_class1': 'Yes',
            'transload_available': 'Yes',
            'interstate_access': 'Yes',
            'port_access': 'Yes',
            'data_gap_notes': '',
        })
        self.assertEqual(response.status_code, 302)

        _, companies, sites, _ = self.loaded_data
        with self.app.test_request_context('/verification'):
            verification = build_verification_queue(
                sites,
                companies,
                review_store_path=self.review_store_path,
            )

        houston = next(item for item in verification['items'] if item['site_name'] == 'Houston Rail Park')
        self.assertEqual(houston['review_status_label'], 'Confirmed')
        self.assertEqual(houston['readiness']['label'], 'Needs Verification')
        self.assertEqual(houston['blocked_count'], 2)
        self.assertIn('Review saved, but outreach is still blocked by 2 blockers.', houston['queue_note'])
        self.assertTrue(any('last_verified' in task for task in houston['tasks']))
        self.assertTrue(any('source_confidence' in task for task in houston['tasks']))

        queue_response = self.client.get('/verification')
        queue_body = queue_response.get_data(as_text=True)
        self.assertIn('Confirmed', queue_body)
        self.assertIn('Review saved, but outreach is still blocked by 2 blockers.', queue_body)

    def test_verification_queue_prioritizes_blocked_records_above_incomplete_records(self):
        _, companies, sites, _ = self.loaded_data
        save_review_store(self.review_store_path, {
            'Denver Industrial Yard': build_review_update(
                {},
                'blocked',
                notes='Owner and acreage are blocked pending local follow-up.',
                source_update_url='https://example.com/denver-yard',
                source_confidence='Medium',
                last_verified='2026-05-19',
                acres='',
                rail_served='Yes',
                nearby_class1='Yes',
                transload_available='No',
                interstate_access='Yes',
                port_access='No',
                data_gap_notes='Owner will not confirm available acreage.',
            ),
            'Houston Rail Park': build_review_update(
                {},
                'in_review',
                source_update_url='https://example.com/houston-rail-park',
                source_confidence='',
                last_verified='',
                acres='250',
                rail_served='Yes',
                nearby_class1='Yes',
                transload_available='Yes',
                interstate_access='Yes',
                port_access='Yes',
                data_gap_notes='',
            ),
        })

        with self.app.test_request_context('/verification'):
            verification = build_verification_queue(
                sites,
                companies,
                review_store_path=self.review_store_path,
            )

        self.assertEqual(verification['items'][0]['site_name'], 'Denver Industrial Yard')
        self.assertTrue(verification['items'][0]['is_blocked'])
        self.assertEqual(verification['items'][1]['site_name'], 'Houston Rail Park')
        self.assertFalse(verification['items'][1]['is_blocked'])

    def test_site_review_update_validates_site_and_status(self):
        missing_response = self.client.post('/sites/Not%20A%20Site/review', data={
            'review_status': 'confirmed',
        })
        bad_status_response = self.client.post('/sites/Denver%20Industrial%20Yard/review', data={
            'review_status': 'done-ish',
        })

        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(bad_status_response.status_code, 400)

    def test_opportunity_workspace_payload_uses_selected_pair(self):
        segments, companies, sites, _ = self.loaded_data
        workspace = build_opportunity_workspace(companies[0], sites[0], segments)

        self.assertEqual(workspace['company']['company'], 'Acme Chemicals')
        self.assertEqual(workspace['site']['site_name'], 'Houston Rail Park')
        self.assertIn('score', workspace['priority'])
        self.assertIn('breakdown', workspace['priority'])
        self.assertGreaterEqual(len(workspace['priority']['reasons']), 1)
        self.assertGreater(workspace['site_match']['compatibility_score'], 0)
        self.assertIn('lane', workspace)
        self.assertIn('research_readiness', workspace)
        self.assertIn('opportunity_readiness', workspace)
        self.assertEqual(workspace['opportunity_readiness']['label'], VERIFY_SITE_LABEL)
        self.assertEqual(workspace['external_use']['status'], 'Hold for verification')
        self.assertTrue(workspace['external_use']['human_review_required'])
        self.assertFalse(workspace['external_use']['outreach_usable'])
        self.assertIn('verification_tasks', workspace)
        self.assertGreater(workspace['lane']['lane_score'], 0)
        self.assertGreaterEqual(len(workspace['lane']['lane_reasons']), 1)
        self.assertGreaterEqual(len(workspace['site_match']['matching_reasons']), 1)
        self.assertGreaterEqual(len(workspace['talking_points']), 1)
        self.assertGreaterEqual(len(workspace['risks_or_data_gaps']), 1)

    def test_workspace_external_use_guardrail_blocks_speculative_ready_records(self):
        segments, companies, sites, _ = self.loaded_data
        company = companies[0].copy()
        company['why_target'] = 'Speculative prospect until a live expansion project is confirmed.'
        site = sites[0].copy()
        site.update({
            'review_status': 'confirmed',
            'source_url': 'https://example.com/houston-rail-park',
            'source_confidence': 'High',
            'last_verified': '2026-05-09',
            'owner_contact': 'Economic development contact confirmed',
            'utilities': 'Utilities confirmed',
            'zoning_entitlement': 'Industrial zoning confirmed',
            'data_gap_notes': '',
        })

        workspace = build_opportunity_workspace(company, site, segments)

        self.assertEqual(workspace['research_readiness']['label'], 'Research Ready')
        self.assertEqual(workspace['external_use']['status'], 'Internal review first')
        self.assertTrue(workspace['external_use']['human_review_required'])
        self.assertFalse(workspace['external_use']['outreach_usable'])

    def test_company_site_comparison_payload_ranks_sites_and_recommends_first_choice(self):
        segments, companies, sites, _ = self.loaded_data
        comparison = build_company_site_comparison(companies[0], sites, segments, limit=2)

        self.assertEqual(comparison['company']['company'], 'Acme Chemicals')
        self.assertEqual(comparison['priority']['score'], companies[0]['priority_score'])
        self.assertEqual(len(comparison['compared_sites']), 2)
        self.assertEqual(comparison['compared_sites'][0]['site']['site_name'], 'Houston Rail Park')
        self.assertGreaterEqual(
            comparison['compared_sites'][0]['compatibility_score'],
            comparison['compared_sites'][1]['compatibility_score'],
        )
        self.assertEqual(comparison['recommended_first_choice']['site_name'], 'Houston Rail Park')
        self.assertGreater(comparison['recommended_first_choice']['lane_score'], 0)
        self.assertIn('lane_readiness_label', comparison['recommended_first_choice'])
        self.assertIn('research_readiness_label', comparison['recommended_first_choice'])
        self.assertIn('next_action', comparison['recommended_first_choice'])
        self.assertIn('reason', comparison['recommended_first_choice'])
        self.assertIn('blocked_count', comparison['recommended_first_choice'])
        self.assertIn('verification_tasks', comparison['recommended_first_choice'])
        self.assertIn('research_readiness', comparison['compared_sites'][0])
        self.assertIn('opportunity_readiness', comparison['compared_sites'][0])
        self.assertIn('actionable', comparison['compared_sites'][0])
        self.assertIn('readiness_label', comparison['recommended_first_choice'])
        self.assertIn('verification_tasks', comparison['compared_sites'][0])
        self.assertIn('lane_reasons', comparison['compared_sites'][0])
        self.assertGreaterEqual(len(comparison['recommended_first_choice']['why']), 1)
        self.assertGreaterEqual(len(comparison['compared_sites'][0]['risks_or_confirmation_items']), 1)

    def test_company_site_comparison_page_shows_decision_table_and_workspace_links(self):
        response = self.client.get('/companies/Acme%20Chemicals/site-comparison')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Company Site Comparison', body)
        self.assertIn('Recommended first-choice site', body)
        self.assertIn('Houston Rail Park', body)
        self.assertIn('Denver Industrial Yard', body)
        self.assertIn('Target Industries', body)
        self.assertIn('Lane', body)
        self.assertIn('Research', body)
        self.assertIn('Readiness', body)
        self.assertIn('Opportunity readiness', body)
        self.assertIn('Research readiness', body)
        self.assertIn('Next action:', body)
        self.assertIn('What blocks it:', body)
        self.assertIn('Strong lane', body)
        self.assertIn('Risks / Confirm', body)
        self.assertIn('/workspace?company=Acme+Chemicals&amp;site=Houston+Rail+Park', body)
        self.assertIn('/downloads/company-site-comparison/Acme%20Chemicals.json?limit=5', body)
        self.assertIn('/downloads/company-site-comparison/Acme%20Chemicals.csv?limit=5', body)

    def test_supply_chain_definitions_have_required_visual_flow_structure(self):
        self.assertGreaterEqual(len(SUPPLY_CHAIN_DEFINITIONS), 10)
        required_slugs = {
            'pellets',
            'steel',
            'chemicals',
            'agriculture',
            'automotive',
            'construction-materials',
            'energy',
            'forest-products',
            'food-cold-storage',
            'machinery',
            'plastics-resins',
            'warehousing-distribution',
        }
        self.assertTrue(required_slugs.issubset({chain['slug'] for chain in SUPPLY_CHAIN_DEFINITIONS}))

        for chain in SUPPLY_CHAIN_DEFINITIONS:
            self.assertTrue(chain['name'])
            self.assertTrue(chain['summary'])
            self.assertGreaterEqual(len(chain['steps']), 4)
            for step in chain['steps']:
                self.assertIn(step['role'], {
                    'Upstream inputs',
                    'Processing',
                    'Storage / transload',
                    'Downstream customers',
                })
                self.assertTrue(step['title'])
                self.assertTrue(step['terms'])
                self.assertTrue(step['opportunity'])

    def test_supply_chain_catalog_matches_companies_and_supports_filters(self):
        _, companies, _, _ = self.loaded_data
        catalog = build_supply_chain_catalog(companies)
        chemicals = next(chain for chain in catalog if chain['slug'] == 'chemicals')
        warehousing = next(chain for chain in catalog if chain['slug'] == 'warehousing-distribution')

        self.assertGreaterEqual(len(catalog), 10)
        self.assertEqual(chemicals['count'], 1)
        self.assertEqual(chemicals['top_companies'][0]['company'], 'Acme Chemicals')
        self.assertEqual(chemicals['top_companies'][0]['opportunity_label'], 'Strong rail prospect')
        self.assertEqual(chemicals['top_companies'][0]['readiness_label'], 'Verify site first')
        self.assertEqual(chemicals['ready_count'], 0)
        self.assertEqual(chemicals['site_review_count'], 1)
        self.assertEqual(warehousing['top_companies'][0]['company'], 'Front Range Logistics')

        filtered = filter_supply_chains(
            catalog,
            group='Chemicals',
            query='industrial gases',
            opportunity='Strong rail prospect',
            readiness='Verify site first',
            min_priority=1,
            sort='ready',
        )
        self.assertEqual([chain['slug'] for chain in filtered], ['chemicals'])

        summary = build_supply_chain_scan_summary([chemicals, warehousing])
        self.assertEqual(summary['chain_count'], 2)
        self.assertEqual(summary['company_matches'], 2)
        self.assertEqual(summary['strong_prospects'], 1)
        self.assertEqual(summary['ready_for_outreach'], 0)

        options = build_supply_chain_filter_options(catalog)
        self.assertIn('Chemicals', options['groups'])
        self.assertIn('Ready for outreach', options['readinesses'])
        self.assertIn({'value': 'ready', 'label': 'Ready for outreach'}, options['sorts'])

    def test_supply_chain_detail_assigns_step_company_matches(self):
        _, companies, _, _ = self.loaded_data
        detail = build_supply_chain_detail('chemicals', companies)

        self.assertEqual(detail['name'], 'Chemicals')
        self.assertEqual(detail['companies'][0]['company'], 'Acme Chemicals')
        self.assertEqual(len(detail['steps']), 4)
        self.assertEqual(detail['action_queue'][0]['company'], 'Acme Chemicals')
        self.assertIn('Compare industrial sites', detail['action_queue'][0]['recommended_action'])
        self.assertTrue(any(
            company['company'] == 'Acme Chemicals'
            for step in detail['steps']
            for company in step['companies']
        ))

    def test_supply_chains_routes_render_catalog_and_detail_workflow_links(self):
        catalog_response = self.client.get('/supply-chains')
        detail_response = self.client.get('/supply-chains/chemicals')

        self.assertEqual(catalog_response.status_code, 200)
        catalog_body = catalog_response.get_data(as_text=True)
        self.assertIn('Supply Chains', catalog_body)
        self.assertIn('Pellets', catalog_body)
        self.assertIn('Steel', catalog_body)
        self.assertIn('Food / Cold Storage', catalog_body)
        self.assertIn('/supply-chains/chemicals', catalog_body)
        self.assertIn('Strong rail prospects', catalog_body)
        self.assertIn('Ready for outreach', catalog_body)
        self.assertIn('Verify/compare sites', catalog_body)

        self.assertEqual(detail_response.status_code, 200)
        detail_body = detail_response.get_data(as_text=True)
        self.assertIn('Action Queue', detail_body)
        self.assertIn('Visual Flow', detail_body)
        self.assertIn('Upstream inputs', detail_body)
        self.assertIn('Processing', detail_body)
        self.assertIn('Storage / transload', detail_body)
        self.assertIn('Downstream customers', detail_body)
        self.assertIn('Rail-service possible', detail_body)
        self.assertIn('Strong rail prospect', detail_body)
        self.assertIn('Ready for outreach', detail_body)
        self.assertIn('Compare industrial sites', detail_body)
        self.assertIn('Acme Chemicals', detail_body)
        self.assertIn('/companies/Acme%20Chemicals', detail_body)
        self.assertIn('/companies/Acme%20Chemicals/site-comparison', detail_body)
        self.assertIn('/workspace?company=Acme+Chemicals&amp;site=Houston+Rail+Park', detail_body)

    def test_supply_chains_route_filters_group_search_readiness_and_sort(self):
        response = self.client.get('/supply-chains?group=Chemicals&q=industrial%20gases&opportunity=Strong%20rail%20prospect&readiness=Verify%20site%20first&min_priority=1&sort=ready')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Chemicals</a>', body)
        self.assertNotIn('Steel</a>', body)
        self.assertIn('value="ready" selected', body)

    def test_opportunity_workspace_page_shows_action_context(self):
        response = self.client.get('/workspace?company=Acme%20Chemicals&site=Houston%20Rail%20Park')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Opportunity Workspace', body)
        self.assertIn('Decision Snapshot', body)
        self.assertIn('Acme Chemicals', body)
        self.assertIn('Houston Rail Park', body)
        self.assertIn('Why This Pair Fits', body)
        self.assertIn('Lane Readiness', body)
        self.assertIn('Research Checklist', body)
        self.assertIn('Research readiness', body)
        self.assertIn('Opportunity readiness', body)
        self.assertIn('External use', body)
        self.assertIn('External Use Guardrail', body)
        self.assertIn('Ready for outreach means ready to prepare the conversation', body)
        self.assertIn('Verification Tasks', body)
        self.assertIn('Strong lane', body)
        self.assertIn('Talking Points', body)
        self.assertIn('Risks And Data Gaps', body)
        self.assertIn('Qualification Checklist', body)
        self.assertIn('Material volumes', body)
        self.assertIn('estimated annual volume', body)
        self.assertIn('Lane fit', body)
        self.assertIn('Site requirements', body)
        self.assertIn('/downloads/workspace.json?company=Acme+Chemicals&amp;site=Houston+Rail+Park', body)
        self.assertIn('/workspace/brief?company=Acme+Chemicals&amp;site=Houston+Rail+Park', body)
        self.assertIn('/companies/Acme%20Chemicals/site-comparison', body)

    def test_workspace_export_brief_preview_confirms_file_and_next_action_context(self):
        response = self.client.get('/workspace/brief?company=Acme%20Chemicals&site=Houston%20Rail%20Park')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Outreach Handoff', body)
        self.assertIn('Outreach Brief', body)
        self.assertIn('What This Is For', body)
        self.assertIn('Executive Summary', body)
        self.assertIn('Decision Gates', body)
        self.assertIn('Brief Highlights', body)
        self.assertIn('Before External Use', body)
        self.assertIn('Evidence Snapshot', body)
        self.assertIn('Questions To Answer', body)
        self.assertIn('Full TXT Preview', body)
        self.assertIn('Download TXT', body)
        self.assertIn('Acme Chemicals', body)
        self.assertIn('Houston Rail Park', body)
        self.assertIn('Hold for verification', body)
        self.assertIn('Verify site first', body)
        self.assertIn('Needs Verification', body)
        self.assertIn('Resolve before outreach', body)
        self.assertIn('External use', body)
        self.assertIn('Source confidence', body)
        self.assertIn('Confirm contact target', body)
        self.assertIn('What annual inbound and outbound volumes are realistic', body)
        self.assertIn('Material volumes', body)
        self.assertIn('Talking Points', body)
        self.assertIn('Review Site', body)
        exported_files = os.listdir(os.path.join(self.tempdir.name, 'exports'))
        self.assertTrue(any(name.startswith('opportunity_brief_acme_chemicals_houston_rail_park') for name in exported_files))

    def test_command_center_pipeline_and_verification_pages_render_workflow(self):
        responses = [
            self.client.get('/'),
            self.client.get('/pipeline'),
            self.client.get('/verification'),
        ]
        try:
            self.assertEqual([response.status_code for response in responses], [200, 200, 200])
            center_body = responses[0].get_data(as_text=True)
            self.assertIn('Command Center', center_body)
            self.assertIn('What To Do Today', center_body)
            self.assertIn('Export Packet', center_body)
            self.assertIn('Today: site verification', center_body)
            self.assertIn('Use Pipeline for stage management and Site Verification for the full cleanup list.', center_body)
            self.assertNotIn('<h2>Verification Queue</h2>', center_body)

            pipeline_body = responses[1].get_data(as_text=True)
            self.assertIn('Opportunity Pipeline', pipeline_body)
            self.assertIn('Site verification', pipeline_body)
            self.assertIn('Acme Chemicals', pipeline_body)
            self.assertIn('Why this stage:', pipeline_body)
            self.assertIn('External use:', pipeline_body)
            self.assertIn('To advance:', pipeline_body)
            self.assertIn('name="readiness"', pipeline_body)
            self.assertIn('Apply Filters', pipeline_body)

            verification_body = responses[2].get_data(as_text=True)
            self.assertIn('Site Verification', verification_body)
            self.assertIn('Houston Rail Park', verification_body)
            self.assertIn('Top Blocker', verification_body)
            self.assertIn('Outreach Unlock', verification_body)
        finally:
            for response in responses:
                response.close()

    def test_operating_layer_helpers_build_action_queues(self):
        _, companies, sites, rail_infrastructure = self.loaded_data

        with self.app.test_request_context('/'):
            pipeline = build_opportunity_pipeline(
                companies,
                sites,
                review_store_path=self.review_store_path,
            )
            verification = build_verification_queue(
                sites,
                companies,
                review_store_path=self.review_store_path,
            )
            center = build_command_center(
                companies,
                sites,
                rail_infrastructure,
                review_store_path=self.review_store_path,
            )

        self.assertEqual(pipeline['total'], 2)
        self.assertGreaterEqual(pipeline['summary']['site_verification'], 1)
        self.assertGreaterEqual(verification['total'], 1)
        self.assertTrue(center['today_work'])
        action_urls = [item['primary_action']['url'] for item in center['today_work']]
        self.assertEqual(len(action_urls), len(set(action_urls)))
        self.assertTrue(all(item['why'] for item in center['today_work']))
        self.assertIn('saved_views', center)
        self.assertIn('verification', center)

    def test_pipeline_filters_companies_by_stage_inputs(self):
        _, companies, sites, _ = self.loaded_data

        with self.app.test_request_context('/pipeline?state=TX&min_score=70'):
            pipeline = build_opportunity_pipeline(
                companies,
                sites,
                review_store_path=self.review_store_path,
                filters={'state': 'TX', 'min_score': 70},
            )

        self.assertEqual(pipeline['total'], 1)
        self.assertEqual(pipeline['unfiltered_total'], 2)
        stage_companies = [
            item['company']
            for stage in pipeline['stages']
            for item in stage['items']
        ]
        self.assertEqual(stage_companies, ['Acme Chemicals'])

        response = self.client.get('/pipeline?state=TX&min_score=70')
        try:
            body = response.get_data(as_text=True)
            self.assertIn('1 of 2 companies grouped', body)
            self.assertIn('Acme Chemicals', body)
            self.assertNotIn('Front Range Logistics', body)
            self.assertIn('value="70"', body)
        finally:
            response.close()

    def test_pipeline_groups_by_readiness_and_chooses_stage_actions(self):
        _, companies, sites, _ = self.loaded_data
        reviewed_sites = [
            {
                **sites[0],
                'source_url': 'https://example.com/site',
                'source_confidence': 'High',
                'last_verified': '2026-05-09',
                'data_gap_notes': '',
                'review_status': 'confirmed',
                'review_notes': 'owner utilities zoning',
            },
            sites[1],
        ]
        staged_companies = [
            {**companies[0], 'priority_score': 95, 'best_site_match_score': 90, 'best_lane_score': 80},
            {**companies[1], 'best_site_name': '', 'best_recommended_site': ''},
        ]

        with self.app.test_request_context('/pipeline'):
            pipeline = build_opportunity_pipeline(staged_companies, reviewed_sites, limit_per_stage=10)

        stages = {stage['label']: stage for stage in pipeline['stages']}
        ready_item = stages['Outreach ready']['items'][0]
        compare_item = stages['Site selection']['items'][0]

        self.assertEqual(ready_item['primary_action']['label'], 'Open Workspace')
        self.assertEqual(ready_item['readiness_label'], READY_LABEL)
        self.assertIn('Prepare the selected company-site workspace', ready_item['advance_action'])
        self.assertEqual(compare_item['primary_action']['label'], 'Compare Sites')
        self.assertEqual(compare_item['readiness_label'], 'Compare sites')

    def test_site_verification_keeps_confirmed_incomplete_and_sorts_blocked_first(self):
        _, companies, sites, _ = self.loaded_data
        save_review_store(self.review_store_path, {
            'Houston Rail Park': build_review_update(
                {},
                'confirmed',
                notes='Local review saved, but source and date are still missing.',
                acres='250',
                rail_served='Yes',
                nearby_class1='Yes',
                transload_available='Yes',
                interstate_access='Yes',
                port_access='Yes',
            ),
            'Denver Industrial Yard': build_review_update(
                {},
                'blocked',
                notes='Availability blocked until owner confirms acreage.',
            ),
        })

        with self.app.test_request_context('/verification'):
            queue = build_verification_queue(sites, companies, review_store_path=self.review_store_path)

        self.assertEqual(queue['items'][0]['site_name'], 'Denver Industrial Yard')
        houston = next(item for item in queue['items'] if item['site_name'] == 'Houston Rail Park')
        self.assertEqual(houston['review_status_label'], 'Confirmed')
        self.assertGreater(houston['task_count'], 0)
        self.assertIn('Review saved, but outreach is still blocked', houston['queue_note'])
        self.assertTrue(houston['top_blocker'])
        self.assertIn('unlock', houston['unlock_note'])

    def test_site_detail_save_updates_pipeline_verification_workspace_and_exports(self):
        post_response = self.client.post('/sites/Houston%20Rail%20Park/review', data={
            'review_status': 'confirmed',
            'review_notes': 'Confirmed owner, utilities, zoning, and active rail service.',
            'reviewed_by': 'Test User',
            'source_update_url': 'https://example.com/houston-rail-park',
            'source_confidence': 'High',
            'last_verified': '2026-05-09',
            'data_gap_notes': '',
            'acres': '250',
            'rail_served': 'Yes',
            'nearby_class1': 'Yes',
            'transload_available': 'Yes',
            'interstate_access': 'Yes',
            'port_access': 'Yes',
        }, follow_redirects=True)
        self.assertEqual(post_response.status_code, 200)
        self.assertIn('Site is usable for outreach', post_response.get_data(as_text=True))
        post_response.close()

        pipeline_response = self.client.get('/pipeline')
        verification_response = self.client.get('/verification')
        workspace_response = self.client.get('/workspace?company=Acme%20Chemicals&site=Houston%20Rail%20Park')
        export_response = self.client.get('/downloads/workspace.json?company=Acme%20Chemicals&site=Houston%20Rail%20Park')
        try:
            self.assertIn('Ready for outreach', pipeline_response.get_data(as_text=True))
            self.assertNotIn('Houston Rail Park', verification_response.get_data(as_text=True))
            self.assertIn('Research checklist is current for outreach prep.', workspace_response.get_data(as_text=True))
            payload = json.loads(export_response.get_data(as_text=True))
            self.assertEqual(payload['research_readiness']['label'], 'Research Ready')
            self.assertEqual(payload['opportunity_readiness']['label'], READY_LABEL)
            self.assertEqual(payload['external_use']['status'], 'Ready for outreach prep')
            self.assertFalse(payload['external_use']['human_review_required'])
            self.assertTrue(payload['external_use']['outreach_usable'])
            self.assertEqual(payload['verification_tasks'], [])
        finally:
            pipeline_response.close()
            verification_response.close()
            workspace_response.close()
            export_response.close()

    def test_dashboard_download_routes_reuse_export_helpers(self):
        responses = [
            self.client.get('/downloads/top-companies.csv?state=TX&limit=1'),
            self.client.get('/downloads/top-companies.json?state=TX&limit=1'),
            self.client.get('/downloads/company/Acme%20Chemicals.json'),
            self.client.get('/downloads/site/Houston%20Rail%20Park.json'),
            self.client.get('/downloads/opportunity-packet.txt'),
        ]
        try:
            self.assertEqual([response.status_code for response in responses], [200, 200, 200, 200, 200])
            self.assertIn('text/csv', responses[0].content_type)
            self.assertIn('application/json', responses[1].content_type)
            self.assertIn('application/json', responses[2].content_type)
            self.assertIn('application/json', responses[3].content_type)
            self.assertIn('text/plain', responses[4].content_type)
            csv_body = responses[0].get_data(as_text=True)
            self.assertIn('opportunity_readiness_label', csv_body)
            self.assertIn('site_readiness_label', csv_body)
            json_body = responses[1].get_data(as_text=True)
            self.assertIn('opportunity_readiness', json_body)
            self.assertIn('site_profile', json_body)
            site_report_body = responses[3].get_data(as_text=True)
            self.assertIn('review_status', site_report_body)
            self.assertIn('research_readiness', site_report_body)
            packet_body = responses[4].get_data(as_text=True)
            self.assertIn('OmniMapping Opportunity Packet', packet_body)
            self.assertIn('Internal triage artifact', packet_body)
            self.assertIn('Outreach Prep Candidates', packet_body)
        finally:
            for response in responses:
                response.close()

    def test_workspace_download_routes_return_json_and_txt_brief(self):
        responses = [
            self.client.get('/downloads/workspace.json?company=Acme%20Chemicals&site=Houston%20Rail%20Park'),
            self.client.get('/downloads/workspace.txt?company=Acme%20Chemicals&site=Houston%20Rail%20Park'),
        ]
        try:
            self.assertEqual([response.status_code for response in responses], [200, 200])
            self.assertIn('application/json', responses[0].content_type)
            self.assertIn('text/plain', responses[1].content_type)
            self.assertIn('Acme Chemicals', responses[0].get_data(as_text=True))
            brief_body = responses[1].get_data(as_text=True)
            self.assertIn('OPPORTUNITY BRIEF', brief_body)
            self.assertIn('Houston Rail Park', brief_body)
            self.assertIn('REVIEWED READINESS CONTEXT', brief_body)
            self.assertIn('Opportunity readiness: Verify site first', brief_body)
            self.assertIn('Research readiness: Needs Verification', brief_body)
            self.assertIn('Outreach usable: No', brief_body)
            self.assertIn('External use status: Hold for verification', brief_body)
            self.assertIn('Human review required: Yes', brief_body)
            self.assertIn('Verification tasks:', brief_body)
        finally:
            for response in responses:
                response.close()

    def test_company_site_comparison_download_routes_return_json_and_csv(self):
        responses = [
            self.client.get('/downloads/company-site-comparison/Acme%20Chemicals.json?limit=2'),
            self.client.get('/downloads/company-site-comparison/Acme%20Chemicals.csv?limit=2'),
        ]
        try:
            self.assertEqual([response.status_code for response in responses], [200, 200])
            self.assertIn('application/json', responses[0].content_type)
            self.assertIn('text/csv', responses[1].content_type)
            self.assertIn('recommended_first_choice', responses[0].get_data(as_text=True))
            csv_body = responses[1].get_data(as_text=True)
            self.assertIn('lane_score', csv_body)
            self.assertIn('opportunity_readiness_label', csv_body)
            self.assertIn('research_readiness_label', csv_body)
            self.assertIn('review_status', csv_body)
            self.assertIn('source_confidence', csv_body)
            self.assertIn('last_verified', csv_body)
            self.assertIn('blocked_count', csv_body)
            self.assertIn('verification_tasks', csv_body)
            self.assertIn('Houston Rail Park', csv_body)
            self.assertIn('Denver Industrial Yard', csv_body)
        finally:
            for response in responses:
                response.close()

    def test_ranked_company_downloads_match_visible_filtered_state(self):
        page_response = self.client.get('/companies?q=Front%20Range&readiness=Verify%20site%20first&limit=10')
        csv_response = self.client.get('/downloads/top-companies.csv?q=Front%20Range&readiness=Verify%20site%20first&limit=10')
        json_response = self.client.get('/downloads/top-companies.json?q=Front%20Range&readiness=Verify%20site%20first&limit=10')

        try:
            page_body = page_response.get_data(as_text=True)
            csv_body = csv_response.get_data(as_text=True)
            json_body = json_response.get_data(as_text=True)
            csv_rows = list(csv.DictReader(io.StringIO(csv_body)))
            json_payload = json.loads(json_body)

            self.assertEqual(page_response.status_code, 200)
            self.assertEqual(csv_response.status_code, 200)
            self.assertEqual(json_response.status_code, 200)
            self.assertIn('Front Range Logistics', page_body)
            self.assertNotIn('Acme Chemicals', page_body)
            self.assertIn('Front Range Logistics', csv_body)
            self.assertNotIn('Acme Chemicals', csv_body)
            self.assertIn('Front Range Logistics', json_body)
            self.assertNotIn('Acme Chemicals', json_body)
            self.assertIn('opportunity_readiness_label', csv_body)
            self.assertIn('opportunity_readiness', json_body)
            self.assertEqual([row['company'] for row in csv_rows], ['Front Range Logistics'])
            self.assertEqual(
                [item['company_profile']['company'] for item in json_payload['companies']],
                ['Front Range Logistics'],
            )
            self.assertEqual(json_payload['export_info']['total_companies'], 1)
            self.assertEqual(json_payload['export_info']['filtered_company_count'], 1)
            dashboard_context = json_payload['export_info']['dashboard_context']
            self.assertEqual(dashboard_context['source'], 'dashboard')
            self.assertEqual(dashboard_context['view'], 'ranked_companies')
            self.assertEqual(dashboard_context['source_company_count'], 2)
            self.assertEqual(dashboard_context['dashboard_filtered_company_count'], 1)
            self.assertEqual(dashboard_context['dashboard_exported_company_count'], 1)
            self.assertTrue(dashboard_context['review_overlay_applied'])
            self.assertEqual(dashboard_context['applied_filters']['query'], 'Front Range')
            self.assertEqual(dashboard_context['applied_filters']['readiness'], VERIFY_SITE_LABEL)
        finally:
            page_response.close()
            csv_response.close()
            json_response.close()

    def test_core_workflow_page_links_resolve(self):
        pages = [
            '/',
            '/verification',
            '/sites/Houston%20Rail%20Park',
            '/pipeline',
            '/companies/Acme%20Chemicals',
            '/companies/Acme%20Chemicals/site-comparison',
            '/workspace?company=Acme%20Chemicals&site=Houston%20Rail%20Park',
            '/companies?state=TX&segment=Chemicals&commodity=chemicals&min_score=1',
            '/sites?state=TX&port_access=Yes&transload_available=Yes&source_confidence=Unspecified',
            '/map?state=TX&segment=Chemicals&commodity=chemicals&min_score=1',
        ]
        checked = set()

        for page in pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, 200, page)
            body = response.get_data(as_text=True)
            response.close()

            for raw_href in re.findall(r'href="([^"]+)"', body):
                href = html.unescape(raw_href)
                parsed = urlsplit(href)
                if parsed.scheme or href.startswith('#') or href.startswith('mailto:'):
                    continue
                if parsed.path.startswith('/static/'):
                    continue

                route = href
                if route in checked:
                    continue
                checked.add(route)
                link_response = self.client.get(route)
                try:
                    self.assertLess(link_response.status_code, 400, f"{page} links to {route}")
                finally:
                    link_response.close()

        self.assertIn('/pipeline', checked)
        self.assertIn('/verification', checked)
        self.assertIn('/workspace?company=Acme+Chemicals&site=Houston+Rail+Park', checked)
        self.assertIn('/downloads/workspace.txt?company=Acme+Chemicals&site=Houston+Rail+Park', checked)

    def test_dashboard_health_route_reports_loaded_counts(self):
        response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['companies'], 2)
        self.assertEqual(payload['sites'], 2)


if __name__ == '__main__':
    unittest.main()
