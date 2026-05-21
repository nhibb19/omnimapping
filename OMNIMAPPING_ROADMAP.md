# OmniMapping Roadmap

## Project Overview
OmniMapping is a comprehensive CLI-driven economic development platform for rail-served industrial opportunity analysis. It processes validated CSV datasets of companies, industrial sites, rail infrastructure, and market segments to calculate priority scores, generate opportunity briefs, perform site matching, and support data exports and interactive map generation. The platform enhances company records with geographic intelligence and provides detailed scoring breakdowns for informed decision-making.

## Current Architecture
The application follows a modular architecture centered around a CLI interface in `main.py`, with specialized modules handling different aspects of the system:

- **`main.py`**: Application entry point, data loading orchestration, and CLI menu system. Coordinates data validation, normalization, geographic enhancement, scoring calculations, and user interactions.
- **`dashboard.py`**: Lightweight local Flask dashboard entry point. Reuses `main.load_data()` plus existing scoring, search, matching, and export helpers to present browser-based company and site workflows.
- **`modules/ui.py`**: User interface components including CSV validation, data normalization functions, display formatting, opportunity brief generation, and user input handling.
- **`modules/scoring.py`**: Core scoring algorithms for company priority assessment, including site compatibility, freight intensity, land needs, multimodal potential, industry fit, and strategic alignment.
- **`modules/search.py`**: Search and filtering functionality for companies and sites, including keyword search, state/commodity filtering, and best-site matching algorithms.
- **`modules/export.py`**: Data export capabilities for CSV, JSON, and text formats, supporting opportunity briefs, company profiles, site/company report discovery, focused company reports, focused site reports, and site matching reports.
- **`modules/geography.py`**: Geographic analysis functions for clustering, distance calculations, and regional insights.
- **`modules/geographic_scoring.py`**: Advanced geographic intelligence for multimodal logistics, port access, rail hub proximity, and location-based scoring enhancements.
- **`templates/`**: Flask dashboard templates for ranked companies, company profiles, industrial site lists, and site profiles.

## Data Flow
1. **Data Loading**: Load and validate CSV files from `data/` directory (companies.csv, industrial_sites.csv, rail_infrastructure.csv, segments.csv).
2. **Normalization**: Standardize record formats and handle missing data.
3. **Geographic Enhancement**: Enrich company records with rail infrastructure proximity, multimodal access, and regional intelligence.
4. **Scoring**: Calculate priority scores for each company based on site compatibility, freight needs, and strategic fit.
5. **User Interaction**: Provide CLI menus and a local Flask dashboard for searching, filtering, viewing profiles, generating briefs, site matching, exports, and map generation.
6. **Output Generation**: Produce exports in `exports/` and interactive maps in `maps/`.

## Current Modules and Functionality
- **Data Management**: Robust CSV loading with validation and normalization.
- **Scoring System**: Multi-factor priority scoring with detailed breakdowns and risk assessments.
- **Search & Filtering**: Advanced search by keywords, state, commodity, score thresholds, and segments.
- **Site Matching**: Algorithmic matching of companies to optimal industrial sites with compatibility scores.
- **Export Capabilities**: Multiple export formats for opportunities, briefs, profiles, focused company/site JSON reports, report target directories, and matching reports.
- **Map Generation**: Interactive HTML maps for companies, sites, and top opportunities.
- **Geographic Analysis**: Clustering analysis, multimodal logistics profiling, and geographic opportunity mapping.

