import os
import requests
from lxml import etree
import re
from dotenv import load_dotenv
from flask import Flask, render_template
from contacts import get_contacts
from companies import get_companies

# Flask-App initialisieren
app = Flask(__name__)

# Konfiguration aus der .env-Datei laden (.env enthält KAS_LOGIN und KAS_PW)
load_dotenv()
KAS_LOGIN = os.getenv("KAS_LOGIN")
KAS_PASSWORD = os.getenv("KAS_PW")
KAS_API_URL = "https://kasapi.kasserver.com/soap/KasApi.php"

# Reguläre Ausdrücke für verschiedene Datenarten
plz_ort_pattern = re.compile(r'(\d{5})\s+(.+)')  # z. B. "12345 Berlin"
strasse_pattern = re.compile(r'(.+?)\s+(\d+[a-zA-Z]?)$')  # z. B. "Musterstraße 12a"
street_with_number_pattern = re.compile(r'.*\d.*')  # Prüft, ob eine Zahl in der Adresse vorkommt

# Funktion zur Adressaufteilung
def split_billing_address(billing_address: str):
    address_parts = billing_address.split('\n')

    # Initiale Platzhalterwerte
    street = 'Unbekannt'
    city = 'Unbekannt'
    plz = 'Unbekannt'

    # Durchlaufe alle Adresszeilen und überprüfe
    for part in address_parts:
        # Prüfen, ob die Zeile eine Zahl (PLZ) und einen Ort enthält
        match_plz_ort = plz_ort_pattern.match(part)
        if match_plz_ort:
            plz = match_plz_ort.group(1)
            city = match_plz_ort.group(2)
            break

        # Wenn es eine Straße mit einer Zahl ist
        if street_with_number_pattern.match(part):
            match_street = strasse_pattern.match(part)
            if match_street:
                street = match_street.group(1)  # Straße ohne Hausnummer
                house_number = match_street.group(2)  # Hausnummer
                street = f"{street} {house_number}"  # Straße und Hausnummer zusammenführen

    return {'street': street, 'city': city, 'plz': plz}

