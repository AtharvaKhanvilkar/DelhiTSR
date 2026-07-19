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
        self.base_url = "http://esearch.delhigovt.nic.in/Complete_search.aspx"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "http://esearch.delhigovt.nic.in",
            "Referer": "http://esearch.delhigovt.nic.in/Complete_search.aspx"
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
            alert_script = soup.find("script", text=re.compile(r"alert\("))
            if alert_script:
                match = re.search(r"alert\(['\"]([^'\"]+)['\"]\)", alert_script.text)
                if match:
                    return {"ok": False, "error": match.group(1)}

            tables = soup.find_all("table")
            records = []
            
            for table in tables:
                rows = table.find_all("tr")
                if not rows:
                    continue
                
                header_text = "".join([th.text for th in rows[0].find_all(["th", "td"])]).lower()
                if "reg. no" in header_text or "registration number" in header_text or "first party" in header_text:
                    headers = [th.text.strip() for th in rows[0].find_all(["th", "td"])]
                    
                    for r_idx in range(1, len(rows)):
                        cols = rows[r_idx].find_all("td")
                        if len(cols) < len(headers):
                            continue
                        
                        row_data = {}
                        for h_idx, header in enumerate(headers):
                            val = cols[h_idx].text.strip()
                            h_clean = header.lower().replace(".", "").replace(" ", "_")
                            row_data[h_clean] = val
                        
                        records.append({
                            "reg_no": row_data.get("reg_no") or row_data.get("registration_number") or "",
                            "reg_date": row_data.get("reg_date") or row_data.get("registration_date") or "",
                            "first_party": row_data.get("first_party") or row_data.get("party_i") or "",
                            "second_party": row_data.get("second_party") or row_data.get("party_ii") or "",
                            "property_address": row_data.get("property_address") or row_data.get("address") or row_data.get("property_description") or "",
                            "deed_type": row_data.get("deed_name") or row_data.get("deed_type") or row_data.get("nature") or "Deed"
                        })
            
            return {"ok": True, "records": records}
        except Exception as e:
            return {"ok": False, "error": str(e)}
