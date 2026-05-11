"""Supply chain definitions and company matching for dashboard workflows."""

from .scoring import safe_int


SUPPLY_CHAIN_DEFINITIONS = [
    {
        "slug": "pellets",
        "name": "Pellets",
        "group": "Bulk Materials",
        "summary": "Wood, iron, resin, feed, and processed bulk pellets that depend on repeatable inbound feedstock and covered storage.",
        "terms": ["pellet", "wood fiber", "pulp", "resin", "feed", "iron ore", "recovered fiber", "plastic"],
        "steps": [
            {
                "role": "Upstream inputs",
                "title": "Fiber, resin, ore, and feedstocks",
                "terms": ["wood fiber", "pulp", "resin", "iron ore", "feed"],
                "opportunity": "Confirm inbound carload volumes and storage requirements.",
            },
            {
                "role": "Processing",
                "title": "Pelletizing and conversion",
                "terms": ["paper", "packaging", "resin", "feed", "engineered materials"],
                "opportunity": "Target rail-served conversion sites and transload support.",
            },
            {
                "role": "Storage / transload",
                "title": "Covered storage and bulk transfer",
                "terms": ["storage", "transload", "distribution", "warehouse"],
                "opportunity": "Screen for covered storage, truck scale, and railcar unloading needs.",
            },
            {
                "role": "Downstream customers",
                "title": "Manufacturers and packaging users",
                "terms": ["building products", "packaging", "pipe", "food"],
                "opportunity": "Connect pellet flows to manufacturers with recurring inbound demand.",
            },
        ],
    },
    {
        "slug": "steel",
        "name": "Steel",
        "group": "Metals",
        "summary": "Scrap, iron units, mills, service centers, pipe, fabrication, and finished steel distribution.",
        "terms": ["steel", "scrap", "iron", "coil", "pipe", "tube", "metals", "rebar"],
        "steps": [
            {"role": "Upstream inputs", "title": "Scrap, iron units, alloys", "terms": ["scrap", "iron", "alloys"], "opportunity": "Look for bulk inbound rail and inventory yard requirements."},
            {"role": "Processing", "title": "Mills and pipe/tube production", "terms": ["steel mills", "pipe", "tube", "billets"], "opportunity": "Prioritize heavy manufacturing sites with rail service."},
            {"role": "Storage / transload", "title": "Coil, plate, and pipe inventory", "terms": ["service centers", "coil", "plate", "distribution"], "opportunity": "Offer rail-served laydown and metals transload options."},
            {"role": "Downstream customers", "title": "Fabricators, construction, energy", "terms": ["fabricated", "construction", "energy", "infrastructure"], "opportunity": "Match finished steel flows to regional demand nodes."},
        ],
    },
    {
        "slug": "chemicals",
        "name": "Chemicals",
        "group": "Chemicals",
        "summary": "Bulk chemicals, industrial gases, coatings, solvents, and railcar-friendly liquid or dry inputs.",
        "terms": ["chemical", "chemicals", "chlorine", "caustic", "solvents", "coatings", "industrial gases"],
        "steps": [
            {"role": "Upstream inputs", "title": "Feedstocks and intermediates", "terms": ["feedstocks", "chlorine", "caustic", "solvents"], "opportunity": "Confirm hazmat handling, tank storage, and railcar needs."},
            {"role": "Processing", "title": "Chemical manufacturing", "terms": ["chemical products", "specialty chemicals", "industrial gases"], "opportunity": "Prioritize sites with rail, utilities, and buffer compatibility."},
            {"role": "Storage / transload", "title": "Tank, railcar, and packaged storage", "terms": ["transload", "storage", "railcar", "warehouse"], "opportunity": "Surface transload-capable sites and rail-served storage options."},
            {"role": "Downstream customers", "title": "Coatings, plastics, and industrial users", "terms": ["coatings", "resins", "building products", "engineered materials"], "opportunity": "Link inbound chemicals to downstream producers already in the prospect list."},
        ],
    },
    {
        "slug": "agriculture",
        "name": "Agriculture",
        "group": "Food And Agriculture",
        "summary": "Grain, oilseeds, fertilizer, feed ingredients, and ag processing lanes.",
        "terms": ["agriculture", "grain", "oilseeds", "fertilizer", "feed", "agribusiness"],
        "steps": [
            {"role": "Upstream inputs", "title": "Grain, fertilizer, and feed", "terms": ["grain", "fertilizer", "feed"], "opportunity": "Screen for covered storage, blending, and seasonal surge capacity."},
            {"role": "Processing", "title": "Food and ingredient production", "terms": ["food ingredients", "agricultural products", "processing"], "opportunity": "Position rail-served processing and transload locations."},
            {"role": "Storage / transload", "title": "Elevators, warehouses, and river/rail transfer", "terms": ["bulk handling", "transload", "warehouse", "river"], "opportunity": "Prioritize rail plus port or river access where available."},
            {"role": "Downstream customers", "title": "Food, feed, and export channels", "terms": ["food", "feed", "export", "prepared foods"], "opportunity": "Connect ag flows to food and cold-chain users."},
        ],
    },
    {
        "slug": "automotive",
        "name": "Automotive",
        "group": "Advanced Manufacturing",
        "summary": "OEM plants, supplier parks, components, batteries, steel, and finished vehicle logistics.",
        "terms": ["automotive", "vehicles", "components", "parts", "batteries", "supplier"],
        "steps": [
            {"role": "Upstream inputs", "title": "Steel, batteries, parts", "terms": ["steel", "batteries", "components", "parts"], "opportunity": "Identify inbound component and metal storage needs."},
            {"role": "Processing", "title": "Assembly and supplier manufacturing", "terms": ["automotive plants", "vehicles", "supplier"], "opportunity": "Target supplier parks and rail-served industrial sites."},
            {"role": "Storage / transload", "title": "Parts sequencing and finished goods staging", "terms": ["logistics", "warehouse", "distribution"], "opportunity": "Offer rail-adjacent space for sequencing and overflow."},
            {"role": "Downstream customers", "title": "Dealers, parts networks, and export lanes", "terms": ["vehicles", "logistics", "consumer goods"], "opportunity": "Connect road, port, and rail options for outbound coverage."},
        ],
    },
    {
        "slug": "construction-materials",
        "name": "Construction Materials",
        "group": "Bulk Materials",
        "summary": "Aggregates, cement, wallboard, precast products, insulation, and heavy building-products flows.",
        "terms": ["construction", "aggregates", "cement", "gypsum", "building materials", "wallboard", "precast"],
        "steps": [
            {"role": "Upstream inputs", "title": "Aggregates, cement, gypsum, additives", "terms": ["aggregates", "cement", "gypsum", "additives"], "opportunity": "Confirm bulk inbound volumes and storage form."},
            {"role": "Processing", "title": "Concrete, wallboard, and precast production", "terms": ["concrete", "wallboard", "precast", "building products"], "opportunity": "Match heavy inbound needs to rail-served production sites."},
            {"role": "Storage / transload", "title": "Bulk terminals and laydown yards", "terms": ["terminal", "transload", "storage", "yard"], "opportunity": "Prioritize rail-served bulk terminals and truck distribution points."},
            {"role": "Downstream customers", "title": "Infrastructure and regional construction markets", "terms": ["infrastructure", "construction", "distribution"], "opportunity": "Tie sites to regional growth and highway access."},
        ],
    },
    {
        "slug": "energy",
        "name": "Energy",
        "group": "Energy",
        "summary": "Fertilizer, LNG-adjacent equipment, pipe, industrial gas, and energy infrastructure materials.",
        "terms": ["energy", "natural gas", "lng", "fertilizer", "pipe", "industrial gas", "nitrogen"],
        "steps": [
            {"role": "Upstream inputs", "title": "Gas, pipe, steel, equipment", "terms": ["natural gas", "pipe", "steel", "equipment"], "opportunity": "Screen for project cargo, pipe storage, and heavy industrial access."},
            {"role": "Processing", "title": "Fertilizer, gases, and energy equipment", "terms": ["fertilizer", "industrial gases", "nitrogen", "equipment"], "opportunity": "Target rail-served industrial development sites."},
            {"role": "Storage / transload", "title": "Pipe yards and bulk terminals", "terms": ["pipe", "terminal", "storage", "transload"], "opportunity": "Confirm laydown, crane, and bulk-transfer needs."},
            {"role": "Downstream customers", "title": "Utilities, construction, and export infrastructure", "terms": ["energy", "construction", "export", "infrastructure"], "opportunity": "Position sites around corridors with heavy project demand."},
        ],
    },
    {
        "slug": "forest-products",
        "name": "Forest Products",
        "group": "Forest Products",
        "summary": "Wood fiber, pulp, paper, packaging, building products, and recovered fiber flows.",
        "terms": ["forest", "wood", "pulp", "paper", "packaging", "recovered fiber", "containerboard"],
        "steps": [
            {"role": "Upstream inputs", "title": "Wood fiber, pulp, recovered fiber", "terms": ["wood fiber", "pulp", "recovered fiber"], "opportunity": "Confirm inbound railcar or bale storage requirements."},
            {"role": "Processing", "title": "Paper, packaging, building products", "terms": ["paper", "packaging", "building products", "containerboard"], "opportunity": "Target manufacturing and storage sites with rail access."},
            {"role": "Storage / transload", "title": "Roll stock, bale, and finished product storage", "terms": ["storage", "distribution", "warehouse"], "opportunity": "Offer warehouse plus rail optionality for bulky inventory."},
            {"role": "Downstream customers", "title": "Packaging converters and construction channels", "terms": ["packaging products", "construction", "building products"], "opportunity": "Connect forest-products flows to manufacturers and DCs."},
        ],
    },
    {
        "slug": "food-cold-storage",
        "name": "Food / Cold Storage",
        "group": "Food And Agriculture",
        "summary": "Food manufacturing, refrigerated inputs, frozen goods, cold-chain warehousing, and port-connected distribution.",
        "terms": ["food", "cold storage", "frozen", "refrigerated", "prepared foods", "cold-chain"],
        "steps": [
            {"role": "Upstream inputs", "title": "Food inputs, packaging, refrigerated goods", "terms": ["food", "packaging", "refrigerated"], "opportunity": "Confirm temperature-control and lane requirements."},
            {"role": "Processing", "title": "Food manufacturing and packing", "terms": ["prepared foods", "food products", "manufacturing"], "opportunity": "Target highway-strong sites with rail optionality."},
            {"role": "Storage / transload", "title": "Cold-chain warehousing", "terms": ["cold storage", "frozen", "cold-chain", "warehouse"], "opportunity": "Surface large industrial sites for cold storage prospects."},
            {"role": "Downstream customers", "title": "Retail, foodservice, and export channels", "terms": ["distribution", "logistics", "export"], "opportunity": "Link cold storage users to port and interstate corridors."},
        ],
    },
    {
        "slug": "machinery",
        "name": "Machinery",
        "group": "Advanced Manufacturing",
        "summary": "Heavy equipment, agricultural machinery, aerospace components, oversized freight, and supplier inputs.",
        "terms": ["machinery", "equipment", "engines", "components", "aerospace", "construction and mining"],
        "steps": [
            {"role": "Upstream inputs", "title": "Steel, castings, engines, components", "terms": ["steel", "castings", "engines", "components"], "opportunity": "Confirm oversized inbound parts and heavy-haul constraints."},
            {"role": "Processing", "title": "Equipment and aerospace manufacturing", "terms": ["machinery", "equipment", "aerospace", "defense"], "opportunity": "Prioritize rail-served heavy industrial sites."},
            {"role": "Storage / transload", "title": "Oversized staging and distribution", "terms": ["oversized", "distribution", "storage", "logistics"], "opportunity": "Screen sites for laydown, clearance, and truck access."},
            {"role": "Downstream customers", "title": "Agriculture, construction, defense", "terms": ["agricultural equipment", "construction", "defense"], "opportunity": "Connect machinery flows to sector-specific demand regions."},
        ],
    },
    {
        "slug": "plastics-resins",
        "name": "Plastics / Resins",
        "group": "Chemicals",
        "summary": "Resin producers, plastics pipe, coatings inputs, engineered materials, and pelletized polymer flows.",
        "terms": ["plastic", "resin", "polymers", "pvc", "engineered materials", "pipe"],
        "steps": [
            {"role": "Upstream inputs", "title": "Hydrocarbons, resins, polymers", "terms": ["hydrocarbons", "resins", "polymers"], "opportunity": "Confirm hopper car, silo, and bulk-packaging requirements."},
            {"role": "Processing", "title": "Pipe, PVC, coatings, engineered materials", "terms": ["pipe", "pvc", "coatings", "engineered materials"], "opportunity": "Target manufacturers with resin-intensive inbound flows."},
            {"role": "Storage / transload", "title": "Resin transload and warehouse", "terms": ["transload", "warehouse", "storage", "distribution"], "opportunity": "Position rail-to-truck resin transfer and covered storage."},
            {"role": "Downstream customers", "title": "Construction, packaging, industrial users", "terms": ["construction", "packaging", "building products"], "opportunity": "Connect resin supply to high-volume converters."},
        ],
    },
    {
        "slug": "warehousing-distribution",
        "name": "Warehousing / Distribution",
        "group": "Logistics",
        "summary": "3PLs, intermodal partners, large industrial parks, truck-rail transfer, and regional distribution centers.",
        "terms": ["warehousing", "distribution", "logistics", "intermodal", "warehouse", "supply chain"],
        "steps": [
            {"role": "Upstream inputs", "title": "Consumer goods and industrial freight", "terms": ["consumer goods", "industrial goods", "freight"], "opportunity": "Understand lane density and tenant demand."},
            {"role": "Processing", "title": "Contract logistics and value-added services", "terms": ["contract logistics", "dedicated transportation", "logistics services"], "opportunity": "Target operators needing industrial real estate and multimodal optionality."},
            {"role": "Storage / transload", "title": "Warehouse, transload, and drayage nodes", "terms": ["warehouse", "transload", "drayage", "intermodal"], "opportunity": "Prioritize rail-served parks and port/interstate access."},
            {"role": "Downstream customers", "title": "Regional retail and industrial customers", "terms": ["distribution", "parcel", "consumer goods"], "opportunity": "Connect logistics users to existing industrial site workflows."},
        ],
    },
]


