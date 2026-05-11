"""Tests for the OmniMapping Flask dashboard."""

import contextlib
import io
import os
import sys
import tempfile
import unittest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT_DIR)

import main
from dashboard import (
    build_company_site_comparison,
    build_company_scan_summary,
    build_opportunity_workspace,
    build_site_scan_summary,
    build_supply_chain_filter_options,
    build_supply_chain_scan_summary,
    create_app,
    filter_companies_for_dashboard,
    filter_site_directory,
    parse_limit,
    parse_min_score,
    unique_sorted,
)
from modules.data_quality import build_research_readiness
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
        self.assertEqual(summary['ready_for_outreach'], 1)

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
        self.assertEqual(chemicals['top_companies'][0]['readiness_label'], 'Ready for outreach')
        self.assertEqual(chemicals['ready_count'], 1)
        self.assertEqual(chemicals['site_review_count'], 0)
        self.assertEqual(warehousing['top_companies'][0]['company'], 'Front Range Logistics')

        filtered = filter_supply_chains(
            catalog,
            group='Chemicals',
            query='industrial gases',
            opportunity='Strong rail prospect',
            readiness='Ready for outreach',
            min_priority=1,
            sort='ready',
        )
        self.assertEqual([chain['slug'] for chain in filtered], ['chemicals'])

        summary = build_supply_chain_scan_summary([chemicals, warehousing])
        self.assertEqual(summary['chain_count'], 2)
        self.assertEqual(summary['company_matches'], 2)
        self.assertEqual(summary['strong_prospects'], 1)
        self.assertEqual(summary['ready_for_outreach'], 1)

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
        self.assertIn('Open opportunity workspace', detail['action_queue'][0]['recommended_action'])
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
        self.assertIn('Needs site review', catalog_body)

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
        self.assertIn('Open opportunity workspace', detail_body)
        self.assertIn('Acme Chemicals', detail_body)
        self.assertIn('/companies/Acme%20Chemicals', detail_body)
        self.assertIn('/companies/Acme%20Chemicals/site-comparison', detail_body)
        self.assertIn('/workspace?company=Acme+Chemicals&amp;site=Houston+Rail+Park', detail_body)

    def test_supply_chains_route_filters_group_search_readiness_and_sort(self):
        response = self.client.get('/supply-chains?group=Chemicals&q=industrial%20gases&opportunity=Strong%20rail%20prospect&readiness=Ready%20for%20outreach&min_priority=1&sort=ready')

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
