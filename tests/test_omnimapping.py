"""Minimal test harness for OmniMapping.

Run with:
    python3 -m unittest discover -s tests
"""

import csv
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure the project root is importable when tests run from tests/.
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT_DIR)

import main
from modules.scoring import calculate_priority_score, calculate_overall_opportunity_score, calculate_site_compatibility_score
from modules.search import search_companies, get_top_opportunities, find_best_sites_for_company, filter_by_min_score, get_companies_by_segment
from modules.ui import get_priority_reasons
from modules.data_quality import build_data_quality_report
from modules.export import (
    export_to_csv,
    export_opportunity_briefs,
    export_company_profiles_json,
    export_site_matching_report,
    export_segment_analysis,
    export_geographic_analysis,
    export_summary_json,
    export_company_report_json,
    export_site_report_json,
    export_top_companies_json,
    build_top_companies_export,
    build_company_directory,
    build_site_directory,
    find_company_for_report,
    find_site_for_report,
)
from modules.geography import (
    generate_company_map,
    generate_sites_map,
    generate_top_opportunities_map,
    generate_geographic_opportunity_map,
    export_geographic_profiles,
)


class TestOmniMapping(unittest.TestCase):
    def write_csv(self, filepath, rows):
        with open(filepath, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def sample_dataset(self):
        segments = [
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
        ]
        companies = [
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
        ]
        sites = [
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
                'acres': '120',
            },
        ]
        rail_infrastructure = [
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
        ]
        return segments, companies, sites, rail_infrastructure

    def write_sample_data_dir(self, root_dir):
        segments, companies, sites, rail_infrastructure = self.sample_dataset()
        data_dir = os.path.join(root_dir, 'data')
        os.makedirs(data_dir, exist_ok=True)
        self.write_csv(os.path.join(data_dir, 'segments.csv'), segments)
        self.write_csv(os.path.join(data_dir, 'companies.csv'), companies)
        self.write_csv(os.path.join(data_dir, 'industrial_sites.csv'), sites)
        self.write_csv(os.path.join(data_dir, 'rail_infrastructure.csv'), rail_infrastructure)
        return segments, companies, sites, rail_infrastructure

    def test_load_data_computes_scores_and_site_matches(self):
        sample_segments = [
            {
                'segment': 'Chemicals',
                'stage': 'active',
                'rail_score': '5',
                'reason': 'Test segment',
                'omnitrax_angle': 'rail',
                'commodity_type': 'chemicals',
            }
        ]

        sample_companies = [
            {
                'company': 'Acme Chemicals',
                'segment': 'Chemicals',
                'state': 'TX',
                'city': 'Houston',
                'commodity_type': 'chemicals',
                'rail_fit_score': '4',
                'industrial_real_estate_score': '3',
                'omnitrax_outreach_angle': 'rail',
                'inbound_materials': 'chemical',
                'outbound_products': 'chemical',
            }
        ]

        sample_sites = [
            {
                'site_name': 'Houston Industrial Park',
                'state': 'TX',
                'city': 'Houston',
                'rail_served': 'yes',
                'nearby_class1': 'yes',
                'transload_available': 'yes',
                'interstate_access': 'yes',
                'port_access': 'yes',
                'target_industries': 'chemicals, energy',
                'acres': '300',
            }
        ]

        sample_rail = [
            {
                'location': 'Houston Hub',
                'type': 'Yard',
                'latitude': '29.7604',
                'longitude': '-95.3698',
                'rail_connections': '5',
                'capacity_score': '8',
                'logistics_score': '7',
            }
        ]

        with patch.object(main, 'validate_data_files', return_value=[]), \
                patch.object(main, 'load_csv', side_effect=[sample_segments, sample_companies, sample_sites, sample_rail]), \
                patch.object(main, 'enhance_company_geography', lambda companies, rail: companies):
            segments, companies, sites, rail_infrastructure = main.load_data()

        self.assertEqual(len(segments), 1)
        self.assertEqual(len(companies), 1)
        self.assertEqual(len(sites), 1)
        self.assertEqual(len(rail_infrastructure), 1)

        company = companies[0]
        self.assertIn('priority_score', company)
        self.assertIn('best_site_name', company)
        self.assertEqual(company['best_site_name'], 'Houston Industrial Park')
        self.assertTrue(0 <= int(company['priority_score']) <= 100)
        self.assertEqual(company['site_match_quality_label'], 'Excellent')

    def test_run_verification_returns_success_for_valid_data(self):
        sample_segments = [{
            'segment': 'Chemicals',
            'stage': 'active',
            'rail_score': '5',
            'reason': 'Test segment',
            'omnitrax_angle': 'rail',
            'commodity_type': 'chemicals',
        }]

        sample_companies = [{
            'company': 'Acme Chemicals',
            'segment': 'Chemicals',
            'state': 'TX',
            'city': 'Houston',
            'commodity_type': 'chemicals',
            'rail_fit_score': '4',
            'industrial_real_estate_score': '3',
            'omnitrax_outreach_angle': 'rail',
            'inbound_materials': 'chemical',
            'outbound_products': 'chemical',
            'priority_score': '85',
            'best_site_match_score': '100',
            'score_breakdown': {
                'rail_fit': 16,
                'logistics_intensity': 15,
                'land_intensity': 9,
                'multimodal_potential': 12,
                'site_match_quality': 10,
                'industry_fit': 5,
                'strategic_fit': 8,
            },
        }]

        sample_sites = [{
            'site_name': 'Houston Industrial Park',
            'state': 'TX',
            'city': 'Houston',
            'rail_served': 'yes',
            'nearby_class1': 'yes',
            'transload_available': 'yes',
            'interstate_access': 'yes',
            'port_access': 'yes',
            'target_industries': 'chemicals, energy',
            'acres': '300',
        }]

        sample_rail = [{
            'location': 'Houston Hub',
            'type': 'Yard',
            'latitude': '29.7604',
            'longitude': '-95.3698',
            'rail_connections': '5',
            'capacity_score': '8',
            'logistics_score': '7',
        }]

        with patch.object(main, 'load_data', return_value=(sample_segments, sample_companies, sample_sites, sample_rail)), \
                patch.object(main, 'get_top_opportunities', return_value=sample_companies), \
                patch.object(main, 'find_best_sites_for_company', return_value=[{'site': sample_sites[0], 'compatibility_score': 100}]):
            result = main.run_verification()

        self.assertEqual(result, 0)

    def test_run_verification_loads_temp_project_data_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    result = main.run_verification()
            finally:
                os.chdir(previous_cwd)

        verification_output = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn('[PASS] CSV validation', verification_output)
        self.assertIn('[PASS] Data load', verification_output)
        self.assertIn('[PASS] Top opportunities sort', verification_output)
        self.assertIn('[PASS] Site matching', verification_output)
        self.assertIn('Data Quality Summary', verification_output)
        self.assertIn('Source confidence:', verification_output)
        self.assertIn('Blank acreage sites:', verification_output)
        self.assertIn('Needs confirmation:', verification_output)
        self.assertIn('Loaded 2 companies', verification_output)
        self.assertIn('PASS OmniMapping verification completed successfully.', verification_output)

    def test_load_data_reads_temp_project_csvs_and_enriches_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(len(segments), 2)
        self.assertEqual(len(companies), 2)
        self.assertEqual(len(sites), 2)
        self.assertEqual(len(rail_infrastructure), 2)
        self.assertTrue(all('priority_score' in company for company in companies))
        self.assertTrue(all('score_breakdown' in company for company in companies))
        self.assertTrue(all(company.get('best_site_name') for company in companies))

    def test_metadata_fields_are_optional_and_default_for_old_csvs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)
            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(len(sites), 2)
        self.assertEqual(len(rail_infrastructure), 2)
        self.assertEqual(sites[0]['source_confidence'], 'Unspecified')
        self.assertEqual(rail_infrastructure[0]['source_confidence'], 'Unspecified')
        self.assertIn('needs_confirmation', sites[0])
        self.assertIn('data_quality_flags', rail_infrastructure[0])

    def test_data_quality_report_counts_confidence_and_gaps(self):
        sites = [
            {
                'site_name': 'Needs Acreage',
                'acres': '',
                'nearby_class1': '',
                'interstate_access': 'Yes',
                'port_access': '',
                'transload_available': 'Yes',
                'source_confidence': 'Medium',
                'data_gap_notes': 'Confirm acreage.',
            },
            {
                'site_name': 'Complete Site',
                'acres': '100',
                'nearby_class1': 'BNSF',
                'interstate_access': 'Yes',
                'port_access': 'No',
                'transload_available': 'No',
                'source_confidence': 'High',
            },
        ]
        rail_infrastructure = [
            {
                'location': 'Approx Rail',
                'port_nearby': 'Yes',
                'interstate_access': 'I-95',
                'transload_hub': 'Yes',
                'source_confidence': 'High',
                'data_gap_notes': 'Coordinates are approximate city-center points.',
            }
        ]

        report = build_data_quality_report(sites, rail_infrastructure)

        self.assertEqual(report['source_confidence_counts'], {'High': 2, 'Medium': 1})
        self.assertEqual(report['blank_acreage_sites'], 1)
        self.assertEqual(report['approximate_coordinate_records'], 1)
        self.assertEqual(report['missing_class1_sites'], 1)
        self.assertEqual(report['missing_port_sites'], 1)
        self.assertEqual(report['missing_interstate_rail_records'], 0)
        self.assertEqual(report['missing_port_rail_records'], 0)
        self.assertEqual(report['missing_transload_rail_records'], 0)

    def test_validate_csv_file_reports_blank_required_values_and_invalid_numbers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, 'companies.csv')
            with open(filepath, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['company', 'segment', 'state', 'city', 'commodity_type', 'rail_fit_score', 'industrial_real_estate_score'])
                writer.writerow(['', 'Chemicals', 'TX', '', 'chemicals', 'not_a_number', ''])

            issues = main.validate_csv_file(
                filepath,
                required_fields=['company', 'segment', 'state', 'city', 'commodity_type', 'rail_fit_score', 'industrial_real_estate_score'],
                numeric_fields=['rail_fit_score', 'industrial_real_estate_score']
            )

        self.assertTrue(any(f"missing required 'company' on line 2" in issue for issue in issues))
        self.assertTrue(any(f"missing required 'city' on line 2" in issue for issue in issues))
        self.assertTrue(any(f"non-numeric value for 'rail_fit_score' on line 2: not_a_number" in issue for issue in issues))
        self.assertTrue(any(f"missing numeric field 'industrial_real_estate_score' on line 2" in issue for issue in issues))

    def test_validate_data_files_reports_missing_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Only create companies.csv and nothing else.
            filepath = os.path.join(tmpdir, 'companies.csv')
            with open(filepath, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['company', 'segment', 'state', 'city', 'commodity_type', 'rail_fit_score', 'industrial_real_estate_score'])
                writer.writerow(['Acme Chemicals', 'Chemicals', 'TX', 'Houston', 'chemicals', '4', '3'])

            issues = main.validate_data_files(data_dir=tmpdir)

        self.assertIn(f"Missing data file: {os.path.join(tmpdir, 'segments.csv')}", issues)
        self.assertIn(f"Missing data file: {os.path.join(tmpdir, 'industrial_sites.csv')}", issues)
        self.assertIn(f"Missing data file: {os.path.join(tmpdir, 'rail_infrastructure.csv')}", issues)

    def test_priority_score_range_and_breakdown_total(self):
        company = {
            'rail_fit_score': 5,
            'estimated_rail_distance': 5,
            'inbound_materials': 'steel',
            'outbound_products': 'coal',
            'industrial_real_estate_score': 5,
            'nearest_port': 'Port Houston',
            'transload_potential': 'High',
            'port_to_consumer_score': '40',
            'commodity_type': 'coal',
            'omnitrax_outreach_angle': 'rail',
            'segment': 'Steel Mills',
        }
        segment_data = {'segment': 'Steel Mills'}

        score, breakdown = calculate_priority_score(company, segment_data, best_site_match_score=95)

        self.assertTrue(0 <= score <= 100)
        self.assertEqual(score, sum(breakdown.values()))
        self.assertEqual(set(breakdown.keys()), {
            'rail_fit',
            'logistics_intensity',
            'land_intensity',
            'multimodal_potential',
            'site_match_quality',
            'industry_fit',
            'strategic_fit',
        })

    def test_priority_score_handles_invalid_numeric_inputs(self):
        company = {
            'rail_fit_score': 'not a number',
            'estimated_rail_distance': 'far',
            'inbound_materials': 'steel',
            'outbound_products': 'coal',
            'industrial_real_estate_score': 'unknown',
            'nearest_port': '',
            'transload_potential': 'maybe',
            'port_to_consumer_score': 'abc',
            'commodity_type': 'steel',
            'omnitrax_outreach_angle': 'rail',
            'segment': 'Steel Mills',
        }
        segment_data = {'segment': 'Steel Mills'}

        score, breakdown = calculate_priority_score(company, segment_data, best_site_match_score=70)

        self.assertTrue(0 <= score <= 100)
        self.assertEqual(score, sum(breakdown.values()))
        self.assertIn('rail_fit', breakdown)
        self.assertIn('logistics_intensity', breakdown)

    def test_get_priority_reasons_matches_strong_drivers(self):
        company = {
            'score_breakdown': {
                'rail_fit': 22,
                'multimodal_potential': 14,
                'logistics_intensity': 15,
                'site_match_quality': 8,
                'industry_fit': 5,
                'land_intensity': 10,
                'strategic_fit': 6,
            }
        }

        reasons = get_priority_reasons(company)
        self.assertTrue(any('rail' in reason.lower() for reason in reasons))
        self.assertTrue(any('multimodal' in reason.lower() for reason in reasons))
        self.assertTrue(any('logistics' in reason.lower() for reason in reasons))

    def test_overall_opportunity_score_handles_malformed_values(self):
        company = {
            'rail_fit_score': 'bad',
            'inbound_materials': 'coal',
            'outbound_products': 'ore',
            'industrial_real_estate_score': 'bad',
            'nearest_port': 'Port Example',
            'nearest_class1_railroad': 'yes',
            'estimated_rail_distance': 'close',
            'transload_potential': 'High',
            'port_to_consumer_score': 'bad',
            'omnitrax_outreach_angle': 'industrial',
            'why_target': 'global growth',
            'company': 'Global Test Co',
        }
        segment_data = {'segment': 'Energy'}

        score, breakdown = calculate_overall_opportunity_score(company, segment_data)

        self.assertTrue(0 <= score <= 100)
        self.assertEqual(set(breakdown.keys()), {
            'rail_fit',
            'logistics_intensity',
            'land_intensity',
            'multimodal_potential',
            'industrial_outdoor_storage',
            'supply_chain_criticality',
            'expansion_likelihood',
            'omnitrax_strategic_fit',
        })

    def test_site_compatibility_score_clamps_and_handles_invalid_acres(self):
        company = {
            'segment': 'Chemicals',
            'commodity_type': 'chemicals',
            'state': 'TX',
        }
        site = {
            'rail_served': 'yes',
            'transload_available': 'yes',
            'port_access': 'yes',
            'interstate_access': 'yes',
            'target_industries': 'chemicals',
            'state': 'TX',
            'acres': 'large',
        }

        score = calculate_site_compatibility_score(company, site)
        self.assertTrue(0 <= score <= 100)

    def test_top_opportunities_sorting(self):
        companies = [
            {'company': 'C', 'priority_score': '25'},
            {'company': 'A', 'priority_score': '90'},
            {'company': 'B', 'priority_score': '50'},
        ]

        top_two = get_top_opportunities(companies, limit=2)
        self.assertEqual([item['company'] for item in top_two], ['A', 'B'])

    def test_search_score_helpers_tolerate_blank_and_malformed_scores(self):
        companies = [
            {'company': 'A', 'segment': 'Steel', 'priority_score': '90'},
            {'company': 'B', 'segment': 'Steel', 'priority_score': ''},
            {'company': 'C', 'segment': 'Energy', 'priority_score': 'not-scored'},
            {'company': 'D', 'segment': 'Energy', 'priority_score': '45.5'},
        ]

        top_companies = get_top_opportunities(companies, limit=4)
        filtered = filter_by_min_score(companies, 40)
        segment_stats = get_companies_by_segment(companies)

        self.assertEqual([item['company'] for item in top_companies], ['A', 'D', 'B', 'C'])
        self.assertEqual([item['company'] for item in filtered], ['A', 'D'])
        self.assertEqual(segment_stats['Steel']['avg_score'], 45.0)
        self.assertEqual(segment_stats['Energy']['avg_score'], 22.5)

    def test_company_search_and_report_matching_exact_match_precedence(self):
        companies = [
            {'company': 'Acme Chemicals International', 'segment': 'Chemicals', 'state': 'TX', 'city': 'Houston', 'commodity_type': 'chemicals', 'priority_score': '95'},
            {'company': 'Acme Chemicals', 'segment': 'Chemicals', 'state': 'LA', 'city': 'Baton Rouge', 'commodity_type': 'chemicals', 'priority_score': '70'},
        ]

        search_results = search_companies(companies, ' acme chemicals '.strip())
        matched_company, report_candidates = find_company_for_report(companies, ' Acme Chemicals ')

        self.assertEqual([company['company'] for company in search_results], ['Acme Chemicals International', 'Acme Chemicals'])
        self.assertEqual(matched_company['company'], 'Acme Chemicals')
        self.assertEqual([company['company'] for company in report_candidates], ['Acme Chemicals'])

    def test_company_search_and_report_matching_partial_match(self):
        companies = [
            {'company': 'Front Range Logistics', 'segment': 'Warehousing', 'state': 'CO', 'city': 'Denver', 'commodity_type': 'steel', 'priority_score': '64'},
            {'company': 'Range Materials', 'segment': 'Steel', 'state': 'UT', 'city': 'Salt Lake City', 'commodity_type': 'steel', 'priority_score': '82'},
            {'company': 'Coastal Chemicals', 'segment': 'Chemicals', 'state': 'TX', 'city': 'Freeport', 'commodity_type': 'chemicals', 'priority_score': '91'},
        ]

        search_results = search_companies(companies, 'Range')
        matched_company, report_candidates = find_company_for_report(companies, 'Range')

        self.assertEqual([company['company'] for company in search_results], ['Front Range Logistics', 'Range Materials'])
        self.assertEqual(matched_company['company'], 'Range Materials')
        self.assertEqual([company['company'] for company in report_candidates], ['Range Materials', 'Front Range Logistics'])

    def test_company_search_and_report_matching_no_match(self):
        companies = [
            {'company': 'Acme Chemicals', 'segment': 'Chemicals', 'state': 'TX', 'city': 'Houston', 'commodity_type': 'chemicals', 'priority_score': '88'},
        ]

        self.assertEqual(search_companies(companies, 'Nonexistent Prospect'), [])
        matched_company, report_candidates = find_company_for_report(companies, 'Nonexistent Prospect')
        self.assertIsNone(matched_company)
        self.assertEqual(report_candidates, [])

    def test_company_report_matching_duplicate_like_names_uses_highest_scored_partial(self):
        companies = [
            {'company': 'Omni Steel', 'segment': 'Steel', 'state': 'TX', 'city': 'Dallas', 'commodity_type': 'steel', 'priority_score': '73'},
            {'company': 'Omni Steel LLC', 'segment': 'Steel', 'state': 'OK', 'city': 'Tulsa', 'commodity_type': 'steel', 'priority_score': '91'},
            {'company': 'Omni Steel Logistics', 'segment': 'Warehousing', 'state': 'KS', 'city': 'Wichita', 'commodity_type': 'steel', 'priority_score': '85'},
        ]

        search_results = search_companies(companies, 'Omni')
        matched_company, report_candidates = find_company_for_report(companies, 'Omni')

        self.assertEqual([company['company'] for company in search_results], ['Omni Steel', 'Omni Steel LLC', 'Omni Steel Logistics'])
        self.assertEqual(matched_company['company'], 'Omni Steel LLC')
        self.assertEqual([company['company'] for company in report_candidates], ['Omni Steel LLC', 'Omni Steel Logistics', 'Omni Steel'])

    def test_best_site_matching_returns_highest_compatibility(self):
        company = {
            'segment': 'Chemicals',
            'commodity_type': 'chemicals',
            'state': 'TX',
        }

        sites = [
            {
                'site_name': 'Houston Industrial Park',
                'rail_served': 'yes',
                'transload_available': 'yes',
                'port_access': 'yes',
                'interstate_access': 'yes',
                'target_industries': 'chemicals',
                'state': 'TX',
                'acres': '300',
            },
            {
                'site_name': 'Small Industrial Lot',
                'rail_served': 'no',
                'transload_available': 'no',
                'port_access': 'no',
                'interstate_access': 'no',
                'target_industries': 'logistics',
                'state': 'OK',
                'acres': '20',
            },
        ]

        matches = find_best_sites_for_company(company, sites, limit=2)
        self.assertEqual(matches[0]['site']['site_name'], 'Houston Industrial Park')
        self.assertGreater(matches[0]['compatibility_score'], matches[1]['compatibility_score'])

    def test_export_to_csv_includes_priority_fields_and_score_reasons(self):
        companies = [
            {
                'company': 'Acme Logistics',
                'segment': 'Warehousing',
                'commodity_type': 'steel',
                'state': 'TX',
                'city': 'Houston',
                'rail_fit_score': 5,
                'industrial_real_estate_score': 4,
                'omnitrax_outreach_angle': 'rail',
                'inbound_materials': 'steel',
                'outbound_products': 'metal',
                'why_target': 'High volume rail inbound',
                'priority_score': 82,
                'score_breakdown': {
                    'rail_fit': 20,
                    'logistics_intensity': 15,
                    'land_intensity': 12,
                    'multimodal_potential': 10,
                    'site_match_quality': 8,
                    'industry_fit': 5,
                    'strategic_fit': 12,
                },
                'best_site_name': 'Houston Rail Park',
                'site_match_quality_label': 'Excellent',
                'freight_intensity_label': 'High',
                'infrastructure_dependency': 'High rail-port-transload dependency',
                'recommended_next_action': 'Begin outreach with a site assessment.',
                'opportunity_risk': 'Confirm acreage and multimodal access.',
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'opportunities.csv')
            export_to_csv(companies, filename='opportunities.csv', output_dir=tmpdir)

            with open(output_path, newline='') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['company'], 'Acme Logistics')
        self.assertEqual(rows[0]['company_info'], 'High volume rail inbound')
        self.assertEqual(rows[0]['segment'], 'Warehousing')
        self.assertEqual(rows[0]['location'], 'Houston, TX')
        self.assertEqual(rows[0]['commodity'], 'steel')
        self.assertEqual(rows[0]['commodity_type'], 'steel')
        self.assertEqual(rows[0]['priority_score'], '82')
        self.assertIn('score_breakdown', rows[0])
        self.assertIn('score_reasons', rows[0])
        self.assertEqual(rows[0]['best_recommended_site'], 'Houston Rail Park')
        self.assertEqual(rows[0]['best_site_name'], 'Houston Rail Park')

    def test_export_to_csv_tolerates_malformed_priority_score(self):
        companies = [
            {
                'company': 'Unscored Prospect',
                'segment': 'Warehousing',
                'commodity_type': 'steel',
                'state': 'TX',
                'city': 'Houston',
                'priority_score': 'pending',
                'score_breakdown': {},
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'opportunities.csv')
            export_to_csv(companies, filename='opportunities.csv', output_dir=tmpdir)

            with open(output_path, newline='') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

        self.assertEqual(rows[0]['priority_score'], '0')

    def test_export_company_profiles_json_includes_score_reasons(self):
        companies = [
            {
                'company': 'Global Test Co',
                'segment': 'Chemicals',
                'commodity_type': 'chemicals',
                'state': 'TX',
                'city': 'Houston',
                'why_target': 'Regional chemical production prospect',
                'rail_fit_score': 3,
                'industrial_real_estate_score': 4,
                'priority_score': 65,
                'score_breakdown': {'rail_fit': 12, 'logistics_intensity': 12},
                'best_site_name': 'Houston Rail Park',
                'best_recommended_site_location': 'Houston, TX',
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_company_profiles_json(companies, output_dir=tmpdir)
            exported_files = [f for f in os.listdir(tmpdir) if f.endswith('.json')]
            self.assertEqual(len(exported_files), 1)

            with open(os.path.join(tmpdir, exported_files[0]), 'r') as f:
                data = json.load(f)

        self.assertEqual(data['export_info']['total_companies'], 1)
        self.assertEqual(data['companies'][0]['company'], 'Global Test Co')
        self.assertEqual(data['companies'][0]['company_info'], 'Regional chemical production prospect')
        self.assertEqual(data['companies'][0]['location'], 'Houston, TX')
        self.assertEqual(data['companies'][0]['commodity'], 'chemicals')
        self.assertIn('score_reasons', data['companies'][0])
        self.assertEqual(data['companies'][0]['best_recommended_site'], 'Houston Rail Park')
        self.assertEqual(data['companies'][0]['best_recommended_site_location'], 'Houston, TX')

    def test_export_site_matching_report_includes_company_basics_and_reasons(self):
        companies = [
            {
                'company': 'Acme Logistics',
                'segment': 'Warehousing',
                'commodity_type': 'steel',
                'state': 'TX',
                'city': 'Houston',
                'rail_fit_score': 5,
                'industrial_real_estate_score': 4,
                'omnitrax_outreach_angle': 'rail',
                'inbound_materials': 'steel',
                'outbound_products': 'metal',
                'why_target': 'High volume rail inbound',
                'priority_score': 82,
                'score_breakdown': {
                    'rail_fit': 20,
                    'logistics_intensity': 15,
                    'land_intensity': 12,
                    'multimodal_potential': 10,
                    'site_match_quality': 8,
                    'industry_fit': 5,
                    'strategic_fit': 12,
                },
            }
        ]
        sites = [
            {
                'site_name': 'Houston Rail Park',
                'state': 'TX',
                'city': 'Houston',
                'rail_served': 'yes',
                'transload_available': 'yes',
                'port_access': 'yes',
                'interstate_access': 'yes',
                'target_industries': 'steel, logistics',
                'acres': '150',
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_site_matching_report(companies, sites, output_dir=tmpdir)
            exported_files = [f for f in os.listdir(tmpdir) if f.endswith('.csv')]
            self.assertEqual(len(exported_files), 1)

            with open(os.path.join(tmpdir, exported_files[0]), newline='') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['company'], 'Acme Logistics')
        self.assertEqual(rows[0]['company_info'], 'High volume rail inbound')
        self.assertEqual(rows[0]['segment'], 'Warehousing')
        self.assertEqual(rows[0]['location'], 'Houston, TX')
        self.assertEqual(rows[0]['commodity'], 'steel')
        self.assertEqual(rows[0]['commodity_type'], 'steel')
        self.assertEqual(rows[0]['best_recommended_site'], 'Houston Rail Park')
        self.assertEqual(rows[0]['best_recommended_site_location'], 'Houston, TX')
        self.assertEqual(rows[0]['recommended_site'], 'Houston Rail Park')
        self.assertIn('score_reasons', rows[0])

    def test_export_opportunity_briefs_include_business_context_and_recommended_site(self):
        companies = [
            {
                'company': 'Acme Logistics',
                'segment': 'Warehousing',
                'commodity_type': 'steel',
                'state': 'TX',
                'city': 'Houston',
                'rail_fit_score': 5,
                'industrial_real_estate_score': 4,
                'omnitrax_outreach_angle': 'rail',
                'inbound_materials': 'steel',
                'outbound_products': 'metal',
                'why_target': 'High volume rail inbound',
                'priority_score': 82,
                'score_breakdown': {'rail_fit': 20, 'logistics_intensity': 15},
            }
        ]
        segments = [{'segment': 'Warehousing'}]
        sites = [
            {
                'site_name': 'Houston Rail Park',
                'state': 'TX',
                'city': 'Houston',
                'rail_served': 'yes',
                'transload_available': 'yes',
                'port_access': 'yes',
                'interstate_access': 'yes',
                'target_industries': 'steel, logistics',
                'acres': '150',
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_opportunity_briefs(companies, segments, sites, output_dir=tmpdir)
            brief_path = os.path.join(tmpdir, 'opportunity_briefs', 'Acme_Logistics_brief.txt')

            with open(brief_path, 'r') as f:
                content = f.read()

        self.assertIn('COMMODITY: steel', content)
        self.assertIn('1. COMPANY CONTEXT:', content)
        self.assertIn('High volume rail inbound', content)
        self.assertIn('2. TOP SCORE DRIVERS:', content)
        self.assertIn('Rail Fit: 20', content)
        self.assertIn('3. RAIL / LOGISTICS RATIONALE:', content)
        self.assertIn('4. RECOMMENDED SITE FIT:', content)
        self.assertIn('BEST RECOMMENDED INDUSTRIAL SITE', content)
        self.assertIn('6. TRANSLOAD / SITE ANGLE:', content)
        self.assertIn('8. NEXT ACTION:', content)
        self.assertNotIn('(N/A/100)', content)
        self.assertIn('Houston Rail Park (Houston, TX)', content)

    def test_export_generation_smoke_writes_expected_files_to_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

            export_dir = os.path.join(tmpdir, 'exports')
            with contextlib.redirect_stdout(io.StringIO()):
                export_to_csv(companies, filename='all_companies.csv', output_dir=export_dir)
                export_opportunity_briefs(companies, segments, sites, output_dir=export_dir)
                export_company_profiles_json(companies, output_dir=export_dir)
                export_site_matching_report(companies, sites, output_dir=export_dir)
                export_segment_analysis(companies, segments, output_dir=export_dir)
                export_geographic_analysis(companies, output_dir=export_dir)
                geographic_profiles_path = export_geographic_profiles(
                    companies,
                    rail_infrastructure,
                    filename=os.path.join(export_dir, 'geographic_profiles.csv')
                )

            self.assertTrue(os.path.exists(os.path.join(export_dir, 'all_companies.csv')))
            self.assertTrue(os.path.exists(os.path.join(export_dir, 'opportunity_briefs', 'Acme_Chemicals_brief.txt')))
            self.assertTrue(os.path.exists(geographic_profiles_path))
            self.assertTrue(any(name.startswith('company_profiles_') and name.endswith('.json') for name in os.listdir(export_dir)))
            self.assertTrue(any(name.startswith('site_matching_report_') and name.endswith('.csv') for name in os.listdir(export_dir)))
            self.assertTrue(any(name.startswith('segment_analysis_') and name.endswith('.csv') for name in os.listdir(export_dir)))
            self.assertTrue(any(name.startswith('geographic_analysis_') and name.endswith('.csv') for name in os.listdir(export_dir)))

            with open(os.path.join(export_dir, 'all_companies.csv'), newline='') as csvfile:
                rows = list(csv.DictReader(csvfile))
            with open(os.path.join(export_dir, 'opportunity_briefs', 'Acme_Chemicals_brief.txt')) as brief_file:
                brief_content = brief_file.read()

        self.assertEqual(len(rows), 2)
        self.assertIn('score_reasons', rows[0])
        self.assertIn('BEST RECOMMENDED INDUSTRIAL SITE', brief_content)

    def test_export_summary_json_includes_operational_rollups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

            export_dir = os.path.join(tmpdir, 'exports')
            with contextlib.redirect_stdout(io.StringIO()):
                summary_path = export_summary_json(
                    companies,
                    segments,
                    sites,
                    rail_infrastructure,
                    output_dir=export_dir,
                    top_limit=2,
                )

            with open(summary_path) as summary_file:
                summary = json.load(summary_file)

        self.assertTrue(os.path.basename(summary_path).startswith('summary_'))
        self.assertEqual(summary['counts']['companies'], 2)
        self.assertEqual(summary['counts']['segments'], 2)
        self.assertEqual(summary['counts']['industrial_sites'], 2)
        self.assertEqual(summary['counts']['rail_infrastructure_records'], 2)
        self.assertEqual(len(summary['top_opportunities']), 2)
        self.assertEqual(summary['top_opportunities'][0]['rank'], 1)
        self.assertIn('priority_score', summary['top_opportunities'][0])
        self.assertIn('Chemicals', {item['segment'] for item in summary['segment_averages']})
        self.assertEqual(summary['state_counts']['TX'], 1)
        self.assertEqual(summary['state_counts']['CO'], 1)
        self.assertEqual(len(summary['best_site_matches']), 2)
        self.assertIn('site_name', summary['best_site_matches'][0])
        self.assertIn('compatibility_score', summary['best_site_matches'][0])

    def test_export_summary_cli_writes_json_from_temp_project_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)
            result = subprocess.run(
                [sys.executable, os.path.join(ROOT_DIR, 'main.py'), '--export-summary'],
                cwd=tmpdir,
                text=True,
                capture_output=True,
                check=False,
            )

            export_dir = os.path.join(tmpdir, 'exports')
            exported_files = os.listdir(export_dir)
            summary_files = [name for name in exported_files if name.startswith('summary_') and name.endswith('.json')]

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(summary_files), 1)

            with open(os.path.join(export_dir, summary_files[0])) as summary_file:
                summary = json.load(summary_file)

        self.assertIn('Exported summary to', result.stdout)
        self.assertEqual(summary['counts']['companies'], 2)
        self.assertEqual(summary['counts']['industrial_sites'], 2)
        self.assertEqual(len(summary['top_opportunities']), 2)

    def test_top_companies_export_filters_and_includes_site_recommendation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

            export_payload = build_top_companies_export(
                companies,
                sites,
                limit=1,
                state='TX',
                segment='Chemicals',
                commodity='chemicals',
                min_score=1,
            )
            export_dir = os.path.join(tmpdir, 'exports')
            with contextlib.redirect_stdout(io.StringIO()):
                export_path = export_top_companies_json(
                    companies,
                    sites,
                    output_dir=export_dir,
                    limit=1,
                    state='TX',
                    segment='Chemicals',
                    commodity='chemicals',
                    min_score=1,
                )

            with open(export_path) as export_file:
                file_payload = json.load(export_file)

        self.assertEqual(export_payload['export_info']['filtered_company_count'], 1)
        self.assertEqual(export_payload['export_info']['exported_company_count'], 1)
        self.assertEqual(export_payload['companies'][0]['rank'], 1)
        self.assertEqual(export_payload['companies'][0]['company_profile']['company'], 'Acme Chemicals')
        self.assertEqual(export_payload['companies'][0]['company_profile']['location'], 'Houston, TX')
        self.assertIn('priority_score', export_payload['companies'][0])
        self.assertIn('score_breakdown', export_payload['companies'][0])
        self.assertGreaterEqual(len(export_payload['companies'][0]['priority_reasons']), 1)
        self.assertEqual(export_payload['companies'][0]['best_recommended_site']['site_name'], 'Houston Rail Park')
        self.assertIn('site_match_score', export_payload['companies'][0]['best_recommended_site'])
        self.assertEqual(file_payload['companies'][0]['company_profile']['company'], 'Acme Chemicals')

    def test_top_companies_json_contract_has_stable_required_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

        payload = build_top_companies_export(companies, sites, limit=1)
        self.assertEqual(set(payload.keys()), {'export_info', 'companies'})

        export_info = payload['export_info']
        self.assertTrue({
            'timestamp',
            'description',
            'total_companies',
            'filtered_company_count',
            'exported_company_count',
            'limit',
            'filters',
        }.issubset(export_info.keys()))

        self.assertEqual(len(payload['companies']), 1)
        company = payload['companies'][0]
        self.assertEqual(set(company.keys()), {
            'rank',
            'company_profile',
            'priority_score',
            'score_breakdown',
            'priority_reasons',
            'best_recommended_site',
        })
        self.assertTrue({
            'company',
            'company_info',
            'location',
            'city',
            'state',
            'segment',
            'commodity',
            'commodity_type',
            'inbound_materials',
            'outbound_products',
            'why_target',
            'omnitrax_outreach_angle',
        }.issubset(company['company_profile'].keys()))
        self.assertTrue({
            'site_name',
            'site_location',
            'site_match_score',
            'matching_reasons',
            'site_profile',
        }.issubset(company['best_recommended_site'].keys()))

    def test_top_companies_cli_writes_filtered_ranked_json_from_temp_project_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)
            result = subprocess.run(
                [
                    sys.executable,
                    os.path.join(ROOT_DIR, 'main.py'),
                    '--top-companies',
                    '--limit', '1',
                    '--state', 'TX',
                    '--segment', 'Chemicals',
                    '--commodity', 'chemicals',
                    '--min-score', '1',
                ],
                cwd=tmpdir,
                text=True,
                capture_output=True,
                check=False,
            )

            export_dir = os.path.join(tmpdir, 'exports')
            exported_files = os.listdir(export_dir)
            top_company_files = [
                name for name in exported_files
                if name.startswith('top_companies_') and name.endswith('.json')
            ]

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(top_company_files), 1)

            with open(os.path.join(export_dir, top_company_files[0])) as top_companies_file:
                payload = json.load(top_companies_file)

        self.assertIn('Exported top companies to', result.stdout)
        self.assertEqual(payload['export_info']['filters']['state'], 'TX')
        self.assertEqual(payload['export_info']['exported_company_count'], 1)
        self.assertEqual(payload['companies'][0]['company_profile']['company'], 'Acme Chemicals')
        self.assertEqual(payload['companies'][0]['best_recommended_site']['site_name'], 'Houston Rail Park')

    def test_top_companies_cli_rejects_invalid_limit_and_min_score_arguments(self):
        invalid_cases = [
            (['--limit', '0'], '--limit must be at least 1'),
            (['--min-score', '-1'], '--min-score must be between 0 and 100'),
            (['--min-score', '101'], '--min-score must be between 0 and 100'),
        ]

        for extra_args, expected_message in invalid_cases:
            with self.subTest(extra_args=extra_args):
                with tempfile.TemporaryDirectory() as tmpdir:
                    result = subprocess.run(
                        [
                            sys.executable,
                            os.path.join(ROOT_DIR, 'main.py'),
                            '--top-companies',
                            *extra_args,
                        ],
                        cwd=tmpdir,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                    self.assertEqual(result.returncode, 1)
                    self.assertIn(expected_message, result.stdout)
                    self.assertFalse(os.path.exists(os.path.join(tmpdir, 'exports')))

    def test_company_report_json_includes_profile_priority_and_top_sites(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

            export_dir = os.path.join(tmpdir, 'exports')
            with contextlib.redirect_stdout(io.StringIO()):
                report_path = export_company_report_json(
                    'Acme Chemicals',
                    companies,
                    sites,
                    output_dir=export_dir,
                )

            with open(report_path) as report_file:
                report = json.load(report_file)

        self.assertTrue(os.path.basename(report_path).startswith('company_report_acme_chemicals_'))
        self.assertEqual(report['export_info']['company_query'], 'Acme Chemicals')
        self.assertEqual(report['export_info']['matched_company'], 'Acme Chemicals')
        self.assertEqual(report['company_profile']['company'], 'Acme Chemicals')
        self.assertEqual(report['company_profile']['location'], 'Houston, TX')
        self.assertIn('score', report['priority'])
        self.assertIn('breakdown', report['priority'])
        self.assertIn('reasons', report['priority'])
        self.assertGreaterEqual(len(report['priority']['reasons']), 1)
        self.assertEqual(len(report['top_site_matches']), 2)
        self.assertEqual(report['top_site_matches'][0]['site_name'], 'Houston Rail Park')
        self.assertIn('compatibility_score', report['top_site_matches'][0])
        self.assertIn('matching_reasons', report['top_site_matches'][0])

    def test_company_report_cli_writes_json_from_temp_project_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)
            result = subprocess.run(
                [sys.executable, os.path.join(ROOT_DIR, 'main.py'), '--company-report', 'Acme Chemicals'],
                cwd=tmpdir,
                text=True,
                capture_output=True,
                check=False,
            )

            export_dir = os.path.join(tmpdir, 'exports')
            exported_files = os.listdir(export_dir)
            report_files = [
                name for name in exported_files
                if name.startswith('company_report_acme_chemicals_') and name.endswith('.json')
            ]

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(report_files), 1)

            with open(os.path.join(export_dir, report_files[0])) as report_file:
                report = json.load(report_file)

        self.assertIn('Exported company report to', result.stdout)
        self.assertEqual(report['company_profile']['company'], 'Acme Chemicals')
        self.assertEqual(len(report['top_site_matches']), 2)

    def test_site_report_json_includes_profile_and_top_company_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

            export_dir = os.path.join(tmpdir, 'exports')
            with contextlib.redirect_stdout(io.StringIO()):
                report_path = export_site_report_json(
                    'Houston Rail Park',
                    sites,
                    companies,
                    output_dir=export_dir,
                )

            with open(report_path) as report_file:
                report = json.load(report_file)

        self.assertTrue(os.path.basename(report_path).startswith('site_report_houston_rail_park_'))
        self.assertEqual(report['export_info']['site_query'], 'Houston Rail Park')
        self.assertEqual(report['export_info']['matched_site'], 'Houston Rail Park')
        self.assertEqual(report['site_profile']['site_name'], 'Houston Rail Park')
        self.assertEqual(report['site_profile']['location'], 'Houston, TX')
        self.assertEqual(len(report['top_matched_companies']), 2)
        self.assertEqual(report['top_matched_companies'][0]['company'], 'Acme Chemicals')
        self.assertIn('compatibility_score', report['top_matched_companies'][0])
        self.assertIn('matching_reasons', report['top_matched_companies'][0])
        self.assertGreaterEqual(len(report['top_matched_companies'][0]['matching_reasons']), 1)

    def test_site_report_cli_writes_json_from_temp_project_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)
            result = subprocess.run(
                [sys.executable, os.path.join(ROOT_DIR, 'main.py'), '--site-report', 'Houston Rail Park'],
                cwd=tmpdir,
                text=True,
                capture_output=True,
                check=False,
            )

            export_dir = os.path.join(tmpdir, 'exports')
            exported_files = os.listdir(export_dir)
            report_files = [
                name for name in exported_files
                if name.startswith('site_report_houston_rail_park_') and name.endswith('.json')
            ]

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(report_files), 1)

            with open(os.path.join(export_dir, report_files[0])) as report_file:
                report = json.load(report_file)

        self.assertIn('Exported site report to', result.stdout)
        self.assertEqual(report['site_profile']['site_name'], 'Houston Rail Park')
        self.assertEqual(len(report['top_matched_companies']), 2)

    def test_company_and_site_directories_are_json_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

        company_directory = build_company_directory(companies)
        site_directory = build_site_directory(sites)

        self.assertEqual(company_directory[0]['company'], 'Acme Chemicals')
        self.assertIn('priority_score', company_directory[0])
        self.assertIn('best_recommended_site', company_directory[0])
        self.assertEqual([site['site_name'] for site in site_directory], ['Denver Industrial Yard', 'Houston Rail Park'])
        self.assertEqual(site_directory[1]['location'], 'Houston, TX')

    def test_list_sites_and_companies_cli_print_json_from_temp_project_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)
            sites_result = subprocess.run(
                [sys.executable, os.path.join(ROOT_DIR, 'main.py'), '--list-sites'],
                cwd=tmpdir,
                text=True,
                capture_output=True,
                check=False,
            )
            companies_result = subprocess.run(
                [sys.executable, os.path.join(ROOT_DIR, 'main.py'), '--list-companies'],
                cwd=tmpdir,
                text=True,
                capture_output=True,
                check=False,
            )

        sites_payload = json.loads(sites_result.stdout)
        companies_payload = json.loads(companies_result.stdout)

        self.assertEqual(sites_result.returncode, 0, sites_result.stderr)
        self.assertEqual(companies_result.returncode, 0, companies_result.stderr)
        self.assertEqual(sites_payload['export_info']['total_sites'], 2)
        self.assertEqual(companies_payload['export_info']['total_companies'], 2)
        self.assertEqual(sites_payload['sites'][1]['site_name'], 'Houston Rail Park')
        self.assertEqual(companies_payload['companies'][0]['company'], 'Acme Chemicals')

    def test_map_generation_smoke_writes_html_files_to_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_sample_data_dir(tmpdir)

            previous_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                segments, companies, sites, rail_infrastructure = main.load_data()
            finally:
                os.chdir(previous_cwd)

            map_dir = os.path.join(tmpdir, 'maps')
            with contextlib.redirect_stdout(io.StringIO()):
                company_map = generate_company_map(companies, output_dir=map_dir)
                sites_map = generate_sites_map(sites, output_dir=map_dir)
                top_map = generate_top_opportunities_map(companies, limit=2, output_dir=map_dir)
                geographic_map = generate_geographic_opportunity_map(companies, rail_infrastructure, output_dir=map_dir)

            expected_maps = [company_map, sites_map, top_map, geographic_map]
            for map_path in expected_maps:
                self.assertTrue(os.path.exists(map_path), map_path)
                self.assertGreater(os.path.getsize(map_path), 1000)

            with open(company_map) as company_map_file:
                company_map_content = company_map_file.read()
            with open(sites_map) as sites_map_file:
                sites_map_content = sites_map_file.read()
            with open(top_map) as top_map_file:
                top_map_content = top_map_file.read()
            with open(geographic_map) as geographic_map_file:
                geographic_map_content = geographic_map_file.read()

        self.assertIn('Acme Chemicals', company_map_content)
        self.assertIn('Denver Industrial Yard', sites_map_content)
        self.assertIn('#1 Opportunity', top_map_content)
        self.assertIn('Geographic Opportunity Score', geographic_map_content)

    def test_curated_omnitrax_source_data_loads_and_contains_current_sites(self):
        previous_cwd = os.getcwd()
        try:
            os.chdir(ROOT_DIR)
            segments, companies, sites, rail_infrastructure = main.load_data()
        finally:
            os.chdir(previous_cwd)

        site_names = {site.get('site_name') for site in sites}
        rail_locations = {record.get('location') for record in rail_infrastructure}
        company_names = {company.get('company') for company in companies}

        self.assertIn('Savannah Gateway Industrial Hub', site_names)
        self.assertIn('Access 25 Logistics Park', site_names)
        self.assertIn('Port of Brownsville Industrial Development Area', site_names)
        self.assertIn('River Ridge Commerce Center', site_names)
        self.assertIn('Savannah Industrial Transportation', rail_locations)
        self.assertIn('Central Texas & Colorado River Railway', rail_locations)
        self.assertIn('Sunrise Industrial Rail', rail_locations)
        self.assertIn('Hyundai Motor Group', company_names)

        for site in sites:
            with self.subTest(site=site.get('site_name')):
                self.assertTrue(site.get('site_name'))
                self.assertTrue(site.get('city'))
                self.assertTrue(site.get('state'))
                self.assertTrue(site.get('rail_served'))
                self.assertTrue(site.get('nearby_class1'))
                self.assertTrue(site.get('transload_available'))
                self.assertTrue(site.get('interstate_access'))
                self.assertTrue(site.get('port_access'))
                self.assertTrue(site.get('target_industries'))
                self.assertTrue(site.get('source_url'))
                self.assertTrue(site.get('source_confidence'))
                self.assertTrue(site.get('last_verified'))

    def test_known_omnitrax_site_appears_in_directory_and_matching_scores_are_valid(self):
        previous_cwd = os.getcwd()
        try:
            os.chdir(ROOT_DIR)
            segments, companies, sites, _ = main.load_data()
        finally:
            os.chdir(previous_cwd)

        site_directory = build_site_directory(sites)
        directory_names = [site.get('site_name') for site in site_directory]
        self.assertIn('Savannah Gateway Industrial Hub', directory_names)

        company = next(company for company in companies if company.get('company') == 'Hyundai Motor Group')
        site = next(site for site in sites if site.get('site_name') == 'Savannah Gateway Industrial Hub')
        compatibility_score = calculate_site_compatibility_score(company, site)

        self.assertGreaterEqual(compatibility_score, 0)
        self.assertLessEqual(compatibility_score, 100)
        self.assertGreaterEqual(compatibility_score, 75)

    def test_current_csv_files_have_no_malformed_records(self):
        previous_cwd = os.getcwd()
        try:
            os.chdir(ROOT_DIR)
            issues = main.validate_data_files()
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(issues, [])


if __name__ == '__main__':
    unittest.main()
