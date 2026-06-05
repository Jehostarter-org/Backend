"""
Airport data for all supported countries on the Jehostarter platform.

Each entry has:
  - id:        short unique code (airport IATA code where applicable)
  - label:     human-readable name with IATA code
  - value:     full name stored in the database
  - country:   ISO 3166-1 alpha-2 country code
  - lat:       latitude (WGS84)
  - lng:       longitude (WGS84)

Supported countries are defined in backend/settings.py → COUNTRY_CURRENCY_MAP:
  NG, GH, CM, KE, ZA, ZW, UG, IN, NP, CN, GB, FR, ES, PT, CY, US, CA, AU
"""

AIRPORTS = [
    # ── 🇳🇬 Nigeria ─────────────────────────────────────────────────────────
    {"id": "los", "label": "Murtala Muhammed International (LOS)",   "value": "Murtala Muhammed International Airport (LOS)",   "country": "NG", "lat": 6.5774,  "lng": 3.3210},
    {"id": "abv", "label": "Nnamdi Azikiwe International (ABV)",     "value": "Nnamdi Azikiwe International Airport (ABV)",     "country": "NG", "lat": 9.0068,  "lng": 7.2632},
    {"id": "kan", "label": "Aminu Kano International (KAN)",         "value": "Aminu Kano International Airport (KAN)",         "country": "NG", "lat": 12.0476, "lng": 8.5246},
    {"id": "phc", "label": "Port Harcourt International (PHC)",      "value": "Port Harcourt International Airport (PHC)",      "country": "NG", "lat": 5.0156,  "lng": 6.9496},
    {"id": "enu", "label": "Akanu Ibiam International (ENU)",        "value": "Akanu Ibiam International Airport (ENU)",        "country": "NG", "lat": 6.4742,  "lng": 7.5619},

    # ── 🇬🇭 Ghana ────────────────────────────────────────────────────────────
    {"id": "acc", "label": "Kotoka International (ACC)",             "value": "Kotoka International Airport (ACC)",             "country": "GH", "lat": 5.6052,  "lng": -0.1668},
    {"id": "kum", "label": "Kumasi International (KMS)",             "value": "Kumasi International Airport (KMS)",             "country": "GH", "lat": 6.7146,  "lng": -1.5908},
    {"id": "tdi", "label": "Takoradi Airport (TKD)",                "value": "Takoradi Airport (TKD)",                         "country": "GH", "lat": 4.8961,  "lng": -1.7748},

    # ── 🇨🇲 Cameroon ─────────────────────────────────────────────────────────
    {"id": "dla", "label": "Douala International (DLA)",            "value": "Douala International Airport (DLA)",             "country": "CM", "lat": 4.0061,  "lng": 9.7194},
    {"id": "yao", "label": "Yaoundé Nsimalen International (YAO)",  "value": "Yaoundé Nsimalen International Airport (YAO)",   "country": "CM", "lat": 3.7225,  "lng": 11.5533},
    {"id": "nsi", "label": "Yaoundé International (NSI)",           "value": "Yaoundé International Airport (NSI)",            "country": "CM", "lat": 3.7652,  "lng": 11.4291},

    # ── 🇰🇪 Kenya ────────────────────────────────────────────────────────────
    {"id": "nbo", "label": "Jomo Kenyatta International (NBO)",     "value": "Jomo Kenyatta International Airport (NBO)",      "country": "KE", "lat": -1.3192, "lng": 36.9278},
    {"id": "mba", "label": "Moi International (MBA)",               "value": "Moi International Airport (MBA)",                "country": "KE", "lat": -4.0348, "lng": 39.5942},
    {"id": "kis", "label": "Kisumu International (KIS)",            "value": "Kisumu International Airport (KIS)",             "country": "KE", "lat": -0.0862, "lng": 34.7289},
    {"id": "eld", "label": "Eldoret International (EDL)",           "value": "Eldoret International Airport (EDL)",            "country": "KE", "lat": 0.4044,  "lng": 35.2381},

    # ── 🇿🇦 South Africa ──────────────────────────────────────────────────────
    {"id": "jnb", "label": "O.R. Tambo International (JNB)",        "value": "O.R. Tambo International Airport (JNB)",         "country": "ZA", "lat": -26.1392, "lng": 28.2460},
    {"id": "cpt", "label": "Cape Town International (CPT)",         "value": "Cape Town International Airport (CPT)",          "country": "ZA", "lat": -33.9648, "lng": 18.6017},
    {"id": "dur", "label": "King Shaka International (DUR)",        "value": "King Shaka International Airport (DUR)",         "country": "ZA", "lat": -29.6144, "lng": 31.1197},
    {"id": "plz", "label": "Port Elizabeth International (PLZ)",    "value": "Port Elizabeth International Airport (PLZ)",     "country": "ZA", "lat": -33.9849, "lng": 25.6174},

    # ── 🇿🇼 Zimbabwe ──────────────────────────────────────────────────────────
    {"id": "hre", "label": "Robert Gabriel Mugabe International (HRE)", "value": "Robert Gabriel Mugabe International Airport (HRE)", "country": "ZW", "lat": -17.9318, "lng": 31.0928},
    {"id": "buq", "label": "Joshua Mqabuko Nkomo International (BUQ)",  "value": "Joshua Mqabuko Nkomo International Airport (BUQ)",  "country": "ZW", "lat": -20.0174, "lng": 28.6179},

    # ── 🇺🇬 Uganda ────────────────────────────────────────────────────────────
    {"id": "ebb", "label": "Entebbe International (EBB)",           "value": "Entebbe International Airport (EBB)",            "country": "UG", "lat": 0.0424,  "lng": 32.4437},

    # ── 🇮🇳 India ────────────────────────────────────────────────────────────
    {"id": "del", "label": "Indira Gandhi International (DEL)",     "value": "Indira Gandhi International Airport (DEL)",      "country": "IN", "lat": 28.5562, "lng": 77.1000},
    {"id": "bom", "label": "Chhatrapati Shivaji Maharaj International (BOM)", "value": "Chhatrapati Shivaji Maharaj International Airport (BOM)", "country": "IN", "lat": 19.0896, "lng": 72.8656},
    {"id": "maa", "label": "Chennai International (MAA)",           "value": "Chennai International Airport (MAA)",            "country": "IN", "lat": 12.9900, "lng": 80.1693},
    {"id": "blr", "label": "Kempegowda International (BLR)",        "value": "Kempegowda International Airport (BLR)",         "country": "IN", "lat": 13.1986, "lng": 77.7066},
    {"id": "hyd", "label": "Rajiv Gandhi International (HYD)",      "value": "Rajiv Gandhi International Airport (HYD)",       "country": "IN", "lat": 17.2313, "lng": 78.4299},
    {"id": "ccu", "label": "Netaji Subhas Chandra Bose International (CCU)", "value": "Netaji Subhas Chandra Bose International Airport (CCU)", "country": "IN", "lat": 22.6547, "lng": 88.4467},

    # ── 🇳🇵 Nepal ────────────────────────────────────────────────────────────
    {"id": "ktm", "label": "Tribhuvan International (KTM)",         "value": "Tribhuvan International Airport (KTM)",          "country": "NP", "lat": 27.6967, "lng": 85.3592},
    {"id": "pkr", "label": "Pokhara International (PKR)",           "value": "Pokhara International Airport (PKR)",            "country": "NP", "lat": 28.2008, "lng": 83.9817},

    # ── 🇨🇳 China ────────────────────────────────────────────────────────────
    {"id": "pek", "label": "Beijing Capital International (PEK)",   "value": "Beijing Capital International Airport (PEK)",    "country": "CN", "lat": 40.0799, "lng": 116.6031},
    {"id": "pvg", "label": "Shanghai Pudong International (PVG)",   "value": "Shanghai Pudong International Airport (PVG)",    "country": "CN", "lat": 31.1443, "lng": 121.8083},
    {"id": "can", "label": "Guangzhou Baiyun International (CAN)",  "value": "Guangzhou Baiyun International Airport (CAN)",   "country": "CN", "lat": 23.3925, "lng": 113.2988},
    {"id": "szx", "label": "Shenzhen Bao'an International (SZX)",  "value": "Shenzhen Bao'an International Airport (SZX)",   "country": "CN", "lat": 22.6394, "lng": 113.8145},
    {"id": "ctu", "label": "Chengdu Tianfu International (TFU)",   "value": "Chengdu Tianfu International Airport (TFU)",     "country": "CN", "lat": 30.3197, "lng": 104.4413},

    # ── 🇬🇧 United Kingdom ───────────────────────────────────────────────────
    {"id": "lhr", "label": "London Heathrow (LHR)",                 "value": "London Heathrow Airport (LHR)",                  "country": "GB", "lat": 51.4700, "lng": -0.4543},
    {"id": "lgw", "label": "London Gatwick (LGW)",                  "value": "London Gatwick Airport (LGW)",                   "country": "GB", "lat": 51.1537, "lng": -0.1821},
    {"id": "man", "label": "Manchester Airport (MAN)",             "value": "Manchester Airport (MAN)",                       "country": "GB", "lat": 53.3536, "lng": -2.2750},
    {"id": "bhx", "label": "Birmingham Airport (BHX)",             "value": "Birmingham Airport (BHX)",                       "country": "GB", "lat": 52.4539, "lng": -1.7480},
    {"id": "edi", "label": "Edinburgh Airport (EDI)",             "value": "Edinburgh Airport (EDI)",                        "country": "GB", "lat": 55.9502, "lng": -3.3725},
    {"id": "gla", "label": "Glasgow Airport (GLA)",               "value": "Glasgow Airport (GLA)",                          "country": "GB", "lat": 55.8719, "lng": -4.4330},

    # ── 🇫🇷 France ───────────────────────────────────────────────────────────
    {"id": "cdg", "label": "Paris Charles de Gaulle (CDG)",         "value": "Paris Charles de Gaulle Airport (CDG)",          "country": "FR", "lat": 49.0097, "lng": 2.5479},
    {"id": "ory", "label": "Paris Orly (ORY)",                      "value": "Paris Orly Airport (ORY)",                       "country": "FR", "lat": 48.7262, "lng": 2.3652},
    {"id": "mrs", "label": "Marseille Provence (MRS)",             "value": "Marseille Provence Airport (MRS)",               "country": "FR", "lat": 43.4393, "lng": 5.2214},
    {"id": "lys", "label": "Lyon-Saint Exupéry (LYS)",             "value": "Lyon-Saint Exupéry Airport (LYS)",               "country": "FR", "lat": 45.7263, "lng": 5.0908},

    # ── 🇪🇸 Spain ────────────────────────────────────────────────────────────
    {"id": "mad", "label": "Adolfo Suárez Madrid-Barajas (MAD)",    "value": "Adolfo Suárez Madrid-Barajas Airport (MAD)",     "country": "ES", "lat": 40.4722, "lng": -3.5609},
    {"id": "bcn", "label": "Barcelona-El Prat (BCN)",              "value": "Barcelona-El Prat Airport (BCN)",                "country": "ES", "lat": 41.2971, "lng": 2.0785},
    {"id": "agp", "label": "Málaga-Costa del Sol (AGP)",           "value": "Málaga-Costa del Sol Airport (AGP)",             "country": "ES", "lat": 36.6749, "lng": -4.4922},

    # ── 🇵🇹 Portugal ──────────────────────────────────────────────────────────
    {"id": "lis", "label": "Lisbon Humberto Delgado (LIS)",         "value": "Lisbon Humberto Delgado Airport (LIS)",          "country": "PT", "lat": 38.7813, "lng": -9.1359},
    {"id": "opo", "label": "Porto Francisco Sá Carneiro (OPO)",    "value": "Porto Francisco Sá Carneiro Airport (OPO)",      "country": "PT", "lat": 41.2481, "lng": -8.6814},
    {"id": "fao", "label": "Faro Airport (FAO)",                    "value": "Faro Airport (FAO)",                              "country": "PT", "lat": 37.0144, "lng": -7.9659},

    # ── 🇨🇾 Cyprus ────────────────────────────────────────────────────────────
    {"id": "lca", "label": "Larnaca International (LCA)",           "value": "Larnaca International Airport (LCA)",            "country": "CY", "lat": 34.8755, "lng": 33.6246},
    {"id": "pfo", "label": "Paphos International (PFO)",            "value": "Paphos International Airport (PFO)",             "country": "CY", "lat": 34.7179, "lng": 32.4857},

    # ── 🇺🇸 United States ────────────────────────────────────────────────────
    {"id": "jfk", "label": "John F. Kennedy International (JFK)",   "value": "John F. Kennedy International Airport (JFK)",    "country": "US", "lat": 40.6413, "lng": -73.7781},
    {"id": "lax", "label": "Los Angeles International (LAX)",       "value": "Los Angeles International Airport (LAX)",        "country": "US", "lat": 33.9416, "lng": -118.4085},
    {"id": "ord", "label": "O'Hare International (ORD)",            "value": "O'Hare International Airport (ORD)",             "country": "US", "lat": 41.9786, "lng": -87.9048},
    {"id": "sfo", "label": "San Francisco International (SFO)",     "value": "San Francisco International Airport (SFO)",      "country": "US", "lat": 37.6213, "lng": -122.3790},
    {"id": "atl", "label": "Hartsfield-Jackson Atlanta International (ATL)", "value": "Hartsfield-Jackson Atlanta International Airport (ATL)", "country": "US", "lat": 33.6407, "lng": -84.4277},
    {"id": "mia", "label": "Miami International (MIA)",             "value": "Miami International Airport (MIA)",              "country": "US", "lat": 25.7932, "lng": -80.2906},
    {"id": "iah", "label": "George Bush Intercontinental (IAH)",   "value": "George Bush Intercontinental Airport (IAH)",    "country": "US", "lat": 29.9844, "lng": -95.3414},

    # ── 🇨🇦 Canada ────────────────────────────────────────────────────────────
    {"id": "yyz", "label": "Toronto Pearson International (YYZ)",   "value": "Toronto Pearson International Airport (YYZ)",    "country": "CA", "lat": 43.6777, "lng": -79.6248},
    {"id": "yvr", "label": "Vancouver International (YVR)",         "value": "Vancouver International Airport (YVR)",          "country": "CA", "lat": 49.1947, "lng": -123.1792},
    {"id": "yul", "label": "Montréal-Trudeau International (YUL)",  "value": "Montréal-Trudeau International Airport (YUL)",   "country": "CA", "lat": 45.4706, "lng": -73.7408},
    {"id": "yyc", "label": "Calgary International (YYC)",           "value": "Calgary International Airport (YYC)",            "country": "CA", "lat": 51.1139, "lng": -114.0201},

    # ── 🇦🇺 Australia ──────────────────────────────────────────────────────────
    {"id": "syd", "label": "Sydney Kingsford Smith (SYD)",          "value": "Sydney Kingsford Smith Airport (SYD)",           "country": "AU", "lat": -33.9399, "lng": 151.1753},
    {"id": "mel", "label": "Melbourne Airport (MEL)",               "value": "Melbourne Airport (MEL)",                        "country": "AU", "lat": -37.6733, "lng": 144.8433},
    {"id": "bne", "label": "Brisbane Airport (BNE)",               "value": "Brisbane Airport (BNE)",                         "country": "AU", "lat": -27.3842, "lng": 153.1175},
    {"id": "per", "label": "Perth Airport (PER)",                  "value": "Perth Airport (PER)",                            "country": "AU", "lat": -31.9403, "lng": 115.9668},
    {"id": "adl", "label": "Adelaide Airport (ADL)",               "value": "Adelaide Airport (ADL)",                         "country": "AU", "lat": -34.9475, "lng": 138.5312},
]


def get_airports_by_country(country_code: str | None = None) -> list[dict]:
    """Return airports for a given country, or all airports if country_code is None."""
    if country_code:
        return [a for a in AIRPORTS if a["country"] == country_code.upper()]
    return list(AIRPORTS)


def get_supported_countries() -> list[str]:
    """Return the list of supported country codes that have airport data."""
    return sorted({a["country"] for a in AIRPORTS})
