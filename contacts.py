import requests
import os
from dotenv import load_dotenv
import json  # Für die Debug-Ausgabe

# Lade die Umgebungsvariablen aus der .env-Datei
load_dotenv()

def get_contacts():
    # Die URL und der API-Token werden aus der .env-Datei geladen
    base_url = os.getenv('MOCO_CONTACTS_URL')
    token = os.getenv('MOCO_API_TOKEN')

    # Headers für die Anfrage mit Authorization-Token
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    # Variablen zur Pagination
    page = 1
    has_more_pages = True
    contact_list = []

    while has_more_pages:
        # URL für die aktuelle Seite
        url = f"{base_url}?page={page}"
        print(f"Debug: Abfrage-URL für Seite {page}: {url}")

        # GET-Anfrage an die MocoApp API senden
        response = requests.get(url, headers=headers)

        # Überprüfen, ob die Anfrage erfolgreich war
        if response.status_code == 200:
            # Kontaktdaten aus der Antwort extrahieren
            contacts = response.json()

            # Debug: Ausgabe der vollständigen API-Antwort
            print(f"Debug: Vollständige API-Antwort für Kontakte: {json.dumps(contacts, indent=4)}")

            if len(contacts) == 0:  # Keine weiteren Daten
                has_more_pages = False
            else:
                # Kontaktdaten verarbeiten und Firmennamen extrahieren
                for contact in contacts:
                    # Debug-Ausgabe für jeden Kontakt, um die Datenstruktur zu überprüfen
                    print(f"Debug: Kontakt Daten: {json.dumps(contact, indent=4)}")

                    # Extrahiere alternative Felder für E-Mail, Telefon und Firma
                    email = contact.get('work_email', 'Keine E-Mail verfügbar')  # Verwende das Feld "work_email"
                    phone = contact.get('work_phone', 'Keine Telefonnummer verfügbar')  # Verwende das Feld "work_phone"

                    # Überprüfen, ob das company-Objekt existiert
                    company = contact.get('company')
                    if company:
                        company_name = company.get('name', 'Keine Firma verfügbar')
                    else:
                        company_name = 'Keine Firma verfügbar'

                    # Kontaktinformationen ohne Adressabfrage hinzufügen
                    contact_data = {
                        'contact_id': contact.get('id'),
                        'first_name': contact.get('firstname'),
                        'last_name': contact.get('lastname'),
                        'email': email,  # Verwende das Feld "work_email" für die E-Mail
                        'phone': phone,  # Verwende das Feld "work_phone" für die Telefonnummer
                        'company_name': company_name  # Firmennamen hinzufügen
                    }

                    contact_list.append(contact_data)

            # Zur nächsten Seite wechseln
            page += 1
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return []

    return contact_list