## Completed Scoring/UI Updates
- **Scoring Model**: Fully implemented with priority scores, score breakdowns, and qualitative labels (site match quality, freight intensity, infrastructure dependency).
- **UI Enhancements**: CLI menus with detailed company profiles, opportunity briefs, verification summaries, and risk assessments.
- **Data Integration**: Geographic intelligence integrated into scoring, with enhanced company records including best site matches and multimodal profiles.
- **Export Features**: Comprehensive export options for top opportunities, all companies, briefs, profiles, and site matching reports.
- **Non-Interactive CLI Reports**: Added `--export-summary`, `--top-companies`, `--company-report`, `--site-report`, `--list-companies`, and `--list-sites` for scriptable JSON workflows.
- **Ranked Company JSON Export**: Added `--top-companies` with optional `--limit`, `--state`, `--segment`, `--commodity`, and `--min-score` filters. The export includes company profile basics, priority score, score breakdown, priority reasons, best recommended site, and site match score.
- **Test Coverage**: Added unit and CLI tests for scoring, validation, exports, ranked company JSON export, invalid ranked-export arguments, focused reports, report target directories, maps, and verification workflows.
- **Verification Automation**: Added a lightweight local check script and GitHub Actions workflow that run `python3 main.py --verify` and `python3 -m unittest discover -s tests`.
- **Map Visualization**: Generated maps for companies, industrial sites, and top opportunities with interactive features.
- **Local Web Dashboard**: Added a Flask dashboard for non-technical users with a Command Center landing page, ranked company filters, readiness filters, company detail profiles, industrial site views, top compatible company lists, saved workflow shortcuts, CSV/JSON/TXT download actions, route tests, and a `python3 dashboard.py --smoke-test` command.
- **Opportunity Workspace**: Added a decision-oriented dashboard workspace that combines one company and one industrial site, reusing existing scoring, matching, priority reason, next-action, and brief-generation helpers. The workspace includes pair fit, risks/data gaps, talking points, JSON export, and TXT outreach brief export.
- **Company Site Comparison**: Added a dashboard comparison view for one selected company that ranks top compatible sites, shows key site attributes side by side, includes matching reasons and confirmation items, recommends a first-choice site, links each site to the Opportunity Workspace, and provides JSON/CSV downloads.
- **Command Center Workflow Layer**: Added `/`, `/pipeline`, and `/verification` routes that organize opportunities by next action, prioritize site verification tasks, surface territory plays, and export a plain-text opportunity packet at `/downloads/opportunity-packet.txt`.
- **OmniTRAX Source Data Refresh**: Refreshed source CSVs against official OmniTRAX pages researched on 2026-05-06. `data/rail_infrastructure.csv` now accounts for 37 current OmniTRAX locations from the official locations directory, including railroads, industrial parks, port/terminal railroads, and named development assets. `data/industrial_sites.csv` now includes 28 practical economic-development sites, corridors, transload terminals, ports, and rail-served industrial parks, including Access 25 Logistics Park, Great Western Industrial Park, Savannah Gateway Industrial Hub, Brownsville, River Ridge, Port Muskogee, Port of Catoosa, Stockton, Chicago Rail Link, and other served-market assets. `data/companies.csv` now contains a stronger 64-company prospect universe with speculative prospect language in `why_target` where appropriate. `data/segments.csv` now includes a dedicated Chemicals segment for bulk chemical and resin prospects.
- **Data Source Traceability**: Added `docs/data_sources.md` with source URLs, research date, assumptions, and remaining gaps. README now links to this source note.
- **Data Quality Tests**: Added focused tests that load the curated live data, check required site fields, confirm known current OmniTRAX assets appear in site directory output, verify a Savannah Gateway compatibility score, and assert current CSV validation catches no malformed records.
- **Source Confidence And Freshness Upgrade**: Added optional `source_url`, `source_confidence`, `last_verified`, and `data_gap_notes` metadata for industrial sites and rail infrastructure. Verification now prints source-confidence counts and confirmation flags for acreage, approximate coordinates, and missing Class I/interstate/port/transload details. Dashboard site pages show confidence, last verified date, source/gap notes, and a "Needs confirmation" indicator.
- **Site Discovery Filters**: Expanded the dashboard industrial site directory with filters for state, port access, transload availability, and source confidence while preserving existing scoring and matching logic.

## Real Risks and Challenges
- **Data Quality Dependency**: Heavy reliance on accurate CSV data; changes to file formats or missing fields could break functionality.
- **Scalability**: Current implementation processes data in memory; large datasets may impact performance.
- **Testing Gaps**: Automated tests now cover the main scoring, validation, export, report, and map-generation paths. CI is lightweight and should be expanded if future phases add packaging, linting, or a web/API surface.
- **Dashboard Scope**: The local Flask dashboard improves accessibility for non-technical users, but it is currently single-user and local-only. It does not include authentication, deployed hosting, or a formal API.
- **Dependency Management**: Python environment and package versions (from requirements.txt) need careful management.
- **Data Validation**: While basic validation exists, complex data integrity issues may not be caught.
- **Geographic Accuracy**: Reliance on coordinate data for mapping and distance calculations; inaccuracies could affect scoring.
- **Public Source Limits**: Official OmniTRAX pages confirm the current footprint and many interchanges/services, but parcel-level acreage, exact coordinates, utilities, pricing, and active availability still need human confirmation before external marketing.
- **Trust Metadata Is Advisory**: Source confidence and data gaps are designed to speed screening and confirmation workflows. They intentionally do not alter the scoring model, so users should treat them as decision support rather than weighted ranking signals.

