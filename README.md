# OmniMapping Economic Development Platform

OmniMapping is a command-line economic development tool for rail-served industrial prospecting. It loads company, industrial site, segment, and rail infrastructure data from CSV files, computes priority scores, matches companies with candidate sites, and generates exports and interactive HTML maps.

## Directory Overview

```
/omnimapping/
├── main.py                     # Main application entry point
├── dashboard.py                # Local Flask dashboard entry point
├── requirements.txt            # Python dependencies
├── README.md                   # This documentation
├── data/                       # Input CSV data files
│   ├── companies.csv
│   ├── segments.csv
│   ├── industrial_sites.csv
│   └── rail_infrastructure.csv
├── modules/                    # Modular implementation
│   ├── ui.py
│   ├── scoring.py
│   ├── search.py
│   ├── export.py
│   ├── geography.py
│   └── geographic_scoring.py
├── scripts/
│   └── check.sh                # Local verification script
├── templates/                  # Flask dashboard pages
├── .github/workflows/
│   └── verify.yml              # CI verification workflow
├── exports/                    # Generated export files
├── maps/                       # Generated HTML maps
└── tests/                      # Unit tests
```

## Requirements

- Python 3.8 or newer
- Install dependencies:

```bash
pip install -r requirements.txt
```

## Project hygiene

- Source data lives in `data/`; generated CSV, JSON, TXT, and HTML outputs belong in `exports/` or `maps/`.
- `exports/`, `maps/`, Python caches, virtual environments, and local scratch copies are excluded by `.gitignore`.
- Root-level files such as `*_backup.*`, `*_fixed.*`, and `*_old.*` are treated as local working copies. Review them manually before deleting or promoting them into `data/`.
- Commit source changes only: application code, tests, docs, dependency manifests, and curated input data under `data/`.

## How to Run

Start the interactive OmniMapping menu:

```bash
cd "/Users/nickhibbard/Documents/GitHub/omnimapping"
python3 main.py
```

## Local Dashboard

Start the Flask dashboard for economic development review workflows:

```bash
cd "/Users/nickhibbard/Documents/GitHub/omnimapping"
python3 dashboard.py
```

The dashboard opens with ranked companies and includes:

- Quick search across company names, locations, commodities, inbound/outbound flows, outreach notes, and best-site names.
- State, segment, commodity, minimum score, and row-count filters for prioritizing outreach lists.
- Scan summaries that show ready-for-outreach counts, site-review needs, average priority, and rows currently shown.
- Clear action buttons for reviewing a company, opening a company-site workspace, comparing sites, and downloading filtered CSV/JSON outputs.

The Industrial Sites page includes:

- Quick search across site names, locations, target industries, and data gap notes.
- State, port, transload, source confidence, and confirmation-status filters.
- Scan summaries for ready sites, confirmation needs, rail/transload availability, and high-confidence sources.
- Confirmation flags and data-gap notes that make missing acreage, access details, or other site uncertainties visible before outreach.

Dashboard filters and display summaries do not change priority scoring or site compatibility scoring rules.

## Verification Command

Run a non-interactive verification flow that validates CSV files, loads data, computes scores, confirms all generated scores are within 0-100, verifies top opportunities sort by descending score, checks site matching, and prints a concise data quality summary. The quality summary counts records by source confidence and flags blank acreage, approximate rail coordinates, and missing Class I/interstate/port/transload details across site and rail records. Scoring rules do not use these metadata fields.

```bash
python3 main.py --verify
```

## Local Check Script

Run the same lightweight checks used by CI:

```bash
./scripts/check.sh
```

The script runs:

```bash
python3 main.py --verify
python3 -m unittest discover -s tests
python3 dashboard.py --smoke-test
```

If a local `.venv/` is present, the script automatically uses `.venv/bin/python` so dashboard dependencies such as Flask are available.

## CI Workflow

The GitHub Actions workflow in `.github/workflows/verify.yml` runs on pushes and pull requests. It installs `requirements.txt`, then runs the verification command and the full unittest suite.

## Summary Export Command

Write a compact non-interactive JSON summary with dataset counts, top opportunities, segment averages, state counts, and best site matches:

```bash
python3 main.py --export-summary
```

The command writes to `exports/summary_<timestamp>.json`.

## Top Companies Export Command

