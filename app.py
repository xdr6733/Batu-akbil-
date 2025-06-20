import sys
import subprocess
from flask import Flask, request, jsonify, Response
import os
from bs4 import BeautifulSoup
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

AKBIL_URL = 'https://akillibiletim.com/tBKY_SRG-01.aspx'
MAX_WORKERS = 100  # Increase thread count

# Helper function to fetch card info for a given plate code
def fetch_info(card_number, plate_code, form_data_base, cookies):
    data = form_data_base.copy()
    data.update({
        'ctl00$ddl_City': plate_code,
        'ctl00$cph_Body$ASPxRoundPanel1$txt_MifareID': card_number,
        'ctl00$cph_Body$ASPxRoundPanel1$btnSorgula': 'Sorgula'
    })
    try:
        resp = requests.post(AKBIL_URL, data=data, cookies=cookies, timeout=5)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    soup = BeautifulSoup(resp.text, 'html.parser')
    elem = soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_lbl_kartNo_0")
    if not elem:
        return None
    return {
        "plate_code": plate_code,
        "kart_no": elem.text.strip(),
        "ad_soyad": soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_lbl_AdSoyad_0").text.strip(),
        "kart_tipi": soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_Label3_0").text.strip(),
        "uretim_tarihi": soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_Label4_0").text.strip(),
        "son_islem_tarihi": soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_Label5_0").text.strip(),
        "guncel_bakiye": soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_Label6_0").text.strip(),
        "abonmanlik_binis_hakki": soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_Label1_0").text.strip(),
        "abonman_baslangic": soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_Label7_0").text.strip(),
        "abonman_bitis": soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_lbl_gecerlilikBitisTarihi_0").text.strip(),
        "kart_durumu": soup.find(id="cph_Body_ASPxRoundPanel1_dl_MifareDetail_lbl_kartDurumu_0").text.strip()
    }

@app.route('/api/akbil-search', methods=['GET'])
def akbil_search():
    card_number = request.args.get('card')
    if not card_number:
        err = {"error": "Missing 'card' parameter."}
        return Response(json.dumps(err, indent=2, ensure_ascii=False), mimetype='application/json'), 400

    # Initial request to get base form data and cookies
    session = requests.Session()
    try:
        init_resp = session.get(AKBIL_URL, timeout=10)
        init_resp.raise_for_status()
    except requests.RequestException as e:
        err = {"error": f"Initial request failed: {e}"}
        return Response(json.dumps(err, indent=2, ensure_ascii=False), mimetype='application/json'), 502
    soup_init = BeautifulSoup(init_resp.text, 'html.parser')
    form_data_base = {inp.get('name'): inp.get('value', '')
                      for inp in soup_init.find_all('input', {'type': 'hidden'}) if inp.get('name')}
    cookies = session.cookies.get_dict()

    # Plate codes 1..81 (one request each)
    plate_codes = [str(i) for i in range(1, 82)]
    found = None
    # Use ThreadPoolExecutor with MAX_WORKERS threads
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_info, card_number, code, form_data_base, cookies): code for code in plate_codes}
        for future in as_completed(futures):
            res = future.result()
            if res:
                found = res
                break
        # Cancel remaining tasks
        for fut in futures:
            if not fut.done():
                fut.cancel()

    if not found:
        err = {"error": "Geçerli plate code bulunamadı."}
        return Response(json.dumps(err, indent=2, ensure_ascii=False), mimetype='application/json'), 404

    return Response(json.dumps(found, indent=2, ensure_ascii=False), mimetype='application/json')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