def normalize_text(value):
    """Normalize a string for simple keyword matching."""
    return str(value or "").strip().lower()


def company_search_text(company):
    """Build a searchable company string from existing OmniMapping fields."""
    fields = [
        "company",
        "segment",
        "commodity_type",
        "commodity",
        "inbound_materials",
        "outbound_products",
        "why_target",
        "omnitrax_outreach_angle",
    ]
    return " ".join(normalize_text(company.get(field)) for field in fields)


def matches_any_term(text, terms):
    """Return whether text contains any normalized matching term."""
    normalized = normalize_text(text)
    return any(normalize_text(term) in normalized for term in terms if normalize_text(term))


def rail_opportunity(company):
    """Classify a company as a strong prospect, rail-service possible, or monitor."""
    rail_fit = safe_int(company.get("rail_fit_score"), 0)
    priority_score = safe_int(company.get("priority_score"), 0)
    site_match_score = safe_int(company.get("best_site_match_score"), 0)

    if rail_fit >= 4 or priority_score >= 75 or site_match_score >= 75:
        return {"label": "Strong rail prospect", "tone": "positive"}
    if rail_fit >= 3 or priority_score >= 55 or site_match_score >= 50:
        return {"label": "Rail-service possible", "tone": "review"}
    return {"label": "Monitor", "tone": "neutral"}


