"""
Doppelganger Analysis v2
Expanded database (30 entries) with diverse setups across all sectors.
Default to same-sector matching to avoid the "everything looks like CSCO 1999" problem.
"""

import numpy as np
import pandas as pd


HISTORICAL_ANALOGS = {
    # ══ TECH - BUBBLE ERA ══
    "CSCO_1999": {"company":"Cisco","era":"1999 (dot-com peak)","marketCapB":450,"trailingPE":130,"priceToSalesTrailing12Months":35,"revenueGrowth":0.43,"profitMargins":0.17,"grossMargins":0.65,"momentum_12m":1.30,"returnOnEquity":0.25,"sector":"Technology","narrative":"Networking backbone of the internet. Trading at extreme multiples on assumption of unlimited internet growth.","context":"Dot-com peak. Essential infrastructure but priced for perfection.","outcome":"Fell 85% by 2002. Took 17 years to reach new ATH. Business remained dominant but multiple collapsed.","lesson":"Dominant business + extreme valuation = years of waiting even when fundamentals hold.","tags":["tech","bubble-era","peak-valuation","mega-cap"]},
    "INTC_2000": {"company":"Intel","era":"2000 (dot-com peak)","marketCapB":500,"trailingPE":55,"priceToSalesTrailing12Months":14,"revenueGrowth":0.15,"profitMargins":0.31,"grossMargins":0.63,"momentum_12m":0.45,"returnOnEquity":0.28,"sector":"Technology","narrative":"Dominant chip designer riding PC boom. x86 monopoly.","context":"Seemingly unstoppable at peak hardware boom.","outcome":"Fell 80% by 2002. Lost mobile, lost foundry lead to TSMC. Still below 2000 peak in 2026.","lesson":"Dominance today doesn't protect against technology platform shifts.","tags":["tech","semiconductors","peak-valuation","disruption-risk"]},
    "MSFT_2000": {"company":"Microsoft","era":"2000 (dot-com peak)","marketCapB":600,"trailingPE":62,"priceToSalesTrailing12Months":26,"revenueGrowth":0.16,"profitMargins":0.41,"grossMargins":0.87,"momentum_12m":-0.05,"returnOnEquity":0.24,"sector":"Technology","narrative":"OS monopoly with Office dominance. Facing DOJ antitrust.","context":"Peak multiple just as PC growth began saturating.","outcome":"Stock traded flat for 14 years. Nadella's cloud pivot required to break out.","lesson":"Great businesses need new growth catalysts to grow into premium valuations.","tags":["tech","software","monopoly","valuation-compression","mega-cap"]},

    # ══ TECH - CRISIS DISCOUNTS ══
    "AAPL_2008": {"company":"Apple","era":"2008-2009 (financial crisis)","marketCapB":75,"trailingPE":15,"priceToSalesTrailing12Months":2.1,"revenueGrowth":0.28,"profitMargins":0.15,"grossMargins":0.34,"momentum_12m":-0.55,"returnOnEquity":0.27,"sector":"Technology","narrative":"iPhone launched 2007, App Store 2008. Platform shift underway but market panicking.","context":"Crisis sell-off masked transformative platform launch.","outcome":"Up 100x from 2009 low to 2024. iPhone became largest profit pool in consumer tech.","lesson":"Crisis valuations on companies with new platform advantages create generational opportunities.","tags":["tech","platform-shift","crisis-discount","consumer"]},
    "AMZN_2008": {"company":"Amazon","era":"2008 (pre-AWS recognition)","marketCapB":40,"trailingPE":45,"priceToSalesTrailing12Months":2.0,"revenueGrowth":0.29,"profitMargins":0.04,"grossMargins":0.22,"momentum_12m":-0.45,"returnOnEquity":0.09,"sector":"Consumer Cyclical","narrative":"E-commerce growing through crisis. AWS launched 2006 but unrecognized.","context":"Bezos's reinvestment seen as capital-destructive. Hidden cloud optionality.","outcome":"AWS recognized by 2013, stock up 50x through 2021.","lesson":"Hidden optionality in 'boring' businesses often undervalued during crises.","tags":["tech","ecommerce","hidden-optionality","reinvestment"]},

    # ══ TECH - GROWTH ══
    "NFLX_2015": {"company":"Netflix","era":"2015 (international expansion)","marketCapB":40,"trailingPE":200,"priceToSalesTrailing12Months":7.0,"revenueGrowth":0.26,"profitMargins":0.01,"grossMargins":0.32,"momentum_12m":0.55,"returnOnEquity":0.08,"sector":"Communication Services","narrative":"DVD to streaming transition, massive content spend, international launch.","context":"Burning cash on content but subscriber growth justified optimism.","outcome":"Up 5x to 2021, then 70% drawdown in 2022 on subscriber losses, recovered by 2024.","lesson":"High-growth cash-burners work until competition arrives and growth slows.","tags":["media","hyper-growth","cash-burn","content"]},
    "TSLA_2019": {"company":"Tesla","era":"2019 (pre-profitability)","marketCapB":55,"trailingPE":None,"priceToSalesTrailing12Months":2.5,"revenueGrowth":0.32,"profitMargins":-0.05,"grossMargins":0.17,"momentum_12m":-0.10,"returnOnEquity":-0.08,"sector":"Consumer Cyclical","narrative":"Model 3 ramp, manufacturing hell, short-seller darling.","context":"Just before sustained profitability. Wall Street largely rated Sell.","outcome":"Up 20x through 2021, -75% drawdown, recovered. Still highly volatile.","lesson":"Emerging-profitability stories can 10x+ once cash flow inflects, but volatility extreme.","tags":["auto","pre-profitability","cult-stock","ev"]},
    "NVDA_2016": {"company":"Nvidia","era":"2016 (AI emergence)","marketCapB":30,"trailingPE":30,"priceToSalesTrailing12Months":5.0,"revenueGrowth":0.38,"profitMargins":0.24,"grossMargins":0.59,"momentum_12m":2.20,"returnOnEquity":0.33,"sector":"Technology","narrative":"GPU demand exploding from gaming, crypto, early AI. Deep learning papers using CUDA.","context":"Investors still saw NVDA as gaming company. AI upside not priced.","outcome":"Up 80x through 2024 AI boom. Became 3rd largest company in world.","lesson":"Best product in emerging tech cycle often radically underestimated initially.","tags":["tech","semiconductors","AI","platform-monopoly"]},

    # ══ COVID BENEFICIARY ══
    "ZM_2020": {"company":"Zoom","era":"2020 (COVID peak)","marketCapB":160,"trailingPE":400,"priceToSalesTrailing12Months":60,"revenueGrowth":3.26,"profitMargins":0.25,"grossMargins":0.70,"momentum_12m":4.20,"returnOnEquity":0.25,"sector":"Technology","narrative":"Essential COVID infrastructure. Revenue grew 300%+. Priced as if WFH permanent.","context":"Became a verb during pandemic. Extreme growth rate deemed sustainable.","outcome":"Fell 90% from peak. Teams and Meet commoditized product.","lesson":"Pulled-forward demand reverts. Moats erode fast when product is easily copied.","tags":["tech","covid-beneficiary","demand-pull-forward","commoditization"]},

    # ══ TURNAROUND ══
    "META_2022": {"company":"Meta","era":"2022 (post-ATT crisis)","marketCapB":240,"trailingPE":10,"priceToSalesTrailing12Months":2.3,"revenueGrowth":-0.04,"profitMargins":0.19,"grossMargins":0.80,"momentum_12m":-0.64,"returnOnEquity":0.19,"sector":"Communication Services","narrative":"ATT crushed ad targeting. Reality Labs burning $10B+/yr. Investors rebelled.","context":"Priced as if core Facebook was dying. Worst sentiment in company history.","outcome":"Up 5x by 2024 on AI-driven ads recovery and cost cuts. Year of Efficiency.","lesson":"Durable businesses with fixable problems plus activist pressure recover faster than expected.","tags":["tech","advertising","value-in-growth","efficiency-turnaround"]},

    # ══ FINANCIALS ══
    "C_2008": {"company":"Citigroup","era":"2008 (pre-bailout)","marketCapB":75,"trailingPE":8,"priceToSalesTrailing12Months":0.7,"revenueGrowth":-0.25,"profitMargins":-0.10,"grossMargins":None,"momentum_12m":-0.65,"returnOnEquity":-0.12,"sector":"Financial Services","narrative":"Subprime losses mounting, capital ratio stressed, dividend cut.","context":"Seemingly cheap but actually overleveraged. Book value suspect.","outcome":"Fell 95% more through March 2009. Bailout. 1:10 reverse split.","lesson":"Cyclical financials with leverage problems can fall much further than P/E suggests.","tags":["financials","crisis","leverage","value-trap"]},
    "JPM_2015": {"company":"JPMorgan","era":"2015 (mid-cycle banking)","marketCapB":240,"trailingPE":11,"priceToSalesTrailing12Months":2.4,"revenueGrowth":0.02,"profitMargins":0.25,"grossMargins":None,"momentum_12m":0.08,"returnOnEquity":0.10,"sector":"Financial Services","narrative":"Post-crisis recovery complete, regulatory headwinds, flat NIM.","context":"Best-in-class bank at normal valuation. Boring but reliable.","outcome":"Compounded 12% annually through 2024. Dividend + buybacks + modest growth.","lesson":"Quality banks at normal valuations compound steadily without excitement.","tags":["financials","banking","mid-cycle","compounder","mega-cap"]},
    "BAC_2011": {"company":"Bank of America","era":"2011 (post-crisis deep value)","marketCapB":55,"trailingPE":None,"priceToSalesTrailing12Months":0.5,"revenueGrowth":-0.15,"profitMargins":0.01,"grossMargins":None,"momentum_12m":-0.55,"returnOnEquity":0.00,"sector":"Financial Services","narrative":"Countrywide legacy mortgages, fines, capital raises, Buffett warrants.","context":"Deeply discounted to book. Mortgage liability unclear.","outcome":"Up 5x through 2024 as legacy issues resolved and rates normalized.","lesson":"Post-crisis banks at deep discount to book reward patient investors.","tags":["financials","banking","post-crisis","deep-value"]},

    # ══ STAPLES - DEFENSIVE ══
    "PG_2018": {"company":"Procter & Gamble","era":"2018 (activist pressure)","marketCapB":220,"trailingPE":22,"priceToSalesTrailing12Months":3.3,"revenueGrowth":0.02,"profitMargins":0.15,"grossMargins":0.50,"momentum_12m":-0.05,"returnOnEquity":0.17,"sector":"Consumer Defensive","narrative":"Peltz activism, slow growth, premium brands under attack from DTC.","context":"Quality defensive at reasonable multiple. Growth concerns overblown.","outcome":"Up 80% through 2024 with steady dividend. Activist changes boosted execution.","lesson":"Quality defensives at fair prices deliver steady real returns without excitement.","tags":["staples","defensive","dividend","mega-cap","activism"]},
    "KO_2016": {"company":"Coca-Cola","era":"2016 (refranchising)","marketCapB":180,"trailingPE":24,"priceToSalesTrailing12Months":4.4,"revenueGrowth":-0.05,"profitMargins":0.15,"grossMargins":0.61,"momentum_12m":0.02,"returnOnEquity":0.28,"sector":"Consumer Defensive","narrative":"Declining soda volumes, refranchising bottlers, capex reduction.","context":"Balance sheet transformation. Brand/concentrate focus.","outcome":"Steady 8% annual total return through 2024. Buffett continued holding.","lesson":"Iconic brands at fair valuations provide stable ballast even through volume declines.","tags":["staples","defensive","dividend","brand","mega-cap"]},
    "COST_2015": {"company":"Costco","era":"2015 (quiet compounder)","marketCapB":65,"trailingPE":28,"priceToSalesTrailing12Months":0.6,"revenueGrowth":0.03,"profitMargins":0.02,"grossMargins":0.13,"momentum_12m":0.15,"returnOnEquity":0.20,"sector":"Consumer Defensive","narrative":"Membership warehouse model. Slow growth but wide moat.","context":"Premium multiple for 'boring' retailer. Membership economics dominant.","outcome":"Up 4x through 2024. Premium multiple held and expanded.","lesson":"Premium multiples are often justified by business model quality, not just growth rate.","tags":["retail","staples","compounder","moat","quality"]},

    # ══ UTILITIES ══
    "NEE_2017": {"company":"NextEra Energy","era":"2017 (renewable transition)","marketCapB":75,"trailingPE":22,"priceToSalesTrailing12Months":4.2,"revenueGrowth":0.07,"profitMargins":0.18,"grossMargins":None,"momentum_12m":0.25,"returnOnEquity":0.11,"sector":"Utilities","narrative":"Largest US wind/solar operator. Growth utility vs traditional peers.","context":"Premium to sector on growth thesis. Rate-sensitive.","outcome":"Up 2x through 2021, then sharp decline as rates rose. Still best-in-class.","lesson":"Growth utilities work in low-rate environments but rate-sensitive on the downside.","tags":["utilities","defensive","growth-utility","renewables","rate-sensitive"]},

    # ══ ENERGY ══
    "XOM_2014": {"company":"Exxon","era":"2014 (oil peak)","marketCapB":420,"trailingPE":13,"priceToSalesTrailing12Months":1.0,"revenueGrowth":-0.06,"profitMargins":0.08,"grossMargins":0.28,"momentum_12m":0.05,"returnOnEquity":0.18,"sector":"Energy","narrative":"Dividend aristocrat at oil peak. $100 oil seen as floor.","context":"Saudi about to flood market to kill US shale. Glut forming.","outcome":"Oil to $26 by 2016. Stock -45% through 2020. Recovered on 2022 energy crisis.","lesson":"Commodity producers at cycle peaks with high dividend payouts often disappoint for years.","tags":["energy","commodities","cycle-peak","dividend","mega-cap"]},
    "XOM_2020": {"company":"Exxon","era":"2020 (COVID oil crash)","marketCapB":140,"trailingPE":None,"priceToSalesTrailing12Months":0.5,"revenueGrowth":-0.32,"profitMargins":-0.10,"grossMargins":0.25,"momentum_12m":-0.40,"returnOnEquity":-0.14,"sector":"Energy","narrative":"Oil briefly negative, removed from Dow, dividend questioned.","context":"Deepest energy sector discount in a generation.","outcome":"Up 3x through 2024 as energy crisis and underinvestment hit supply.","lesson":"Deeply cyclical stocks at crisis lows with maintained capital discipline can 3-5x.","tags":["energy","crisis-discount","dividend","mega-cap","contrarian"]},

    # ══ HEALTHCARE ══
    "UNH_2012": {"company":"UnitedHealth","era":"2012 (pre-ACA implementation)","marketCapB":60,"trailingPE":11,"priceToSalesTrailing12Months":0.6,"revenueGrowth":0.08,"profitMargins":0.05,"grossMargins":None,"momentum_12m":0.12,"returnOnEquity":0.19,"sector":"Healthcare","narrative":"Managed care leader, ACA uncertainty, Optum services scaling.","context":"Before the great managed care re-rating of 2013-2021.","outcome":"Up 12x through 2024. Best-performing Dow stock over that period.","lesson":"Quality compounders in stable industries with expanding moats can quietly deliver 10x+.","tags":["healthcare","managed-care","compounder","quality","mega-cap"]},
    "JNJ_2017": {"company":"Johnson & Johnson","era":"2017 (pre-talc litigation)","marketCapB":375,"trailingPE":24,"priceToSalesTrailing12Months":5.0,"revenueGrowth":0.06,"profitMargins":0.23,"grossMargins":0.67,"momentum_12m":0.18,"returnOnEquity":0.23,"sector":"Healthcare","narrative":"Diversified healthcare: consumer/pharma/devices. Aristocrat dividend.","context":"Quality multi-segment healthcare at reasonable multiple.","outcome":"Mid-single-digit returns through 2024. Talc lawsuits weighed on stock.","lesson":"Quality defensives can be hit by unexpected legal/regulatory events.","tags":["healthcare","pharma","defensive","dividend","mega-cap"]},
    "REGN_2011": {"company":"Regeneron","era":"2011 (Eylea launch)","marketCapB":5,"trailingPE":None,"priceToSalesTrailing12Months":10,"revenueGrowth":0.15,"profitMargins":-0.15,"grossMargins":0.70,"momentum_12m":1.25,"returnOnEquity":-0.20,"sector":"Healthcare","narrative":"Single-product biotech with Eylea ophthalmology launch.","context":"Transformational product launch. Cash burn but clear path to profitability.","outcome":"Up 15x through 2015 as Eylea ramped. Best biotech of the decade.","lesson":"Small biotechs with novel products in large markets can deliver 10-15x quickly.","tags":["healthcare","biotech","product-launch","small-cap","specialty"]},

    # ══ INDUSTRIALS ══
    "CAT_2015": {"company":"Caterpillar","era":"2015 (mining/commodity bust)","marketCapB":45,"trailingPE":13,"priceToSalesTrailing12Months":0.9,"revenueGrowth":-0.15,"profitMargins":0.07,"grossMargins":0.29,"momentum_12m":-0.30,"returnOnEquity":0.17,"sector":"Industrials","narrative":"Mining equipment demand collapsed, China slowdown, dealer destocking.","context":"Deep cyclical at cycle trough. Management restructuring.","outcome":"Up 3x through 2024 on infrastructure spending and mining recovery.","lesson":"Deep cyclicals bought at cycle lows with quality management deliver big multi-year returns.","tags":["industrials","cyclical","cycle-trough","machinery"]},

    # ══ CYCLICAL CONSUMER ══
    "HD_2011": {"company":"Home Depot","era":"2011 (housing recovery)","marketCapB":55,"trailingPE":16,"priceToSalesTrailing12Months":0.8,"revenueGrowth":0.03,"profitMargins":0.07,"grossMargins":0.34,"momentum_12m":0.20,"returnOnEquity":0.21,"sector":"Consumer Cyclical","narrative":"Post-housing-crisis recovery beginning. Big-box retail with improving margins.","context":"Early innings of 10-year housing boom. Retail execution excellent.","outcome":"Up 8x through 2021. Best-performing retail stock of the 2010s.","lesson":"Early-cycle consumer cyclicals with strong execution can compound impressively.","tags":["retail","consumer","cyclical","housing","compounder"]},
    "F_2020": {"company":"Ford","era":"2020 (COVID + EV pivot)","marketCapB":25,"trailingPE":None,"priceToSalesTrailing12Months":0.2,"revenueGrowth":-0.18,"profitMargins":-0.01,"grossMargins":0.10,"momentum_12m":-0.25,"returnOnEquity":-0.05,"sector":"Consumer Cyclical","narrative":"COVID auto demand crash, EV transition plans, Farley CEO arrival.","context":"Legacy auto at cycle bottom with credible turnaround.","outcome":"Up 3x through 2022, then gave back on EV execution concerns.","lesson":"Cyclical turnarounds in legacy industries produce sharp rallies followed by volatility.","tags":["auto","cyclical","turnaround","ev-pivot","legacy-industry"]},

    # ══ REAL ESTATE ══
    "PLD_2014": {"company":"Prologis","era":"2014 (e-commerce tailwind)","marketCapB":22,"trailingPE":32,"priceToSalesTrailing12Months":12.5,"revenueGrowth":0.15,"profitMargins":0.25,"grossMargins":None,"momentum_12m":0.22,"returnOnEquity":0.06,"sector":"Real Estate","narrative":"Industrial REIT benefiting from e-commerce logistics boom.","context":"Early recognition of logistics real estate secular trend.","outcome":"Up 4x through 2021 on unprecedented industrial rent growth.","lesson":"Sector-specialist REITs riding clear secular trends outperform broader REITs.","tags":["reit","real-estate","industrial","e-commerce","secular-growth"]},

    # ══ TELECOM ══
    "T_2017": {"company":"AT&T","era":"2017 (Time Warner merger)","marketCapB":240,"trailingPE":18,"priceToSalesTrailing12Months":1.5,"revenueGrowth":-0.02,"profitMargins":0.08,"grossMargins":0.54,"momentum_12m":-0.15,"returnOnEquity":0.09,"sector":"Communication Services","narrative":"Debt-heavy megamerger with Time Warner, 5G spectrum spending.","context":"High dividend yield trap. Structural wireline/media challenges.","outcome":"Stock -50% through 2022. Dividend cut. Warner Media spun off at loss.","lesson":"Dividend traps in declining businesses destroy wealth despite cheap multiples.","tags":["telecom","dividend","value-trap","mega-cap","debt-heavy"]},

    # ══ MATERIALS ══
    "FCX_2020": {"company":"Freeport-McMoRan","era":"2020 (copper pre-EV)","marketCapB":14,"trailingPE":None,"priceToSalesTrailing12Months":1.2,"revenueGrowth":-0.05,"profitMargins":-0.05,"grossMargins":0.13,"momentum_12m":-0.30,"returnOnEquity":-0.07,"sector":"Basic Materials","narrative":"Largest copper miner. EV transition tailwind unrecognized.","context":"Cyclical trough in copper. EV/renewables copper demand thesis nascent.","outcome":"Up 5x through 2022 on copper supercycle recognition.","lesson":"Commodity producers at cycle lows with clear secular tailwinds can 5x in 18 months.","tags":["materials","commodities","copper","ev-tailwind","cycle-trough"]},

    # ══ HYPERGROWTH SAAS ══
    "CRM_2014": {"company":"Salesforce","era":"2014 (enterprise SaaS scaling)","marketCapB":30,"trailingPE":None,"priceToSalesTrailing12Months":7.0,"revenueGrowth":0.33,"profitMargins":-0.05,"grossMargins":0.75,"momentum_12m":0.12,"returnOnEquity":-0.05,"sector":"Technology","narrative":"CRM category leader, expanding platform, still unprofitable on GAAP.","context":"Pre-cloud mainstream adoption. High-growth unprofitable SaaS.","outcome":"Up 10x through 2021, then compression on efficiency demands.","lesson":"Category-leading SaaS at 7-10x sales often rewards patience if growth maintained.","tags":["tech","saas","enterprise","hyper-growth"]},
    "SHOP_2017": {"company":"Shopify","era":"2017 (e-commerce enabler)","marketCapB":10,"trailingPE":None,"priceToSalesTrailing12Months":15,"revenueGrowth":0.73,"profitMargins":-0.04,"grossMargins":0.57,"momentum_12m":1.80,"returnOnEquity":-0.05,"sector":"Technology","narrative":"E-commerce platform for SMBs. Anti-Amazon narrative building.","context":"Mid-cap hyper-growth SaaS. High valuation but explosive growth.","outcome":"Up 15x through 2021, then -85% in 2022 correction. Recovered partially.","lesson":"Hyper-growth mid-caps at high multiples produce both huge wins and huge volatility.","tags":["tech","saas","ecommerce","hyper-growth","mid-cap"]},
}


