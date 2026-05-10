"""
OmniMapping Data Loader
Handles loading and validation of CSV data files.
"""

import csv
import os
from pathlib import Path
from typing import Dict, List, Tuple

from config import (
    COMPANIES_FILE, SEGMENTS_FILE, SITES_FILE, RAIL_FILE,
    CITY_COORDINATES, DATA_DIR
)
from logger import get_logger
from modules.data_quality import annotate_rail_quality, annotate_site_quality

logger = get_logger(__name__)

def load_csv(filename: Path) -> List[Dict]:
    """Load CSV data into a list of dictionaries"""
    logger.debug(f"Loading CSV file: {filename}")
    with open(filename, newline="") as file:
        return list(csv.DictReader(file))

def validate_csv_file(filename: Path, required_fields=None, numeric_fields=None, allow_blank=None) -> List[str]:
    """Validate a single CSV file for malformed rows and field issues."""
    required_fields = required_fields or []
    numeric_fields = numeric_fields or []
    allow_blank = allow_blank or []
    issues = []

    logger.debug(f"Validating CSV file: {filename}")

    with open(filename, newline="") as file:
        reader = csv.DictReader(file, restkey="__extra__", restval="")
        if not reader.fieldnames or all(str(field).strip() == "" for field in reader.fieldnames):
            issues.append(f"{filename}: missing or invalid header row")
            return issues

        missing_headers = [field for field in required_fields if field not in reader.fieldnames]
        if missing_headers:
            issues.append(f"{filename}: missing required header(s): {', '.join(missing_headers)}")

        line_number = 1
        try:
            for line_number, row in enumerate(reader, start=2):
                if row.get("__extra__"):
                    issues.append(f"{filename}: extra columns on line {line_number}: {row['__extra__']}")

                for field in required_fields:
                    if field not in row:
                        continue
                    value = str(row.get(field, "")).strip()
                    if value == "" and field not in allow_blank:
                        issues.append(f"{filename}: missing required '{field}' on line {line_number}")

                for field in numeric_fields:
                    if field not in row:
                        continue
                    value = str(row.get(field, "")).strip()
                    if value == "":
                        if field not in allow_blank:
                            issues.append(f"{filename}: missing numeric field '{field}' on line {line_number}")
                    else:
                        try:
                            float(value)
                        except ValueError:
                            issues.append(f"{filename}: non-numeric value for '{field}' on line {line_number}: {value}")
        except csv.Error as exc:
            issues.append(f"{filename}: malformed CSV row at line {line_number}: {exc}")

    return issues

def normalize_yes_no(value: str) -> str:
    """Normalize yes/no fields for display while preserving unknown text."""
    normalized = str(value or '').strip()
    if normalized.lower() in {'yes', 'true', '1'}:
        return 'Yes'
    if normalized.lower() in {'no', 'false', '0'}:
        return 'No'
    return normalized

def resolve_data_files(data_dir=None) -> Dict[str, Path]:
    """Return the active data file paths, preferring the current project dir."""
    if data_dir is None:
        cwd_data_dir = Path.cwd() / "data"
        if cwd_data_dir.exists():
            data_dir = cwd_data_dir
        else:
            data_dir = DATA_DIR
    else:
        data_dir = Path(data_dir)

    return {
        "segments": data_dir / "segments.csv",
        "companies": data_dir / "companies.csv",
        "sites": data_dir / "industrial_sites.csv",
        "rail": data_dir / "rail_infrastructure.csv",
    }

def validate_data_files(data_dir=None) -> List[str]:
    """Validate all data CSV files prior to loading."""
    files = resolve_data_files(data_dir)
    file_specs = {
        files["segments"]: {
            "required_fields": ["segment", "stage", "rail_score", "reason", "omnitrax_angle", "commodity_type"],
            "numeric_fields": ["rail_score"]
        },
        files["companies"]: {
            "required_fields": ["company", "segment", "state", "city", "commodity_type", "rail_fit_score", "industrial_real_estate_score"],
            "numeric_fields": ["rail_fit_score", "industrial_real_estate_score"]
        },
        files["sites"]: {
            "required_fields": ["site_name", "state", "city", "rail_served", "nearby_class1", "transload_available", "interstate_access", "port_access", "target_industries"],
            "numeric_fields": ["acres"],
            "allow_blank": ["acres"]
        },
        files["rail"]: {
            "required_fields": ["location", "type", "latitude", "longitude", "rail_connections", "capacity_score", "logistics_score"],
            "numeric_fields": ["latitude", "longitude", "rail_connections", "capacity_score", "logistics_score"]
        }
    }

    issues = []
    for filename, spec in file_specs.items():
        if not filename.exists():
            issues.append(f"Missing data file: {filename}")
            continue
        issues.extend(validate_csv_file(filename,
                                        required_fields=spec.get("required_fields"),
                                        numeric_fields=spec.get("numeric_fields"),
                                        allow_blank=spec.get("allow_blank")))

    return issues

def normalize_segment_record(segment: Dict) -> Dict:
    """Normalize segment record fields"""
    return {
        'segment': segment.get('segment', ''),
        'stage': segment.get('stage', ''),
        'rail_score': int(segment.get('rail_score', 0)),
        'reason': segment.get('reason', ''),
        'omnitrax_angle': segment.get('omnitrax_angle', ''),
        'commodity_type': segment.get('commodity_type', ''),
    }

