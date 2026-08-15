import re

# Comprehensive Delhi Locality-to-Category (A-H) Mapping Matrix
# Governed by Rule 4 of Delhi Stamp Rules / Revenue Dept NCT Delhi Notifications
# Ordered strictly by key length descending so specific compound names match before generic ones.

_RAW_LOCALITY_CATEGORIES = {
    # ── CATEGORY A (Posh / Premier Residential & Commercial) ──
    "friends colony east": "A",
    "friends colony west": "A",
    "green park extension": "B",  # Explicit override: Green Park Ext is Category B under official gazette
    "hauz khas enclave": "B",     # Explicit override: Hauz Khas Enclave is Category B
    "amrita shergill marg": "A",
    "bhagwan das road": "A",
    "barakhamba road": "A",
    "kasturba gandhi marg": "A",
    "golf course road": "A",
    "sardar patel marg": "A",
    "new friends colony": "A",
    "shanti niketan": "A",
    "maharani bagh": "A",
    "panchsheel park": "A",
    "anand niketan": "A",
    "connaught place": "A",
    "vasant vihar": "A",
    "sunder nagar": "A",
    "prithviraj road": "A",
    "chanakyapuri": "A",
    "friends colony": "A",
    "golf links": "A",
    "bengali market": "A",
    "hailey road": "A",
    "babar road": "A",
    "tilak marg": "A",
    "west end": "A",
    "jor bagh": "A",
    "lodhi estate": "A",
    "aurangzeb road": "A",
    "dr apj abdul kalam road": "A",
    "shahjahan road": "A",
    "humayun road": "A",
    "ratendone road": "A",

    # ── CATEGORY B (High-End Colonies & Prime Neighborhoods) ──
    "safdarjung development area": "B",
    "asian games village": "B",
    "safdarjung enclave": "B",
    "panchsheel enclave": "B",
    "nizamuddin east": "B",
    "pamposh enclave": "B",
    "hemkunt colony": "B",
    "south extension 1": "B",
    "south extension 2": "B",
    "south extension i": "B",
    "south extension ii": "B",
    "greater kailash 1": "B",
    "greater kailash 2": "B",
    "greater kailash 3": "B",
    "greater kailash 4": "B",
    "greater kailash i": "B",
    "greater kailash ii": "B",
    "greater kailash iii": "B",
    "greater kailash iv": "B",
    "greater kailash enclave": "B",
    "punjabi bagh east": "B",
    "punjabi bagh west": "B",
    "new rajinder nagar": "B",
    "new rajendra nagar": "B",
    "defence colony": "B",
    "greater kailash": "B",
    "gulmohar park": "B",
    "green park": "B",
    "anand lok": "B",
    "neeti bagh": "B",
    "south extension": "B",
    "south ext": "B",
    "sarvpriya vihar": "B",
    "hauz khas": "B",
    "civil lines": "B",
    "model town 1": "B",
    "model town 2": "B",
    "model town 3": "B",
    "model town i": "B",
    "model town ii": "B",
    "model town iii": "B",
    "model town": "B",
    "punjabi bagh": "B",
    "vasant kunj": "B",
    "saket": "B",
    "siri fort": "B",
    "khel gaon": "B",
    "alaknanda": "B",
    "patel nagar east": "B",
    "patel nagar west": "B",
    "patel nagar south": "B",
    "munirka enclave": "B",
    "chandra arya vihar": "B",
    "navjivan vihar": "B",
    "press enclave": "B",

    # ── CATEGORY C (Upper Middle Class Colonies) ──
    "chittaranjan park": "C",
    "c.r. park": "C",
    "cr park": "C",
    "lajpat nagar 1": "C",
    "lajpat nagar 2": "C",
    "lajpat nagar 3": "C",
    "lajpat nagar 4": "C",
    "lajpat nagar i": "C",
    "lajpat nagar ii": "C",
    "lajpat nagar iii": "C",
    "lajpat nagar iv": "C",
    "hargobind enclave": "C",
    "shrestha vihar": "C",
    "yojana vihar": "C",
    "vigyan vihar": "C",
    "ashok vihar 1": "C",
    "ashok vihar 2": "C",
    "ashok vihar 3": "C",
    "ashok vihar 4": "C",
    "ashok vihar i": "C",
    "ashok vihar ii": "C",
    "ashok vihar iii": "C",
    "ashok vihar iv": "C",
    "mayur vihar 1": "C",
    "mayur vihar phase 1": "C",
    "mayur vihar phase i": "C",
    "mayur vihar phase-1": "C",
    "mayur vihar phase-i": "C",
    "patparganj cghs": "C",
    "gujranwala town": "C",
    "derawal nagar": "C",
    "mukherjee nagar": "C",
    "lajpat nagar": "C",
    "east of kailash": "C",
    "malviya nagar": "C",
    "kalkaji": "C",
    "nizamuddin west": "C",
    "karol bagh": "C",
    "patel nagar": "C",
    "ashok vihar": "C",
    "kamla nagar": "C",
    "roop nagar": "C",
    "shakti nagar": "C",
    "preet vihar": "C",
    "anand vihar": "C",
    "ip extension": "C",
    "karkardooma": "C",
    "vikas marg": "C",
    "surajmal vihar": "C",
    "saini enclave": "C",
    "bank apartment": "C",
    "chitra vihar": "C",

    # ── CATEGORY D (Middle Class Residential / Established Hubs) ──
    "kirti nagar": "D",
    "janakpuri": "D",
    "pitampura": "D",
    "paschim vihar": "D",
    "shalimar bagh": "D",
    "mayur vihar phase 2": "D",
    "mayur vihar phase 3": "D",
    "mayur vihar phase ii": "D",
    "mayur vihar phase iii": "D",
    "mayur vihar phase-2": "D",
    "mayur vihar phase-3": "D",
    "mayur vihar phase-ii": "D",
    "mayur vihar phase-iii": "D",
    "mayur vihar 2": "D",
    "mayur vihar 3": "D",
    "mayur vihar": "D",
    "punjabi bagh extension": "D",
    "vasundhara enclave": "D",
    "swasthya vihar": "D",
    "dilshad plaza": "D",
    "sukhdev vihar": "D",
    "gagan vihar": "D",
    "kalyan vihar": "D",
    "prashant vihar": "D",
    "rohini sector 1": "D", "rohini sector 2": "D", "rohini sector 3": "D", "rohini sector 4": "D",
    "rohini sector 5": "D", "rohini sector 6": "D", "rohini sector 7": "D", "rohini sector 8": "D",
    "rohini sector 9": "D", "rohini sector 10": "D", "rohini sector 11": "D", "rohini sector 12": "D",
    "rohini sector 13": "D", "rohini sector 14": "D", "rohini sector 15": "D", "rohini sector 16": "D",
    "rohini sector 17": "D", "rohini sector 18": "D", "rohini sector 19": "D", "rohini sector 20": "D",
    "rohini sector 21": "D", "rohini sector 22": "D", "rohini sector 23": "D", "rohini sector 24": "D",
    "rohini sector 25": "D", "rohini": "D",
    "dwarka sector 1": "D", "dwarka sector 2": "D", "dwarka sector 3": "D", "dwarka sector 4": "D",
    "dwarka sector 5": "D", "dwarka sector 6": "D", "dwarka sector 7": "D", "dwarka sector 8": "D",
    "dwarka sector 9": "D", "dwarka sector 10": "D", "dwarka sector 11": "D", "dwarka sector 12": "D",
    "dwarka sector 13": "D", "dwarka sector 14": "D", "dwarka sector 15": "D", "dwarka sector 16": "D",
    "dwarka sector 17": "D", "dwarka sector 18": "D", "dwarka sector 19": "D", "dwarka sector 20": "D",
    "dwarka sector 21": "D", "dwarka sector 22": "D", "dwarka sector 23": "D", "dwarka sector 24": "D",
    "dwarka sector 25": "D", "dwarka sector 26": "D", "dwarka": "D",
    "laxmi nagar": "D",
    "shakarpur": "D",
    "nirman vihar": "D",
    "pandav nagar": "D",
    "patparganj": "D",
    "vivek vihar": "D",
    "rajouri garden": "D",
    "vikas puri": "D",
    "vikaspuri": "D",
    "uttam nagar": "D",
    "hari nagar": "D",
    "tilak nagar": "D",
    "subhash nagar": "D",
    "tagore garden": "D",
    "ramesh nagar": "D",
    "moti nagar": "D",
    "paschim puri": "D",
    "daryaganj": "D",

    # ── CATEGORY E (Lower Middle Class & Urbanized Villages) ──
    "geeta colony": "E",
    "dilshad garden": "E",
    "shahdara": "E",
    "pahar ganj": "E",
    "paharganj": "E",
    "sadar bazar": "E",
    "chandni chowk": "E",
    "kashmere gate": "E",
    "budh vihar colony phase-i & ii": "E",
    "budh vihar phase 1": "E",
    "budh vihar phase 2": "E",
    "budh vihar colony": "E",
    "budh vihar": "E",
    "dilshad extension": "E",
    "mansarovar park": "E",
    "karawal nagar": "E",
    "shastri nagar": "E",
    "krishna nagar": "E",
    "vishwas nagar": "E",
    "bhajanpura": "E",
    "seelampur": "E",
    "gandhi nagar": "E",
    "jwala nagar": "E",
    "welcome": "E",
    "seemapuri": "E",
    "babarpur": "E",
    "mustafabad": "E",
    "gokalpuri": "E",
    "mandoli": "E",
    "burari": "E",
    "sant nagar": "E",
    "nathupura": "E",
    "timarpur": "E",
    "khyala": "E",
    "mehrauli": "E",
    "chhatarpur": "E",
    "neb sarai": "E",
    "saidulajab": "E",
    "lado sarai": "E",
    "khanpur": "E",
    "govindpuri": "E",
    "badarpur": "E",
    "tughlakabad": "E",
    "hauz qazi": "E",

    # ── CATEGORY F (Industrial / Resettlement Tiers) ──
    "yamuna vihar": "F",
    "majnu ka tila": "F",
    "kalyanpuri": "F",
    "khichripur": "F",
    "trilokpuri": "F",
    "himmatpuri": "F",
    "gazipur": "F",
    "kondli": "F",
    "harsh vihar": "F",
    "sonia vihar": "F",
    "johripur": "F",
    "saboli": "F",
    "meet nagar": "F",
    "nand nagri": "F",
    "mangolpuri": "F",
    "deoli": "F",
    "tigri": "F",
    "madangir": "F",
    "sagarpur": "F",
    "palam": "F",
    "dabri": "F",
    "bindapur": "F",
    "matiala": "F",
    "kakrola": "F",
    "najafgarh": "F",
    "nangloi": "F",
    "mundka": "F",

    # ── CATEGORY G (Unauthorized / Rural Fringe Colonies) ──
    "ambedkar nagar": "G",
    "jahangirpuri": "G",
    "dakshinpuri": "G",
    "sultanpuri": "G",
    "shyam colony": "G",
    "sangam vihar": "G",
    "kirari": "G",
    "prem nagar": "G",
    "mubarakpur": "G",
    "bhalswa": "G",
    "siraspur": "G",
    "libaspur": "G",
    "samaypur": "G",
    "badli": "G",
    "shahbad daulatpur": "G",
    "pooth kalan": "G",
    "begumpur": "G",
    "karala": "G",
    "kanjhawala": "G",
    "bawana": "G",
    "narela": "G",
    "alipur": "G",
    "bakhtawarpur": "G",
    "hamidpur": "G",
    "tajpur": "G",
    "jharoda kalan": "G",
    "dhansa": "G",
    "chhawla": "G",
    "kapashera village": "G",
    "rajokri village": "G",

    # ── CATEGORY H (Rural Border Villages) ──
    "sultanpur majra": "H",
    "fatehpur beri": "H",
    "dera village": "H",
    "bhati village": "H",
    "jonapur": "H",
    "aya nagar": "H",
    "rangpuri": "H",
    "bamnoli": "H",
    "bijwasan village": "H",
    "sultanpur": "H"
}

