import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import holidays
import os
import sys

# --- NASTAVENÍ ---
URL = "https://www.menicka.cz/4125-bistro-pekarka.html"

# Načtení hesel
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

def ziskej_menu():
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
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Chyba při stahování webu: {e}")
        return None

    denni_nabidka = []
    found = False

    all_menus = soup.find_all('div', class_='menicka')
    
    for menu_div in all_menus:
        nadpis = menu_div.find('div', class_='nadpis')
        
        # Pokud najdeme sekci s dnešním datem
        if nadpis and dnes_str in nadpis.text:
            found = True
            
            # --- NOVÁ STRATEGIE: Vytáhnout všechen text ---
            # 1. Odstraníme nadpis z dat (abychom ho neměli v textu dvakrát, přidáme ho hezčí ručně)
            datum_text = nadpis.text.strip()
            
            # 2. Vytáhneme veškerý text a nahradíme HTML tagy za odřádkování
            # separator="<br>" zajistí, že každý div/p/br na webu bude nový řádek v mailu
            obsah_html = menu_div.decode_contents()
            
            # Použijeme BeautifulSoup znovu jen na tento kousek, abychom ho vyčistili
            menu_soup = BeautifulSoup(obsah_html, 'html.parser')
            
            # Najdeme všechny řádky textu
            lines = []
            
            # Projdeme elementy a zkusíme zachovat strukturu
            # Nejjednodušší je vzít prostý text s oddělovači
            raw_text = menu_div.get_text(separator="|||")
            
            split_lines = raw_text.split("|||")
            
            denni_nabidka.append(f"<h2 style='color:#d35400; border-bottom: 2px solid #d35400; padding-bottom: 5px;'>📅 {datum_text}</h2>")
            
            denni_nabidka.append("<div style='font-size: 14px; line-height: 1.6;'>")
            
            for line in split_lines:
                clean_line = line.strip()
                # Vynecháme prázdné řádky a samotné datum (to už máme v nadpisu)
                if clean_line and clean_line != datum_text:
                    # Pokud řádek obsahuje cenu (číslo na konci), zvýrazníme ho
                    if any(char.isdigit() for char in clean_line[-5:]): 
                        denni_nabidka.append(f"<p style='margin: 8px 0;'>{clean_line}</p>")
                    # Pokud je to informace o rozvozu nebo polévka (bez ceny na konci)
                    else:
                        denni_nabidka.append(f"<p style='margin: 5px 0; color: #555;'><i>{clean_line}</i></p>")
            
            denni_nabidka.append("</div>")
            break

    if not found:
        print("Menu pro dnešní den nebylo na stránce nalezeno.")
        return None
    
    return "".join(denni_nabidka)

def poslat_email(obsah):
    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        print("CHYBA: Nejsou nastavena hesla (Secrets) v GitHubu!")
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"Oběd Pekařka - {datetime.now().strftime('%d.%m.')}"

    html_text = f"""
    <html>
      <body style="font-family: Arial, sans-serif; max-width: 600px;">
        <div style="background-color: #fcfcfc; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
            {obsah}
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
        sys.exit(1)

if __name__ == "__main__":
    menu = ziskej_menu()
    if menu:
        poslat_email(menu)
    else:
        print("Dnes se nic neposílá.")
