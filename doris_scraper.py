import base64
import urllib.parse
import re
from bs4 import BeautifulSoup
import requests

def normalize_sro_name(gov_name):
    mapping = {
        "Central -Asaf Ali (SR III)": "SRO III (Asaf Ali Road)",
        "Central-KashmereGate (SR I)": "SRO VI (Kashmere Gate)",
        "East- Geeta Colony (SR VIII)": "SRO VIII (Geeta Colony)",
        "East-Preet Vihar (SR VIIIA)": "SRO VIII-A (Vasundhara Enclave)",
        "New Delhi- INA (SR VII)": "SRO VII (INA)",
        "New Delhi- Sarojini Nagar (SR VII A)": "SRO VII-A (Sarojini Nagar)",
        "North - Libaspur (SR VI E)": "SRO VI-E (Libaspur)",
        "North -Narela(SR VIB)": "SRO VI-B (Narela)",
        "North East-Seelampur (SR IV)": "SRO IV (Seelampur)",
        "North West Model Town (SR VIA)": "SRO VI-A (Pitampura / Model Town)",
        "North West-Khanjwala (SR VID)": "SRO VI-C (Kanjhawala)",
        "North West-Rohini (SR VIC)": "SRO VI-B (Rohini)",
        "Shahdara (SR IVA)": "SRO IV-A (Shahdara)",
        "Shahdara-Vivek Vihar(SR IVB)": "SRO IV-B (Vivek Vihar)",
        "South East - Defence Colony (SR V(1))": "SRO V (Defence Colony)",
        "South East-Mehrauli (SR V)": "SRO V (Mehrauli)",
        "South West (Sub Registrar IXA )": "SRO IX-A (Najafgarh)",
        "South-Hauz Khas (SR V A)": "SRO V-A (Hauz Khas)",
        "SouthWest (Sub Registrar IX)": "SRO IX (Kapashera)",
        "West-Basai Darapur (SR II)": "SRO II (Basai Darapur)",
        "West-Janakpuri (SR IIB)": "SRO II-B (Janakpuri)",
        "West-Punjabi Bagh (SR IIA)": "SRO II-A (Punjabi Bagh)"
    }
    cleaned = gov_name.strip()
    return mapping.get(cleaned) or cleaned

