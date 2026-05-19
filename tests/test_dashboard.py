"""Tests for the OmniMapping Flask dashboard."""

import contextlib
import io
import os
import sys
import tempfile
import unittest

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
        self.assertIn('/companies/Acme%20Chemicals', body)
        self.assertIn('/downloads/top-companies.csv', body)
        self.assertIn('/downloads/top-companies.json', body)
        self.assertIn('Ready for outreach', body)
        self.assertIn('Apply Filters', body)
        self.assertIn('Workspace', body)

    def test_ranked_companies_quick_search_filters_exported_rows(self):
        response = self.client.get('/companies?q=Front%20Range')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Front Range Logistics', body)
        self.assertNotIn('Acme Chemicals', body)

        _, companies, _, _ = self.loaded_data
        self.assertTrue(all('best_lane_score' in company for company in companies))
        filtered = filter_companies_for_dashboard(companies, {'query': 'chemical inputs'})
        self.assertEqual([company['company'] for company in filtered], ['Acme Chemicals'])

        summary = build_company_scan_summary(filtered)
        self.assertEqual(summary['ready_for_outreach'], 0)
        self.assertEqual(summary['verify_site_first'], 1)

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

    def test_home_redirects_to_map_workspace(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/map')

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
        )
        saved = save_review_store(self.review_store_path, {'Denver Industrial Yard': record})
        loaded = load_review_store(self.review_store_path)

        self.assertEqual(saved, loaded)
        self.assertEqual(loaded['Denver Industrial Yard']['review_status'], 'in_review')
        self.assertEqual(loaded['Denver Industrial Yard']['reviewed_by'], 'Alex')

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
            'review_notes': 'Acreage confirmed from public listing.',
            'reviewed_by': 'Jordan',
            'source_update_url': 'https://example.com/denver-yard',
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn('/sites/Denver%20Industrial%20Yard', response.headers['Location'])

        loaded = load_review_store(self.review_store_path)
        self.assertEqual(loaded['Denver Industrial Yard']['review_status'], 'confirmed')
        self.assertEqual(loaded['Denver Industrial Yard']['reviewed_by'], 'Jordan')
        self.assertTrue(loaded['Denver Industrial Yard']['reviewed_at'])

        detail_response = self.client.get('/sites/Denver%20Industrial%20Yard')
        detail_body = detail_response.get_data(as_text=True)
        self.assertIn('Acreage confirmed from public listing.', detail_body)
        self.assertIn('Jordan', detail_body)

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
        self.assertIn('verification_tasks', workspace)
        self.assertGreater(workspace['lane']['lane_score'], 0)
        self.assertGreaterEqual(len(workspace['lane']['lane_reasons']), 1)
        self.assertGreaterEqual(len(workspace['site_match']['matching_reasons']), 1)
        self.assertGreaterEqual(len(workspace['talking_points']), 1)
        self.assertGreaterEqual(len(workspace['risks_or_data_gaps']), 1)

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
        self.assertIn('Verification Tasks', body)
        self.assertIn('Strong lane', body)
        self.assertIn('Talking Points', body)
        self.assertIn('Risks And Data Gaps', body)
        self.assertIn('/downloads/workspace.json?company=Acme+Chemicals&amp;site=Houston+Rail+Park', body)
        self.assertIn('/downloads/workspace.txt?company=Acme+Chemicals&amp;site=Houston+Rail+Park', body)
        self.assertIn('/companies/Acme%20Chemicals/site-comparison', body)

    def test_dashboard_download_routes_reuse_export_helpers(self):
        responses = [
            self.client.get('/downloads/top-companies.csv?state=TX&limit=1'),
            self.client.get('/downloads/top-companies.json?state=TX&limit=1'),
            self.client.get('/downloads/company/Acme%20Chemicals.json'),
            self.client.get('/downloads/site/Houston%20Rail%20Park.json'),
        ]
        try:
            self.assertEqual([response.status_code for response in responses], [200, 200, 200, 200])
            self.assertIn('text/csv', responses[0].content_type)
            self.assertIn('application/json', responses[1].content_type)
            self.assertIn('application/json', responses[2].content_type)
            self.assertIn('application/json', responses[3].content_type)
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
            self.assertIn('OPPORTUNITY BRIEF', responses[1].get_data(as_text=True))
            self.assertIn('Houston Rail Park', responses[1].get_data(as_text=True))
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
            self.assertIn('research_readiness_label', csv_body)
            self.assertIn('verification_tasks', csv_body)
            self.assertIn('Houston Rail Park', csv_body)
            self.assertIn('Denver Industrial Yard', csv_body)
        finally:
            for response in responses:
                response.close()

    def test_dashboard_health_route_reports_loaded_counts(self):
        response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['companies'], 2)
        self.assertEqual(payload['sites'], 2)


if __name__ == '__main__':
    unittest.main()
