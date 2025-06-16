import aiomysql
import os
import asyncio
from dotenv import load_dotenv
from flask import Flask, jsonify
from contacts import get_contacts
from companies import get_companies
from kas2moco import get_accounts, get_domains, get_subdomains, get_subaccounts

# .env laden
load_dotenv()

# DB-Zugang
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

app = Flask(__name__)

# Hauptfunktion zum Einfügen
async def insert_data():
    conn = await aiomysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME
    )
    async with conn.cursor() as cursor:

        # 1. PHP-Versionen speichern
        php_versions = {"8.0", "7.4", "8.1"}
        for version in php_versions:
            await cursor.execute("INSERT IGNORE INTO PHP_VERSION (version) VALUES (%s)", (version,))

        # 2. Services speichern
        services = {"Hosting", "Websupport", "Print"}
        for service in services:
            await cursor.execute("INSERT IGNORE INTO SERVICE (beschreibung) VALUES (%s)", (service,))

        # 3. Kunden + Ansprechpartner
        contacts = get_contacts()
        companies = get_companies()
        company_dict = {c["company_name"]: c for c in companies}
        name_to_kdnr = {}

        for contact in contacts:
            company_name = contact.get("company_name", "Unbekannt")
            company_data = company_dict.get(company_name, {})
            billing_address = company_data.get("billing_address", "Unbekannt")

            street = billing_address.split(",")[0] if "," in billing_address else "Unbekannt"
            plz = "00000"
            ort = "Unbekannt"

            # Firma einfügen
            await cursor.execute(
                "INSERT INTO MOCO_KD_DATEN (name, strasse, plz, ort, serviceID) VALUES (%s, %s, %s, %s, 1)",
                (company_name, street, plz, ort),
            )
            kdNr_Moco = cursor.lastrowid
            name_to_kdnr[company_name] = kdNr_Moco

            # Ansprechpartner einfügen
            await cursor.execute(
                "INSERT INTO MOCO_ANSPRECHPARTNER (nachname, name, tel, email) VALUES (%s, %s, %s, %s)",
                (contact["last_name"], contact["first_name"], contact["phone"], contact["email"]),
            )
            ansprechpartner_id = cursor.lastrowid

            # Verknüpfung Firma <-> Ansprechpartner
            await cursor.execute(
                "INSERT INTO FIRMEN2ANSPRECHPARTNER (firmenkundenID, ansprechpartnerID) VALUES (%s, %s)",
                (kdNr_Moco, ansprechpartner_id),
            )

        # 4. Domains, Accounts, Subaccounts & Subdomains
        accounts = get_accounts(os.getenv("KAS_LOGIN"), os.getenv("KAS_PW"))

        for account in accounts:
            domain_data, _ = get_domains(account["account_login"], account["account_password"])
            moco_kdnr = name_to_kdnr.get(account.get("company_name", "Unbekannt"))

            for domain in domain_data:
                domain_name = domain.get("domain_name", "Unbekannt")
                php_version = domain.get("php_version", "8.0")

                # PHP-Version-ID holen
                await cursor.execute("SELECT id FROM PHP_VERSION WHERE version = %s", (php_version,))
                php_ID = await cursor.fetchone()
                php_ID = php_ID[0] if php_ID else 1

                # Hauptdomain einfügen
                await cursor.execute(
                    "INSERT INTO DOMAINS (name, php_ID, parent_id, redirect_path, redirect_status) VALUES (%s, %s, NULL, '', 0)",
                    (domain_name, php_ID),
                )
                domainID = cursor.lastrowid

                # Hauptaccount einfügen
                await cursor.execute(
                    "INSERT INTO ACCOUNT (domainID, mocoKdID, parent_id, kas_name, kas_kdnr, kas_password) VALUES (%s, %s, NULL, %s, %s, %s)",
                    (domainID, moco_kdnr, account["account_login"], account["account_kdnr"], account["account_password"]),
                )
                accountID = cursor.lastrowid

                # Subaccounts einfügen (als ACCOUNT mit parent_id)
                subaccounts = get_subaccounts(account["account_login"], account["account_password"])
                for sub in subaccounts:
                    await cursor.execute(
                        "INSERT INTO ACCOUNT (domainID, mocoKdID, parent_id, kas_name, kas_kdnr, kas_password) VALUES (%s, %s, %s, %s, '', %s)",
                        (domainID, moco_kdnr, accountID, sub["login"], sub["password"])
                    )

                # Subdomains einfügen (als DOMAINS mit parent_id)
                subdomains = get_subdomains(domain_name)
                for subdomain in subdomains:
                    await cursor.execute(
                        "INSERT INTO DOMAINS (name, php_ID, parent_id, redirect_path, redirect_status) VALUES (%s, %s, %s, '', 0)",
                        (subdomain["subdomain_name"], php_ID, domainID)
                    )

        await conn.commit()
    conn.close()

# API-Endpunkte
@app.route('/api/kunden', methods=['GET'])
async def kunden():
    conn = await aiomysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME
    )
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT id, name, strasse, plz, ort FROM MOCO_KD_DATEN")
        result = await cursor.fetchall()
        kunden = []
        for row in result:
            kunden.append({
                "id": row[0],
                "name": row[1],
                "strasse": row[2],
                "plz": row[3],
                "ort": row[4]
            })

    conn.close()
    return jsonify(kunden)

@app.route('/api/insert', methods=['POST'])
async def insert():
    await insert_data()
    return jsonify({"status": "success", "message": "Daten wurden erfolgreich eingefügt!"})

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