# Sort dictionary by key length descending so compound names match before generic ones
LOCALITY_CATEGORIES = dict(sorted(_RAW_LOCALITY_CATEGORIES.items(), key=lambda item: len(item[0]), reverse=True))

# Land plot rates by Category (per sq. m) and Year
# 1. 2007-2010 (July 18, 2007 to Feb 7, 2011)
LAND_RATES_2007 = {
    "A": 43000, "B": 34100, "C": 27300, "D": 21800,
    "E": 18400, "F": 16100, "G": 13700, "H": 6900
}
# 2. 2011-2012 (Feb 8, 2011 to Dec 4, 2012)
LAND_RATES_2011 = {
    "A": 86000, "B": 68200, "C": 54600, "D": 43600,
    "E": 36800, "F": 32200, "G": 27400, "H": 13800
}
# 3. 2012-2014 (Dec 5, 2012 to Sept 22, 2014)
LAND_RATES_2012 = {
    "A": 645000, "B": 204600, "C": 133200, "D": 106400,
    "E": 58400, "F": 47200, "G": 38500, "H": 19400
}
# 4. Sept 2014-Present (Sept 23, 2014 onwards)
LAND_RATES_2014 = {
    "A": 774000, "B": 245520, "C": 159840, "D": 127680,
    "E": 70080, "F": 56640, "G": 46200, "H": 23280
}

