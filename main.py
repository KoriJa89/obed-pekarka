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
    
    # 1. Kontrola víkendu (5=sobota, 6=neděle)
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

    # Hledáme sekci s dnešním datem
    all_menus = soup.find_all('div', class_='menicka')
    
    for menu_div in all_menus:
        nadpis = menu_div.find('div', class_='nadpis')
        
        # Pokud najdeme nadpis a v něm je dnešní datum
        if nadpis and dnes_str in nadpis.text:
            found = True
            denni_nabidka.append(f"<h2 style='color:#d35400;'>📅 {nadpis.text.strip()}</h2>")
            
            # --- POKUS 1: Standardní hledání (Polévka a Jídla) ---
            polivka = menu_div.find(class_='polivka') # Hledáme jakýkoliv tag s touto třídou
            jidla = menu_div.find_all(class_='jidlo') # Hledáme jakýkoliv tag s touto třídou
            
            # Pokud jsme našli strukturovaná jídla, naformátujeme je hezky
            if jidla:
                if polivka:
                    denni_nabidka.append(f"<b>🍜 Polévka:</b> {polivka.text.strip()}<br>")
                
                denni_nabidka.append("<br><b>🍽️ Hlavní chody:</b><ul style='list-style-type: none; padding: 0;'>")
                for j in jidla:
                    cena = j.find(class_='cena')
                    text_jidla = j.text.strip()
                    
                    if cena:
                         cena_text = cena.text.strip()
                         text_jidla = text_jidla.replace(cena_text, "").strip()
                         denni_nabidka.append(f"<li style='margin-bottom: 8px;'>✅ {text_jidla} <b>({cena_text})</b></li>")
                    else:
                        denni_nabidka.append(f"<li style='margin-bottom: 8px;'>✅ {text_jidla}</li>")
                denni_nabidka.append("</ul>")
            
            # --- POKUS 2: Záchranná brzda (když selže struktura) ---
            else:
                print("POZOR: Nenašel jsem třídu 'jidlo', beru hrubý text.")
                # Vezmeme veškerý text z divu
                raw_text = menu_div.get_text(separator="\n")
                # Odstraníme datum (nadpis), ať tam není 2x
                if nadpis:
                    raw_text = raw_text.replace(nadpis.text.strip(), "")
                
                # Vyčistíme prázdné řádky
                lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                clean_text = "<br>".join(lines)
                
                denni_nabidka.append("<p><i>(Nepodařilo se načíst formátování, zde je hrubý výpis):</i></p>")
                denni_nabidka.append(f"<p>{clean_text}</p>")
                
            break

    if not found:
        print("Menu pro dnešní den nebylo na stránce nalezeno.")
        return None
    
    return "\n".join(denni_nabidka)

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
      <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <div style="background-color: #f9f9f9; padding: 20px; border-radius: 5px;">
            <p>Ahoj, tady je dnešní nabídka z Bistra Pekařka:</p>
            <hr>
            {obsah}
            <hr>
            <p style="color: gray; font-size: 12px;">Odesláno automaticky GitHub agentem.</p>
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