FINGERPRINT_DIMENSIONS = {
    "trailingPE": {"weight": 0.15, "log": True, "cap_low": 1, "cap_high": 500},
    "priceToSalesTrailing12Months": {"weight": 0.15, "log": True, "cap_low": 0.1, "cap_high": 100},
    "revenueGrowth": {"weight": 0.20, "log": False, "cap_low": -0.5, "cap_high": 4.0},
    "profitMargins": {"weight": 0.10, "log": False, "cap_low": -0.5, "cap_high": 0.5},
    "grossMargins": {"weight": 0.10, "log": False, "cap_low": 0, "cap_high": 1.0},
    "momentum_12m": {"weight": 0.15, "log": False, "cap_low": -1.0, "cap_high": 5.0},
    "returnOnEquity": {"weight": 0.10, "log": False, "cap_low": -0.5, "cap_high": 0.5},
    "marketCapB": {"weight": 0.05, "log": True, "cap_low": 1, "cap_high": 5000},
}


def _normalize_value(value, dim_config):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    v = float(value)
    v = max(dim_config["cap_low"], min(dim_config["cap_high"], v))
    if dim_config["log"]:
        log_min = np.log10(max(0.01, dim_config["cap_low"]))
        log_max = np.log10(dim_config["cap_high"])
        log_v = np.log10(max(0.01, v))
        return (log_v - log_min) / (log_max - log_min)
    return (v - dim_config["cap_low"]) / (dim_config["cap_high"] - dim_config["cap_low"])