def get_locality_category(locality_name):
    """
    Resolve a locality string to its official Delhi Circle Rate Category (A to H).
    Returns (category_code, matched_name)
    """
    if not locality_name:
        return "D", "default"
        
    s = locality_name.strip().lower()
    
    # 1. Exact or substring match in ordered dictionary
    for key, cat in LOCALITY_CATEGORIES.items():
        if key in s:
            return cat, key
            
    # 2. Sub-district / SRO name heuristics fallback
    if any(k in s for k in ["vasant", "chanakya", "friends", "golf", "jor"]):
        return "A", "district-a-heuristic"
    elif any(k in s for k in ["defence", "kailash", "south ext", "hauz khas", "saket", "model town"]):
        return "B", "district-b-heuristic"
    elif any(k in s for k in ["lajpat", "kalkaji", "karol", "preet vihar", "malviya"]):
        return "C", "district-c-heuristic"
    elif any(k in s for k in ["rohini", "dwarka", "janakpuri", "mayur", "laxmi", "paschim", "pitampura"]):
        return "D", "district-d-heuristic"
    elif any(k in s for k in ["seelampur", "shahdara", "burari", "mehrauli", "budh vihar"]):
        return "E", "district-e-heuristic"
    elif any(k in s for k in ["narela", "bawana", "sangam vihar", "kanjhawala"]):
        return "G", "district-g-heuristic"
        
    return "D", "default-fallback"

