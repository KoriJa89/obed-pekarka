import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import holidays
import os
import sys
import json

# --- FIREBASE IMPORTY ---
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

# --- NASTAVENÍ ---
URL = "https://www.menicka.cz/4125-bistro-pekarka.html"

# Načtení proměnných prostředí
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")
FIREBASE_CREDENTIALS = os.environ.get("FIREBASE_CREDENTIALS")

# --- INICIALIZACE FIREBASE ---
db = None
if FIREBASE_CREDENTIALS:
    try:
        cred_dict = json.loads(FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Připojeno k Firebase.")
    except Exception as e:
        print(f"❌ Chyba při připojování k Firebase: {e}")

def ziskej_data():
    dnes = datetime.now()
    
    # 1. Kontrola víkendu
    if dnes.weekday() > 4:
        print("Je víkend, agent dnes nepracuje.")
        return None
        
    # 2. Kontrola svátků
    cz_holidays = holidays.CZ()
    if dnes in cz_holidays:
        print(f"Dnes je svátek ({cz_holidays.get(dnes)}), agent nepracuje.")
        return None

    dnes_str = dnes.strftime("%d.%m.%Y")
    print(f"Hledám menu pro datum: {dnes_str}")
    
    try:
        response = requests.get(URL)
        response.encoding = 'windows-1250'
        soup_html = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Chyba při stahování webu: {e}")
        return None

    all_menus = soup_html.find_all('div', class_='menicka')
    
    for menu_div in all_menus:
        nadpis = menu_div.find('div', class_='nadpis')
        
        # Pokud najdeme sekci s dnešním datem
        if nadpis and dnes_str in nadpis.text:
            datum_text = nadpis.text.strip()
            
            # --- ZPRACOVÁNÍ TEXTU (Společné pro Mail i DB) ---
            # Vytáhneme veškerý text a rozdělíme po řádcích
            obsah_html = menu_div.decode_contents()
            raw_text = BeautifulSoup(obsah_html, 'html.parser').get_text(separator="|||")
            split_lines = raw_text.split("|||")
            
            # Připravíme si seznamy pro DB
            db_soup = ""
            db_mains_list = []
            
            # Připravíme si HTML pro Email
            email_lines = []
            email_lines.append(f"<h2 style='color:#d35400; border-bottom: 2px solid #d35400; padding-bottom: 5px;'>📅 {datum_text}</h2>")
            email_lines.append("<div style='font-size: 14px; line-height: 1.6;'>")

            for line in split_lines:
                clean_line = line.strip()
                
                # Přeskočíme prázdné řádky a samotné datum
                if not clean_line or clean_line == datum_text:
                    continue
                
                # Zjišťujeme, jestli řádek obsahuje cenu (číslo na konci)
                has_price = any(char.isdigit() for char in clean_line[-5:])
                
                # --- LOGIKA PRO DATABÁZI ---
                if has_price:
                    # Pokud ještě nemáme polévku a řádek vypadá jako polévka (často levnější nebo první)
                    # Ale pozor, někdy je polévka v samostatném tagu. Zkusíme ji najít bezpečněji.
                    is_likely_soup = "polévka" in clean_line.lower() or "vývar" in clean_line.lower() or "kyselo" in clean_line.lower() or "krém" in clean_line.lower()
                    
                    if not db_soup and is_likely_soup:
                        db_soup = clean_line
                    elif not db_soup and len(db_mains_list) == 0 and "..." in clean_line: 
                         # Fallback: Pokud je to první položka s cenou a nemáme polévku, bereme to jako polévku
                         db_soup = clean_line
                    else:
                        # Vše ostatní s cenou je hlavní jídlo
                        db_mains_list.append(clean_line)

                # --- LOGIKA PRO EMAIL ---
                if has_price: 
                    email_lines.append(f"<p style='margin: 8px 0;'>{clean_line}</p>")
                else:
                    email_lines.append(f"<p style='margin: 5px 0; color: #555;'><i>{clean_line}</i></p>")
            
            email_lines.append("</div>")
            email_html = "".join(email_lines)
            
            # Spojíme hlavní jídla do textu
            db_main_str = "\n".join(db_mains_list)

            # Vrátíme kompletní balíček
            return {
                'found': True,
                'email_html': email_html,
                'db_soup': db_soup,
                'db_main': db_main_str
            }

    print("Menu pro dnešní den nebylo na stránce nalezeno.")
    return None

def poslat_email(obsah_html):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("⚠️ Hesla pro email nejsou nastavena.")
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"Oběd Pekařka - {datetime.now().strftime('%d.%m.')}"

    html_text = f"""
    <html>
      <body style="font-family: Arial, sans-serif; max-width: 600px;">
        <div style="background-color: #fcfcfc; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            {obsah_html}
            <br>
            <hr>
            <p style="color: gray; font-size: 11px; text-align: center;">Odesláno z GitHub Actions</p>
        </div>
      </body>
    </html>
    """
    msg.attach(MIMEText(html_text, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.seznam.cz', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("✅ E-mail byl úspěšně odeslán!")
    except Exception as e:
        print(f"❌ Chyba při odesílání e-mailu: {e}")

def ulozit_do_firebase(polievka, jidlo):
    if not db:
        print("⚠️ Firebase není připojeno.")
        return

    today_id = datetime.now().strftime('%Y-%m-%d')
    
    data = {
        'date': today_id,
        'soup': polievka,
        'mainDish': jidlo,
        'updatedAt': firestore.SERVER_TIMESTAMP
    }

    try:
        db.collection('daily_menus').document(today_id).set(data)
        print("✅ Menu úspěšně uloženo do Firebase databáze!")
        print(f"   Polévka: {polievka}")
        print(f"   Jídlo: {jidlo[:50]}...")
    except Exception as e:
        print(f"❌ Chyba při zápisu do Firebase: {e}")

if __name__ == "__main__":
    vysledek = ziskej_data()
    
    if vysledek and vysledek['found']:
        poslat_email(vysledek['email_html'])
        ulozit_do_firebase(vysledek['db_soup'], vysledek['db_main'])
    else:
        print("Dnes se nic neposílá ani neukládá.")
