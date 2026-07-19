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
            r = self.session.get(self.base_url, headers=self.headers, timeout=10)
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
            r = self.session.post(self.base_url, data=payload, headers=self.headers, timeout=10)
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
            r = self.session.post(self.base_url, data=payload, headers=self.headers, timeout=10)
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
                    c_resp = self.session.get(captcha_url, headers=self.headers, timeout=10)
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
            r = self.session.post(self.base_url, data=payload, headers=self.headers, timeout=15)
            self._extract_tokens(r.text)
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Check for error alerts (like "Incorrect Captcha")
            alert_match = re.search(r"alert\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", r.text)
            if alert_match:
                return {"ok": False, "error": alert_match.group(1).strip()}

            tables = soup.find_all("table")
            records = []
            
            for table in tables:
                rows = table.find_all("tr")
                if not rows:
                    continue
                
                header_text = "".join([th.text for th in rows[0].find_all(["th", "td"])]).lower()
                if "reg. no" in header_text or "registration number" in header_text or "first party" in header_text:
                    headers = [th.text.strip() for th in rows[0].find_all(["th", "td"])]
                    with open("scratch/debug_search.log", "w", encoding="utf-8") as f:
                        f.write(f"Headers: {headers}\n")
                        for r_idx in range(1, len(rows)):
                            c_list = [c.text.strip() for c in rows[r_idx].find_all("td")]
                            f.write(f"Row {r_idx} cols (len={len(c_list)}): {c_list}\n")
                    
                    for r_idx in range(1, len(rows)):
                        # Look only at direct tds to avoid flattening nested tables
                        cols = rows[r_idx].find_all("td", recursive=False)
                        if len(cols) < 3:
                            continue
                        
                        reg_no = ""
                        reg_date = ""
                        first_party = ""
                        second_party = ""
                        addr_text = ""
                        deed_type = "Deed"
                        
                        if len(cols) == 11:
                            reg_no = cols[0].text.strip()
                            reg_date = cols[1].text.strip()
                            first_party = cols[2].text.strip()
                            second_party = cols[4].text.strip()
                            addr_text = cols[6].text.strip()
                            deed_type = cols[9].text.strip()
                        elif len(cols) == 8:
                            reg_no = cols[0].text.strip()
                            reg_date = cols[1].text.strip()
                            first_party = cols[2].text.strip()
                            second_party = cols[3].text.strip()
                            addr_text = cols[4].text.strip()
                            deed_type = cols[6].text.strip()
                        else:
                            # Direct index mapping fallback
                            reg_no = cols[0].text.strip()
                            reg_date = cols[1].text.strip()
                            first_party = cols[2].text.strip()
                            if len(cols) > 4:
                                second_party = cols[3].text.strip()
                                addr_text = cols[4].text.strip()
                            if len(cols) > 6:
                                deed_type = cols[6].text.strip()
                        
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
                        clean_addr = addr_text
                        for marker in ["Reg.No", "Property History", "Reg.Date", "SR_Office"]:
                            lbl_idx = clean_addr.find(marker)
                            if lbl_idx != -1:
                                clean_addr = clean_addr[:lbl_idx].strip()
                        
                        records.append({
                            "reg_no": reg_no,
                            "reg_date": reg_date,
                            "first_party": first_party,
                            "second_party": second_party,
                            "property_address": clean_addr,
                            "deed_type": deed_type
                        })
            
            return {"ok": True, "records": records}
        except Exception as e:
            return {"ok": False, "error": str(e)}