def normalize_area_to_sqm(area_str):
    if not area_str:
        return 0.0
    
    s = str(area_str).strip().lower()
    
    # 1. Prefer explicit Sq. Mtrs / Sq. Meters if present in compound strings
    # e.g., "196.33 Sq. Yards i.e. 164.15 Sq. Mtrs."
    sqm_match = re.search(r'([0-9,.]+)\s*(?:sq\.?\s*m(?:trs|tr|eters|eter)?|sqm|square\s*m(?:eters|eter)?)\b', s)
    if sqm_match:
        try:
            return float(sqm_match.group(1).replace(',', ''))
        except ValueError:
            pass

    # 2. Check for Sq. Yards / Gaj
    sqyd_match = re.search(r'([0-9,.]+)\s*(?:sq\.?\s*y(?:ards|ard|ds|d)?|sqyd|sqyds|square\s*y(?:ards|ard)?|gaj|gaz)\b', s)
    if sqyd_match:
        try:
            val = float(sqyd_match.group(1).replace(',', ''))
            return val * 0.836127
        except ValueError:
            pass

    # 3. Check for Sq. Feet
    sqft_match = re.search(r'([0-9,.]+)\s*(?:sq\.?\s*f(?:eet|oot|t)?|sqft|square\s*f(?:eet|oot)?)\b', s)
    if sqft_match:
        try:
            val = float(sqft_match.group(1).replace(',', ''))
            return val * 0.092903
        except ValueError:
            pass

    # Fallback: Extract first floating number
    match_num = re.search(r'([0-9,.]+)', s)
    if not match_num:
        return 0.0
        
    num_str = match_num.group(1).replace(',', '')
    try:
        val = float(num_str)
    except ValueError:
        return 0.0

    # Default fallback: assume sq.ft if no recognized unit unit
    return val * 0.092903

def get_age_factor(construction_year, registration_year):
    if not construction_year or not registration_year:
        return 1.0
    try:
        age = int(registration_year) - int(construction_year)
    except Exception:
        return 1.0
        
    if age <= 10:
        return 1.0
    elif age <= 20:
        return 0.9
    elif age <= 30:
        return 0.8
    elif age <= 40:
        return 0.7
    elif age <= 50:
        return 0.6
    else:
        return 0.5