def build_fingerprint(stock_data):
    return {dim: _normalize_value(stock_data.get(dim), config) for dim, config in FINGERPRINT_DIMENSIONS.items()}


def compute_similarity(fp1, fp2):
    total_distance = 0
    total_weight = 0
    matched_dims = 0
    for dim, config in FINGERPRINT_DIMENSIONS.items():
        v1 = fp1.get(dim)
        v2 = fp2.get(dim)
        if v1 is None or v2 is None:
            continue
        total_distance += ((v1 - v2) ** 2) * config["weight"]
        total_weight += config["weight"]
        matched_dims += 1
    if matched_dims < 4 or total_weight == 0:
        return 0
    normalized_distance = np.sqrt(total_distance / total_weight)
    similarity = max(0, 1 - normalized_distance)
    confidence_factor = matched_dims / len(FINGERPRINT_DIMENSIONS)
    return similarity * confidence_factor


def find_doppelgangers(ticker, scored_df, top_n=5, sector_filter="same", tag_filter=None):
    """
    Find historical analogues for a current stock.

    sector_filter options:
    - "same" (default): only match same-sector analogs. Best practice.
    - "any": match across all sectors
    - [sector string]: match within a specific sector
    """
    if ticker not in scored_df.index:
        return []

    stock_data = scored_df.loc[ticker].to_dict()
    current_fp = build_fingerprint(stock_data)
    current_sector = stock_data.get("sector")

    matches = []
    for key, analog in HISTORICAL_ANALOGS.items():
        # Sector filter logic
        if sector_filter == "same":
            if analog.get("sector") != current_sector:
                continue
        elif sector_filter == "any":
            pass  # No filter
        elif isinstance(sector_filter, str):
            if analog.get("sector") != sector_filter:
                continue

        if tag_filter and tag_filter not in analog.get("tags", []):
            continue

        analog_fp = build_fingerprint(analog)
        similarity = compute_similarity(current_fp, analog_fp)

        if similarity > 0.3:
            matches.append({
                "match_key": key,
                "company": analog["company"],
                "era": analog["era"],
                "similarity": round(similarity, 3),
                "data": analog,
                "sector": analog.get("sector", "N/A"),
                "context": analog.get("context", ""),
                "outcome": analog.get("outcome", ""),
                "lesson": analog.get("lesson", ""),
                "narrative": analog.get("narrative", ""),
                "tags": analog.get("tags", []),
                "same_sector": analog.get("sector") == current_sector,
            })

    matches.sort(key=lambda x: x["similarity"], reverse=True)

    # If same-sector requested but no matches found, fall back to showing a warning
    if sector_filter == "same" and not matches:
        return []

    return matches[:top_n]


def get_tags_list():
    tags = set()
    for analog in HISTORICAL_ANALOGS.values():
        tags.update(analog.get("tags", []))
    return sorted(tags)


def get_database_stats():
    sectors_with_counts = {}
    for a in HISTORICAL_ANALOGS.values():
        s = a.get("sector", "Unknown")
        sectors_with_counts[s] = sectors_with_counts.get(s, 0) + 1
    return {
        "total_analogs": len(HISTORICAL_ANALOGS),
        "sectors": sorted(sectors_with_counts.keys()),
        "sector_counts": sectors_with_counts,
        "eras_covered": sorted(set(a["era"] for a in HISTORICAL_ANALOGS.values())),
        "tags": get_tags_list(),
    }