Write a non-interactive JSON export of ranked companies with company profile basics, priority score, score breakdown, priority reasons, best recommended site, and site match score:

```bash
python3 main.py --top-companies
```

Use optional filters to narrow the ranked export:

```bash
python3 main.py --top-companies --limit 10 --state TX --segment Chemicals --commodity chemicals --min-score 70
```

The command writes to `exports/top_companies_<timestamp>.json`.

## Company Report Command

Write a focused non-interactive JSON report for one company. The report includes the matched company profile, priority score and breakdown, priority reasons, and the top three available site matches with compatibility scores and matching reasons:

```bash
python3 main.py --company-report "Nucor"
```

The command writes to `exports/company_report_<safe_company_name>_<timestamp>.json`.

## Site Report Command

Write a focused non-interactive JSON report for one industrial site. The report includes the matched site profile and the top compatible companies with compatibility scores, matching reasons, priority scores, and priority reasons:

```bash
python3 main.py --site-report "Houston Ship Channel"
```

The command writes to `exports/site_report_<safe_site_name>_<timestamp>.json`.

## Discovery Commands

Print available companies or sites as JSON before generating focused reports:

```bash
python3 main.py --list-companies
python3 main.py --list-sites
```

## Running Tests

```bash
cd "/Users/nickhibbard/Documents/GitHub/omnimapping"
python3 -m unittest discover -s tests
```

## Main Menu Options

The main menu provides the following choices:

1. Search companies
2. Browse supply chain segments
3. Filter by state
4. Filter by commodity
5. Filter by minimum score
6. View top 20 opportunities
7. View company detail profile
8. Generate opportunity brief
9. Industrial site matching
10. Export ranked opportunities to CSV
11. Generate maps
12. Geographic intelligence & analysis
13. Exit

## Search & Filter Options

From the search menu you can:

1. Search companies by keyword
2. Filter by state
3. Filter by commodity type
4. Filter by minimum priority score
5. Browse companies by segment
6. Return to main menu

## Export Options

The export menu includes:

1. Export top 20 opportunities (CSV)
2. Export all companies (CSV)
3. Export opportunity briefs (TXT)
4. Export company profiles (JSON)
5. Export site matching report (CSV)
6. Return to main menu

### Export output locations

- `exports/top_20_opportunities.csv`
- `exports/all_companies.csv`
- `exports/opportunity_briefs/` (up to 10 text briefs)
- `exports/company_profiles_<timestamp>.json`
- `exports/site_matching_report_<timestamp>.csv`
- `exports/summary_<timestamp>.json`
- `exports/top_companies_<timestamp>.json`
- `exports/company_report_<safe_company_name>_<timestamp>.json`
- `exports/site_report_<safe_site_name>_<timestamp>.json`

## Map Generation Options

The map menu includes:

1. Generate company locations map
2. Generate industrial sites map
3. Generate top opportunities map
4. Return to main menu

### Map output locations

- `maps/companies_map.html`
- `maps/industrial_sites_map.html`
- `maps/top_<limit>_opportunities_map.html`

## Geographic Intelligence & Analysis

This menu includes:

1. View geographic profiles for all companies
2. Analyze geographic clustering by state
3. Generate geographic opportunity map
4. Export geographic profiles to CSV
5. View multimodal logistics analysis
6. Return to main menu

### Geographic analysis outputs

- `maps/geographic_opportunity_map.html`
- `exports/geographic_profiles.csv`

## Scoring Model

OmniMapping computes a composite priority score from 0 to 100 using rule-based sub-scores. The score is built from the following components:

- Rail fit
- Freight/logistics intensity
- Land intensity
- Multimodal potential
- Site match quality
- Industry fit
- Strategic fit

Site compatibility is calculated separately on a 0-100 scale using factors such as rail-served status, transload availability, port access, interstate access, industry match, state/region alignment, and acreage fit.

## Input Data Files

OmniMapping expects the following CSV files in `data/`:

- `data/companies.csv`
- `data/segments.csv`
- `data/industrial_sites.csv`
- `data/rail_infrastructure.csv`

Missing or invalid files will cause the application to print validation issues and exit.

## Source Data Notes