def get_usage_multiplier(usage):
    if not usage:
        return 1.0
    u = str(usage).strip().lower()
    if "commercial" in u:
        return 3.0
    elif "industrial" in u:
        return 2.0
    elif "public" in u or "institutional" in u:
        return 1.25
    return 1.0

def get_structure_multiplier(structure_type):
    if not structure_type:
        return 1.0
    s = str(structure_type).strip().lower()
    if "semi" in s:
        return 0.70
    elif "kucha" in s or "temporary" in s:
        return 0.50
    return 1.0

def calculate_circle_rate_details(locality, area_str, property_type, construction_year=None, registration_year=None, usage_type=None, locality_category=None, structure_type=None):
    area_sqm = normalize_area_to_sqm(area_str)
    if area_sqm <= 0:
        return {
            "circle_value": 0.0,
            "area_sqm": 0.0,
            "locality_category": "D",
            "base_rate_per_sqm": 0.0,
            "age_factor": 1.0,
            "usage_multiplier": 1.0,
            "structure_multiplier": 1.0,
            "effective_rate_per_sqm": 0.0
        }
        
    try:
        reg_yr = int(registration_year) if registration_year else 2026
    except Exception:
        reg_yr = 2026
        
    if reg_yr < 2007:
        return {
            "circle_value": 0.0,
            "area_sqm": round(area_sqm, 2),
            "locality_category": "N/A (Pre-2007)",
            "base_rate_per_sqm": 0.0,
            "age_factor": 1.0,
            "usage_multiplier": 1.0,
            "structure_multiplier": 1.0,
            "effective_rate_per_sqm": 0.0
        }

    if reg_yr <= 2010:
        rates_table = LAND_RATES_2007
        flat_mult = 0.35
    elif reg_yr <= 2011:
        rates_table = LAND_RATES_2011
        flat_mult = 0.65
    elif reg_yr <= 2013:
        rates_table = LAND_RATES_2012
        flat_mult = 0.85
    else:
        rates_table = LAND_RATES_2014
        flat_mult = 1.0

    norm_locality = None
    if locality_category and str(locality_category).strip().upper() in "ABCDEFGH":
        norm_locality = str(locality_category).strip().upper()
        
    if not norm_locality:
        norm_locality, _ = get_locality_category(locality)
                
    p_type = (property_type or "").strip().lower()
    
    if "dda" in p_type or "society" in p_type or "cghs" in p_type:
        if area_sqm <= 30:
            rate = 50400
        elif area_sqm <= 50:
            rate = 54480
        elif area_sqm <= 100:
            rate = 66240
        else:
            rate = 76200
        rate = rate * flat_mult
    elif "flat" in p_type or "builder" in p_type or "apartment" in p_type:
        if area_sqm <= 30:
            rate = 55440
        elif area_sqm <= 50:
            rate = 62652
        elif area_sqm <= 100:
            rate = 79488
        else:
            rate = 95250
        rate = rate * flat_mult
    else:
        rate = rates_table.get(norm_locality, 127680)
        
    age_factor = get_age_factor(construction_year, registration_year)
    usage_mult = get_usage_multiplier(usage_type)
    struct_mult = get_structure_multiplier(structure_type)
    
    effective_rate = rate * age_factor * usage_mult * struct_mult
    circle_value = area_sqm * effective_rate
    
    return {
        "circle_value": round(circle_value, 2),
        "area_sqm": round(area_sqm, 2),
        "locality_category": norm_locality,
        "base_rate_per_sqm": round(rate, 2),
        "age_factor": age_factor,
        "usage_multiplier": usage_mult,
        "structure_multiplier": struct_mult,
        "effective_rate_per_sqm": round(effective_rate, 2)
    }

def calculate_circle_rate_value(locality, area_str, property_type, construction_year=None, registration_year=None, usage_type=None, locality_category=None, structure_type=None):
    res = calculate_circle_rate_details(locality, area_str, property_type, construction_year, registration_year, usage_type, locality_category, structure_type)
    return res["circle_value"], res["area_sqm"]