## Next 3 Implementation Phases

### Phase 1: Testing and Quality Assurance (Q1 2026)
- Continue expanding unit tests for scoring edge cases, data normalization, and export functions as new features are added.
- Continue adding integration tests for data loading and CLI workflows.
- Maintain the lightweight CI workflow for automated verification and unittest coverage.
- Create data validation scripts to ensure CSV integrity and consistency.
- Document testing procedures and expected outputs for key features.

### Phase 2: User Interface and Accessibility Enhancements (Q2 2026)
- Expand the local Flask dashboard based on user feedback, especially configurable saved views, comparison filtering, clearer export naming, and workspace workflow refinements.
- Add API endpoints for programmatic access to scoring and search functionality.
- Implement advanced filtering and visualization in the web interface.
- Create user documentation and guided workflows.
- Improve error handling and user feedback across all interfaces.

### Phase 3: Advanced Analytics and Deployment (Q3-Q4 2026)
- Integrate machine learning for predictive opportunity scoring.
- Add real-time data integration capabilities (APIs for rail infrastructure updates).
- Implement cloud deployment options (AWS/Azure) with containerization.
- Develop advanced geographic analytics (route optimization, supply chain modeling).
- Create multi-user collaboration features and audit logging.

## Run Command
From the project root:
```bash
python3 main.py
```

For the local dashboard:
```bash
python3 dashboard.py --port 5002
```

Then open `http://127.0.0.1:5002`. If no port is provided, Flask uses the dashboard default.

## Verification
To verify the current implementation:
- Run `./scripts/check.sh` to execute the same verification commands used by CI. The script automatically uses `.venv/bin/python` when the local virtual environment is present.
- Run `source .venv/bin/activate && python3 main.py --verify` and confirm successful data loading with explicit pass/fail checks.
- In the `--verify` output, confirm the `Data Quality Summary` shows source-confidence counts, blank acreage sites, approximate coordinate records, missing detail counts, and records needing confirmation.
- Run `source .venv/bin/activate && python3 -m unittest discover -s tests` for the full test suite.
- Run `source .venv/bin/activate && python3 dashboard.py --smoke-test` for a fast dashboard route check.
- Test search, filtering, and export functionalities.
- Open the dashboard and verify the Command Center, Opportunity Pipeline, Verification Queue, ranked company filters, readiness filters, company detail pages, industrial site filters, industrial site confidence/gap display, Opportunity Workspace links, saved shortcuts, and download actions.
- Open `http://127.0.0.1:5002/downloads/opportunity-packet.txt` and confirm the packet includes pipeline counts, top verification items, and territory plays.
- Open `http://127.0.0.1:5002/workspace?company=Nucor&site=Savannah%20Gateway%20Industrial%20Hub` and confirm pair fit, risks/data gaps, talking points, next action, JSON download, and TXT brief download.
- Open `http://127.0.0.1:5002/companies/Nucor/site-comparison` and confirm the selected company basics, priority score, top compatible sites table, first-choice recommendation, workspace links, JSON download, and CSV download.
- Run `python3 main.py --top-companies --limit 10 --min-score 70` and inspect the generated `exports/top_companies_<timestamp>.json`.
- Check generated maps in `maps/` directory.
- Validate scoring outputs and opportunity briefs.

## Remaining Data Gaps

- Confirm active parcel availability, acreage, utilities, zoning, environmental/due-diligence status, and pricing with OmniTRAX or local economic development partners before using the site list externally.
- Replace city/service-area coordinates in `data/rail_infrastructure.csv` with exact GIS coordinates if OmniTRAX publishes map layers or site brochures with precise coordinates.
- Confirm transload capacity details such as car spots, storage capacity, commodity limits, and handling equipment where public pages only state that transloading is offered.
- Review company prospects with a business development lead before outreach; the prospect universe is intentionally realistic but speculative unless a current project is separately confirmed.