def readiness_status(company):
    """Classify how ready a matched company is for follow-up."""
    priority_score = safe_int(company.get("priority_score"), 0)
    site_match_score = safe_int(company.get("best_site_match_score"), 0)
    best_site = company.get("best_site_name") or company.get("best_recommended_site")

    if priority_score >= 70 and site_match_score >= 60 and best_site:
        return {"label": "Ready for outreach", "tone": "positive", "rank": 3}
    if not best_site:
        return {"label": "Needs site review", "tone": "warning", "rank": 1}
    if priority_score >= 60 or site_match_score >= 50:
        return {"label": "Qualify fit", "tone": "review", "rank": 2}
    return {"label": "Monitor", "tone": "neutral", "rank": 0}


def summarize_companies(companies):
    """Return operational counts for a matched company set."""
    strong = [company for company in companies if rail_opportunity(company)["label"] == "Strong rail prospect"]
    possible = [company for company in companies if rail_opportunity(company)["label"] == "Rail-service possible"]
    ready = [company for company in companies if readiness_status(company)["label"] == "Ready for outreach"]
    site_review = [company for company in companies if readiness_status(company)["label"] == "Needs site review"]
    qualify = [company for company in companies if readiness_status(company)["label"] == "Qualify fit"]
    return {
        "count": len(companies),
        "strong_count": len(strong),
        "possible_count": len(possible),
        "monitor_count": max(0, len(companies) - len(strong) - len(possible)),
        "ready_count": len(ready),
        "site_review_count": len(site_review),
        "qualify_count": len(qualify),
        "readiness_monitor_count": max(0, len(companies) - len(ready) - len(site_review) - len(qualify)),
        "average_priority": round(
            sum(safe_int(company.get("priority_score"), 0) for company in companies) / len(companies),
            1,
        ) if companies else 0,
        "average_site_fit": round(
            sum(safe_int(company.get("best_site_match_score"), 0) for company in companies) / len(companies),
            1,
        ) if companies else 0,
    }