class DorisScraperSession:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://esearch.delhigovt.nic.in/Complete_search.aspx"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://esearch.delhigovt.nic.in",
            "Referer": "https://esearch.delhigovt.nic.in/Complete_search.aspx"
        }
        self.viewstate = ""
        self.viewstate_generator = "AA2F82EF"
        self.eventvalidation = ""
        self.randomno = "266"
        self.csrftoken = "266"

    def _extract_tokens(self, html):
        """Helper to parse ASP.NET tokens from HTML page response"""
        soup = BeautifulSoup(html, "html.parser")
        
        vs = soup.find("input", {"id": "__VIEWSTATE"})
        if vs:
            self.viewstate = vs.get("value", "")
            
        vsg = soup.find("input", {"id": "__VIEWSTATEGENERATOR"})
        if vsg:
            self.viewstate_generator = vsg.get("value", "")
            
        ev = soup.find("input", {"id": "__EVENTVALIDATION"})
        if ev:
            self.eventvalidation = ev.get("value", "")

        rno = soup.find("input", {"id": "ctl00_ContentPlaceHolder1_txtrandomno"})
        if rno:
            self.randomno = rno.get("value", "")
            
        ct = soup.find("input", {"id": "ctl00_ContentPlaceHolder1_csrftoken"})
        if ct:
            self.csrftoken = ct.get("value", "")
            
        return soup

    def start_session(self):
        """Initial GET request to load state and fetch SROs"""
        try:
            r = self.session.get(self.base_url, headers=self.headers, timeout=20)
            soup = self._extract_tokens(r.text)
            
            sro_select = soup.find("select", {"id": "ctl00_ContentPlaceHolder1_ddl_sro_s"})
            sros = []
            if sro_select:
                for opt in sro_select.find_all("option"):
                    val = opt.get("value", "")
                    if val != "0":
                        gov_name = opt.text.strip()
                        sros.append({"id": val, "name": normalize_sro_name(gov_name)})
            return {"ok": True, "sro_list": sros}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def select_sro(self, sro_val):
        """Submit postback for SRO selection to load Localities"""
        payload = {
            "ctl00$ContentPlaceHolder1$ToolkitScriptManager2_HiddenField": "",
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$ddl_sro_s",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": self.viewstate,
            "__VIEWSTATEGENERATOR": self.viewstate_generator,
            "__VIEWSTATEENCRYPTED": "",
            "__EVENTVALIDATION": self.eventvalidation,
            "ctl00$ContentPlaceHolder1$ddl_sro_s": sro_val,
            "ctl00$ContentPlaceHolder1$ddl_loc_s": "0",
            "ctl00$ContentPlaceHolder1$ddl_year_s": "0",
            "ctl00$ContentPlaceHolder1$txtkhasra": "",
            "ctl00$ContentPlaceHolder1$ddl_deed_s": "0",
            "ctl00$ContentPlaceHolder1$ddl_s_deed_s": "0",
            "ctl00$ContentPlaceHolder1$txt_regno_s": "",
            "ctl00$ContentPlaceHolder1$txt_first_s": "",
            "ctl00$ContentPlaceHolder1$txt_second_s": "",
            "ctl00$ContentPlaceHolder1$txtcaptcha_s": "",
            "ctl00$ContentPlaceHolder1$txtrandomno": self.randomno,
            "ctl00$ContentPlaceHolder1$csrftoken": self.csrftoken
        }
        try:
            r = self.session.post(self.base_url, data=payload, headers=self.headers, timeout=20)
            soup = self._extract_tokens(r.text)
            
            loc_select = soup.find("select", {"id": "ctl00_ContentPlaceHolder1_ddl_loc_s"})
            localities = []
            if loc_select:
                for opt in loc_select.find_all("option"):
                    val = opt.get("value", "")
                    if val != "0":
                        localities.append({"id": val, "name": opt.text.strip()})
            return {"ok": True, "locality_list": localities}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def select_locality(self, sro_val, loc_val):
        """Submit postback for Locality selection to load Years & Captcha"""
        payload = {
            "ctl00$ContentPlaceHolder1$ToolkitScriptManager2_HiddenField": "",
            "__EVENTTARGET": "ctl00$ContentPlaceHolder1$ddl_loc_s",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": self.viewstate,
            "__VIEWSTATEGENERATOR": self.viewstate_generator,
            "__VIEWSTATEENCRYPTED": "",
            "__EVENTVALIDATION": self.eventvalidation,
            "ctl00$ContentPlaceHolder1$ddl_sro_s": sro_val,
            "ctl00$ContentPlaceHolder1$ddl_loc_s": loc_val,
            "ctl00$ContentPlaceHolder1$ddl_year_s": "0",
            "ctl00$ContentPlaceHolder1$txtkhasra": "",
            "ctl00$ContentPlaceHolder1$ddl_deed_s": "0",
            "ctl00$ContentPlaceHolder1$ddl_s_deed_s": "0",
            "ctl00$ContentPlaceHolder1$txt_regno_s": "",
            "ctl00$ContentPlaceHolder1$txt_first_s": "",
            "ctl00$ContentPlaceHolder1$txt_second_s": "",
            "ctl00$ContentPlaceHolder1$txtcaptcha_s": "",
            "ctl00$ContentPlaceHolder1$txtrandomno": self.randomno,
            "ctl00$ContentPlaceHolder1$csrftoken": self.csrftoken
        }
        try:
            r = self.session.post(self.base_url, data=payload, headers=self.headers, timeout=20)
            soup = self._extract_tokens(r.text)
            
            # Extract Years
            year_select = soup.find("select", {"id": "ctl00_ContentPlaceHolder1_ddl_year_s"})
            years = []
            if year_select:
                for opt in year_select.find_all("option"):
                    val = opt.get("value", "")
                    if val != "0":
                        years.append(opt.text.strip())
            
            # Find Captcha Image
            captcha_img = soup.find("img", {"alt": "Captcha"})
            captcha_b64 = ""
            if captcha_img:
                src = captcha_img.get("src", "")
                if src:
                    # Construct full image URL (relative to base URL)
                    captcha_url = urllib.parse.urljoin(self.base_url, src)
                    c_resp = self.session.get(captcha_url, headers=self.headers, timeout=20)
                    if c_resp.status_code == 200:
                        captcha_b64 = "data:image/png;base64," + base64.b64encode(c_resp.content).decode("utf-8")
                        
            return {"ok": True, "reg_years": years, "captcha_image_base64": captcha_b64}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def execute_search(self, sro_val, loc_val, year_val, params, captcha_text):
        """Execute search with the CAPTCHA code and extract table records"""
        payload = {
            "ctl00$ContentPlaceHolder1$ToolkitScriptManager2_HiddenField": "",
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__VIEWSTATE": self.viewstate,
            "__VIEWSTATEGENERATOR": self.viewstate_generator,
            "__VIEWSTATEENCRYPTED": "",
            "__EVENTVALIDATION": self.eventvalidation,
            "ctl00$ContentPlaceHolder1$ddl_sro_s": sro_val,
            "ctl00$ContentPlaceHolder1$ddl_loc_s": loc_val,
            "ctl00$ContentPlaceHolder1$ddl_year_s": year_val,
            "ctl00$ContentPlaceHolder1$txtkhasra": params.get("property_address", ""),
            "ctl00$ContentPlaceHolder1$ddl_deed_s": "0",
            "ctl00$ContentPlaceHolder1$ddl_s_deed_s": "0",
            "ctl00$ContentPlaceHolder1$txt_regno_s": params.get("reg_no", ""),
            "ctl00$ContentPlaceHolder1$txt_first_s": params.get("first_party", ""),
            "ctl00$ContentPlaceHolder1$txt_second_s": params.get("second_party", ""),
            "ctl00$ContentPlaceHolder1$txtcaptcha_s": captcha_text,
            "ctl00$ContentPlaceHolder1$btn_search_s": "Search",
            "ctl00$ContentPlaceHolder1$txtrandomno": self.randomno,
            "ctl00$ContentPlaceHolder1$csrftoken": self.csrftoken
        }
        try:
            r = self.session.post(self.base_url, data=payload, headers=self.headers, timeout=45)
            self._extract_tokens(r.text)
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Check for error alerts (like "Incorrect Captcha")
            alert_match = re.search(r"alert\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", r.text)
            if alert_match:
                return {"ok": False, "error": alert_match.group(1).strip()}

            def parse_rows(soup_obj):
                parsed = []
                tables = soup_obj.find_all("table")
                date_regex = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}$")
                known_deeds = ["CONVEYANCE", "SALE", "LEASE", "GIFT", "MORTGAGE", "RELINQUISHMENT", "WILL", "GPA", "POWER OF ATTORNEY", "DEED"]
                
                for table in tables:
                    rows = table.find_all("tr")
                    if not rows:
                        continue
                    header_text = "".join([th.text for th in rows[0].find_all(["th", "td"])]).lower()
                    if "reg. no" in header_text or "registration number" in header_text or "first party" in header_text or "deed" in header_text:
                        for r_idx in range(1, len(rows)):
                            # Look only at direct tds to avoid flattening nested tables
                            cols = rows[r_idx].find_all("td", recursive=False)
                            if len(cols) < 3:
                                continue
                            
                            raw_texts = [c.text.strip() for c in cols]
                            
                            # Detect which column index contains the registration date (DD-MM-YYYY)
                            date_col_idx = -1
                            for c_i, val in enumerate(raw_texts):
                                if date_regex.match(val):
                                    date_col_idx = c_i
                                    break
                            
                            reg_no = ""
                            reg_date = ""
                            first_party = ""
                            second_party = ""
                            addr_text = ""
                            deed_type = "Deed"
                            
                            if len(cols) == 11 and date_col_idx == 1:
                                reg_no = raw_texts[0]
                                reg_date = raw_texts[1]
                                first_party = raw_texts[2]
                                second_party = raw_texts[4]
                                addr_text = raw_texts[6]
                                deed_type = raw_texts[9]
                            elif len(cols) == 8 and date_col_idx == 1:
                                reg_no = raw_texts[0]
                                reg_date = raw_texts[1]
                                first_party = raw_texts[2]
                                second_party = raw_texts[3]
                                addr_text = raw_texts[4]
                                deed_type = raw_texts[6]
                            else:
                                # Dynamic alignment based on date_col_idx
                                if date_col_idx == 2:
                                    # Column 1 was Book/Vol No (e.g. '1')
                                    reg_no = raw_texts[0]
                                    reg_date = raw_texts[2]
                                    
                                    col3 = raw_texts[3] if len(raw_texts) > 3 else ""
                                    if any(kd in col3.upper() for kd in known_deeds):
                                        deed_type = col3
                                        first_party = "POI"
                                        second_party = raw_texts[4] if len(raw_texts) > 4 and raw_texts[4].upper() not in known_deeds else ""
                                        addr_text = raw_texts[5] if len(raw_texts) > 5 else (raw_texts[4] if len(raw_texts) > 4 else "")
                                    else:
                                        first_party = col3
                                        second_party = raw_texts[4] if len(raw_texts) > 4 else ""
                                        deed_type = raw_texts[5] if len(raw_texts) > 5 else "Deed"
                                        addr_text = raw_texts[6] if len(raw_texts) > 6 else (raw_texts[5] if len(raw_texts) > 5 else "")
                                elif date_col_idx == 1:
                                    reg_no = raw_texts[0]
                                    reg_date = raw_texts[1]
                                    first_party = raw_texts[2] if len(raw_texts) > 2 else ""
                                    second_party = raw_texts[3] if len(raw_texts) > 3 else ""
                                    addr_text = raw_texts[4] if len(raw_texts) > 4 else ""
                                    deed_type = raw_texts[5] if len(raw_texts) > 5 else "Deed"
                                else:
                                    reg_no = raw_texts[0]
                                    reg_date = raw_texts[1] if len(raw_texts) > 1 else ""
                                    first_party = raw_texts[2] if len(raw_texts) > 2 else ""
                                    second_party = raw_texts[3] if len(raw_texts) > 3 else ""
                                    addr_text = raw_texts[4] if len(raw_texts) > 4 else ""
                                    deed_type = raw_texts[5] if len(raw_texts) > 5 else "Deed"
                            
                            # Clean deed_type if it is comma-separated (e.g. SALE,SALE WITHIN MC AREA)
                            if "," in deed_type:
                                deed_type = deed_type.split(",")[0].strip()
                            
                            # Fallback for historical registration details in address block if main details are empty
                            if not reg_no or not reg_date:
                                match = re.search(r"Reg\.?No.*?\s+(\d+)\s*([14])?\s*([\d]{2}[\-/][\d]{2}[\-/][\d]{4})\s+([A-Za-z_ \-]+)\s+(\d+)", addr_text, re.IGNORECASE)
                                if match:
                                    reg_val = match.group(1)
                                    if match.group(2):
                                        reg_no = reg_val
                                    else:
                                        reg_no = reg_val[:-1] if len(reg_val) > 1 else reg_val
                                    reg_date = match.group(3)
                                    deed_type = match.group(4).strip()
                                    if "," in deed_type:
                                        deed_type = deed_type.split(",")[0].strip()
                            
                            # Strip nested table or historical lines from the property address text
                             # Strip nested table or historical lines from the property address text
                            clean_addr = addr_text
                            for marker in ["Reg.No", "Property History", "Reg.Date", "SR_Office"]:
                                lbl_idx = clean_addr.find(marker)
                                if lbl_idx != -1:
                                    clean_addr = clean_addr[:lbl_idx].strip()
                            
                            # Sanity check: Reject phantom empty rows (like '<td colspan="6">Deed</td>')
                            if not reg_no and not reg_date and not first_party and not second_party and (not clean_addr or clean_addr.upper() == "DEED"):
                                continue
                                
                            # Shifted column correction: If second_party is a pure integer/plot number (e.g. '93' or 'FLAT 93'), shift it to address
                            if second_party and (second_party.isdigit() or re.match(r'^(?:FLAT|PLOT|NO\.?)\s*\d+$', second_party, re.IGNORECASE)):
                                if not clean_addr or clean_addr == "—":
                                    clean_addr = second_party
                                elif second_party not in clean_addr:
                                    clean_addr = f"Plot/Flat No. {second_party}, {clean_addr}"
                                second_party = "POI" if first_party != "POI" else "—"

                            parsed.append({
                                "reg_no": reg_no,
                                "reg_date": reg_date,
                                "first_party": first_party,
                                "second_party": second_party,
                                "property_address": clean_addr,
                                "deed_type": deed_type
                            })
                return parsed

            records = parse_rows(soup)
            
            # Find pagination page count from page links (Page$2, Page$3, etc.)
            max_page = 1
            for link in soup.find_all("a", href=True):
                m = re.search(r"Page\$(\d+)", link["href"])
                if m:
                    page_num = int(m.group(1))
                    if page_num > max_page:
                        max_page = page_num
                        
            # Loop through subsequent pages and fetch records
            if max_page > 1:
                for page_num in range(2, max_page + 1):
                    page_payload = {
                        "ctl00$ContentPlaceHolder1$ToolkitScriptManager2_HiddenField": "",
                        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$gv_search",
                        "__EVENTARGUMENT": f"Page${page_num}",
                        "__VIEWSTATE": self.viewstate,
                        "__VIEWSTATEGENERATOR": self.viewstate_generator,
                        "__VIEWSTATEENCRYPTED": "",
                        "__EVENTVALIDATION": self.eventvalidation,
                        "ctl00$ContentPlaceHolder1$ddl_sro_s": sro_val,
                        "ctl00$ContentPlaceHolder1$ddl_loc_s": loc_val,
                        "ctl00$ContentPlaceHolder1$ddl_year_s": year_val,
                        "ctl00$ContentPlaceHolder1$txtkhasra": params.get("property_address", ""),
                        "ctl00$ContentPlaceHolder1$ddl_deed_s": "0",
                        "ctl00$ContentPlaceHolder1$ddl_s_deed_s": "0",
                        "ctl00$ContentPlaceHolder1$txt_regno_s": params.get("reg_no", ""),
                        "ctl00$ContentPlaceHolder1$txt_first_s": params.get("first_party", ""),
                        "ctl00$ContentPlaceHolder1$txt_second_s": params.get("second_party", ""),
                        "ctl00$ContentPlaceHolder1$txtcaptcha_s": captcha_text,
                        "ctl00$ContentPlaceHolder1$txtrandomno": self.randomno,
                        "ctl00$ContentPlaceHolder1$csrftoken": self.csrftoken
                    }
                    try:
                        r_page = self.session.post(self.base_url, data=page_payload, headers=self.headers, timeout=45)
                        self._extract_tokens(r_page.text)
                        soup_page = BeautifulSoup(r_page.text, "html.parser")
                        records.extend(parse_rows(soup_page))
                    except Exception as e:
                        # Log error but don't crash if we have previous pages' results
                        print(f"Warning: Failed to fetch search results page {page_num}: {e}")
            
            # De-duplicate fetched records across postback pages
            unique_records = []
            seen = set()
            for rec in records:
                key = (
                    rec.get("reg_no", "").strip().lower(),
                    rec.get("reg_date", "").strip().lower(),
                    rec.get("first_party", "").strip().lower(),
                    rec.get("second_party", "").strip().lower(),
                    rec.get("deed_type", "").strip().lower(),
                    rec.get("property_address", "").strip().lower(),
                )
                if key not in seen:
                    seen.add(key)
                    unique_records.append(rec)
            records = unique_records
            
            if not records:
                page_text_lower = soup.text.lower()
                if "no record" in page_text_lower or "no transaction" in page_text_lower:
                    return {"ok": True, "records": []}
                else:
                    return {
                        "ok": False,
                        "error": "Registry session expired or CAPTCHA verification failed. Please refresh the page and try again."
                    }
            
            return {"ok": True, "records": records}
        except Exception as e:
            return {"ok": False, "error": str(e)}
