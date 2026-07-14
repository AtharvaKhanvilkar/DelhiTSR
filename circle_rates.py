import re

# Mappings for common Delhi localities to Categories (A-H)
# Ordered by length descending so that specific compound names match first
LOCALITY_CATEGORIES = {
    "friends colony east": "A",
    "friends colony west": "A",
    "green park extension": "B",
    "hauz khas enclave": "B",
    "shanti niketan": "A",
    "maharani bagh": "A",
    "panchsheel park": "A",
    "anand niketan": "A",
    "connaught place": "A",
    "vasant vihar": "A",
    "sunder nagar": "A",
    "golf links": "A",
    "west end": "A",
    "jor bagh": "A",
    
    "safdarjung enclave": "B",
    "defence colony": "B",
    "greater kailash": "B",
    "gulmohar park": "B",
    "green park": "B",
    "anand lok": "B",
    "south extension": "B",
    "nizamuddin east": "B",
    "sarvpriya vihar": "B",
    "panchsheel enclave": "B",
    "hauz khas": "B",
    
    "chittaranjan park": "C",
    "nizamuddin west": "C",
    "lajpat nagar": "C",
    "east of kailash": "C",
    "malviya nagar": "C",
    "vasant kunj": "C",
    "karol bagh": "C",
    "patel nagar": "C",
    "alaknanda": "C",
    "kalkaji": "C",
    "munirka": "C",
    
    "shalimar bagh": "D",
    "paschim vihar": "D",
    "sukhdev vihar": "D",
    "gagan vihar": "D",
    "anand vihar": "D",
    "mayur vihar": "D",
    "pitampura": "D",
    "laxmi nagar": "D",
    "janakpuri": "D",
    "hari nagar": "D",
    "kirti nagar": "D",
    "dwarka": "D",
    "rohini": "D",
    "daryaganj": "D",
    
    "dilshad garden": "E",
    "geeta colony": "E",
    "chandni chowk": "E",
    "pahar ganj": "E",
    "hauz qazi": "E",
    
    "majnu ka tila": "F",
    "yamuna vihar": "F",
    "kalyanpuri": "F",
    "khichripur": "F",
    "nand nagri": "F",
    
    "ambedkar nagar": "G",
    "jahangirpuri": "G",
    "dakshinpuri": "G",
    "sangam vihar": "G",
    "sultanpuri": "G",
    
    "sultanpur majra": "H"
}

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

def normalize_area_to_sqm(area_str):
    if not area_str:
        return 0.0
    
    # Clean the string, convert to lowercase
    s = area_str.strip().lower()
    
    # Extract first numeric sequence (handles commas/decimals)
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
        
    if age < 0:
        return 1.0
    elif age <= 10:
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
        
    # Delhi circle rates were introduced on July 18, 2007.
    # We do not evaluate circle rates for any deeds registered before 2007.
    try:
        reg_yr = int(registration_year) if registration_year else 2026
    except Exception:
        reg_yr = 2026
        
    if reg_yr < 2007:
        return 0.0, 0.0

    # Determine rate table and flat multiplier based on the registration year
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
        norm_locality = "D"
        if locality:
            cleaned_locality = locality.strip().lower()
            for key in LOCALITY_CATEGORIES:
                if key in cleaned_locality:
                    norm_locality = LOCALITY_CATEGORIES[key]
                    break
                
    # Normalize property_type
    p_type = (property_type or "").strip().lower()
    
    # Calculate flat or land rate
    if "dda" in p_type or "society" in p_type or "cghs" in p_type:
        # DDA / CGHS / Society Flat
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
        # Private builder flat
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
        # Default to current rates if year is missing/invalid
        year = 2026

    # Normalize gender
    g = (gender or "male").strip().lower()
    if g not in ["male", "female", "joint"]:
        g = "male"

    if year < 2003:
        # Before 2003: 8% for all
        return 0.08
    elif year <= 2007:
        # 2003 - 2007: Male 8%, Female 5%, Joint 7%
        if g == "female":
            return 0.05
        elif g == "joint":
            return 0.07
        else:
            return 0.08
    else:
        # 2008 onwards
        # Check for July 2023 MCD surcharge increase for properties > 25 Lakhs (2.5 million)
        if year >= 2024 or (year == 2023 and valuation_basis > 2500000):
            if g == "female":
                return 0.05
            elif g == "joint":
                return 0.06
            else:
                return 0.07
        else:
            # 2008 - 2023 (or < 25L): Male 6%, Female 4%, Joint 5%
            if g == "female":
                return 0.04
            elif g == "joint":
                return 0.05
            else:
                return 0.06
