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
    "chittaranjan park": "C", # Category C in official gazette
    "c.r. park": "C",
    "cr park": "C",
    "patel nagar east": "B",
    "patel nagar west": "B",
    "patel nagar south": "B",
    "kirti nagar": "D", # Category D

    # ── CATEGORY C (Upper Middle Class Colonies) ──
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
    "janakpuri": "D", # Category D in official table
    "pitampura": "D",
    "paschim vihar": "D",
    "shalimar bagh": "D",
    "ashok vihar": "C",
    "kamla nagar": "C",
    "roop nagar": "C",
    "shakti nagar": "C",
    "preet vihar": "C",
    "anand vihar": "C",
    "ip extension": "C",
    "karkardooma": "C",
    "vikas marg": "C",

    # ── CATEGORY D (Middle Class Residential / Established Hubs) ──
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
    "dwarka sector 1": "D",
    "dwarka sector 2": "D",
    "dwarka sector 3": "D",
    "dwarka sector 4": "D",
    "dwarka sector 5": "D",
    "dwarka sector 6": "D",
    "dwarka sector 7": "D",
    "dwarka sector 8": "D",
    "dwarka sector 9": "D",
    "dwarka sector 10": "D",
    "dwarka sector 11": "D",
    "dwarka sector 12": "D",
    "dwarka sector 13": "D",
    "dwarka sector 14": "D",
    "dwarka sector 15": "D",
    "dwarka sector 16": "D",
    "dwarka sector 17": "D",
    "dwarka sector 18": "D",
    "dwarka sector 19": "D",
    "dwarka sector 20": "D",
    "dwarka sector 21": "D",
    "dwarka sector 22": "D",
    "dwarka sector 23": "D",
    "dwarka sector 24": "D",
    "dwarka": "D",
    "rohini sector 1": "D",
    "rohini sector 2": "D",
    "rohini sector 3": "D",
    "rohini sector 4": "D",
    "rohini sector 5": "D",
    "rohini sector 6": "D",
    "rohini sector 7": "D",
    "rohini sector 8": "D",
    "rohini sector 9": "D",
    "rohini sector 10": "D",
    "rohini sector 11": "D",
    "rohini sector 12": "D",
    "rohini sector 13": "D",
    "rohini sector 14": "D",
    "rohini sector 15": "D",
    "rohini": "D",
    "laxmi nagar": "D",
    "shakarpur": "D",
    "geeta colony": "E", # Category E
    "nirman vihar": "D",
    "pandav nagar": "D",
    "patparganj": "D",
    "dilshad garden": "E",
    "shahdara": "E",
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
    "pahar ganj": "E",
    "paharganj": "E",
    "sadar bazar": "E",
    "chandni chowk": "E",
    "kashmere gate": "E",

    # ── CATEGORY E (Lower Middle Class & Urbanized Villages) ──
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
    "yamuna vihar": "F",
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
    "majnu ka tila": "F",
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
    "ambedkar nagar": "G",
    "jahangirpuri": "G",
    "dakshinpuri": "G",
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
    "sultanpuri": "G",
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
    "sultanpur majra": "H",
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
    
    s = area_str.strip().lower()
    match_num = re.search(r'([0-9,.]+)', s)
    if not match_num:
        return 0.0
        
    num_str = match_num.group(1).replace(',', '')
    try:
        val = float(num_str)
    except ValueError:
        return 0.0
        
    # Normalize units:
    # 1 Gaj (sq.yd) = 0.836127 sqm
    # 1 Sq.Ft = 0.092903 sqm
    if any(u in s for u in ["sq.ft", "sqft", "square feet", "square foot", "sq feet", "sq foot"]):
        return val * 0.092903
    elif any(u in s for u in ["sq.yd", "sqyds", "sqyd", "square yards", "square yard", "sq yards", "sq yard", "gaj", "gaz"]):
        return val * 0.836127
    elif any(u in s for u in ["sq.m", "sqm", "square meter", "square metre", "sq meters", "sq metres", "sq. meters"]):
        return val * 1.0
        
    # Default fallback: assume sq.ft if no unit is found
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

def calculate_circle_rate_value(locality, area_str, property_type, construction_year=None, registration_year=None, usage_type=None, locality_category=None):
    area_sqm = normalize_area_to_sqm(area_str)
    if area_sqm <= 0:
        return 0.0, 0.0
        
    try:
        reg_yr = int(registration_year) if registration_year else 2026
    except Exception:
        reg_yr = 2026
        
    # Circle rates introduced on July 18, 2007
    if reg_yr < 2007:
        return 0.0, 0.0

    # Rate table selection based on registration year
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

    # Determine category
    norm_locality = None
    if locality_category and str(locality_category).strip().upper() in "ABCDEFGH":
        norm_locality = str(locality_category).strip().upper()
        
    if not norm_locality:
        norm_locality, _ = get_locality_category(locality)
                
    p_type = (property_type or "").strip().lower()
    
    # Calculate flat or land rate
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
        # Land plot
        rate = rates_table.get(norm_locality, 127680)
        
    age_factor = get_age_factor(construction_year, registration_year)
    usage_mult = get_usage_multiplier(usage_type)
    circle_value = area_sqm * rate * age_factor * usage_mult
    return round(circle_value, 2), round(area_sqm, 2)

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
        if year >= 2024 or (year == 2023 and valuation_basis > 2500000):
            if g == "female":
                return 0.05
            elif g == "joint":
                return 0.06
            else:
                return 0.07
        else:
            if g == "female":
                return 0.04
            elif g == "joint":
                return 0.05
            else:
                return 0.06
