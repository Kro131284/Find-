import requests
import os
from dotenv import load_dotenv
import json  # Für die Debug-Ausgabe

# Debugging aktivieren (True = Debug-Ausgaben anzeigen)
DEBUG = True

# Lade die Umgebungsvariablen aus der .env-Datei
load_dotenv()

def get_companies():
    # API-Details aus Umgebungsvariablen laden
    base_url = os.getenv('MOCO_API_URL')
    token = os.getenv('MOCO_API_TOKEN')

    if not base_url or not token:
        print("Fehler: MOCO_API_URL oder MOCO_API_TOKEN fehlt in .env")
        return []

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    page = 1
    company_list = []

    while True:
        url = f"{base_url}?page={page}"
        if DEBUG:
            print(f"Debug: API-URL für Seite {page}: {url}")

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            print(f"Fehler: {response.status_code} - {response.text}")
            break

        companies = response.json()

        if DEBUG:
            print(f"Debug: API-Antwort für Firmen, Seite {page}:\n{json.dumps(companies, indent=4)}")

        if not companies:  # Falls keine Firmen mehr vorhanden sind
            break

        for company in companies:
            if DEBUG:
                print(f"Debug: Verarbeitete Firmendaten:\n{json.dumps(company, indent=4)}")

            billing_address = company.get('billing_address') or \
                              company.get('invoice_address') or \
                              company.get('address') or \
                              'Keine Rechnungsadresse verfügbar'

            # Prüfe, ob der identifier in den Firmendaten vorhanden ist
            identifier = company.get('identifier', 'Kein Identifier verfügbar')
            if DEBUG:
                print(f"Debug: Identifier für Firma {company.get('name', 'Unbekannte Firma')}: {identifier}")

            company_data = {
                'company_id': company.get('id', 'Unbekannt'),
                'identifier': identifier,  # Hier wird der identifier gesetzt
                'company_name': company.get('name', 'Unbekannte Firma'),
                'email': company.get('email', 'Keine E-Mail verfügbar'),
                'tel': company.get('phone', 'Keine Telefonnummer verfügbar'),
                'billing_address': billing_address,
                'tags': company.get('tags', []),
                'website': company.get('website', 'Keine Website verfügbar')
            }

            company_list.append(company_data)

        page += 1  # Nächste Seite

    return company_list
