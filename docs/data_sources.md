# OmniMapping Data Sources

Researched on 2026-05-06. This note documents the source trail for the curated OmniTRAX footprint and prospect data in `data/`.

## Primary OmniTRAX Sources

- OmniTRAX current locations directory: https://omnitrax.com/locations/
- OmniTRAX rail transportation overview: https://omnitrax.com/rail-transportation/
- OmniTRAX real estate and Rail-Ready Sites program: https://omnitrax.com/real-estate/
- OmniTRAX transloading services overview: https://omnitrax.com/transload-services-and-terminals/
- Access 25 Logistics Park: https://omnitrax.com/access-25/
- Savannah Gateway Industrial Hub and Savannah Industrial Transportation: https://omnitrax.com/savannah-gateway-industrial-hub-2/
- Brownsville & Rio Grande International Railway: https://omnitrax.com/brownsville-rio-grande/
- Port Muskogee Railroad: https://omnitrax.com/our-managed-railroad-port-muskogee-railroad-llc/
- River Ridge Development Authority and Commerce Center: https://omnitrax.com/river-ridge-development-authority/
- Stockton Terminal and Eastern Railroad: https://omnitrax.com/stockton-terminal-and-eastern-railroad/
- Alabama & Tennessee River Railway: https://omnitrax.com/alabama-tennessee-2/
- Central Texas & Colorado River Railway: https://omnitrax.com/central-texas-colorado-river-railway/

## Data Assumptions

- `rail_infrastructure.csv` is intended to account for every current location listed in the OmniTRAX locations directory where practical. Coordinates are approximate city or service-area coordinates for map display, not surveyed track coordinates.
- `industrial_sites.csv` emphasizes named industrial parks, rail-ready sites, transload locations, ports, terminal access points, and market corridors that economic development users can screen. Not every railroad corridor has a named available parcel in public OmniTRAX pages.
- Acreage is populated only where public sources provide a clear figure. Blank acreage means the asset is verified but public acreage was not confirmed.
- `nearby_class1`, `interstate_access`, `port_access`, and `target_industries` are derived from OmniTRAX location pages when available. Where a page is incomplete, values are conservative and should be confirmed before external marketing.
- `companies.csv` is a prospect universe, not a claim that each company has an active project. Speculative records say so in `why_target` and are selected for fit with OmniTRAX rail-served markets, heavy freight profiles, transload use cases, or industrial real estate demand.

## Source Metadata Fields

`industrial_sites.csv` and `rail_infrastructure.csv` include optional trust and freshness metadata:

- `source_url`: the official OmniTRAX page or the current locations directory used for the record.
- `source_confidence`: `High` for directly traceable official records, `Medium` for useful screening records derived from broader corridor/transload/location context, and `Unspecified` when older CSVs omit the field.
- `last_verified`: the date the source trail was last checked.
- `data_gap_notes`: human-readable confirmation items, such as blank public acreage, approximate coordinates, or missing parcel/capacity detail.

These fields are surfaced in verification and the dashboard only. They do not change company priority scores or site compatibility scores.

## Known Gaps For Human Confirmation

- Parcel-level availability, exact acreage, utilities, zoning, due-diligence status, and pricing require confirmation from OmniTRAX or local economic development partners.
- Some railroad pages confirm services and interchanges but do not publish specific transload site capacity, car spots, or commodity handling details.
- Several map coordinates are city-center approximations and should be replaced with precise coordinates if OmniTRAX publishes GIS layers or site brochures in a future update.

## Verification

Run `python3 main.py --verify` or `./scripts/check.sh` from the project root. The verification output includes a `Data Quality Summary` with source confidence counts, blank acreage count, approximate coordinate count, missing site and rail detail counts, and the number of site and rail records that need confirmation.