def normalize_company_record(company: Dict) -> Dict:
    """Normalize company record fields"""
    return {
        'company': company.get('company', ''),
        'segment': company.get('segment', ''),
        'state': company.get('state', ''),
        'city': company.get('city', ''),
        'commodity_type': company.get('commodity_type', ''),
        'rail_fit_score': int(company.get('rail_fit_score', 0)),
        'industrial_real_estate_score': int(company.get('industrial_real_estate_score', 0)),
        'inbound_materials': company.get('inbound_materials', ''),
        'outbound_products': company.get('outbound_products', ''),
        'why_target': company.get('why_target', ''),
        'omnitrax_outreach_angle': company.get('omnitrax_outreach_angle', ''),
        'latitude': None,
        'longitude': None,
        'nearest_major_city': '',
        'nearest_port': '',
        'nearest_class1_railroad': '',
        'estimated_rail_distance': 100,
    }

def normalize_site_record(site: Dict) -> Dict:
    """Normalize site record fields"""
    normalized = {
        'site_name': site.get('site_name', ''),
        'state': site.get('state', ''),
        'city': site.get('city', ''),
        'rail_served': normalize_yes_no(site.get('rail_served', '')),
        'nearby_class1': normalize_yes_no(site.get('nearby_class1', '')),
        'transload_available': normalize_yes_no(site.get('transload_available', '')),
        'interstate_access': normalize_yes_no(site.get('interstate_access', '')),
        'port_access': normalize_yes_no(site.get('port_access', '')),
        'target_industries': site.get('target_industries', ''),
        'acres': site.get('acres', ''),
        'source_confidence': site.get('source_confidence', ''),
        'source_url': site.get('source_url', ''),
        'last_verified': site.get('last_verified', ''),
        'data_gap_notes': site.get('data_gap_notes', ''),
    }
    return annotate_site_quality(normalized)

def normalize_rail_infrastructure_record(rail: Dict) -> Dict:
    """Normalize rail infrastructure record fields"""
    normalized = {
        'location': rail.get('location', ''),
        'type': rail.get('type', ''),
        'latitude': float(rail.get('latitude', 0)),
        'longitude': float(rail.get('longitude', 0)),
        'rail_connections': int(rail.get('rail_connections', 0)),
        'capacity_score': int(rail.get('capacity_score', 0)),
        'logistics_score': int(rail.get('logistics_score', 0)),
        'port_nearby': normalize_yes_no(rail.get('port_nearby', '')),
        'interstate_access': normalize_yes_no(rail.get('interstate_access', '')),
        'transload_hub': normalize_yes_no(rail.get('transload_hub', '')),
        'source_confidence': rail.get('source_confidence', ''),
        'source_url': rail.get('source_url', ''),
        'last_verified': rail.get('last_verified', ''),
        'data_gap_notes': rail.get('data_gap_notes', ''),
    }
    return annotate_rail_quality(normalized)

def enhance_company_geography(companies: List[Dict], rail_infrastructure: List[Dict]) -> List[Dict]:
    """Add geographic intelligence to company data"""
    logger.info("Enhancing company geography data")

    from modules.geography import calculate_rail_proximity_score

    for company in companies:
        city = company.get('city', '').strip()
        if city in CITY_COORDINATES:
            company['latitude'], company['longitude'] = CITY_COORDINATES[city]

        # Calculate rail proximity
        if company.get('latitude') and company.get('longitude'):
            distance, nearest_rail = calculate_rail_proximity_score(company, rail_infrastructure)
            if distance is not None:
                company['estimated_rail_distance'] = distance
                company['nearest_class1_railroad'] = nearest_rail.get('location', '') if nearest_rail else ''

    return companies

def load_data(data_dir=None) -> Tuple[List[Dict], List[Dict], List[Dict], List[Dict]]:
    """Load all data files"""
    logger.info("Loading all data files")

    files = resolve_data_files(data_dir)
    issues = validate_data_files() if data_dir is None else validate_data_files(data_dir)
    if issues:
        logger.error("Data validation issues found")
        for issue in issues:
            logger.error(f"- {issue}")
        raise ValueError("Data validation failed. Please fix the reported CSV issues before running OmniMapping.")

    try:
        segments = [normalize_segment_record(s) for s in load_csv(files["segments"])]
        companies = [normalize_company_record(c) for c in load_csv(files["companies"])]
        sites = [normalize_site_record(s) for s in load_csv(files["sites"])]
        rail_infrastructure = [normalize_rail_infrastructure_record(r) for r in load_csv(files["rail"])]

        # Enhance companies with geographic intelligence
        companies = enhance_company_geography(companies, rail_infrastructure)

        logger.info(f"Loaded {len(companies)} companies, {len(sites)} sites, {len(rail_infrastructure)} rail records")
        return segments, companies, sites, rail_infrastructure

    except FileNotFoundError as e:
        logger.error(f"Error loading data files: {e}")
        raise ValueError("Please ensure all data files are present in the data/ directory.")