def matched_company_payload(company):
    """Build a compact company payload for supply-chain templates."""
    opportunity = rail_opportunity(company)
    readiness = readiness_status(company)
    best_site_name = company.get("best_site_name") or company.get("best_recommended_site", "")
    return {
        "company": company.get("company", ""),
        "segment": company.get("segment", ""),
        "commodity": company.get("commodity_type") or company.get("commodity", ""),
        "location": ", ".join(part for part in [company.get("city", ""), company.get("state", "")] if part),
        "priority_score": safe_int(company.get("priority_score"), 0),
        "rail_fit_score": safe_int(company.get("rail_fit_score"), 0),
        "best_site_name": best_site_name,
        "best_site_match_score": safe_int(company.get("best_site_match_score"), 0),
        "opportunity_label": opportunity["label"],
        "opportunity_tone": opportunity["tone"],
        "readiness_label": readiness["label"],
        "readiness_tone": readiness["tone"],
        "readiness_rank": readiness["rank"],
        "recommended_action": recommended_company_action(company, best_site_name, readiness["label"]),
    }


def recommended_company_action(company, best_site_name=None, readiness_label=None):
    """Return the next practical dashboard action for a matched company."""
    best_site_name = best_site_name or company.get("best_site_name") or company.get("best_recommended_site", "")
    readiness_label = readiness_label or readiness_status(company)["label"]
    if readiness_label == "Ready for outreach" and best_site_name:
        return "Open opportunity workspace and confirm outreach timing."
    if readiness_label == "Needs site review":
        return "Compare industrial sites and choose a first-choice location."
    if readiness_label == "Qualify fit":
        return "Validate material volumes, lane fit, and site requirements."
    return "Monitor as a market category and revisit when project signals improve."