# Hilfsfunktion für SOAP-Anfragen
def send_soap_request(action, kas_login, kas_password, params={}):
    try:
        print(f"🔹 SOAP-Anfrage: {action} für {kas_login}")
        soap_body = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
            <soapenv:Body>
                <KasApi>
                    <Params><![CDATA[ 
                        {{
                            "kas_login": "{kas_login}",
                            "kas_auth_type": "plain",
                            "kas_auth_data": "{kas_password}",
                            "kas_action": "{action}",
                            "KasRequestParams": {params}
                        }}
                    ]]></Params>
                </KasApi>
            </soapenv:Body>
        </soapenv:Envelope>"""
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "urn:xmethodsKasApi#KasApi"}
        response = requests.post(KAS_API_URL, data=soap_body, headers=headers)
        if response.status_code != 200:
            raise Exception(f"❌ Fehler bei {action}. Status Code: {response.status_code}")
        if not response.content:
            raise Exception(f"⚠️ Keine Daten für {action} erhalten.")
        return etree.fromstring(response.content)
    except Exception as e:
        print(f"❌ Fehler bei {action}: {e}")
        return None

# Hauptaccounts abrufen
def get_accounts(kas_login, kas_password):
    root = send_soap_request("get_accounts", kas_login, kas_password)
    if root is None:
        return []
    accounts = []
    for account in root.xpath('//item'):
        account_data = {}
        for field in account.xpath('./item'):
            key = field.xpath('./key/text()')
            value = field.xpath('./value/text()')
            if key and value:
                account_data[key[0]] = value[0]
        if account_data:
            accounts.append(account_data)
    return accounts

# Domains & Subdomains abrufen
def get_domains(account_login, account_password):
    root = send_soap_request("get_domains", account_login, account_password)
    if root is None:
        return [], {}
    domains = []
    redirects = {}
    for domain in root.xpath('//item'):
        domain_data = {
            field.xpath('./key/text()')[0]: field.xpath('./value/text()')[0]
            for field in domain.xpath('./item')
            if field.xpath('./key/text()') and field.xpath('./value/text()')
        }
        domain_redirect_status = domain_data.get("domain_redirect_status", "0")
        domain_path = domain_data.get("domain_path", "")
        if domain_redirect_status == "301":
            if domain_path not in redirects:
                redirects[domain_path] = []
            redirects[domain_path].append(domain_data)
        else:
            domains.append(domain_data)
    return domains, redirects

def get_subdomains(account_login, account_password):
    root = send_soap_request("get_subdomains", account_login, account_password)
    if root is None:
        return []
    subdomains = []
    for subdomain in root.xpath('//item'):
        subdomain_data = {field.xpath('./key/text()')[0]: field.xpath('./value/text()')[0]
                          for field in subdomain.xpath('./item')
                          if field.xpath('./key/text()') and field.xpath('./value/text()')}
        if subdomain_data:
            subdomains.append(subdomain_data)
    return subdomains

def get_subaccounts(account_login, account_password):
    root = send_soap_request("get_accounts", account_login, account_password)
    if root is None:
        return []
    subaccounts = []
    for subaccount in root.xpath('//item'):
        subaccount_data = {field.xpath('./key/text()')[0]: field.xpath('./value/text()')[0]
                           for field in subaccount.xpath('./item')
                           if field.xpath('./key/text()') and field.xpath('./value/text()')}
        if subaccount_data:
            subaccounts.append(subaccount_data)
    return subaccounts

# Helper function to normalize domains
def normalize_domain(domain):
    """Normalizes a domain name for matching."""
    domain = domain.lower()
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.replace("www.", "")
    domain = domain.strip()  # Remove leading/trailing spaces
    if domain.endswith("/"):
        domain = domain[:-1]
    return domain

@app.route('/show-data', methods=['GET'])
def show_data():
    # Moco-Daten verarbeiten
    contacts = get_contacts()
    companies = get_companies()
    company_dict = {company['company_name']: company for company in companies}
    moco_data = []
    
    # Liste der Kunden, die "Hosting"-Tag haben
    hosting_contacts = []

    for contact in contacts:
        company_name = contact.get('company_name', 'Keine Firma verfügbar')
        company_data = company_dict.get(company_name, None)
        if company_data:
            billing_address = company_data.get('billing_address', 'Keine Rechnungsadresse verfügbar')
            billing_address_parts = split_billing_address(billing_address)
            tags = company_data.get('tags', [])
            website = company_data.get('website', 'Keine Website verfügbar')
            identifier = company_data.get('identifier', 'Kein Identifier verfügbar')  # add identifier
            moco_entry = {
                'company_name': company_name,
                'billing_address': billing_address_parts,
                'first_name': contact['first_name'],
                'last_name': contact['last_name'],
                'email': contact['email'],
                'phone': contact['phone'],
                'tags': tags,
                'website': website,
                'identifier': identifier,  # add identifier
                'kas_account_link': None,  # Initialize with None
                'kas_account_id': None     # Initialize with None
            }
        else:
            moco_entry = {
                'company_name': company_name,
                'billing_address': 'Rechnungsadresse nicht gefunden',
                'first_name': contact['first_name'],
                'last_name': contact['last_name'],
                'email': contact['email'],
                'phone': contact['phone'],
                'tags': 'Keine Tags verfügbar',
                'website': 'Keine Website verfügbar',
                'identifier': 'Kein Identifier verfügbar',  # add identifier
                'kas_account_link': None,  # Initialize with None
                'kas_account_id': None     # Initialize with None
            }

        # Wenn der Kontakt das Tag "Hosting" hat, prüfen wir die Website
        if 'Hosting' in moco_entry.get('tags', []) and moco_entry['website'] != 'Keine Website verfügbar':
            hosting_contacts.append(moco_entry)

        moco_data.append(moco_entry)

    # Sortiere moco_data nach Firmennamen (case-insensitive)
    moco_data = sorted(moco_data, key=lambda entry: entry['company_name'].lower())

    # Gruppiere moco_data nach Firmennamen
    grouped_data = {}
    for entry in moco_data:
        company_name = entry['company_name']
        if company_name not in grouped_data:
            grouped_data[company_name] = []
        grouped_data[company_name].append(entry)

    # KAS-Daten verarbeiten
    kas_accounts = get_accounts(KAS_LOGIN, KAS_PASSWORD)
    all_domains, all_redirects, all_subdomains, all_subaccounts = [], [], [], []
    kas_data_with_hosting = []  # Neue Liste für KAS-Daten mit Hosting
    kas_account_ids = {}  # Dictionary to store KAS account IDs

    # Create dictionaries to quickly look up domains and company names by account login
    domain_to_account = {}
    company_to_account = {}

    for account in kas_accounts:
        account_login = account.get("account_login")
        account_password = account.get("account_password")
        account_comment = account.get("account_comment") #add account comment
        if not account_password:
            print(f"⚠️ Kein Passwort für {account_login} -> Überspringe Account")
            domains = [{"domain_name": "Kein Passwortmanager aktiviert"}]
            redirects = {}
            subdomains = []
            subaccounts = []
        else:
            print(f"🔹 Verarbeite Account: {account_login}")
            domains, redirects = get_domains(account_login, account_password)
            subdomains = get_subdomains(account_login, account_password)
            subaccounts = get_subaccounts(account_login, account_password)
            
            for domain in domains:
                domain_name = domain.get("domain_name")
                if domain_name:
                    normalized_domain = normalize_domain(domain_name)
                    domain_to_account[normalized_domain] = account_login
                    # Falls in den Domain-Daten ein Firmenname enthalten ist (z. B. "account_company_name"), speichere ihn
                    account_company = domain.get("account_company_name")
                    if account_company:
                        company_to_account[account_company] = account_login
            
            for redirect_path, redirect_domains in redirects.items():
                for domain in redirect_domains:
                    domain_name = domain.get("domain_name")
                    if domain_name:
                        normalized_domain = normalize_domain(domain_name)
                        domain_to_account[normalized_domain] = account_login
            
            for subdomain in subdomains:
                subdomain_name = subdomain.get("subdomain_name")
                if subdomain_name:
                    normalized_subdomain = normalize_domain(subdomain_name)
                    domain_to_account[normalized_subdomain] = account_login
            
            # Subaccounts verarbeiten
            for subaccount in subaccounts:
                sub_login = subaccount.get("account_login")
                sub_password = subaccount.get("account_password")
                if sub_login and sub_password:
                    print(f"  🔸 Subaccount {sub_login} -> Abrufe Domains & Subdomains")
                    subaccount["domains"], subaccount_redirects = get_domains(sub_login, sub_password)
                    subaccount["subdomains"] = get_subdomains(sub_login, sub_password)
                    redirects.update(subaccount_redirects)
                    
                    for subaccount_domain in subaccount["domains"]:
                        subaccount_domain_name = subaccount_domain.get("domain_name")
                        if subaccount_domain_name:
                            normalized_subaccount_domain = normalize_domain(subaccount_domain_name)
                            domain_to_account[normalized_subaccount_domain] = account_login
                            account_company = subaccount_domain.get("account_company_name")
                            if account_company:
                                company_to_account[account_company] = account_login
                else:
                    print(f"  ⚠️ Subaccount {sub_login} hat kein Passwort -> Überspringe")
                    subaccount["domains"] = []
                    subaccount["subdomains"] = []
        
        all_domains.append(domains)
        all_redirects.append(redirects)
        all_subdomains.append(subdomains)
        all_subaccounts.append(subaccounts)

        # Generate a unique ID for the KAS account
        kas_account_id = f"kas-account-{account_login}"
        counter = 1
        while kas_account_id in kas_account_ids.values():
            kas_account_id = f"kas-account-{account_login}-{counter}"
            counter += 1
        kas_account_ids[account_login] = kas_account_id
        account['kas_account_id'] = kas_account_id
        account['account_comment'] = account_comment #add account comment

       # Jetzt prüfen wir für die "Hosting"-Kunden, ob eine Domain existiert
        for hosting_contact in hosting_contacts:
            website_url = hosting_contact.get('website')
            normalized_website = normalize_domain(website_url)
            matched_account_login = None
            if normalized_website in domain_to_account:
                matched_account_login = domain_to_account[normalized_website]
            # Falls keine Domain gefunden wurde, versuchen wir über den Firmennamen
            elif hosting_contact.get('company_name') in company_to_account:
                matched_account_login = company_to_account[hosting_contact.get('company_name')]

            if matched_account_login:
                hosting_contact['kas_account_link'] = matched_account_login
                hosting_contact['kas_account_id'] = kas_account_ids.get(matched_account_login)
            else:
                kas_data_with_hosting.append({
                    'company_name': hosting_contact['company_name'],
                    'website': hosting_contact['website'],
                    'error': 'Keine passende Domain oder Firma gefunden für die Website'
                })

        # Add data-kas-comment attribute
        account['data_kas_comment'] = account_comment.lower() if account_comment else ""

    # Erstelle kas_data als Liste von Tupeln, damit das Template sie direkt iterieren kann.
    kas_data = list(zip(kas_accounts, all_domains, all_redirects, all_subdomains, all_subaccounts))

    # Link MOCO entries to KAS accounts – zuerst über die Website, ansonsten über den Firmennamen
    for entry in moco_data:
        if entry['website'] != 'Keine Website verfügbar':
            normalized_website = normalize_domain(entry['website'])
            if normalized_website in domain_to_account:
                entry['kas_account_link'] = domain_to_account[normalized_website]
                entry['kas_account_id'] = kas_account_ids.get(domain_to_account[normalized_website])
            elif entry['company_name'] in company_to_account:
                entry['kas_account_link'] = company_to_account[entry['company_name']]
                entry['kas_account_id'] = kas_account_ids.get(company_to_account[entry['company_name']])

    return render_template("kas2moco2.html", moco_data=moco_data, kas_data=kas_data,
                           grouped_data=grouped_data, kas_data_with_hosting=kas_data_with_hosting,
                           kas_account_ids=kas_account_ids)

if __name__ == '__main__':
    app.run(debug=True, port=2450)