The curated OmniTRAX source-data refresh is documented in [docs/data_sources.md](/Users/nickhibbard/Documents/New project/omnimapping/docs/data_sources.md). It lists the official OmniTRAX pages used, the 2026-05-06 research date, and assumptions for approximate coordinates, public acreage gaps, and speculative company prospect records.

Industrial site and rail infrastructure CSVs now include optional source metadata fields:

- `source_url`
- `source_confidence`
- `last_verified`
- `data_gap_notes`

Older CSVs without these fields still load; missing confidence is reported as `Unspecified`.

## Local Web Dashboard

Start the lightweight local dashboard for a scanable, browser-based view of ranked companies and industrial sites:

```bash
cd "/Users/nickhibbard/Documents/New project/omnimapping"
python3 dashboard.py
```

Open `http://127.0.0.1:5000` in a browser. The dashboard keeps the CLI intact and uses the same data loading, scoring, search, site matching, and export helpers.

Dashboard views:

- Ranked companies with filters for state, segment, commodity, minimum score, and row limit.
- Company profile pages with priority score, score breakdown, priority reasons, best recommended site, top site matches, risk, and next action.
- Industrial site directory with filters for state, port access, transload availability, and source confidence.
- Industrial site pages with site details, data confidence, last verified date, data gaps, a "Needs confirmation" indicator, and top compatible companies.
- Opportunity Workspace pages that combine one company and one site into a decision-ready view with pair fit, risks/data gaps, talking points, and next action.
- Company Site Comparison pages that rank the selected company's top compatible sites side by side, identify a first-choice site, show fit reasons and confirmation items, and link each site into the Opportunity Workspace.
- CSV, JSON, and TXT download actions for ranked company lists, company reports, site reports, company site comparisons, workspace JSON, and workspace outreach briefs.

To open a workspace directly, use:

```text
http://127.0.0.1:5000/workspace?company=Nucor&site=Savannah%20Gateway%20Industrial%20Hub
```

To compare top site matches for one company, open the company profile and choose **Compare Top Sites**, or use:

```text
http://127.0.0.1:5000/companies/Nucor/site-comparison
```

The comparison page includes JSON and CSV download buttons for the comparison payload and table.

Run a quick route smoke test without starting a browser:

```bash
python3 dashboard.py --smoke-test
```

## Known Limitations

- Geographic intelligence is simplified and relies on hard-coded city/state lookups rather than live geocoding.
- Estimated rail distances and site coordinates are approximate.
- Opportunity brief export writes up to 10 briefs to `exports/opportunity_briefs/`.
- Geographic profiles CSV export writes to `exports/geographic_profiles.csv`.
- The dashboard is a local single-user Flask interface; it does not include authentication, background jobs, or hosted deployment configuration.
- Map generation requires `folium` and `geopy`.
- There is no external API or CRM integration in the current implementation.
- The scoring model is rule-based and heuristic-based, not a machine learning model.

## Development workflow

1. Create a new feature branch for your changes.
2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```
3. Install dependencies:

```bash
pip install -r requirements.txt
```
4. Verify the repository and data flow:

```bash
python3 main.py --verify
```
5. Generate a compact summary export:

```bash
python3 main.py --export-summary
```
6. Generate a ranked company JSON export:

```bash
python3 main.py --top-companies --limit 10 --min-score 70
```
7. Generate a focused company report:

```bash
python3 main.py --company-report "Nucor"
```
8. Generate a focused site report:

```bash
python3 main.py --site-report "Houston Ship Channel"
```
9. List valid company and site report targets:

```bash
python3 main.py --list-companies
python3 main.py --list-sites
```
10. Run unit tests:

```bash
python3 -m unittest discover -s tests
```
11. Optional: run the full verification and test checks together before sharing changes:

```bash
python3 main.py --verify && python3 -m unittest discover -s tests
```
12. Run the application interactively:

```bash
python3 main.py
```
13. Check the working tree before committing:

```bash
git status --short
git ls-files -o --exclude-standard
git ls-files -i -o --exclude-standard
```

The ignored-files check should show only disposable generated artifacts such as caches, maps, or exports.

## Notes

- Generated exports and maps are written to `exports/` and `maps/` respectively.
- The verification command provides a quick check for data loading, scoring, and site matching behavior.
- Use the main menu to explore company search, segment browsing, filtering, briefs, site matching, exports, and maps.