def match_companies_for_definition(definition, companies):
    """Find companies relevant to one supply-chain definition."""
    terms = definition.get("terms", [])
    matched = [
        company for company in companies
        if matches_any_term(company_search_text(company), terms)
    ]
    return sorted(
        matched,
        key=lambda company: (
            safe_int(company.get("priority_score"), 0),
            safe_int(company.get("rail_fit_score"), 0),
            safe_int(company.get("best_site_match_score"), 0),
        ),
        reverse=True,
    )


def build_supply_chain_catalog(companies):
    """Build the overview catalog for all configured supply chains."""
    chains = []
    for definition in SUPPLY_CHAIN_DEFINITIONS:
        matched_companies = match_companies_for_definition(definition, companies)
        summary = summarize_companies(matched_companies)
        chains.append({
            **definition,
            **summary,
            "top_companies": [matched_company_payload(company) for company in matched_companies[:4]],
            "flow_step_count": len(definition.get("steps", [])),
        })
    return chains


def build_supply_chain_detail(slug, companies):
    """Build one supply-chain detail payload with step-level company matches."""
    definition = next(
        (item for item in SUPPLY_CHAIN_DEFINITIONS if item.get("slug") == slug),
        None,
    )
    if not definition:
        return None

    matched_companies = match_companies_for_definition(definition, companies)
    chain_payload = {
        **definition,
        **summarize_companies(matched_companies),
        "companies": [matched_company_payload(company) for company in matched_companies],
        "action_queue": build_supply_chain_action_queue(matched_companies),
        "steps": [],
    }

    for index, step in enumerate(definition.get("steps", []), start=1):
        step_companies = [
            company for company in matched_companies
            if matches_any_term(company_search_text(company), step.get("terms", []))
        ]
        if not step_companies and matched_companies:
            step_companies = matched_companies[:3]
        chain_payload["steps"].append({
            **step,
            "index": index,
            "companies": [matched_company_payload(company) for company in step_companies[:6]],
            **summarize_companies(step_companies),
        })

    return chain_payload


