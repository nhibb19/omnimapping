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
    create_app,
    filter_companies_for_dashboard,
    filter_site_directory,
    parse_limit,
    parse_min_score,
    unique_sorted,
)
from modules.export import build_site_directory


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
        )
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

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
        self.assertIn('Data Confidence', detail_body)
        self.assertIn('Source confidence', detail_body)
        self.assertIn('Last verified', detail_body)
        self.assertIn('Data gaps', detail_body)
        self.assertIn('Matched companies', detail_body)
        self.assertIn('Acme Chemicals', detail_body)
        self.assertIn('/downloads/site/Houston%20Rail%20Park.json', detail_body)
        self.assertIn('/workspace?company=Acme+Chemicals&amp;site=Houston+Rail+Park', detail_body)

    def test_site_filters_work_for_state_port_transload_and_confidence(self):
        _, _, sites, _ = self.loaded_data
        directory = build_site_directory(sites)

        filtered = filter_site_directory(directory, {
            'state': 'TX',
            'port_access': 'Yes',
            'transload_available': 'Yes',
            'source_confidence': 'Unspecified',
        })

        self.assertEqual([site['site_name'] for site in filtered], ['Houston Rail Park'])

        confirmation_filtered = filter_site_directory(directory, {
            'query': 'Denver',
            'state': '',
            'port_access': '',
            'transload_available': '',
            'source_confidence': '',
            'needs_confirmation': 'yes',
        })
        self.assertEqual([site['site_name'] for site in confirmation_filtered], ['Denver Industrial Yard'])

        summary = build_site_scan_summary(directory)
        self.assertEqual(summary['needs_confirmation'], 1)

    def test_opportunity_workspace_payload_uses_selected_pair(self):
        segments, companies, sites, _ = self.loaded_data
        workspace = build_opportunity_workspace(companies[0], sites[0], segments)

        self.assertEqual(workspace['company']['company'], 'Acme Chemicals')
        self.assertEqual(workspace['site']['site_name'], 'Houston Rail Park')
        self.assertIn('score', workspace['priority'])
        self.assertIn('breakdown', workspace['priority'])
        self.assertGreaterEqual(len(workspace['priority']['reasons']), 1)
        self.assertGreater(workspace['site_match']['compatibility_score'], 0)
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
        self.assertIn('Risks / Confirm', body)
        self.assertIn('/workspace?company=Acme+Chemicals&amp;site=Houston+Rail+Park', body)
        self.assertIn('/downloads/company-site-comparison/Acme%20Chemicals.json?limit=5', body)
        self.assertIn('/downloads/company-site-comparison/Acme%20Chemicals.csv?limit=5', body)

    def test_opportunity_workspace_page_shows_action_context(self):
        response = self.client.get('/workspace?company=Acme%20Chemicals&site=Houston%20Rail%20Park')

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn('Opportunity Workspace', body)
        self.assertIn('Decision Snapshot', body)
        self.assertIn('Acme Chemicals', body)
        self.assertIn('Houston Rail Park', body)
        self.assertIn('Why This Pair Fits', body)
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
            self.assertIn('rank,site_name,compatibility_score', csv_body)
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