def resolve_smart_circle_valuation(data, meta, locality_category=None):
    """
    Versatile 4-Tier Valuation & Area Resolution Algorithm:
    Tier 1: Explicit Deed Govt Prescribed Value Recital
    Tier 2: Composite Area Summation (Covered + Stilt Parking)
    Tier 3: Smart Priority Area Hierarchy
    Tier 4: Statutory Circle Rate Matrix Fallback
    """
    locality = meta.get("locality", "").strip() if meta else ""
    p_type = data.get("property_type") or (meta.get("property_type") if meta else None) or "private_flat"
    const_year = data.get("construction_year") or (meta.get("construction_year") if meta else None)
    usage_type = data.get("usage_type") or data.get("land_use") or (meta.get("land_use") if meta else None)
    structure_type = data.get("structure_type")
    
    reg_year = None
    exec_date = data.get("date_of_execution")
    if exec_date and "-" in exec_date:
        parts = exec_date.split("-")
        if len(parts) == 3 and len(parts[2]) == 4:
            reg_year = parts[2]

    # Tier 1: Explicit Govt Prescribed Value in Deed Text
    explicit_val = (
        data.get("circle_rate_value_stated") or
        data.get("govt_prescribed_value") or
        data.get("declared_circle_value") or
        data.get("circle_rate_value")
    )
    if explicit_val:
        try:
            val_num = float(re.sub(r"[^\d.]", "", str(explicit_val)))
            if val_num > 0:
                area_raw = data.get("covered_area") or data.get("built_up_area") or data.get("area")
                area_sqm = normalize_area_to_sqm(area_raw)
                return {
                    "circle_value": round(val_num, 2),
                    "area_sqm": round(area_sqm, 2),
                    "valuation_source": "Explicit Deed Govt Recital"
                }
        except Exception:
            pass

    # Tier 2: Composite Area Summation (Covered + Stilt Parking)
    covered_raw = data.get("covered_area") or data.get("built_up_area")
    stilt_raw = data.get("stilt_area") or data.get("stilt_parking_area")
    
    if covered_raw and stilt_raw:
        cov_sqm = normalize_area_to_sqm(covered_raw)
        stilt_sqm = normalize_area_to_sqm(stilt_raw)
        if cov_sqm > 0:
            cov_det = calculate_circle_rate_details(locality, str(cov_sqm) + " sqm", p_type, const_year, reg_year, usage_type, locality_category, structure_type)
            stilt_det = calculate_circle_rate_details(locality, str(stilt_sqm) + " sqm", p_type, const_year, reg_year, usage_type, locality_category, structure_type)
            composite_val = cov_det["circle_value"] + (stilt_det["circle_value"] * 0.25)
            total_sqm = cov_sqm + stilt_sqm
            return {
                "circle_value": round(composite_val, 2),
                "area_sqm": round(total_sqm, 2),
                "valuation_source": "Composite Covered + Stilt Summation"
            }

    # Tier 3: Smart Priority Area Hierarchy
    p_lower = str(p_type).lower()
    if "flat" in p_lower or "builder" in p_lower or "apartment" in p_lower or "floor" in p_lower:
        best_area = (
            data.get("covered_area") or
            data.get("built_up_area") or
            data.get("carpet_area") or
            data.get("super_built_up_area") or
            data.get("undivided_land_share_area") or
            data.get("area")
        )
    elif "plot" in p_lower or "land" in p_lower or "agricultural" in p_lower:
        best_area = (
            data.get("plot_area") or
            data.get("land_area") or
            data.get("area")
        )
    else:
        best_area = (
            data.get("built_up_area") or
            data.get("covered_area") or
            data.get("area")
        )

    det = calculate_circle_rate_details(locality, best_area, p_type, const_year, reg_year, usage_type, locality_category, structure_type)
    det["valuation_source"] = "Statutory Circle Rate Matrix"
    return det

def get_historical_stamp_duty_rate(registration_year, gender, valuation_basis):
    try:
        year = int(registration_year)
    except Exception:
        year = 2026

    g = (gender or "male").strip().lower()
    if g not in ["male", "female", "joint"]:
        g = "male"

    if year < 2003:
        return 0.08
    elif year <= 2007:
        if g == "female":
            return 0.05
        elif g == "joint":
            return 0.07
        else:
            return 0.08
    else:
        # Standard Delhi Rates (Stamp Duty + MCD Transfer Tax):
        # Female Buyer: 4% (3% SD + 1% MCD)
        # Joint (Female + Male): 5% (3.5% SD + 1.5% MCD)
        # Male Buyers: 6% (3% SD + 3% MCD)
        if g == "female":
            return 0.04
        elif g == "joint":
            return 0.05
        else:
            return 0.06