def build_supply_chain_action_queue(companies, limit=8):
    """Build prioritized next actions for a supply-chain detail page."""
    sorted_companies = sorted(
        companies,
        key=lambda company: (
            readiness_status(company)["rank"],
            safe_int(company.get("priority_score"), 0),
            safe_int(company.get("best_site_match_score"), 0),
            safe_int(company.get("rail_fit_score"), 0),
        ),
        reverse=True,
    )
    return [matched_company_payload(company) for company in sorted_companies[:limit]]


def filter_supply_chains(chains, group=None, query=None, min_priority=None, opportunity=None, readiness=None, sort=None):
    """Filter supply-chain overview cards by group and search text."""
    filtered = list(chains)
    if group:
        filtered = [chain for chain in filtered if chain.get("group") == group]
    if min_priority is not None:
        filtered = [chain for chain in filtered if safe_int(chain.get("average_priority"), 0) >= min_priority]
    if opportunity:
        opportunity_counts = {
            "Strong rail prospect": "strong_count",
            "Rail-service possible": "possible_count",
            "Monitor": "monitor_count",
        }
        count_key = opportunity_counts.get(opportunity)
        filtered = [chain for chain in filtered if count_key and chain.get(count_key, 0) > 0]
    if readiness:
        readiness_counts = {
            "Ready for outreach": "ready_count",
            "Qualify fit": "qualify_count",
            "Needs site review": "site_review_count",
            "Monitor": "readiness_monitor_count",
        }
        count_key = readiness_counts.get(readiness)
        filtered = [chain for chain in filtered if count_key and chain.get(count_key, 0) > 0]
    if query:
        query_text = normalize_text(query)
        filtered = [
            chain for chain in filtered
            if query_text in normalize_text(
                " ".join([
                    chain.get("name", ""),
                    chain.get("group", ""),
                    chain.get("summary", ""),
                    " ".join(chain.get("terms", [])),
                    " ".join(company.get("company", "") for company in chain.get("top_companies", [])),
                ])
            )
        ]
    sort_key = sort or "strong"
    if sort_key == "priority":
        return sorted(filtered, key=lambda chain: safe_int(chain.get("average_priority"), 0), reverse=True)
    if sort_key == "site_fit":
        return sorted(filtered, key=lambda chain: safe_int(chain.get("average_site_fit"), 0), reverse=True)
    if sort_key == "ready":
        return sorted(filtered, key=lambda chain: chain.get("ready_count", 0), reverse=True)
    if sort_key == "matches":
        return sorted(filtered, key=lambda chain: chain.get("count", 0), reverse=True)
    return sorted(filtered, key=lambda chain: chain.get("strong_count", 0), reverse=True)
