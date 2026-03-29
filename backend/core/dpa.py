# backend/core/dpa.py

DPA_REGISTRY: dict[str, dict] = {
    "DE": {
        "name": "Der Bundesbeauftragte für den Datenschutz und die Informationsfreiheit (BfDI)",
        "short_name": "BfDI",
        "email": "poststelle@bfdi.bund.de",
        "url": "https://www.bfdi.bund.de/DE/Service/Beschwerden/beschwerden_node.html",
        "language": "de",
    },
    "FR": {
        "name": "Commission Nationale de l'Informatique et des Libertés (CNIL)",
        "short_name": "CNIL",
        "email": None,
        "url": "https://www.cnil.fr/fr/plaintes",
        "language": "fr",
    },
    "NL": {
        "name": "Autoriteit Persoonsgegevens (AP)",
        "short_name": "AP",
        "email": "info@autoriteitpersoonsgegevens.nl",
        "url": "https://www.autoriteitpersoonsgegevens.nl/nl/klacht-indienen-bij-de-ap",
        "language": "nl",
    },
    "IE": {
        "name": "Data Protection Commission (DPC)",
        "short_name": "DPC",
        "email": "info@dataprotection.ie",
        "url": "https://forms.dataprotection.ie/contact",
        "language": "en",
    },
    "GB": {
        "name": "Information Commissioner's Office (ICO)",
        "short_name": "ICO",
        "email": None,
        "url": "https://ico.org.uk/make-a-complaint/",
        "language": "en",
    },
    "AT": {
        "name": "Österreichische Datenschutzbehörde (DSB)",
        "short_name": "DSB",
        "email": "dsb@dsb.gv.at",
        "url": "https://www.dsb.gv.at/",
        "language": "de",
    },
    "BE": {
        "name": "Autorité de protection des données",
        "short_name": "APD",
        "email": "contact@apd-gba.be",
        "url": "https://www.autoriteprotectiondonnees.be/citoyen/agir/introduire-une-plainte",
        "language": "fr",
    },
    "CH": {
        "name": "Eidgenössischer Datenschutz- und Öffentlichkeitsbeauftragter (EDÖB)",
        "short_name": "EDÖB",
        "email": "info@edoeb.admin.ch",
        "url": "https://www.edoeb.admin.ch/",
        "language": "de",
    },
    "SE": {
        "name": "Integritetsskyddsmyndigheten (IMY)",
        "short_name": "IMY",
        "email": "imy@imy.se",
        "url": "https://www.imy.se/",
        "language": "sv",
    },
    "DK": {
        "name": "Datatilsynet",
        "short_name": "Datatilsynet",
        "email": "dt@datatilsynet.dk",
        "url": "https://www.datatilsynet.dk/",
        "language": "da",
    },
    "NO": {
        "name": "Datatilsynet",
        "short_name": "Datatilsynet",
        "email": "postkasse@datatilsynet.no",
        "url": "https://www.datatilsynet.no/",
        "language": "no",
    },
    "IT": {
        "name": "Garante per la protezione dei dati personali",
        "short_name": "Garante",
        "email": "protocollo@gpdp.it",
        "url": "https://www.garanteprivacy.it/",
        "language": "it",
    },
    "ES": {
        "name": "Agencia Española de Protección de Datos (AEPD)",
        "short_name": "AEPD",
        "email": None,
        "url": "https://www.aepd.es/",
        "language": "es",
    },
    "PL": {
        "name": "Urząd Ochrony Danych Osobowych (UODO)",
        "short_name": "UODO",
        "email": "kancelaria@uodo.gov.pl",
        "url": "https://uodo.gov.pl/",
        "language": "pl",
    },
    "US": {
        "name": "Federal Trade Commission (FTC)",
        "short_name": "FTC",
        "email": None,
        "url": "https://www.ftc.gov/complaint",
        "language": "en",
        "note": (
            "The FTC handles data broker complaints in the US. "
            "Not GDPR, but can be used for US-based brokers."
        ),
    },
}


def get_dpa_for_country(country_code: str) -> dict | None:
    """Get DPA info for a country code."""
    return DPA_REGISTRY.get(country_code.upper())


def get_dpa_for_broker_country(broker_country: str) -> dict | None:
    """Get DPA info. Falls back to the EU DPA where the user resides (not implemented yet)."""
    return get_dpa_for_country(broker_country)
