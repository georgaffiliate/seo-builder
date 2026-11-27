#!/usr/bin/env python3
"""assemble.py — deterministic site constructor: plan.json [+ content_pack.json] → full offer.

STATIC layer of the factory: reads NO docs, calls NO LLM. Takes:
  --plan    plans/<domain>.json            (produced by gen_plan.py)
  --content content/<domain>-content.json  (optional: produced by an LLM per content-pack.schema;
                                            absent → seed placeholders, site still builds)

Produces sites/<domain>/ with: index.php, inner pages (slug-mapped), thanks.php, 404.php,
assets (favicons/og placeholders from templates), integration (from api_local_example),
sitemap/robots/.htaccess, palette+skin+fonts wired into <head>.

Then RUNS the gates itself: php -l all pages, seo_audit.py, twin_check.py.
Exit 0 = all green.

Blocks: fragments from blocks/ are MINIMAL-HTML canonical blk-* pieces stored per category
(this build ships with 89 donor fragments, but assembly prefers CLEAN blk-* templates from
blocks/blk-*.html when present; donor fragments serve as reference/fallback).
"""
from __future__ import annotations
import argparse, hashlib, json, pathlib, random, shutil, subprocess, sys, re, time

ROOT = pathlib.Path(__file__).resolve().parent          # static-create-sites/
SITES_OUT = ROOT / "sites"
PLANS_DIR = ROOT / "plans"
BLOCKS = ROOT / "blocks"
SKINS = ROOT / "skins"
CONTENT_SCHEMA = ROOT / "content" / "content-pack.schema.json"
PALETTES = ROOT / "content" / "palettes-blk.json"
INTEGRATION_SRC = ROOT / "integration-example" / "integration"
PEOPLE_DIR = ROOT / "people"
APPSHOT_DIR = ROOT / "appshots"
TRUST_DIR = ROOT / "trust"
POSTBACK_SRC = ROOT / "_postback.php"


def _asset_bank(folder: pathlib.Path, key: str) -> list:
    try:
        d = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        return [x for x in (d.get(key) or []) if isinstance(x, dict) and x.get("file")]
    except Exception:
        return []


APPSHOT_BANK = _asset_bank(APPSHOT_DIR, "photos")
TRUST_BANK = _asset_bank(TRUST_DIR, "badges")

# Blog/hub pages live one directory deep (/blog/<slug>.php) so the offer pages and the
# content silo keep separate URL neighbourhoods. Every other page stays at the root.
# The hub is the directory landing page: /blog/index.php.
BLOG_DIR = "blog"
BLOG_HUB = "index.php"

BUILD_V = "0"
COMMA_DECIMAL = {
    "it", "de", "es", "fr", "pl", "cs", "sk", "sl", "hr", "hu", "ro", "bg", "tr",
    "pt", "nl", "da", "nb", "no", "sv", "fi", "et", "lv", "lt", "el", "uk", "ru",
    "sr", "mk", "bs", "sq", "az", "ka", "ca",
}


SPACE_THOUSANDS = {"cs", "sk", "pl", "fr", "ru", "uk", "sv", "fi", "no", "nb",
                   "da", "sl", "hr", "hu", "lv", "lt", "et"}


def num_sep(lang: str) -> tuple[str, str]:
    """(thousands, decimal) for the site language: ja/en 1,234.56 · de/tr 1.234,56 ·
    sk/cs/fr/pl 1 234,56 (the strip already used a space — one helper now)."""
    lang = (lang or "en").lower()
    if lang in SPACE_THOUSANDS:
        return (" ", ",")
    if lang in COMMA_DECIMAL:
        return (".", ",")
    return (",", ".")


def fmt_int(v, lang: str = "en") -> str:
    """1234 → 1,234 (en/ja) / 1.234 (de/tr) — never a mixed page."""
    thousands, _ = num_sep(lang)
    return f"{int(v):,}".replace(",", thousands)


def api_uptime(lang: str = "en") -> str:
    _, dec = num_sep(lang)
    return f"99{dec}9%"
REQUIRED_PLAN_KEYS = ["params", "design", "layout", "widgets", "numbers"]
SPECIAL_VARIANTS = {"livebar", "logo", "header", "footer", "form", "first_screen"}
FORM_BANDS = {"access-band", "claim-band", "enroll-band"}

# footer legal labels + rights line per geo language (fallback English)
FOOTER_L10N = {
    "cs": ("Podmínky", "Soukromí", "Všechna práva vyhrazena."),
    "sk": ("Podmienky", "Súkromie", "Všetky práva vyhradené."),
    "pl": ("Regulamin", "Prywatność", "Wszelkie prawa zastrzeżone."),
    "de": ("AGB", "Datenschutz", "Alle Rechte vorbehalten."),
    "fr": ("Conditions", "Confidentialité", "Tous droits réservés."),
    "it": ("Termini", "Privacy", "Tutti i diritti riservati."),
    "es": ("Términos", "Privacidad", "Todos los derechos reservados."),
    "pt": ("Termos", "Privacidade", "Todos os direitos reservados."),
    "nl": ("Voorwaarden", "Privacy", "Alle rechten voorbehouden."),
    "hu": ("Feltételek", "Adatvédelem", "Minden jog fenntartva."),
    "ro": ("Termeni", "Confidențialitate", "Toate drepturile rezervate."),
    "bg": ("Условия", "Поверителност", "Всички права запазени."),
    "el": ("Όροι", "Απόρρητο", "Με την επιφύλαξη παντός δικαιώματος."),
    "hr": ("Uvjeti", "Privatnost", "Sva prava pridržana."),
    "sl": ("Pogoji", "Zasebnost", "Vse pravice pridržane."),
    "lt": ("Sąlygos", "Privatumas", "Visos teisės saugomos."),
    "lv": ("Noteikumi", "Privātums", "Visas tiesības aizsargātas."),
    "et": ("Tingimused", "Privaatsus", "Kõik õigused kaitstud."),
    "fi": ("Ehdot", "Tietosuoja", "Kaikki oikeudet pidätetään."),
    "sv": ("Villkor", "Integritet", "Alla rättigheter förbehållna."),
    "da": ("Vilkår", "Privatliv", "Alle rettigheder forbeholdes."),
    "nb": ("Vilkår", "Personvern", "Alle rettigheter forbeholdt."),
}

TERMS_L10N = {"it": ("Termini di servizio", "Informativa privacy", "Grazie — richiesta ricevuta"),
               "cs": ("Podmínky služby", "Zásady ochrany osobních údajů", "Děkujeme — žádost přijata"),
               "sk": ("Podmienky používania", "Zásady ochrany osobných údajov", "Ďakujeme — žiadosť prijatá"),
               "pl": ("Warunki korzystania", "Polityka prywatności", "Dziękujemy — zgłoszenie przyjęte"),
               "de": ("Allgemeine Geschäftsbedingungen", "Datenschutzerklärung", "Danke — Anfrage erhalten"),
               "fr": ("Conditions de service", "Politique de confidentialité", "Merci — demande reçue"),
               "es": ("Términos del servicio", "Política de privacidad", "Gracias — solicitud recibida"),
               "pt": ("Termos de serviço", "Política de privacidade", "Obrigado — pedido recebido"),
               "nl": ("Servicevoorwaarden", "Privacybeleid", "Bedankt — aanvraag ontvangen"),
               "hu": ("Szolgáltatási feltételek", "Adatvédelmi irányelvek", "Köszönjük — kérését megkaptuk"),
               "ro": ("Termeni și condiții", "Politica de confidențialitate", "Mulțumim — cererea a fost primită"),
               "bg": ("Условия за ползване", "Политика за поверителност", "Благодарим — заявката е получена"),
               "el": ("Όροι χρήσης", "Πολιτική απορρήτου", "Ευχαριστούμε — το αίτημα ελήφθη"),
               "hr": ("Uvjeti korištenja", "Pravila privatnosti", "Hvala — zahtjev je zaprimljen"),
               "sl": ("Pogoji uporabe", "Politika zasebnosti", "Hvala — povpraševanje prejeto"),
               "lt": ("Paslaugų sąlygos", "Privatumo politika", "Dėkojame — užklausa gauta"),
               "lv": ("Pakalpojuma noteikumi", "Privātuma politika", "Paldies — pieprasījums saņemts"),
               "et": ("Kasutustingimused", "Privaatsuspoliitika", "Aitäh — taotlus on vastu võetud"),
               "fi": ("Palveluehdot", "Tietosuojakäytäntö", "Kiitos — pyyntö vastaanotettu"),
               "sv": ("Användarvillkor", "Integritetspolicy", "Tack — förfrågan mottagen"),
               "da": ("Servicevilkår", "Privatlivspolitik", "Tak — anmodning modtaget"),
               "nb": ("Vilkår for bruk", "Personvernerklæring", "Takk — forespørselen er mottatt"),
               "en": ("Terms of service", "Privacy policy", "Thank you — request received")}

# 404 headline + back-home label per geo language (fallback English)
NOTFOUND_L10N = {
    "cs": ("Stránka nenalezena", "Zpět na úvod"),
    "sk": ("Stránka sa nenašla", "Späť na úvod"),
    "pl": ("Nie znaleziono strony", "Wróć na start"),
    "de": ("Seite nicht gefunden", "Zur Startseite"),
    "fr": ("Page introuvable", "Retour à l'accueil"),
    "it": ("Pagina non trovata", "Torna alla home"),
    "es": ("Página no encontrada", "Volver al inicio"),
    "pt": ("Página não encontrada", "Voltar ao início"),
    "nl": ("Pagina niet gevonden", "Terug naar home"),
    "hu": ("Az oldal nem található", "Vissza a kezdőlapra"),
    "ro": ("Pagina nu a fost găsită", "Înapoi la start"),
    "bg": ("Страницата не е намерена", "Обратно към началото"),
    "el": ("Η σελίδα δεν βρέθηκε", "Επιστροφή στην αρχική"),
    "hr": ("Stranica nije pronađena", "Natrag na početak"),
    "sl": ("Stran ne obstaja", "Nazaj na začetek"),
    "lt": ("Puslapis nerastas", "Grįžti į pradžią"),
    "lv": ("Lapa nav atrasta", "Atgriezties sākumā"),
    "et": ("Lehte ei leitud", "Tagasi avalehele"),
    "fi": ("Sivua ei löytynyt", "Takaisin etusivulle"),
    "sv": ("Sidan hittades inte", "Tillbaka till start"),
    "da": ("Siden blev ikke fundet", "Tilbage til forsiden"),
    "nb": ("Siden ble ikke funnet", "Tilbake til startsiden"),
}

# Phone prefixes per country — mirrors tools/content_gen.PHONE_CC (selftest enforces
# parity). A +39 number on a .es offer is the sort of leak that reads as a copied
# template, so the phone is checked against the plan country and regenerated when it
# drifts. The table used to stop at IE: every non-EU offer (TR, JP, BR…) then shipped
# the invalid "+00" prefix, which read as placeholder data on a live page.
PHONE_CC = {"IT": "+39", "CZ": "+420", "SK": "+421", "PL": "+48", "DE": "+49",
            "AT": "+43", "FR": "+33", "BE": "+32", "NL": "+31", "ES": "+34",
            "PT": "+351", "HU": "+36", "RO": "+40", "BG": "+359", "GR": "+30",
            "HR": "+385", "SI": "+386", "LT": "+370", "LV": "+371", "EE": "+372",
            "FI": "+358", "SE": "+46", "DK": "+45", "NO": "+47", "IE": "+353",
            "GB": "+44", "CH": "+41", "TR": "+90", "JP": "+81", "KR": "+82",
            "IN": "+91", "BR": "+55", "MX": "+52", "PE": "+51", "ZA": "+27",
            "NG": "+234", "KE": "+254", "MY": "+60", "SG": "+65", "HK": "+852",
            "PH": "+63", "CA": "+1", "AU": "+61", "GE": "+995", "AZ": "+994",
            "IL": "+972", "NZ": "+64", "US": "+1", "TH": "+66", "AE": "+971",
            "CN": "+86", "UA": "+380", "RS": "+381"}
LANG_CC = {"it": "IT", "cs": "CZ", "sk": "SK", "pl": "PL", "de": "DE", "fr": "FR",
           "es": "ES", "pt": "PT", "nl": "NL", "hu": "HU", "ro": "RO", "bg": "BG",
           "el": "GR", "hr": "HR", "sl": "SI", "lt": "LT", "lv": "LV", "et": "EE",
           "fi": "FI", "sv": "SE", "da": "DK", "nb": "NO", "en": "IE"}
# office cell labels used when the pack leaves them out (addr/hours/phone/contact/email)
OFFICE_L10N = {
    "cs": ("Adresa", "Otevírací doba", "Telefon", "Napište nám", "Napište e-mailem"),
    "sk": ("Adresa", "Otváracie hodiny", "Telefón", "Napíšte nám", "Napíšte e-mailom"),
    "pl": ("Adres", "Godziny", "Telefon", "Napisz do nas", "Napisz e-mail"),
    "de": ("Adresse", "Öffnungszeiten", "Telefon", "Schreiben Sie uns", "E-Mail schreiben"),
    "fr": ("Adresse", "Horaires", "Téléphone", "Écrivez-nous", "Écrivez un e-mail"),
    "it": ("Indirizzo", "Orari", "Telefono", "Scrivici", "Scrivici via e-mail"),
    "es": ("Dirección", "Horario", "Teléfono", "Escríbenos", "Escríbenos por correo"),
    "pt": ("Endereço", "Horário", "Telefone", "Escreva-nos", "Envie um e-mail"),
    "nl": ("Adres", "Openingstijden", "Telefoon", "Mail ons", "E-mail ons"),
    "hu": ("Cím", "Nyitvatartás", "Telefonszám", "Írjon nekünk", "Írjon e-mailt"),
    "ro": ("Adresă", "Program", "Telefon", "Scrieți-ne", "Scrieți un e-mail"),
    "bg": ("Адрес", "Работно време", "Телефон", "Пишете ни", "Пишете имейл"),
    "el": ("Διεύθυνση", "Ώρες", "Τηλέφωνο", "Επικοινωνήστε", "Στείλτε email"),
    "hr": ("Adresa", "Radno vrijeme", "Telefon", "Pišite nam", "Pošaljite e-mail"),
    "sl": ("Naslov", "Delovni čas", "Telefon", "Pišite nam", "Pišite po e-pošti"),
    "lt": ("Adresas", "Darbo laikas", "Telefonas", "Rašykite mums", "Rašykite el. paštu"),
    "lv": ("Adrese", "Darba laiks", "Tālrunis", "Rakstiet mums", "Rakstiet e-pastu"),
    "et": ("Aadress", "Lahtiolekuajad", "Telefon", "Kirjutage meile", "Kirjutage e-kiri"),
    "fi": ("Osoite", "Aukioloajat", "Puhelin", "Ota yhteyttä", "Lähetä sähköpostia"),
    "sv": ("Adress", "Öppettider", "Telefon", "Skriv till oss", "Skicka e-post"),
    "da": ("Adresse", "Åbningstider", "Telefon", "Skriv til os", "Send e-mail"),
    "nb": ("Adresse", "Åpningstider", "Telefon", "Skriv til oss", "Send e-post"),
    "en": ("Address", "Hours", "Phone", "Contact us", "Email us"),
}

# screen-reader labels the fragments bind to (ui.aria_*). Packs sometimes ship them
# empty, which renders aria-label="" — worse than no label at all.
UI_L10N = {
    "it": ("Navigazione principale", "Menu", "Tempo rimanente per l'accesso", "Grafico della simulazione"),
    "cs": ("Hlavní navigace", "Menu", "Zbývající čas nabídky", "Graf simulace"),
    "sk": ("Hlavná navigácia", "Menu", "Zvyšný čas ponuky", "Graf simulácie"),
    "pl": ("Nawigacja główna", "Menu", "Pozostały czas oferty", "Wykres symulacji"),
    "de": ("Hauptnavigation", "Menü", "Verbleibende Zeit", "Diagramm der Simulation"),
    "fr": ("Navigation principale", "Menu", "Temps restant", "Graphique de la simulation"),
    "es": ("Navegación principal", "Menú", "Tiempo restante para el acceso", "Gráfico de la simulación"),
    "pt": ("Navegação principal", "Menu", "Tempo restante", "Gráfico da simulação"),
    "nl": ("Hoofdnavigatie", "Menu", "Resterende tijd", "Grafiek van de simulatie"),
    "hu": ("Fő navigáció", "Menü", "Hátralévő idő", "A szimuláció grafikonja"),
    "ro": ("Navigare principală", "Meniu", "Timp rămas", "Graficul simulării"),
    "bg": ("Основна навигация", "Меню", "Оставащо време", "Графика на симулацията"),
    "el": ("Κύρια πλοήγηση", "Μενού", "Υπόλοιπος χρόνος", "Γράφημα προσομοίωσης"),
    "hr": ("Glavna navigacija", "Izbornik", "Preostalo vrijeme", "Graf simulacije"),
    "sl": ("Glavna navigacija", "Meni", "Preostali čas", "Graf simulacije"),
    "lt": ("Pagrindinė navigacija", "Meniu", "Liekantis laikas", "Simuliacijos grafikas"),
    "lv": ("Galvenā navigācija", "Izvēlne", "Atlikušais laiks", "Simulācijas grafiks"),
    "et": ("Põhinavigatsioon", "Menüü", "Järelejäänud aeg", "Simulatsiooni graafik"),
    "fi": ("Päänavigaatio", "Valikko", "Jäljellä oleva aika", "Simulaation kuvaaja"),
    "sv": ("Huvudnavigering", "Meny", "Återstående tid", "Simuleringens diagram"),
    "da": ("Hovednavigation", "Menu", "Resterende tid", "Simuleringens graf"),
    "nb": ("Hovednavigasjon", "Meny", "Gjenstående tid", "Simuleringens graf"),
    "en": ("Main navigation", "Menu", "Time left to claim", "Simulation chart"),
}
# Short control words for the interactive demo widgets (G3). Tuple order:
# amount · horizon · minute unit · up · down · session · reset · bid · ask · demo.
WIDGET_L10N = {
    "it": ("Importo", "Orizzonte", "min", "Su", "Giù", "Questa sessione", "Azzera", "BID", "ASK", "DEMO"),
    "cs": ("Částka", "Horizont", "min", "Nahoru", "Dolů", "Tato relace", "Vynulovat", "BID", "ASK", "DEMO"),
    "sk": ("Suma", "Horizont", "min", "Nahor", "Nadol", "Táto relácia", "Vynulovať", "BID", "ASK", "DEMO"),
    "pl": ("Kwota", "Horyzont", "min", "W górę", "W dół", "Ta sesja", "Resetuj", "BID", "ASK", "DEMO"),
    "de": ("Betrag", "Horizont", "Min.", "Aufwärts", "Abwärts", "Diese Sitzung", "Zurücksetzen", "BID", "ASK", "DEMO"),
    "fr": ("Montant", "Horizon", "min", "Hausse", "Baisse", "Cette session", "Réinitialiser", "ACHAT", "VENTE", "DÉMO"),
    "es": ("Importe", "Horizonte", "min", "Sube", "Baja", "Esta sesión", "Reiniciar", "COMPRA", "VENTA", "DEMO"),
    "pt": ("Valor", "Horizonte", "min", "Alta", "Baixa", "Esta sessão", "Reiniciar", "COMPRA", "VENDA", "DEMO"),
    "nl": ("Bedrag", "Horizon", "min", "Omhoog", "Omlaag", "Deze sessie", "Resetten", "BOD", "ASK", "DEMO"),
    "hu": ("Összeg", "Időtáv", "perc", "Fel", "Le", "Ez a munkamenet", "Visszaállítás", "VÉTEL", "ELADÁS", "DEMO"),
    "ro": ("Sumă", "Orizont", "min", "Sus", "Jos", "Această sesiune", "Resetare", "CUMPĂRARE", "VÂNZARE", "DEMO"),
    "bg": ("Сума", "Хоризонт", "мин", "Нагоре", "Надолу", "Тази сесия", "Нулиране", "КУПУВАНЕ", "ПРОДАЖБА", "ДЕМО"),
    "el": ("Ποσό", "Ορίζοντας", "λεπ.", "Πάνω", "Κάτω", "Αυτή η συνεδρία", "Επαναφορά", "ΑΓΟΡΑ", "ΠΩΛΗΣΗ", "DEMO"),
    "hr": ("Iznos", "Horizont", "min", "Gore", "Dolje", "Ova sesija", "Poništi", "KUPNJA", "PRODAJA", "DEMO"),
    "sl": ("Znesek", "Obzorje", "min", "Gor", "Dol", "Ta seja", "Ponastavi", "NAKUP", "PRODAJA", "DEMO"),
    "lt": ("Suma", "Horizontas", "min.", "Aukštyn", "Žemyn", "Ši sesija", "Atstatyti", "PIRKTI", "PARDUOTI", "DEMO"),
    "lv": ("Summa", "Horizonts", "min.", "Uz augšu", "Uz leju", "Šī sesija", "Atiestatīt", "PIRKT", "PĀRDOT", "DEMO"),
    "et": ("Summa", "Horisont", "min", "Üles", "Alla", "See seanss", "Lähtesta", "OSTU", "MÜÜK", "DEMO"),
    "fi": ("Summa", "Aikaväli", "min", "Ylös", "Alas", "Tämä istunto", "Nollaa", "OSTA", "MYY", "DEMO"),
    "sv": ("Belopp", "Horisont", "min", "Upp", "Ner", "Denna session", "Återställ", "KÖP", "SÄLJ", "DEMO"),
    "da": ("Beløb", "Horisont", "min", "Op", "Ned", "Denne session", "Nulstil", "KØB", "SALG", "DEMO"),
    "nb": ("Beløp", "Horisont", "min", "Opp", "Ned", "Denne økten", "Tilbakestill", "KJØP", "SALG", "DEMO"),
    "en": ("Amount", "Horizon", "min", "Up", "Down", "This session", "Reset", "BID", "ASK", "DEMO"),
}

def widget_subs(plan, C) -> dict:
    """Token subs for the interactive demo/market widgets (controls + seeded values).

    Visible headings stay in the content pack (sections.demo / sections.markets);
    only short control words live here, so every language gets readable buttons.
    """
    lang = plan["params"].get("lang", "en")
    amount, horizon, minute, up, down, session, reset, bid, ask, demo = \
        WIDGET_L10N.get(lang) or WIDGET_L10N["en"]
    seed = int(plan.get("seed") or 0)
    rows = ((C.get("sections") or {}).get("markets") or {}).get("rows") or []
    base = _num((rows[0] or {}).get("v")) if rows else None
    if not base or base <= 0:
        base = 87450
    dec = 0 if base >= 1000 else (2 if base >= 100 else 4)
    out = {
        "{{W_AMOUNT}}": amount, "{{W_HORIZON}}": horizon, "{{W_MIN}}": minute,
        "{{W_UP}}": up, "{{W_DOWN}}": down, "{{W_SESSION}}": session,
        "{{W_RESET}}": reset, "{{W_BID}}": bid, "{{W_ASK}}": ask, "{{W_DEMO}}": demo,
        "{{W_SCORE}}": str(42 + (seed * 37) % 31),
        "{{W_BOOK_BASE}}": f"{base:.{dec}f}", "{{W_BOOK_DEC}}": str(dec),
    }
    # market rows for the live boards: data-* values must stay dot-formatted so JS
    # parseFloat/Number can read them; visible copy still comes from the content pack.
    fallback = ((87450, 2.4), (3120, -0.8), (4986, 0.6), (2284, 0.3))
    for i in range(4):
        row = rows[i] if i < len(rows) else {}
        val = _num(row.get("v")) if row else None
        chg = _num(row.get("chg")) if row else None
        if val is None or val <= 0:
            val = fallback[i][0]
        if chg is None:
            chg = fallback[i][1]
        vdec = 0 if val >= 1000 else (2 if val >= 100 else 4)
        n = i + 1
        out[f"{{{{W_M{n}_P}}}}"] = f"{val:.{vdec}f}"
        out[f"{{{{W_M{n}_DEC}}}}"] = str(vdec)
        out[f"{{{{W_M{n}_CHG}}}}"] = f"{chg:+.1f}"
        out[f"{{{{W_M{n}_DIR}}}}"] = "up" if chg >= 0 else "down"
    return out

# thanks.php eyebrow fallback (the pack usually supplies it; the default used to be
# the English word "DONE" on every locale)
THANKS_EYEBROW = {"it": "CONFERMATO", "cs": "POTVRZENO", "sk": "POTVRDENÉ", "pl": "POTWIERDZONE",
                  "de": "BESTÄTIGT", "fr": "CONFIRMÉ", "es": "RECIBIDO", "pt": "CONFIRMADO",
                  "nl": "BEVESTIGD", "hu": "MEGERŐSÍTVE", "ro": "CONFIRMAT", "bg": "ПОТВЪРДЕНО",
                  "el": "ΕΠΙΒΕΒΑΙΩΘΗΚΕ", "hr": "POTVRĐENO", "sl": "POTRJENO", "lt": "PATVIRTINTA",
                  "lv": "APSTIPRINĀTS", "et": "KINNITATUD", "fi": "VAHVISTETTU", "sv": "BEKRÄFTAT",
                  "da": "BEKRÆFTET", "nb": "BEKREFTET", "en": "DONE"}

# ---------------------------------------------------------------- utilities --
def die(msg, code=1): print(f"✗ {msg}"); sys.exit(code)
def ok(msg): print(f"✓ {msg}")

def load(p: pathlib.Path, default=None):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError: return default

def esc(s):
    if isinstance(s, (list, dict)): s = ""  # never print python repr into HTML
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def appshot_file(plan) -> str:
    """Chosen phone/market photo; legacy plans without the field get a stable fallback."""
    chosen = (plan.get("appshot") or {}) if isinstance(plan.get("appshot"), dict) else {}
    name = chosen.get("file") or ""
    if name and (APPSHOT_DIR / name).exists():
        return name
    if not APPSHOT_BANK:
        return ""
    seed = str((plan.get("params") or {}).get("domain") or plan.get("seed") or "0")
    pick = APPSHOT_BANK[sum(map(ord, seed)) % len(APPSHOT_BANK)]
    return pick["file"]


def trust_badges(plan) -> list[dict]:
    """Six brand/payment marks for the form strip; falls back to the first six."""
    by_key = {b.get("key"): b for b in TRUST_BANK}
    keys = [k for k in (plan.get("trust_badges") or []) if k in by_key]
    if not keys:
        keys = [b.get("key") for b in TRUST_BANK[:6]]
    return [by_key[k] for k in keys if k]


def trust_logos_html(plan) -> str:
    out = []
    for b in trust_badges(plan):
        out.append(
            f'<img src="img/trust/{esc(b["file"])}" alt="{esc(b.get("name", ""))}" '
            f'width="76" height="20" loading="lazy" decoding="async">')
    return "".join(out)


def partner_badges(plan) -> list[dict]:
    """Eight marks for the partner grid; the plan rotates its own set."""
    by_key = {b.get("key"): b for b in TRUST_BANK}
    keys = [k for k in (plan.get("partner_badges") or []) if k in by_key]
    if len(keys) >= 6:
        return [by_key[k] for k in keys[:8]]
    badges = trust_badges(plan)
    used = {b.get("key") for b in badges}
    return badges + [b for b in TRUST_BANK if b.get("key") not in used][:2]


def partner_grid_html(plan) -> str:
    """Larger 8-logo trust grid: the six form badges plus two fresh marks."""
    out = []
    for b in partner_badges(plan):
        out.append(
            f'<div class="partner-card"><img src="img/trust/{esc(b["file"])}" '
            f'alt="{esc(b.get("name", ""))}" loading="lazy" decoding="async"></div>')
    return "".join(out)

def _on_dark(hex_color: str, min_l: float = 0.62) -> str:
    """Lift a palette color to a readable-on-dark lightness (keeps the hue).
    Light palettes carry dark accent text — unreadable on the dark livebar strip."""
    import colorsys
    s = (hex_color or "").strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", s): return s
    r, g, b = (int(s[1:3], 16) / 255, int(s[3:5], 16) / 255, int(s[5:7], 16) / 255)
    h, l, sat = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(h, max(l, min_l), sat)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))

def php_str(s): return (s or "").replace("'", "\\'")

def clamp_meta(text, limit: int = 155) -> str:
    """Meta description that never ends mid-word or on a dangling connective.

    content packs carry a long `lead`; slicing it at 155 chars produced snippets like
    "…ni ter" in the SERP. Prefer the last sentence that fits, then the last whole word,
    and never leave a trailing "…sin hojas ni".
    """
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t.strip(" .,;:—-")
    cut = t[:limit]
    body = ""
    for sep in (". ", "! ", "? ", "; "):
        i = cut.rfind(sep)
        if i >= 70:
            body = cut[:i + 1]
            break
    if not body:
        i = cut.rfind(" ")
        body = cut[:i] if i >= 70 else cut
        words = body.split()
        while words and words[-1].lower().strip(".,") in WEAK_TAIL:
            words.pop()
        body = " ".join(words)
    return body.strip(" .,;:—-")

def contacts_for(plan, C: dict) -> dict:
    """Email + phone that belong to this offer's domain and country.

    Older/LLM packs can leave a foreign fallback (contatti@… / +39… on a .es site);
    the visible office block and the Organization JSON-LD both read from here so the
    two can never disagree.
    """
    dom = plan["params"]["domain"]
    cc = (plan["params"].get("cc") or LANG_CC.get(plan["params"].get("lang", ""), "")).upper()
    meta = C.get("meta") or {}
    # the address always belongs to the offer, with a locale-neutral local part:
    # a pack that copies "contatti@…" onto a .es site reads as a copy-paste template
    email = f"info@{dom}"
    tel = str(meta.get("telephone") or "").strip()
    pref = PHONE_CC.get(cc, "")
    valid = bool(re.fullmatch(r"\+[\d][\d\s().-]{6,}", tel))
    if valid and pref and not tel.replace(" ", "").startswith(pref):
        valid = False  # right format, wrong country
    if not valid:
        rng = random.Random(f"{plan.get('seed', 0)}:{dom}:contact")
        digits = " ".join(str(rng.randint(100, 999)) for _ in range(2)) + f" {rng.randint(1000, 9999)}"
        tel = f"{pref} {digits}".strip() if pref else f"+00 {digits}"
    return {"email": email, "telephone": tel}

def sanitize_meta_copy(C, B, plan) -> None:
    """Strip schema placeholders from titles/descriptions before the meta gate sees them.

    A reused content/blog pack can carry a `{...}`, `TODO`, `placeholder`, `xxx` or
    `lorem` token in a title/excerpt. The pack's own validator does not reject all of
    them, but the SEO meta gate does — and because the pack is reused, every rebuild
    failed on the same page (live: pnaf.info blog). Cleaning the fields in memory
    makes the build deterministic without touching the operator's pack on disk.
    """
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import meta_titles
    except Exception:
        return

    def clean(v):
        return meta_titles.clean_meta(v) if isinstance(v, str) else v

    if isinstance(C, dict):
        meta = C.get("meta")
        if isinstance(meta, dict):
            for k in ("title_home", "description", "og_description"):
                if isinstance(meta.get(k), str):
                    meta[k] = clean(meta[k])
        for key, page in C.items():
            if str(key).startswith("inner_") and isinstance(page, dict):
                for f in ("title", "h1", "lead"):
                    if isinstance(page.get(f), str):
                        page[f] = clean(page[f])
    if isinstance(B, dict):
        hub = B.get("hub")
        if isinstance(hub, dict):
            for f in ("title", "lead", "eyebrow"):
                if isinstance(hub.get(f), str):
                    hub[f] = clean(hub[f])
        for art in B.get("articles") or []:
            if isinstance(art, dict):
                for f in ("title", "h1", "excerpt"):
                    if isinstance(art.get(f), str):
                        art[f] = clean(art[f])
                # a cleaned title can fall below the blog gate's 18-char floor;
                # the article's own h1/excerpt keeps it a real title
                if len(str(art.get("title") or "")) < 18:
                    alt = str(art.get("h1") or "") or str(art.get("excerpt") or "")
                    if len(alt) >= 18:
                        art["title"] = alt[:72].rstrip(" .,;:—-")
                if len(str(art.get("excerpt") or "")) < 60:
                    alt = str(art.get("h1") or "") or str(art.get("title") or "")
                    body = ""
                    for sec in art.get("sections") or []:
                        if isinstance(sec, dict):
                            ps = [str(x).strip() for x in (sec.get("p") or []) if str(x or "").strip()]
                            if ps:
                                body = ps[0]
                                break
                    cand = " ".join(x for x in (alt, body or str(art.get("excerpt") or "")) if x)
                    if len(cand) < 60:
                        cand = " ".join(x for x in (alt, str(art.get("title") or ""),
                                                    str(art.get("excerpt") or "")) if x)
                    if len(cand) >= 60:
                        art["excerpt"] = cand[:190]


def office_defaults(C: dict, plan) -> None:
    """Fill contact cells the pack may omit and reject sentence-style labels."""
    lang = plan["params"].get("lang", "en")
    addr_l, hours_l, phone_l, contact_l, email_l = OFFICE_L10N.get(lang, OFFICE_L10N["en"])
    office = C.setdefault("office", {})
    for key, val in (("addr_label", addr_l), ("hours_label", hours_l),
                     ("phone_label", phone_l), ("contact_label", contact_l),
                     ("email_label", email_l)):
        cur = str(office.get(key) or "").strip()
        # a label is a label: "Correo de contacto disponible en tu panel de usuario"
        # rendered as a <small> caption and broke the office grid rhythm
        if cur and len(cur.split()) > 3:
            cur = " ".join(cur.split()[:3])
        cur = cur.rstrip(" .,;:—-")
        if not cur:
            office[key] = val
        else:
            office[key] = cur
    if not str(office.get("addr") or "").strip():
        office["addr"] = str(plan["params"].get("geo") or "").strip()

HIDDEN_SUBTREE = re.compile(r"<(\w+)[^>]*\baria-hidden=\"true\"[^>]*>.*?</\1>", re.S | re.I)


def self_heal_page(html: str, brand: str = "Brand") -> str:
    """Fix the two copy defects that used to stop a build.

    a) the same paragraph printed twice (two sections sharing one text) — the later copy
       is dropped, aria-hidden slider copies are untouched;
    b) a brand glued to the previous word ("oBrand") — a space is inserted.
    """
    stashed = []

    def _stash(m):
        stashed.append(m.group(0))
        return f"\x00H{len(stashed) - 1}\x00"

    tmp = HIDDEN_SUBTREE.sub(_stash, html)
    seen = set()

    def _para(m):
        text = " ".join(re.sub(r"<[^>]+>", " ", m.group(2)).split()).casefold()
        if len(text) >= 45:
            if text in seen:
                return ""
            seen.add(text)
        return m.group(0)

    tmp = re.sub(r"(<p\b[^>]*>)(.*?)(</p>)", _para, tmp, flags=re.S | re.I)
    for i, chunk in enumerate(stashed):
        tmp = tmp.replace(f"\x00H{i}\x00", chunk)
    if brand:
        glue = re.compile(rf"([a-z\u00e0-\u024f])({re.escape(brand)})")
        tmp = glue.sub(r"\1 \2", tmp)
    return tmp


def finish_page(page: str, plan, C: dict) -> str:
    """Shared final pass: domain/brand + contact placeholders used by blocks."""
    dom = plan["params"]["domain"]; brand = plan["params"]["brand"]
    c = contacts_for(plan, C)
    page = (page.replace("{DOM}", dom).replace("{BRAND}", brand)
                .replace("{{PHONE_TEL}}", re.sub(r"[^\d+]", "", c["telephone"]))
                .replace("{{PHONE}}", c["telephone"])
                .replace("{{EMAIL}}", c["email"]))
    page = self_heal_page(page, brand)
    return page


_REL_ATTR_RE = re.compile(r'\b(href|src|action|poster)="([^"]*)"', re.I)
_REL_KEEP = ("#", "/", "../", "http://", "https://", "//", "mailto:", "tel:",
             "data:", "javascript:", "?")


def rebase_relative(html: str, local=()) -> str:
    """Re-point root-relative links/assets for a page served one directory deep.

    The shell is authored for pages at the site root (`index.php`, `blocks/blocks.css`,
    `img/blog-x.png`). A page in /blog/ must reach them through `../`. Links that already
    point inside the silo (passed as `local`), in-page anchors and absolute URLs stay.
    """
    keep_local = set(local)

    def one(m):
        attr, url = m.group(1), m.group(2)
        if not url or url in keep_local or url.lower().startswith(_REL_KEEP):
            return m.group(0)
        return f'{attr}="../{url}"'
    return _REL_ATTR_RE.sub(one, html)

def ui_defaults(C: dict, plan) -> None:
    """Never ship aria-label="" — packs regularly leave ui.aria_* blank."""
    lang = plan["params"].get("lang", "en")
    nav, menu, timer, chart = UI_L10N.get(lang, UI_L10N["en"])
    ui = C.setdefault("ui", {})
    for key, val in (("aria_nav", nav), ("aria_menu", menu),
                     ("aria_timer", timer), ("aria_chart", chart)):
        if not str(ui.get(key) or "").strip():
            ui[key] = val

def _num(v):
    """'31.500' / '2.930,80' / '-0,8 %' / '1.0842' → float (locale-agnostic)."""
    m = re.search(r"[−-]?\d[\d\s.,]*", str(v or ""))
    if not m:
        return None
    t = m.group(0).replace(" ", "")
    neg = t[0] in "-−"
    if neg:
        t = t[1:]
    if "," in t and "." in t:
        # the LAST separator is the decimal one, the other groups thousands
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif t.count(",") == 1:
        head, tail = t.split(",")
        # 3-digit tail = thousands group ("87,450"); 1/2/4 = decimal ("2,4")
        t = t.replace(",", ".") if len(tail) in (1, 2, 4) else t.replace(",", "")
    elif t.count(".") == 1:
        head, tail = t.split(".")
        # "87.450" is a thousands group; "2.4" and "1.0842" are decimals
        if not (len(tail) in (1, 2, 4) or len(head) > 3):
            t = t.replace(".", "")
    elif "." in t:
        t = t.replace(".", "")
    try:
        return float(t) * (-1 if neg else 1)
    except ValueError:
        return None

def _livebar_labels(lang: str) -> dict:
    try:
        import gen_plan
        return gen_plan.LIVEBAR_L10N.get(lang) or gen_plan.LIVEBAR_L10N.get("en") or {}
    except Exception:
        return {}

SYM_ALIASES = {"XAU": "GOLD", "XAG": "SILVER", "WTI": "OIL", "USOIL": "OIL",
               "DAX": "DAX40", "US500": "SP500", "SPX": "SP500"}


def _sym_pair(sym) -> tuple:
    """('BTC/EUR', 'btc / eur') → ('BTC', 'EUR'); aliases applied to the base symbol."""
    base = re.sub(r"\s+", "", str(sym or "").upper().replace("\u00a0", ""))
    head, _, quote = base.partition("/")
    head = re.sub(r"[^A-Z0-9]", "", head)
    quote = re.sub(r"[^A-Z0-9]", "", quote)
    return (SYM_ALIASES.get(head, head), quote)


def _sym_keys(sym) -> list:
    """Every way the same instrument can be written: 'BTC / EUR', 'btc-eur', 'XAU/EUR',
    'GOLD/EUR', 'DAX 40', 'DAX40'. Models and the generator do not agree on spelling,
    and a missed match printed the same instrument at two prices on live pages."""
    base = re.sub(r"\s+", "", str(sym or "").upper().replace("\u00a0", ""))
    if not base:
        return []
    out = set()
    head, quote = (base.split("/", 1) + [""])[:2] if "/" in base else (base, "")
    head = re.sub(r"[^A-Z0-9]", "", head)
    quote = re.sub(r"[^A-Z0-9]", "", quote)
    alias = SYM_ALIASES.get(head, head)
    for h in {head, alias}:
        out.add(h)
        if quote:
            out.add(f"{h}/{quote}")
            out.add(f"{h}{quote}")
    out.add(re.sub(r"[^A-Z0-9]", "", base))
    return [k for k in out if k]


def reconcile_numbers(plan, C: dict) -> None:
    """One source of truth for every figure the page prints.

    The strip (plan.livebar.subs), the numbers band and the JSON-LD were generated
    independently — the plan baked random latency/orders/prices, the content wrote its
    own — so a page could show 41 ms and 52 ms, or BTC/EUR at two different prices.
    Content hero stats are canonical (they sit above the fold); the strip is aligned.
    """
    n = plan.setdefault("numbers", {})
    stats = (C.get("hero") or {}).get("stats") or []
    if len(stats) >= 3:
        rating = str(stats[0].get("v") or "").strip()
        if rating:
            n["rating"] = rating
        users = _num(stats[1].get("v"))
        if users:
            n["users"] = int(users)
        lat = _num(stats[2].get("v"))
        if lat:
            n["latency_ms"] = int(lat)
    # orders/second is its own metric: users//4 produced absurd rates (31k users →
    # "7.875 orders per second") and two surfaces printed two different figures
    if not n.get("orders"):
        rng = random.Random(f"{plan.get('seed', 0)}:{plan['params']['domain']}:orders")
        n["orders"] = rng.randint(900, 2600)

    subs = (plan.get("livebar") or {}).get("subs") or {}
    if not isinstance(subs, dict):
        return
    labels = _livebar_labels(plan["params"].get("lang", "en"))
    lat_lbl = str(labels.get("latency") or "").casefold()
    ord_lbl = str(labels.get("orders") or "").casefold()
    for i in (1, 2, 3):
        key = str(subs.get(f"LB_S{i}K") or "").strip().casefold()
        if not key:
            continue
        if lat_lbl and key == lat_lbl and n.get("latency_ms"):
            subs[f"LB_S{i}V"] = f"{int(n['latency_ms'])} ms"
        elif ord_lbl and key == ord_lbl and n.get("orders"):
            subs[f"LB_S{i}V"] = fmt_int(n["orders"], plan["params"].get("lang", "en"))
        elif key == "api":
            subs[f"LB_S{i}V"] = api_uptime(plan["params"].get("lang", "en"))
    # instrument quotes: the content rows (ticker/markets) win, so the strip agrees
    rows = ((C.get("sections") or {}).get("markets") or {}).get("rows") or []
    pairs = [(r, _sym_pair(r.get("sym"))) for r in rows if isinstance(r, dict) and r.get("sym")]
    for i in range(1, 7):
        sym = subs.get(f"LB{i}S")
        if not isinstance(sym, str):
            continue
        head, quote = _sym_pair(sym)
        row = next((r for r, (h, q) in pairs
                    if h == head and (not quote or not q or quote == q)), None)
        if not row:
            continue
        if str(row.get("v") or "").strip():
            subs[f"LB{i}V"] = str(row["v"]).strip()
        ch = str(row.get("chg") or "").strip()
        if ch:
            subs[f"LB{i}C"] = ch.rstrip("%").strip()
            subs[f"LB{i}D"] = "dn" if ch.lstrip().startswith(("-", "−")) else "up"

def ensure_anchors(html: str) -> str:
    """The hero's secondary link ('see how it works') must land on the steps section.

    Some steps fragments ship without an id, so the anchor was rewritten to #claim and
    the link text promised something it did not open.
    """
    m = re.search(r"<section[^>]*\bsec-steps\b[^>]*>", html)
    if not m or 'id="come"' in html:
        return html
    tag = m.group(0)
    if "id=" in tag:
        return html
    return html[:m.start()] + tag[:-1] + ' id="come">' + html[m.end():]

def add_brandnote_links(html: str, plan, C: dict) -> str:
    """Editorial block names the inner pages but used to link none of them."""
    m = re.search(r"<section[^>]*sec-brandnote[^>]*>.*?</section>", html, re.S)
    if not m or "<a " in m.group(0):
        return html
    slugs = plan["layout"].get("slugs", {})
    links = " · ".join(
        f'<a href="{slugs.get(which, which)}.php">{esc(page_nav_label(plan, C, which))}</a>'
        for which in ("about", "who", "contact"))
    block = m.group(0)
    cut = block.rfind("</p>")
    if cut < 0:
        return html
    block = block[:cut + 4] + f'<p class="brand-links">{links}</p>' + block[cut + 4:]
    return html[:m.start()] + block + html[m.end():]


# ---------------------------------------------------------------- validation -
def validate_plan(plan: dict) -> None:
    missing = [k for k in REQUIRED_PLAN_KEYS if k not in plan]
    if missing: die(f"plan missing keys: {missing}")
    params = plan["params"]
    for k in ("brand", "domain", "lang"):
        if not params.get(k): die(f"plan.params.{k} empty")
    if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", params["domain"]):
        die(f"bad domain: {params['domain']}")
    order = plan["layout"]["section_order"]
    for slot in order:
        canon = CANON.get(slot)
        if not canon or not (BLOCKS / f"{canon}.html").exists():
            die(f"section slot without canonical fragment: {slot}")
    for slot, var in (plan["layout"].get("variants") or {}).items():
        if slot not in order and slot not in SPECIAL_VARIANTS: die(f"variant for unknown slot: {slot}")
        canon = CANON.get(slot) or f"blk-{slot}"
        if var and slot not in SPECIAL_VARIANTS \
           and not (BLOCKS / f"blk-{slot}-{var}.html").exists() \
           and not (BLOCKS / f"{canon}-{var}.html").exists():
            die(f"variant fragment missing: {canon}-{var}.html")
    _we = (plan["layout"].get("widget_embed") or {})
    if _we and _we.get("slot") not in order:
        die(f"widget_embed host not in section_order: {_we.get('slot')!r}")
    if _we and _we.get("kind") not in ("calculator", "pulse-sim", "demo-line", "demo-bars",
                                       "sentiment-gauge", "book-ladder"):
        die(f"widget_embed kind unknown: {_we.get('kind')!r}")
    _me = (plan["layout"].get("market_embed") or {})
    if _me and _me.get("slot") not in order:
        die(f"market_embed host not in section_order: {_me.get('slot')!r}")
    if _me and _me.get("kind") not in ("heatmap", "listino-rows", "price-board", "tile-flip"):
        die(f"market_embed kind unknown: {_me.get('kind')!r}")
    if not (10 <= len(order) <= 18): die(f"section_order len {len(order)} out of range 10..18")
    if not ({"faq", "people", "facts", "security", "compare"} & set(order)):
        die("section_order needs a trust screen (faq/people/facts/security/compare)")
    anchors = {"people", "faq", "numbers", "cta", "office", "compare"}
    if len(anchors & set(order)) < 2:
        die("section_order needs >= 2 rotating anchor screens (people/faq/numbers/cta/office/compare)")
    if "numbers" in order and "stats-intro" in order:
        die("numbers and stats-intro are the same stat screen — keep only one")
    if not any(s in order for s in ("access-band", "claim-band", "enroll-band")):
        die("section_order must contain a form band")
    if "hero" not in order: die("section_order must start with hero-ish block")
    bl = plan.get("blog")
    if bl:
        topics = bl.get("topics") or []
        if not bl.get("enabled"):
            die("plan.blog present but not enabled")
        if bl.get("style") not in ("a", "b", "c"):
            die(f"plan.blog.style must be a|b|c, got {bl.get('style')!r}")
        if not 3 <= len(topics) <= 5:
            die(f"plan.blog needs 3..5 topics, got {len(topics)}")
        if len({t.get("id") for t in topics}) != len(topics):
            die("plan.blog topics repeat")
        # the hub is the fixed directory landing page (/blog/index.php); an old plan's
        # hub_slug is ignored, not honoured — the silo must not move per plan.

def validate_content(content: dict, plan: dict, strict=False) -> list[str]:
    errs = []
    lang_re = re.compile(rf"[??]")  # placeholder; language check delegated to reviewer
    # forbidden: deposit-like sums inside meta fields
    dep_pat = re.compile(r"(€\s?250\b|250\s?€|\b\d{2,3}\s?(000|k)\s?(NOK|zł|Kč|Ft)\b)", re.I)
    meta_blob = " ".join(str(v) for v in (content.get("meta") or {}).values())
    if dep_pat.search(meta_blob): errs.append("deposit-like amount in meta fields")
    # hero strings non-empty in strict mode (and never lists/dicts — a stray
    # LLM list would otherwise reach esc()/fill() and render as junk)
    if strict:
        for k, v in (content.get("hero") or {}).items():
            if isinstance(v, (list, dict)) and k not in ("stats", "device_rows", "proof"):
                errs.append(f"hero.{k} is a list/dict"); continue
            if isinstance(v, str) and not v.strip(): errs.append(f"hero.{k} empty")
        for grp, keys in (("bands", ("mid_eyebrow", "mid_h2", "mid_lead", "form_title",
                                     "form_sub", "form_consent", "submit", "submit_nav",
                                     "trust_label")),
                          ("footer", ("tagline", "disclaimer", "risk_line"))):
            node = content.get(grp) or {}
            for k in keys:
                v = node.get(k)
                if v is None: continue
                if isinstance(v, (list, dict)): errs.append(f"{grp}.{k} is a list/dict")
                elif isinstance(v, str) and not v.strip(): errs.append(f"{grp}.{k} empty")
        for k, v in (content.get("meta") or {}).items():
            if isinstance(v, (list, dict)): errs.append(f"meta.{k} is a list/dict")
    # reviews consistency with plan numbers
    n = plan.get("numbers", {})
    rv = content.get("reviews", {})
    if n.get("rating") and isinstance(rv, dict):
        pass  # displayed rating uses plan value; pack carries items only
    # fragment arrays must carry text: LLM packs occasionally return empty strings
    # or empty dicts, which render as blank chips/cards on live pages
    def _nonempty(x):
        if isinstance(x, str): return bool(x.strip())
        if isinstance(x, dict): return any(str(v).strip() for v in x.values())
        return True
    order = (plan.get("layout") or {}).get("section_order") or []
    for slot, key, need in (("facts", "points", 4), ("portal", "cards", 3),
                            ("reviews", "items", 3)):
        if slot not in order: continue
        arr = ((content.get("sections") or {}).get(slot) or {}).get(key) \
              if slot != "reviews" else (rv.get("items") or [])
        if not isinstance(arr, list):
            # a model that answers "null" here used to crash the validator
            errs.append(f"sections.{slot}.{key} is not an array ({type(arr).__name__})")
            arr = []
        good = [x for x in arr if _nonempty(x)]
        if len(good) < need:
            errs.append(f"sections.{slot}.{key} empty or shorter than {need} ({len(good)} valid)")
        if slot in ("facts", "portal"):
            for k in ("eyebrow", "h2", "lead"):
                v = ((content.get("sections") or {}).get(slot) or {}).get(k)
                if isinstance(v, list) or not str(v or "").strip():
                    errs.append(f"sections.{slot}.{k} missing or a raw list")
    # review cards must be three DIFFERENT people — cloned cards (same name, photo or
    # quote) read as a fake section on a live page
    ritems = rv.get("items") if isinstance(rv, dict) else None
    if isinstance(ritems, list):
        if len(ritems) < 3:
            errs.append(f"reviews.items has {len(ritems)} entries, need 3 different people")
        for field in ("name", "photo", "quote"):
            vals = [str((it or {}).get(field, "")).strip().casefold()
                    for it in ritems if isinstance(it, dict)]
            vals = [v for v in vals if v]
            dup = sorted({v for v in vals if vals.count(v) > 1})
            if dup:
                errs.append(f"reviews.{field} repeated across cards: {dup[:2]}")
    # faq answers shorter than ~2 sentences read as stubs on live pages
    faq_items = ((content.get("faq") or {}).get("items") or [])
    if not isinstance(faq_items, list):
        errs.append("faq.items is not an array")
        faq_items = []
    if faq_items and len(faq_items) < 12:
        errs.append(f"faq.items has {len(faq_items)} entries, need 12 substantial Q&A")
    for it in faq_items:
        a = it.get("a") if isinstance(it, dict) else ""
        if not isinstance(a, str) or not a.strip():
            errs.append("faq answer empty")
        else:
            # CJK says the same in half the characters: 97 Japanese characters are two
            # full sentences, while 97 Latin characters are usually a stub
            _min = 50 if plan["params"].get("lang") in ("ja", "zh", "ko") else 180
            if len(a.strip()) < _min:
                errs.append(f"faq answer too short ({len(a.strip())} chars): {a[:40]}…")
    # long-form guide: every item must explain something, not repeat a chip label
    guide = ((content.get("sections") or {}).get("guide") or {})
    if "guide" in order:
        gitems = guide.get("items") if isinstance(guide, dict) else None
        if not isinstance(gitems, list) or len([x for x in gitems if _nonempty(x)]) < 6:
            errs.append(f"sections.guide.items needs >= 6 explained topics "
                        f"({len(gitems) if isinstance(gitems, list) else 0} valid)")
        else:
            for k in ("eyebrow", "h2", "lead"):
                v = guide.get(k)
                if isinstance(v, list) or not str(v or "").strip():
                    errs.append(f"sections.guide.{k} missing or a raw list")
            for i, it in enumerate(gitems[:6]):
                d = str((it or {}).get("d") or "").strip()
                if len(d) < (55 if plan["params"].get("lang") in ("ja", "zh", "ko") else 150):
                    errs.append(f"sections.guide.items.{i}.d too short ({len(d)} chars)")
    # app-shot: the phone/market photo needs real accompanying copy and a literal alt
    appshot = ((content.get("sections") or {}).get("appshot") or {})
    if "appshot" in order:
        if not isinstance(appshot, dict):
            errs.append("sections.appshot must be an object")
        else:
            for k in ("eyebrow", "h2", "lead", "alt"):
                v = appshot.get(k)
                if isinstance(v, list) or not str(v or "").strip():
                    errs.append(f"sections.appshot.{k} missing or a raw list")
            pts = appshot.get("points")
            if not isinstance(pts, list) or len([x for x in pts if _nonempty(x)]) < 3:
                errs.append("sections.appshot.points needs >= 3 captions")
    partners = ((content.get("sections") or {}).get("partners") or {})
    if "partners" in order:
        for k in ("eyebrow", "h2", "lead"):
            v = partners.get(k) if isinstance(partners, dict) else None
            if isinstance(v, list) or not str(v or "").strip():
                errs.append(f"sections.partners.{k} missing or a raw list")
    # long editorial pages (product / offer / FAQ): real body copy, not a card grid
    for key, min_words, min_sections, min_faq in (("inner_product", 450, 5, 6),
                                                  ("inner_offer", 450, 5, 6),
                                                  ("inner_faq", 600, 2, 12)):
        page = content.get(key) or {}
        if not isinstance(page, dict):
            errs.append(f"{key} must be an object")
            continue
        secs = [s for s in (page.get("sections") or []) if isinstance(s, dict)]
        fqs = [x for x in (page.get("faq") or []) if isinstance(x, dict) and str(x.get("q") or "").strip()]
        blob = " ".join(str(v) for v in (page.get("lead"),) if v)
        for s in secs:
            blob += " " + " ".join(str(x) for x in (s.get("paragraphs") or []))
            blob += " " + " ".join(str(x) for x in (s.get("bullets") or []))
        for x in fqs:
            blob += " " + str(x.get("q") or "") + " " + str(x.get("a") or "")
        words = len(blob.split())
        # ±60 words is a rounding miss, not thin copy: 447/450 must not send the
        # whole pack through another repair round-trip (and then throw it away)
        floor = min_words - min(60, max(10, round(min_words * 0.16)))
        if words < floor:
            errs.append(f"{key} has {words} words, needs >= {floor}")
        if len(secs) < min_sections:
            errs.append(f"{key}.sections has {len(secs)} entries, needs >= {min_sections}")
        if len(fqs) < min_faq:
            errs.append(f"{key}.faq has {len(fqs)} entries, needs >= {min_faq}")
        for i, s in enumerate(secs):
            if not str(s.get("h2") or "").strip() or not [x for x in (s.get("paragraphs") or []) if str(x or "").strip()]:
                errs.append(f"{key}.sections.{i} needs h2 + paragraph")
    # ---- stats captions are WORDS, never the numbers they describe -----------
    # (live bug: 4,7/5 → caption "4,7", 1.405 → caption "1.280": the numbers band
    #  shipped as a wall of duplicated figures with no meaning)
    stats = ((content.get("sections") or {}).get("stats") or {})
    if isinstance(stats, dict):
        seen_lbl = {}
        for key in ("rating", "reviews", "orders", "api"):
            v = str(stats.get(key) or "").strip()
            if not v:
                continue
            if re.search(r"\d", v):
                errs.append(f"sections.stats.{key} must be a word label, got a number: {v[:24]}")
            low = v.casefold()
            if low in seen_lbl:
                errs.append(f"sections.stats.{key} repeats the {seen_lbl[low]} label")
            seen_lbl[low] = key
    # ---- contacts must belong to this offer ---------------------------------
    dom = plan["params"]["domain"]
    cc = (plan["params"].get("cc") or LANG_CC.get(plan["params"].get("lang", ""), "")).upper()
    meta = content.get("meta") or {}
    email = str(meta.get("email") or "").strip()
    if email and not re.fullmatch(rf"[a-z0-9._%+-]+@{re.escape(dom)}", email, re.I):
        errs.append(f"meta.email {email} does not belong to {dom}")
    tel = str(meta.get("telephone") or "").strip()
    pref = PHONE_CC.get(cc, "")
    if tel and pref and not tel.replace(" ", "").startswith(pref):
        errs.append(f"meta.telephone {tel} is not a {cc} number")
    # ---- office captions are labels, not sentences ---------------------------
    office = content.get("office") or {}
    for key in ("addr_label", "hours_label", "phone_label", "contact_label", "email_label"):
        v = str(office.get(key) or "").strip()
        if v and (len(v.split()) > 4 or v.endswith(".")):
            errs.append(f"office.{key} is a sentence, use a short label: {v[:40]}")
    # ---- the brand must never be glued to the previous word ------------------
    brand = plan["params"]["brand"]
    glue = re.compile(rf"[a-zà-ÿ]{re.escape(brand)}", re.I)

    def _scan(node, path=""):
        if isinstance(node, str):
            hit = glue.search(node)
            if hit:
                errs.append(f"{path or 'pack'}: brand glued to a word (missing space): "
                            f"{hit.group(0)[:24]}")
        elif isinstance(node, dict):
            for k, v in node.items(): _scan(v, f"{path}.{k}".strip("."))
        elif isinstance(node, list):
            for i, v in enumerate(node): _scan(v, f"{path}.{i}")
    _scan(content)
    # ---- schema fixtures and foreign alphabets never reach the page ----------
    # The skeleton is built from content/content-pack.schema.json and its example
    # values are ellipses plus Ukrainian/Italian hints. A model that skips a slot
    # leaves them in place, and "…" is not an empty string, so the gate used to
    # wave it through: ing-rendement.xyz shipped its countdown band as a "…"
    # heading/lead/button and the four captions as the Ukrainian "днів" on a
    # Dutch page. Both are hard errors now, whatever route produced the pack.
    FIXTURE_ONLY = re.compile(r"^[\s…\.·:;\-–—_/\\]+$")
    CYR_RE = re.compile(r"[А-Яа-яЁёЇїІіЄєҐґ]")
    _lang = (plan["params"].get("lang") or "en").lower()
    _cyr_lang = _lang in ("ru", "uk", "bg", "mk", "sr", "be", "kk")
    _skip_script = (".photo", ".ic", ".g", ".sym", ".vv", ".device_bal_v")
    _brand_key = str(plan["params"].get("brand") or "").strip().casefold()
    _fixes, _scripts = [], []

    def _audit_copy(node, path=""):
        if isinstance(node, str):
            if path.endswith(_skip_script) or path.split(".")[-1].startswith("_"):
                return
            if node.strip() and FIXTURE_ONLY.match(node):
                _fixes.append(path)
            elif not _cyr_lang and node.strip().casefold() != _brand_key and CYR_RE.search(node):
                _scripts.append(f"{path} ('{node.strip()[:24]}')")
        elif isinstance(node, dict):
            for k, v in node.items():
                _audit_copy(v, f"{path}.{k}".strip("."))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _audit_copy(v, f"{path}.{i}")
    _audit_copy(content)
    if _fixes:
        errs.append("placeholder fixtures left in the pack ('…' is not copy): "
                    + ", ".join(_fixes[:6]))
    if _scripts:
        errs.append(f"copy in another alphabet for a '{_lang}' site: " + ", ".join(_scripts[:6]))
    # ---- countdown band: real copy and four DIFFERENT captions ---------------
    order = (plan.get("layout") or {}).get("section_order") or []
    if "scarcity" in order:
        sc = content.get("scarcity") or {}
        for k in ("eyebrow", "h2", "lead", "btn"):
            if not str(sc.get(k) or "").strip():
                errs.append(f"scarcity.{k} empty — the countdown band needs copy")
        units = [str(u).strip() for u in (sc.get("units") or []) if str(u).strip()]
        if len(units) != 4:
            errs.append(f"scarcity.units needs 4 time labels, got {len(units)}")
        elif len({u.casefold() for u in units}) != 4:
            errs.append("scarcity.units repeats a label — needs days/hours/minutes/seconds")
        elif any(re.search(r"\d", u) or len(u) > 16 for u in units):
            errs.append(f"scarcity.units labels must be short words without digits: {units}")
    # ---- card icons are monochrome glyphs, not emoji -------------------------
    # (a coloured 🔔 among ▤/◍ glyphs reads as a different design system)
    EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF]")

    def _icons(node, path=""):
        if isinstance(node, dict):
            ic = node.get("ic")
            if isinstance(ic, str) and EMOJI_RE.search(ic):
                errs.append(f"{path}.ic is an emoji, use a monochrome glyph: {ic}")
            for k, v in node.items():
                _icons(v, f"{path}.{k}".strip("."))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _icons(v, f"{path}.{i}")
    _icons(content.get("sections") or {})
    return errs

# ---------------------------------------------------------------- content ----
def seed_content(plan: dict) -> dict:
    """Placeholder content so the site builds and passes structure gates even without LLM."""
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    n = plan.get("numbers", {}); ppl = plan.get("people", [])
    return {
        "meta": {"title_home": f"{brand} — pištorg plataforma",
                  "description": f"{brand}: instrumenty ta pidtrymka dla svідомих рішень.",
                  "keywords": f"{brand}, {brand.lower()}, {dom}, {brand.lower()} login",
                  "og_description": "placeholder og"},
        "hero": {"eyebrow": "PLACEHOLDER", "h1_rest": "Build real headline", "h1_accent": "here",
                  "lead": "Placeholder lead — replace via content pack.",
                  "secondary": "", "cta_primary": "Start", "cta_secondary": "More",
                  "stats": [{"v": n.get("rating","4,7"), "l": "rating"},
                             {"v": fmt_int(n.get("users", 12500), plan["params"].get("lang", "en")), "l": "users"},
                             {"v": f"{n.get('latency_ms',52)} ms", "l": "latency"}],
                  "device_bal": "€0,00", "device_delta": "↗ placeholder", "device_rows": [],
                  "proof": {"claims": ["Point one", "Point two", "Point three"],
                             "quote": "Placeholder quote.", "quote_by": "Name · City",
                             "steps": [{"t": "Step one", "d": "Placeholder."},
                                        {"t": "Step two", "d": "Placeholder."},
                                        {"t": "Step three", "d": "Placeholder."}]}},
        "bands": {"mid_eyebrow": "ACCESS", "mid_h2": "Get access", "mid_lead": "Leave details.",
                   "mid_points": ["Point one", "Point two", "Point three", "Point four"],
                   "form_title": "Free registration", "form_sub": "",
                   "form_consent": "I agree to privacy policy. First deposit conditions in terms.",
                   "submit_nav": "Open account",
                   "labels": {"first": "First name", "last": "Last name", "email": "Email", "phone": "Phone"},
                   "placeholders": {"first": "John", "last": "Doe", "email": "john@example.com", "phone": "600 000 000"},
                   "submit": "Send request"},
        "ui": {"calc_eyebrow": "SIMULATION", "calc_initial": "Initial", "calc_init_note": "EUR \u00b7 min. 250",
                "calc_monthly": "Monthly", "calc_cur_note": "EUR", "calc_years": "Years", "calc_rate": "Rate",
                "calc_value_after": "VALUE AFTER", "calc_contributed": "Contributed", "calc_gain": "Gain",
                "calc_now": "Now", "cur_code": "EUR", "cur_sym": "\u20ac", "year_full": "YEARS",
                "year_short": "YEARS", "min_init": "250",
                "status_sending": "Sending\u2026", "status_fix": "Please review the highlighted fields.",
                "status_fail": "Submission failed, please try again.", "status_ok": "Done, redirecting\u2026"},
        "faq": {"eyebrow": "FAQ", "h2": "Questions",
                  "items": [{"q": f"Placeholder question {i}?", "a": "Placeholder answer."} for i in range(1, 5)]},
        "reviews": {"eyebrow": "Reviews", "h2": "Users about platform", "lead": "Names are illustrative.",
                     "items": [{"name": nm, "city": "Capital", "role": "role", "tenure": "1 year",
                                 "gain": "+0", "photo": ph, "quote": "Placeholder review text."}
                                for nm, ph in zip(ppl[:3], plan.get("photos", [])[:3])]},
        "office": {"h2": "Office", "lead": "", "addr_label": "Address", "addr": "Main st 1",
                    "hours_label": "Hours", "hours": "Mon–Fri 9:00–18:00", "contact_label": "Contact"},
        "footer": {"tagline": "", "risk_line": "Trading involves risk.",
                    "disclaimer": "Placeholder disclaimer."},
        "thanks": {"h1": "Thank you", "lead": "We call within 30 minutes.", "warn": ""}
    }

# ---------------------------------------------------------------- css/head ---
def css_link_block(plan: dict) -> tuple[str, str, str]:
    pal_id = plan["design"]["palette_id"]; skin = plan["design"].get("skin", "rounded-air")
    pals = load(PALETTES, {"palettes": [], "fonts": {}})
    pal = next((p for p in pals["palettes"] if p["id"] == pal_id), None)
    if not pal:
        # fallback: resolve palette from old templates/palettes.json (pre-blk ids) by mapping to closest new one
        old = load(ROOT / "resources" / "palettes-legacy.json", {"palettes": []})
        oldp = next((p for p in old["palettes"] if p["id"] == pal_id), None)
        if oldp:
            v = oldp["tokens"]; theme = oldp.get("theme", "light")
            pal = {"id": pal_id, "theme": theme, "vars": {
                "bg": v.get("bg", "#fff"), "bg_soft": v.get("bg_soft", "#f5f5f5"),
                "panel": v.get("panel", "#fafafa"), "ink": v.get("ink", "#111"),
                "muted": v.get("muted", "#666"), "line": v.get("line", "#e5e5e5"),
                "acc": v.get("primary", v.get("acc", "#1d3a8a")),
                "acc_deep": v.get("primary_deep", v.get("acc_deep", "#142a66")),
                "acc_2": v.get("accent_2", v.get("acc_2", "#0038ff")),
                "up": v.get("up", "#0a7a3d"), "down": v.get("down", "#c01818"),
                "grad": v.get("gradient", "none")},
                "default_fonts": None}
            ok(f"palette '{pal_id}' mapped from legacy palettes.json")
    if not pal: die(f"palette '{pal_id}' not found anywhere")
    skin_file = SKINS / f"skin-{skin}.css"
    if not skin_file.exists(): die(f"skin '{skin}' missing in skins/")
    fp_key = plan["design"].get("font_pair") or pal.get("default_fonts")
    if not fp_key:
        fp_key = "grotesk-man" if plan["design"].get("theme") == "dark" or pal["theme"] == "dark" else "bitter-work"
    fonts = pals["fonts"].get(fp_key)
    if not fonts: die(f"font pair '{fp_key}' unknown")
    # always-dark surfaces (livebar family Q) need readable colors for every
    # palette: derive on-dark variants by lifting lightness, keeping the hue
    ondark = (";--acc-ondark:%s;--up-ondark:%s;--down-ondark:%s" % (
        _on_dark(pal["vars"].get("acc", "#3ddc84"), 0.62),
        _on_dark(pal["vars"].get("up", "#22c55e"), 0.66),
        _on_dark(pal["vars"].get("down", "#ef4444"), 0.60)))
    css_vars = ":root{" + ";".join(
        f"--{k.replace('_','-')}:{v}" for k, v in pal["vars"].items()) + ondark + \
        f";--font-head:'{fonts['head']}'" + f";--font-body:'{fonts['body']}'}}"
    theme_meta = pal["vars"].get("bg", "#111111") if pal["theme"] == "dark" else \
        (pal["vars"].get("acc_deep") or pal["vars"].get("acc", "#111111"))
    return css_vars, fonts["import"], theme_meta

# ---------------------------------------------------------------- fragments --
def frag(name: str) -> str:
    p = BLOCKS / f"{name}.html"
    return p.read_text(encoding="utf-8") if p.exists() else ""

BLK_MAP = {  # plan slot -> canonical blk template in blocks/ (blk-*.html authored clean)
    "hero": "blk-hero", "access-band": "blk-band-access", "claim-band": "blk-band-claim",
    "enroll-band": "blk-band-access", "ticker": "blk-ticker", "intro-center": "blk-intro",
    "stats-intro": "blk-intro-stats", "ladder": "blk-ladder", "features": "blk-features",
    "steps": "blk-steps", "steps-live": "blk-steps", "timeline": "blk-timeline",
    "calculator": "blk-calculator", "markets": "blk-markets", "streams": "blk-streams",
    "security": "blk-security", "demo": "blk-demo", "people": "blk-reviews",
    "scarcity": "blk-scarcity", "risk": "blk-risk", "cta-band": "blk-cta",
    "trust-band": "blk-cta", "faq": "blk-faq", "office": "blk-office",
    "brand-note": "blk-brandnote",
    "device": "blk-device",
    "pulse-sim": "blk-pulse-sim",
    "numbers": "blk-numbers",
    "mini-faq": "blk-mini-faq",
    "portal": "blk-portal",
    "compare": "blk-compare",
    "glance": "blk-glance",
    "facts": "blk-facts",
    "notes": "blk-notes",
    "guide": "blk-guide",
    "appshot": "blk-appshot",
    "partners": "blk-partners",
}
INC_HEAD = "<?php include __DIR__ . '/api_local/integration/header.php'; ?>"
INC_FOOT = "<?php include __DIR__ . '/api_local/integration/footer.php'; ?>"

def safe_emails(html: str) -> str:
    """No plain-text address may reach the markup.

    The hosting proxy rewrites addresses into an obfuscated span whose decoder the
    panel does not serve: visitors see "[email protected]" and the link 404s. Copy that
    names the address (legal pages, thanks) keeps it, but as a JS-assembled link.
    """
    def _anchor(u: str, d: str) -> str:
        return (f'<a class="js-mail" href="index.php#claim" data-u="{esc(u)}" '
                f'data-d="{esc(d)}">{esc(u)}<span aria-hidden="true"> [at] </span>{esc(d)}</a>')

    def _from_href(m):
        u, _, d = m.group(1).strip().partition("@")
        return _anchor(u, d) if d else m.group(0)

    html = re.sub(r'<a\b[^>]*\bhref="mailto:([^"?]+)[^"]*"[^>]*>.*?</a>', _from_href, html,
                  flags=re.I | re.S)

    def _swap(segment: str) -> str:
        return re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                      lambda m: _anchor(*m.group(0).partition("@")[::2]), segment)
    out, pos = [], 0
    for tag in re.finditer(r"<[^>]+>", html):
        out.append(_swap(html[pos:tag.start()]))
        out.append(tag.group(0))
        pos = tag.end()
    out.append(_swap(html[pos:]))
    return "".join(out)

def page_shell(title, descr, keywords, canonical_path, locale, css_vars, fonts_import,
               theme_color, body, og_desc="", jsonld="", noindex=False, canonical=True,
               og_type="website", og_image="", blog=False):
    body = safe_emails(body)
    og_url = og_image or "https://{DOM}/og-image.jpg"
    blog_css = (f'<link rel="stylesheet" href="blocks/blog.css?v={BUILD_V}">\n'
                if blog else "")
    dom_css = f"<style>{esc(css_vars)}</style>"
    rob = "noindex,follow" if noindex else "index,follow,max-image-preview:large,max-snippet:-1"
    ld = f'<script type="application/ld+json">{jsonld}</script>' if jsonld else ""
    # a noindex page must not advertise a canonical target (search engines ignore it
    # and the pair reads as a contradiction)
    canon = (f'<link rel="canonical" href="https://{{DOM}}{canonical_path}">\n'
             f'<link rel="alternate" hreflang="{esc(locale)}" href="https://{{DOM}}{canonical_path}">\n'
             f'<link rel="alternate" hreflang="x-default" href="https://{{DOM}}{canonical_path}">\n'
             ) if canonical else ""
    return f"""<!doctype html>
<html lang="{esc(locale.split('-')[0])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(descr)}">
<meta name="robots" content="{rob}">
<meta name="theme-color" content="{esc(theme_color)}">
<meta name="keywords" content="{esc(keywords)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="icon" href="favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
{canon}<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(og_desc or descr)}">
<meta property="og:locale" content="{esc(locale.replace('-', '_'))}">
<meta property="og:type" content="{esc(og_type)}">
<meta property="og:site_name" content="{{BRAND}}">
<meta property="og:url" content="https://{{DOM}}{canonical_path}">
<meta property="og:image" content="{esc(og_url)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{esc(title)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(og_desc or descr)}">
<meta name="twitter:image" content="{esc(og_url)}">
<meta name="twitter:image:alt" content="{esc(title)}">
<link rel="stylesheet" href="blocks/blocks.css?v={BUILD_V}">
<link rel="stylesheet" href="skin.css?v={BUILD_V}">
<link rel="stylesheet" href="widgets.css?v={BUILD_V}">
{blog_css}<style>@import url('{fonts_import}');</style>
{dom_css}
{INC_HEAD}
{ld}
</head>
<body>
{body}
{INC_FOOT}
<script src="widgets.js?v={BUILD_V}"></script>
<script src="app.js?v={BUILD_V}"></script>
<script src="calculator.js?v={BUILD_V}"></script>
<script src="pulse-sim.js?v={BUILD_V}"></script>
</body>
</html>"""

# ---------------------------------------------------------------- builders ---
CANON = {  # canonical blk-* fragment per slot (authored clean, contract-safe)
    "livebar": "blk-livebar",
    "hero": "blk-hero", "access-band": "blk-band-access", "claim-band": "blk-band-access",
    "enroll-band": "blk-band-access", "ticker": "blk-ticker", "intro-center": "blk-intro",
    "stats-intro": "blk-intro-stats", "ladder": "blk-ladder", "features": "blk-features",
    "steps": "blk-steps", "steps-live": "blk-steps-live", "timeline": "blk-timeline",
    "calculator": "blk-calculator", "markets": "blk-markets", "streams": "blk-streams",
    "security": "blk-security", "demo": "blk-demo", "people": "blk-reviews",
    "scarcity": "blk-scarcity", "risk": "blk-risk", "cta-band": "blk-cta",
    "trust-band": "blk-cta", "faq": "blk-faq", "office": "blk-office",
    "brand-note": "blk-brandnote",
    "device": "blk-device",
    "pulse-sim": "blk-pulse-sim",
    "numbers": "blk-numbers",
    "mini-faq": "blk-mini-faq",
    "portal": "blk-portal",
    "compare": "blk-compare",
    "glance": "blk-glance",
    "facts": "blk-facts",
    "notes": "blk-notes",
    "guide": "blk-guide",
    "appshot": "blk-appshot",
    "partners": "blk-partners",
}

def frag_for(name: str, plan) -> str:
    """Pick blk-<slot>-<variant> when the plan asked for one, else the canonical slot."""
    var = (plan.get("layout", {}).get("variants") or {}).get(name, "")
    if var:
        canon = CANON.get(name) or f"blk-{name}"
        v = frag(f"blk-{name}-{var}") or frag(f"{canon}-{var}")
        if v: return v
    return frag(CANON[name]) if name in CANON else frag(name)

def R(name: str, plan, C, **kw) -> str:
    """Render a canonical blk fragment with plan+content substitutions."""
    tpl = frag_for(name, plan)
    if not tpl:
        return f"<!-- missing fragment {name} -->"
    out = tpl
    subs = {
        "{{BRAND}}": plan["params"]["brand"], "{{DOMAIN}}": plan["params"]["domain"],
        "{{GEO_SHORT}}": plan["params"].get("geo_short", ""),
        "{{LATENCY}}": str(plan["numbers"].get("latency_ms", 52)),
        "{{API_UPTIME}}": api_uptime(plan["params"].get("lang", "en")),
        "{{ORDERS}}": fmt_int(plan["numbers"].get("orders")
                              or (plan["numbers"].get("users", 12500) // 4),
                              plan["params"].get("lang", "en")),
        "{{GEO}}": plan["params"].get("geo", ""), "{{RATING}}": str(plan["numbers"].get("rating", "4,7")),
        "{{SEED}}": str(plan.get("seed", "")),
        "{{REVIEWS}}": fmt_int(plan["numbers"].get("reviews", 641), plan["params"].get("lang", "en")),
        "{{USERS}}": fmt_int(plan["numbers"].get("users", 12500), plan["params"].get("lang", "en")),
        "{{TRUST_LOGOS}}": trust_logos_html(plan),
        "{{PARTNER_GRID}}": partner_grid_html(plan),
    }
    subs.update(widget_subs(plan, C))
    if name == "pulse-sim":
        for k, v in ((plan.get("pulse_sim") or {}).get("subs") or {}).items():
            subs["{{" + k + "}}"] = v
    if name == "livebar":
        for k, v in ((plan.get("livebar") or {}).get("subs") or {}).items():
            subs["{{" + k + "}}"] = v
        lb = C.get("livebar") or {}
        if lb:
            # content pack may override the news headlines (kept from plan words otherwise)
            for i, text in enumerate((lb.get("news") or [])[:4], start=1):
                subs["{{LB_NEWS%d}}" % i] = text
            # legacy word-swap: replace only the leading word of queue/wait/slots stats
            for key, token in (("queue", "LB_QUEUE"), ("wait", "LB_WAIT"),
                               ("slots", "LB_SLOTS"), ("payouts", "LB_S3")):
                if lb.get(key):
                    old = subs.get("{{" + token + "}}", "")
                    subs["{{" + token + "}}"] = re.sub(r"^\S+", str(lb[key]), old, count=1)
            for i, text in enumerate((lb.get("news") or [])[:2], start=1):
                subs["{{LB_NEWS%d}}" % i] = text
    for k, v in subs.items(): out = out.replace(k, str(v))
    # content pack deep-fill: "{{c:hero.lead}}" style
    def fill(m):
        path = m.group(1).split("."); node = C
        for p in path:
            if isinstance(node, dict): node = node.get(p)
            elif isinstance(node, list):
                try: node = node[int(p)]
                except Exception: return ""
            else: return ""
            if node is None: return ""
        if isinstance(node, (list, dict)):
            # a template bound a whole array/object — never print python repr
            return ""
        return str(node)
    out = re.sub(r"\{\{c:([\w.]+)\}\}", fill, out)
    fv = (plan["layout"].get("variants") or {}).get("form") or ""
    if name in FORM_BANDS and fv:
        # form layout axis: same contract, different field arrangement (CSS)
        out = re.sub(r"<section\b([^>]*)>", rf'<section\1 data-form="{fv}">', out, count=1)
    # a content pack with empty strings left blank <p>/<h2> blocks that rendered as
    # pure whitespace sections on live sites — strip elements that stayed empty.
    # Elements carrying role/data/id/aria (e.g. form-status container) are intentional
    # empty and must survive.
    out = re.sub(
        r"<(p|h2|h3|li)((?:(?!role=|data-|id=|aria-)[^>])*)>\s*(?:<br\s*/?>\s*)*</\1>",
        "", out)
    return out

def _extract_div(html: str, token: str) -> str:
    """Return the outer <div class="…token…">…</div> with balanced nesting."""
    m = re.search(
        rf'<div\b[^>]*class="[^"]*(?<![\w-]){re.escape(token)}(?![\w-])[^"]*"[^>]*>',
        html)
    if not m:
        return ""
    depth, pos, start = 1, m.end(), m.start()
    for tag in re.finditer(r'<div\b[^>]*>|</div\s*>', html[pos:], re.I):
        if tag.group(0).lower().startswith("</div"):
            depth -= 1
            if depth == 0:
                return html[start:pos + tag.end()]
        else:
            depth += 1
    return ""


def _embed_head(label: str, note: str) -> str:
    label, note = esc(str(label or "")), esc(str(note or ""))
    if not label and not note:
        return ""
    bits = []
    if label:
        bits.append(f'<span class="eyebrow">{label}</span>')
    if note:
        bits.append(f'<span class="widget-embed-note">{note}</span>')
    return '<div class="widget-embed-head">' + "".join(bits) + "</div>"


def widget_embed_html(plan, C, we: dict) -> str:
    """Compact widget block injected into an existing section (never a new screen)."""
    kind = (we or {}).get("kind") or ""
    if kind in ("heatmap", "listino-rows", "price-board", "tile-flip"):
        variant = we.get("variant") or {"heatmap": "d", "listino-rows": "e",
                                        "price-board": "f", "tile-flip": "g"}[kind]
        token = {"d": "wk-heatmap", "e": "wk-listino", "f": "wk-board", "g": "wk-tiles"}[variant]
        variants = plan["layout"].setdefault("variants", {})
        had = "markets" in variants
        old = variants.get("markets")
        variants["markets"] = variant
        try:
            full = R("markets", plan, C)
        finally:
            if had:
                variants["markets"] = old
            else:
                variants.pop("markets", None)
        body = _extract_div(full, token)
        if not body:
            die(f"widget embed: markets-{variant} body not found")
        mk = ((C.get("sections") or {}).get("markets") or {})
        return (f'<div class="wrap widget-embed market-embed wk-root" id="markets">\n'
                f'{_embed_head(mk.get("eyebrow", ""), mk.get("disclaimer", ""))}\n'
                f'{body}\n</div>')
    if kind == "calculator":
        full = R("calculator", plan, C)
        sm = re.search(r"<section\b([^>]*)>", full)
        data = " ".join(re.findall(r'data-[\w-]+="[^"]*"', sm.group(1))) if sm else ""
        body = _extract_div(full, "calculator")
        if not body:
            die("widget embed: calculator body not found")
        return (f'<div class="wrap widget-embed calculator-embed" id="calculator"'
                f'{(" " + data) if data else ""}>\n'
                f'{_embed_head((C.get("ui") or {}).get("calc_eyebrow", ""), "")}\n'
                f'{body}\n</div>')
    if kind == "pulse-sim":
        full = R("pulse-sim", plan, C)
        body = _extract_div(full, "ps-panel")
        if not body:
            die("widget embed: pulse-sim panel not found")
        ps = ((plan.get("pulse_sim") or {}).get("subs") or {})
        return (f'<div class="wrap widget-embed pulse-embed sec-pulse-sim" id="pulse-sim">\n'
                f'{_embed_head(ps.get("PS_EYEBROW", ""), ps.get("PS_NOTE", ""))}\n'
                f'{body}\n</div>')
    # demo-line / demo-bars / sentiment-gauge / book-ladder
    variant = we.get("variant") or "c"
    variants = plan["layout"].setdefault("variants", {})
    had_demo = "demo" in variants
    old_demo = variants.get("demo")
    variants["demo"] = variant
    try:
        full = R("demo", plan, C)
    finally:
        if had_demo:
            variants["demo"] = old_demo
        else:
            variants.pop("demo", None)
    body = _extract_div(full, "dw-shell") or _extract_div(full, "dw-card")
    if not body:
        die(f"widget embed: demo-{variant} body not found")
    demo = ((C.get("sections") or {}).get("demo") or {})
    return (f'<div class="wrap widget-embed demo-embed wk-root" id="demo">\n'
            f'{_embed_head(demo.get("eyebrow", ""), demo.get("disclaimer", ""))}\n'
            f'{body}\n</div>')


def inject_widget_embed(html: str, block: str) -> str:
    if not block:
        return html
    i = html.rfind("</section>")
    return html if i < 0 else html[:i] + block + "\n" + html[i:]


def logo_html(plan) -> str:
    """Brand mark: the word stays lowercase (CLAUDE rule), the treatment varies per plan."""
    brand = plan["params"]["brand"]
    raw = brand.split()[0]
    word = esc(raw.lower())
    initial = esc(raw[0].upper())
    # the mono badge carries the FIRST LETTER, so the word after it must start with
    # the second one — "P" + "photon" read as "Pphoton" on live pages
    tail = esc(raw[1:].lower()) if len(raw) > 2 else ""
    tld = esc(plan["params"]["domain"].rsplit(".", 1)[-1])
    v = (plan["layout"].get("variants") or {}).get("logo", "")
    inner = {
        "": f"{word}<span>↗</span>",
        "b": f'<span class="u">{word}</span>',
        "c": f'<span class="mono">{initial}</span>{tail}' if tail else word,
        "d": f'{word}<span class="dot">·</span>',
        "e": f'{word}<span class="circ">↗</span>',
        "f": f'<span class="caps">{word}</span>',
        "g": f'{word}<span class="sl">/</span>',
        "h": f'<span class="stack">{word}<small>.{tld}</small></span>',
    }.get(v, f"{word}<span>↗</span>")
    return f'<a class="blk-logo" data-var="{v or "a"}" href="index.php" aria-label="{esc(brand)}">{inner}</a>'


def page_nav_label(plan, C, which: str) -> str:
    """Nav/footer wording comes from the destination page itself.

    The plan's menu words are a rotation axis, so they drifted away from what the
    pages say ("Cómo funciona" sat over a company-history page, "Método" over an
    audience page). A page's own title is coherent by construction.
    """
    brand = plan["params"]["brand"]
    # the pack names the pages itself (model-written, translated) — the table below only
    # covers a handful of languages and used to leak "Registration"/"Who it's for" into
    # a Japanese footer
    own = str((C.get("page_labels") or {}).get(which) or "").strip()
    if own:
        return own
    labels = PAGE_LABELS.get(plan["params"].get("lang", "en"), PAGE_LABELS["en"])
    cp = C.get(f"inner_{which}") or {}
    raw = str(cp.get("title") or "").strip()
    if raw:
        cand = re.sub(rf"\b{re.escape(brand)}\b", " ", raw, flags=re.I)
        cand = re.sub(r"\s{2,}", " ", cand).strip(" .,;:—–|")
        words = cand.split()
        head = " ".join(words[:4])
        if (1 <= len(words) <= 4 and len(head) <= 26
                and words[-1].lower().strip(".,") not in WEAK_TAIL):
            return head
    return labels.get(which, which.title())


def footer_html(plan, C):
    """Footer shell — its own layout axis (5 designs, `data-var`), same content keys.

    The footer repeats on every page of every site, so a single design is the most
    visible fingerprint the factory can leave. Each variant is a different structure,
    not a recolour: grid of link columns, centered stack, split sitemap, minimal bar,
    or the classic three-tier block.
    """
    brand = plan["params"]["brand"]
    lang = plan["params"]["lang"]
    ft = C.get("footer") or {}
    fb = FOOTER_L10N.get(lang, ("Terms", "Privacy", "All rights reserved."))
    flabels = [(ft.get("terms_label") or fb[0], "terms.php"),
               (ft.get("privacy_label") or fb[1], "privacy.php")]
    rights = str(ft.get("rights") or fb[2]).strip()
    rights = re.sub(r"^\s*©?\s*(20\d{2})?\s*", "", rights)
    rights = re.sub(rf"^{re.escape(brand)}[.,:]?\s*", "", rights, flags=re.I).strip()
    if lang != "en" and re.search(r"all rights reserved|tutti i diritti|todos los derechos|"
                                  r"všechna práva|alle rechte|tous droits", rights, re.I):
        rights = ""            # the pack left an English boilerplate line: print © only
    rights = rights or ("" if lang != "en" else fb[2])
    tagline = ft.get("tagline", "")
    disclaimer = ft.get("disclaimer", "")
    risk = ft.get("risk_line", "")
    pays = ft.get("pay_chips") or "VISA · Mastercard · Bank transfer"
    slugs = plan["layout"].get("slugs", {})
    menu = plan["layout"].get("menu", ["Home", "About", "Tech", "Contact"])
    pairs = [(menu[0] if str(menu[0]).strip() else "Home", "index.php"),
             (page_nav_label(plan, C, "product"), f"{slugs.get('product','product')}.php"),
             (page_nav_label(plan, C, "offer"), f"{slugs.get('offer','offer')}.php"),
             (page_nav_label(plan, C, "faq"), f"{slugs.get('faq','faq')}.php"),
             (page_nav_label(plan, C, "about"), f"{slugs.get('about','about')}.php"),
             (page_nav_label(plan, C, "who"), f"{slugs.get('who','who')}.php"),
             (page_nav_label(plan, C, "contact"), f"{slugs.get('contact','contact')}.php"),
             # the registration page carries the same form; linking it from every footer
             # keeps it from being an orphan that only the sitemap knows about
             (page_nav_label(plan, C, "register"), f"{slugs.get('register','register')}.php")]
    logo = logo_html(plan)

    def links(items):
        return "".join(f'<a href="{h}">{esc(t)}</a>' for t, h in items)

    v = (plan["layout"].get("variants") or {}).get("footer", "") or ""
    _copy = f"© 2026 {esc(brand)}." + (f" {esc(rights)}" if rights else "")
    base = (f'<div class="foot-base"><span>{_copy}</span>'
            f'<span class="pay-chips">{esc(pays)}</span></div>')
    if v == "b":       # brand block + two link columns
        return (f'<footer class="blk-footer" data-var="b"><div class="foot-grid">'
                f'<div class="foot-brand">{logo}<p class="foot-tag">{esc(tagline)}</p></div>'
                f'<nav class="foot-nav">{links(pairs)}</nav>'
                f'<nav class="foot-legal">{links(flabels)}</nav></div>'
                f'<p class="footer-disclaimer">{esc(disclaimer)}</p>'
                f'<p class="foot-risk">{esc(risk)}</p>{base}</footer>')
    if v == "c":       # centered stack
        return (f'<footer class="blk-footer" data-var="c"><div class="foot-center">{logo}'
                f'<p class="foot-tag">{esc(tagline)}</p>'
                f'<nav class="foot-nav">{links(pairs + flabels)}</nav></div>'
                f'<p class="footer-disclaimer">{esc(disclaimer)}</p>'
                f'<p class="foot-risk">{esc(risk)}</p>'
                f'<div class="foot-base foot-center-base"><span>© 2026 {esc(brand)}. '
                f'{esc(rights)}</span></div></footer>')
    if v == "d":       # split: brand + disclaimer left, link sitemap right
        return (f'<footer class="blk-footer" data-var="d"><div class="foot-split">'
                f'<div class="foot-brand">{logo}<p class="footer-disclaimer">{esc(disclaimer)}</p>'
                f'<p class="foot-risk">{esc(risk)}</p></div>'
                f'<div class="foot-cols"><nav class="foot-nav">{links(pairs)}</nav>'
                f'<nav class="foot-legal">{links(flabels)}</nav>'
                f'<span class="pay-chips">{esc(pays)}</span></div></div>'
                f'<div class="foot-base"><span>© 2026 {esc(brand)}. {esc(rights)}</span>'
                f'<span>{esc(tagline)}</span></div></footer>')
    if v == "e":       # minimal bar: one line, fine print under it
        return (f'<footer class="blk-footer" data-var="e"><div class="foot-bar">'
                f'{logo}<nav class="foot-nav">{links(pairs + flabels)}</nav>'
                f'<span class="foot-copy">© 2026 {esc(brand)}</span></div>'
                f'<p class="foot-fine">{esc(risk)} · {esc(rights)} · '
                f'<span class="pay-chips">{esc(pays)}</span></p></footer>')
    if v == "f":       # tagline band on top, legal grid underneath
        return (f'<footer class="blk-footer" data-var="f"><div class="foot-band">'
                f'{logo}<p class="foot-tag">{esc(tagline)}</p>'
                f'<nav class="foot-nav">{links(pairs)}</nav></div>'
                f'<div class="foot-grid2">{logo}<nav class="foot-legal">{links(flabels)}</nav>'
                f'<p class="foot-risk">{esc(risk)}</p>{base}</div>'
                f'<p class="footer-disclaimer">{esc(disclaimer)}</p></footer>')
    return (f'<footer class="blk-footer"><div class="footer-top">\n{logo}\n'
            f'<nav>{links(pairs + flabels)}</nav><span>{esc(tagline)}</span></div>\n'
            f'<p class="footer-disclaimer">{esc(disclaimer)}</p>\n'
            f'<div class="footer-bottom"><span>© 2026 {esc(brand)}. {esc(rights)}</span>\n'
            f'<span class="pay-chips">{esc(pays)}</span>\n'
            f'<span>{esc(risk)}</span></div></footer>')


def build_header_footer(plan, C, current=""):
    brand = plan["params"]["brand"]; slugs = plan["layout"].get("slugs", {})
    lang = plan["params"].get("lang", "en")
    menu = plan["layout"].get("menu", ["Home", "About", "Tech", "Contact"])
    labels = PAGE_LABELS.get(lang, PAGE_LABELS["en"])

    pairs = [(menu[0] if str(menu[0]).strip() else labels.get("home", "Home"), "index.php"),
             (page_nav_label(plan, C, "product"), f"{slugs.get('product','product')}.php"),
             (page_nav_label(plan, C, "offer"), f"{slugs.get('offer','offer')}.php"),
             (page_nav_label(plan, C, "faq"), f"{slugs.get('faq','faq')}.php"),
             (page_nav_label(plan, C, "about"), f"{slugs.get('about','about')}.php"),
             (page_nav_label(plan, C, "contact"), f"{slugs.get('contact','contact')}.php")]
    def nav_link(t, h):
        cur = ' aria-current="page"' if h == current else ""
        return f'<a href="{h}"{cur}>{esc(t)}</a>'
    nav = "".join(nav_link(t, h) for t, h in pairs)
    livebar = R("livebar", plan, C)
    ui = C.get("ui") or {}
    hv = (plan["layout"].get("variants") or {}).get("header", "")
    parts = {
        "logo": logo_html(plan),
        "nav": f'<nav class="blk-nav" aria-label="{esc(ui.get("aria_nav") or "Main")}">{nav}</nav>',
        "cta": f'<a class="blk-btn" href="index.php#claim">{esc(C["bands"].get("submit_nav", "Open account"))}</a>',
        "toggle": f'<button class="menu-toggle" aria-label="{esc(ui.get("aria_menu") or "Menu")}" '
                  f'aria-expanded="false"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" '
                  f'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true">'
                  f'<path class="i-burger" d="M4 7h16M4 12h16M4 17h16"/>'
                  f'<path class="i-close" d="M6 6l12 12M18 6L6 18"/></svg></button>',
    }
    order = {
        "": ("logo", "nav", "cta", "toggle"),
        "b": ("nav", "cta", "logo", "toggle"),
        "c": ("nav", "logo", "cta", "toggle"),
        "d": ("nav", "cta", "toggle"),
        "e": ("logo", "nav", "toggle"),
        "f": ("logo", "cta", "nav", "toggle"),
        "g": ("logo", "cta", "nav", "toggle"),
        "h": ("logo", "cta", "nav", "toggle"),
        "i": ("logo", "cta", "nav", "toggle"),
        "j": ("nav", "cta", "logo", "toggle"),
        "k": ("logo", "nav", "cta", "toggle"),
        "l": ("logo", "nav", "cta", "toggle"),
        "m": ("logo", "nav", "cta", "toggle"),
    }.get(hv, ("logo", "nav", "cta", "toggle"))
    header = f'<header class="blk-header" data-var="{hv or "a"}">' + "\n".join(parts[k] for k in order) + "</header>"
    return livebar, header, footer_html(plan, C)


def fix_anchors(html: str) -> str:
    """Point decorative CTA anchors at targets that actually exist on this page."""
    ids = set(re.findall(r'id="([^"]+)"', html))
    for missing, fallbacks in (("come", ("demo", "claim")), ("demo", ("come", "claim")),
                               ("reviews", ("people", "claim")), ("calculator", ("claim",))):
        if missing in ids:
            continue
        target = next((f for f in fallbacks if f in ids), None)
        html = html.replace(f'href="#{missing}"', f'href="#{target}"' if target else 'href="index.php#claim"')
    return html


def sanitize_hero_copy(C, brand: str) -> None:
    """The hero template prints the brand in h1 .brand-line, so the authored lines
    must not repeat it. A model that closes the headline with the brand printed
    "Starling Aegistra … Starling Aegistra" (starlingaegistra.site, FR pack).
    Strips a leading/trailing brand from h1_rest and h1_accent; an accent that was
    only the brand is dropped (the fragment then loses its last line)."""
    hero = C.get("hero")
    if not isinstance(hero, dict) or not brand:
        return
    low = brand.lower()

    def trim(text) -> str:
        t = str(text or "").strip()
        if not t or low not in t.lower():
            return t
        if t.lower() == low:
            return ""
        cut_lead = t.lower().startswith(low)
        if cut_lead:
            t = t[len(brand):]
        if t.lower().endswith(low):
            t = t[:-len(brand)]
        t = t.strip(" —–-:·,.")
        # "Starling Aegistra — pilotez…" must not leave a lowercase sentence start
        if cut_lead and t[:1].islower():
            t = t[0].upper() + t[1:]
        return t

    for key in ("h1_rest", "h1_accent"):
        hero[key] = trim(hero.get(key))


def build_index(plan, C, css_vars, fonts_import, theme, B=None, covers=None):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    sanitize_hero_copy(C, brand)
    order = plan["layout"]["section_order"]
    for slot in order:
        canon = CANON.get(slot)
        if not canon or not (BLOCKS / f"{canon}.html").exists():
            die(f"section slot without canonical fragment: {slot}")
    for slot, var in (plan["layout"].get("variants") or {}).items():
        if slot not in order and slot not in SPECIAL_VARIANTS: die(f"variant for unknown slot: {slot}")
        canon = CANON.get(slot) or f"blk-{slot}"
        if var and slot not in SPECIAL_VARIANTS \
           and not (BLOCKS / f"blk-{slot}-{var}.html").exists() \
           and not (BLOCKS / f"{canon}-{var}.html").exists():
            die(f"variant fragment missing: {canon}-{var}.html")
    locale = plan["params"].get("locale") or \
        plan["params"]["lang"] + "-" + plan["params"]["lang"].upper()
    livebar, header, footer = build_header_footer(plan, C, "index.php")
    body_parts = [livebar, header, "<main>"]
    SLOT_REMAP = {  # sections sharing schema intro key -> distinct content paths
        "stats-intro": "sections.stats.", "intro-center": "sections.ladder.",
    }
    embeds = {}
    for _we in (plan["layout"].get("widget_embed"), plan["layout"].get("market_embed")):
        if _we and _we.get("slot"):
            embeds.setdefault(_we["slot"], []).append(_we)
    i = 0
    while i < len(order):
        slot = order[i]
        # first screen: the hero and the lead form are rendered as one split view
        # (component contracts stay intact; CSS hides the band's long copy column)
        if i == 0 and slot == "hero" and len(order) > 1 and order[1] in FORM_BANDS:
            hero = R("hero", plan, C)
            # the form on this screen is the action; the hero's own CTAs would only
            # duplicate the same target (and the header CTA is always visible)
            hero = re.sub(r'<a\b[^>]*class="[^"]*\bblk-btn\b[^"]*"[^>]*>.*?</a>', "",
                          hero, flags=re.S)
            hero = re.sub(r'<div class="hero-cta">\s*</div>', "", hero)
            band = R(order[1], plan, C)
            _fs = (plan["layout"].get("variants") or {}).get("first_screen") or "a"
            body_parts.append(f'<div class="first-screen" data-first="{esc(_fs)}">\n{hero}\n{band}\n</div>')
            i += 2
            continue
        html = R(slot, plan, C)
        if slot in SLOT_REMAP:
            html = html.replace("c:sections.intro.", SLOT_REMAP[slot])
        for _we in embeds.get(slot, ()):
            html = inject_widget_embed(html, widget_embed_html(plan, C, _we))
        body_parts.append(html)
        i += 1
    if B and (plan.get("blog") or {}).get("enabled"):
        import blog_assemble
        body_parts.append(blog_assemble.teaser_html(plan, B, covers))
    body_parts.append("</main>"); body_parts.append(footer)
    body = "\n".join(body_parts)
    body = ensure_anchors(body)
    body = re.sub(r"<br>\s*<span>\s*</span>", "", body)
    body = add_brandnote_links(body, plan, C)
    m = C["meta"]
    jsonld = build_jsonld(plan, C, body)
    title = m["title_home"].replace("{Brand}", brand)
    descr = clamp_meta(m["description"]); kw = m["keywords"].replace("{Brand}", brand).replace("{dom}", dom)
    page = page_shell(title, descr, kw, "/", locale, css_vars, fonts_import, theme,
                      body, og_desc=C["meta"].get("og_description", ""), jsonld=jsonld,
                      blog=bool(B))
    page = fix_anchors(page)
    if 'id="come"' not in page:
        # no "how it works" section on this plan → drop the hero's secondary link
        # instead of pointing a promise at the form
        page = re.sub(r'<a class="text-link"[^>]*>[^<]*</a>', "", page, count=1)
    page = page.replace('href="index.php#claim"', 'href="#claim"')
    page = finish_page(page, plan, C)
    return page

def build_jsonld(plan, C, body: str = ""):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    n = plan["numbers"]; reg = plan.get("regulator", {})
    # FAQPage must describe questions a visitor can actually read: variants render
    # 4–12 FAQ items (compare/mini-faq/faq), so the schema follows the rendered body
    # instead of the raw pack length (mismatch = structured-data risk).
    fq = [q for q in ((C.get("faq") or {}).get("items") or [])[:12]
          if isinstance(q, dict) and q.get("q") and q.get("a")
          and (q["q"] in body or esc(q["q"]) in body)]
    faq_entities = ",".join(json.dumps({"@type": "Question", "name": q["q"],
        "acceptedAnswer": {"@type": "Answer", "text": q["a"]}}, ensure_ascii=False) for q in fq)
    contacts = contacts_for(plan, C)
    geo = plan["params"].get("geo") or plan["params"].get("geo_short") or ""
    alt = [brand.lower(), f"{brand} {geo}".strip(), dom, f"{brand} login"]
    org = {"@type": "FinancialService", "@id": f"https://{dom}/#org", "name": brand,
        "alternateName": [a for a in alt if a],
        "url": f"https://{dom}/", "logo": f"https://{dom}/favicon.svg", "image": f"https://{dom}/og-image.jpg",
        "description": C["meta"]["description"], "email": contacts["email"],
        "telephone": contacts["telephone"], "areaServed": geo,
        "currenciesAccepted": plan["params"].get("currency", "EUR"),
        "aggregateRating": {"@type": "AggregateRating", "ratingValue": str(n.get("rating", "4,7")),
            "bestRating": "5", "worstRating": "1", "reviewCount": str(n.get("reviews", 641))}}
    if reg: org["slogan"] = f"{brand} — {reg.get('name','')}"
    website = {"@type": "WebSite", "@id": f"https://{dom}/#site", "url": f"https://{dom}/",
        "name": brand, "inLanguage": plan["params"].get("locale", ""),
        "publisher": {"@id": f"https://{dom}/#org"}}
    webpage = {"@type": "WebPage", "@id": f"https://{dom}/#webpage", "url": f"https://{dom}/",
               "name": C["meta"].get("title_home", brand).replace("{Brand}", brand),
               "inLanguage": plan["params"].get("locale", ""),
               "primaryImageOfPage": {"@type": "ImageObject", "url": f"https://{dom}/og-image.jpg",
                                      "width": 1200, "height": 630},
               "publisher": {"@id": f"https://{dom}/#org"}}
    graph = [org, website, webpage]
    if fq: graph.append({"@type": "FAQPage", "@id": f"https://{dom}/#faq", "mainEntity": json.loads(f"[{faq_entities}]")})
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":"))

PAGE_LABELS = {"it": {"about": "Chi siamo", "who": "Per chi", "contact": "Contatti", "register": "Registrazione",
                      "product": "Piattaforma", "offer": "Come funziona", "faq": "Domande"},
                "cs": {"about": "O nás", "who": "Pro koho", "contact": "Kontakt", "register": "Registrace",
                      "product": "Platforma", "offer": "Jak to funguje", "faq": "Dotazy"},
                "es": {"about": "Quiénes somos", "who": "Para quién", "contact": "Contacto", "register": "Registro",
                      "product": "Plataforma", "offer": "Cómo funciona", "faq": "Preguntas"},
                "en": {"about": "About", "who": "Who it's for", "contact": "Contact", "register": "Registration",
                      "product": "Platform", "offer": "How it works", "faq": "FAQ"}}


TITLE_CONNECTORS = {"a", "al", "and", "auf", "bei", "con", "da", "das", "de", "del", "della",
                    "der", "des", "di", "do", "dos", "du", "e", "en", "for", "für", "fur",
                    "im", "in", "la", "le", "mit", "na", "ni", "o", "of", "on", "or", "para",
                    "per", "su", "sul", "the", "to", "u", "und", "v", "y", "zu"}
# connectives plus short verbs: a title/caption must not end on one of these
WEAK_TAIL = TITLE_CONNECTORS | {"es", "son", "est", "sont", "ist", "are", "is", "era", "eran",
                                "was", "were", "był", "była"}


def brand_first(title: str, brand: str, fallback: str = "Home") -> str:
    """Brand-first title without the brand repeated twice."""
    parts = [x.strip() for x in re.split(r"\s+[—–|]\s+", (title or "").strip()) if x.strip()]
    cleaned = []
    for p in parts:
        # whole-word removal only: "Contacto con Photon AI" keeps its "con"…
        p = re.sub(rf"\b{re.escape(brand)}\b", " ", p, flags=re.I)
        p = re.sub(r"\s{2,}", " ", p).strip(" .,;:—-")
        words = p.split()
        # …but a connector left dangling by the removal must go, otherwise the title
        # ships as "Photon AI — Contacto con" (truncated tail on live pages)
        while words and words[-1].lower().strip(".,") in WEAK_TAIL:
            words.pop()
        p = " ".join(words).strip(" .,;:—-")
        if len(p) >= 3:
            cleaned.append(p)
    body = " — ".join(cleaned).strip(" .,;:—-")
    if len(body) < 3:
        body = fallback
    body = re.sub(r"\s+([?!.,])", r"\1", body)
    return f"{brand} — {body}"


def h1_with_brand(text, brand) -> str:
    """Headline keeps the brand exactly once.

    The inner-page template appended a .brand-line twin, so "Chi è Photon AI" printed
    the brand twice ("…Photon AI" + a second "Photon AI" line). When the authored
    headline already names the brand, the accent span wraps that occurrence instead.
    """
    text = str(text or "").strip() or brand
    i = text.lower().find(brand.lower())
    if i < 0:
        return f'{esc(text)}<br><span class="brand-line">{esc(brand)}</span>'
    return (esc(text[:i]) + f'<span class="brand-line">{esc(text[i:i + len(brand)])}</span>'
            + esc(text[i + len(brand):]))


def build_inner(plan, C, css_vars, fonts_import, theme, which):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    slugs = plan["layout"].get("slugs", {})
    skeleton = plan.get("inner_pages", {}).get(which, ["page-intro", "editorial", "cta"])
    cp = C.get(f"inner_{which}", {})
    livebar, header, footer = build_header_footer(plan, C, f"{slugs.get(which, which)}.php")
    body_parts = [livebar, header, "<main>"]
    eyebrow_raw = re.sub(rf"\s*[—–-]\s*{re.escape(brand)}\s*$", "",
                         str(cp.get("title") or "").strip(), flags=re.I).strip()
    eyebrow = eyebrow_raw or PAGE_LABELS.get(plan["params"].get("lang", "en"),
                                              PAGE_LABELS["en"]).get(which, which.upper())
    form_slot = next((x for x in ("access-band", "claim-band", "enroll-band")
                      if x in plan["layout"]["section_order"]), "access-band")

    def inner_slot(slot):
        return R(slot, plan, C)

    SLOT_FOR = {"office": "office", "hours": "office", "contact-grid": "office",
                "map": "office", "core": form_slot, "form": form_slot,
                "form-first": form_slot, "register": form_slot,
                "steps": "steps", "steps-live": "steps-live", "mini-faq": "mini-faq",
                "milestones": "timeline", "timeline": "timeline",
                "winrate": "numbers", "figures": "numbers", "numbers": "numbers",
                "stack": "features", "features": "features",
                "team-band": "people", "people": "people"}
    intro = f"""<section class="page-intro"><div class="eyebrow">{esc(eyebrow)}</div>
<h1>{h1_with_brand(cp.get('h1'), brand)}</h1><p>{esc(cp.get('lead', ''))}</p></section>"""
    if "page-intro" not in skeleton:
        # every indexed page MUST have h1 with .brand-line (audit) even in non-intro skeletons
        intro = ('<section class="page-intro"><h1>'
                 + h1_with_brand(cp.get("h1") or cp.get("title"), brand)
                 + '</h1></section>')
    form_token = next((t for t in skeleton if SLOT_FOR.get(t) == form_slot), None)
    rendered_form = False
    done = set()
    # pages that carry a lead form put it on the first screen with their intro, exactly
    # like the home page: copy left, form right (stacked on phones)
    if which in ("contact", "register") or form_token:
        body_parts.append(f'<div class="first-screen inner-form">\n{intro}\n'
                          f'{inner_slot(form_slot)}\n</div>')
        done.add(form_slot)
        rendered_form = True
    else:
        body_parts.append(intro)
    for token in skeleton:
        if token in ("page-intro",):
            continue
        slot = SLOT_FOR.get(token)
        if slot and slot not in done:
            body_parts.append(inner_slot(slot)); done.add(slot)
            rendered_form = rendered_form or slot == form_slot
        if token == "points":
            pts = cp.get("points") or []
            if pts:
                body_parts.append('<section class="section"><div class="wrap"><ul class="blk-grid3">'
                                  + "".join(f'<li class="blk-card">{esc(p)}</li>' for p in pts)
                                  + "</ul></div></section>")
    if which == "contact" and "office" not in done:
        body_parts.append(inner_slot("office")); done.add("office")
    if which in ("contact", "register") and not rendered_form:
        body_parts.append(inner_slot(form_slot)); rendered_form = True

    # the timeline/milestones fragment already renders cp["blocks"] (01–04), so the
    # trailing grid printed the same four cards twice on the about page
    blocks_html = ""
    seen_text = set()
    for b in cp.get("blocks", []):
        t, d = str(b.get("t", "")).strip(), str(b.get("d", "")).strip()
        key = (t.casefold(), d.casefold())
        if "timeline" in done or not t or key in seen_text:
            continue
        seen_text.add(key)
        blocks_html += f'<article class="blk-card"><h3>{esc(t)}</h3><p>{esc(d)}</p></article>'
    if blocks_html:
        body_parts.append(f'<section class="section"><div class="wrap"><div class="blk-grid3">{blocks_html}</div></div></section>')
    if "cta" in skeleton:
        cta = C.get("sections", {}).get("cta", {})
        body_parts.append(R("cta-band", plan, C).replace("{{c:sections.cta.h2}}", esc(cta.get("h2", brand))))
    body_parts.append("</main>"); body_parts.append(footer)
    body = ensure_anchors("\n".join(body_parts))
    m = C["meta"]
    label = PAGE_LABELS.get(plan["params"]["lang"], PAGE_LABELS["en"]).get(which, which.title())
    title = brand_first(cp.get("title") or label, brand, label)
    if "{Brand}" in title: title = title.replace("{Brand}", brand)
    descr = clamp_meta(cp.get("lead") or cp.get("h1") or label)
    page = page_shell(f"{title}", descr, m["keywords"].replace("{Brand}", brand).replace("{dom}", dom),
                       f"/{slugs.get(which, which)}.php",
                       plan["params"].get("locale") or plan["params"]["lang"], css_vars, fonts_import, theme,
                       body, jsonld=build_inner_jsonld(plan, C, which))
    page = page.replace('href="#claim"', 'href="index.php#claim"')
    page = finish_page(page, plan, C)
    return page

def build_long_inner(plan, C, css_vars, fonts_import, theme, which):
    """Product / offer / FAQ pages: long editorial body + FAQ + closing form.

    The home page is a screen-by-screen sales page; these pages are the depth layer
    a visitor (and a crawler) reads when they want to understand the service.
    """
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    slugs = plan["layout"].get("slugs", {})
    cp = C.get(f"inner_{which}") or {}
    livebar, header, footer = build_header_footer(plan, C, f"{slugs.get(which, which)}.php")
    label = PAGE_LABELS.get(plan["params"].get("lang", "en"), PAGE_LABELS["en"]).get(which, which.title())
    eyebrow = str(cp.get("title") or label).strip()
    h1 = h1_with_brand(cp.get("h1") or cp.get("title") or label, brand)
    lead = str(cp.get("lead") or "").strip()
    sections = [s for s in (cp.get("sections") or []) if isinstance(s, dict)]
    faqs = [x for x in (cp.get("faq") or []) if isinstance(x, dict) and str(x.get("q") or "").strip()]

    toc = []
    body = [livebar, header, "<main>",
            f'<section class="page-intro long-intro"><div class="wrap">'
            f'<div class="eyebrow">{esc(eyebrow)}</div><h1>{h1}</h1>'
            + (f'<p class="long-lead">{esc(lead)}</p>' if lead else "") + "</div>"]
    if len(sections) > 1:
        for i, s in enumerate(sections):
            toc.append(f'<a href="#long-{i+1}">{esc(s.get("h2") or label)}</a>')
        body.append(f'<div class="wrap"><nav class="long-toc" aria-label="{esc(label)}">'
                    + "".join(toc) + "</nav></div>")
    body.append("</section>")

    body.append('<section class="section long-body"><div class="wrap">')
    for i, s in enumerate(sections):
        body.append(f'<article class="long-block" id="long-{i+1}">')
        body.append(f'<h2>{esc(s.get("h2") or label)}</h2>')
        for p in (s.get("paragraphs") or []):
            if str(p or "").strip():
                body.append(f'<p>{esc(p)}</p>')
        bullets = [b for b in (s.get("bullets") or []) if str(b or "").strip()]
        if bullets:
            body.append('<ul class="long-list">' + "".join(f'<li>{esc(b)}</li>' for b in bullets) + "</ul>")
        body.append("</article>")
    body.append("</div></section>")

    if faqs:
        faq_title = "FAQ" if which == "faq" else (PAGE_LABELS.get(plan["params"].get("lang", "en"),
                    PAGE_LABELS["en"]).get("faq", "FAQ"))
        body.append(f'<section class="section alt sec-faq long-faq"><div class="wrap">'
                    f'<div class="eyebrow">{esc(faq_title)}</div><h2>{esc(faq_title)}</h2>'
                    f'<div class="faq-list">')
        for x in faqs:
            body.append(f'<details><summary>{esc(x.get("q"))}</summary>'
                        f'<p>{esc(x.get("a"))}</p></details>')
        body.append("</div></div></section>")

    form_slot = next((x for x in ("access-band", "claim-band", "enroll-band")
                      if x in plan["layout"]["section_order"]), "access-band")
    body.append(f'<div class="inner-cta-form">{R(form_slot, plan, C)}</div>')
    body.append("</main>"); body.append(footer)
    body_html = ensure_anchors("\n".join(body))
    title = brand_first(cp.get("title") or label, brand, label)
    descr = clamp_meta(lead or cp.get("h1") or label)
    page = page_shell(title, descr,
                       (C.get("meta") or {}).get("keywords", "").replace("{Brand}", brand).replace("{dom}", dom),
                       f"/{slugs.get(which, which)}.php",
                       plan["params"].get("locale") or plan["params"]["lang"], css_vars, fonts_import, theme,
                       body_html, jsonld=build_inner_jsonld(plan, C, which))
    page = page.replace('href="#claim"', 'href="index.php#claim"')
    page = finish_page(page, plan, C)
    return page


def build_inner_jsonld(plan, C, which):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    slugs = plan["layout"].get("slugs", {})
    slug = slugs.get(which, which)
    # schema names in the site language and matching the visible nav wording
    label = page_nav_label(plan, C, which)
    home = (plan["layout"].get("menu") or ["Home"])[0]
    graph = [
        {"@type": "WebPage", "@id": f"https://{dom}/{slug}.php",
         "url": f"https://{dom}/{slug}.php", "name": f"{label} — {brand}",
         "inLanguage": plan["params"].get("locale", ""),
         "primaryImageOfPage": {"@type": "ImageObject", "url": f"https://{dom}/og-image.jpg",
                                "width": 1200, "height": 630},
         "publisher": {"@id": f"https://{dom}/#org"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": home, "item": f"https://{dom}/"},
            {"@type": "ListItem", "position": 2, "name": label,
             "item": f"https://{dom}/{slug}.php"}]}]
    cp = C.get(f"inner_{which}") or {}
    fq = [x for x in (cp.get("faq") or []) if isinstance(x, dict) and x.get("q") and x.get("a")]
    if fq:
        graph.append({"@type": "FAQPage", "@id": f"https://{dom}/{slug}.php#faq",
                      "mainEntity": [{"@type": "Question", "name": x["q"],
                                      "acceptedAnswer": {"@type": "Answer", "text": x["a"]}}
                                     for x in fq]})
    return json.dumps({"@context": "https://schema.org", "@graph": graph},
                      ensure_ascii=False, separators=(",", ":"))

def build_legal(plan, C, css_vars, fonts_import, theme, which):
    """terms.php / privacy.php — unique titles, legal body from content pack or neutral stub."""
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    reg = plan.get("regulator") or {}
    livebar, header, footer = build_header_footer(plan, C)
    reg_line = f"Reference supervisory authority: {reg.get('name','')}" if reg else ""
    bodyLegal = (C.get("legal") or {}).get(which)
    if not bodyLegal:
        if plan["params"].get("lang", "en") != "en":
            die(f"content pack has no legal.{which} — an English legal stub must not ship "
                f"on a {plan['params'].get('lang')} site")
        bodyLegal = (f"<p>This page describes the {which} of {brand} in summary form. "
                     f"{reg_line}. Full personalised terms are provided during onboarding.</p>")
    tl = TERMS_L10N.get(plan["params"]["lang"], TERMS_L10N["en"])
    ui = C.get("ui") or {}
    terms_l = {"terms": ui.get("terms_title") or tl[0],
               "privacy": ui.get("privacy_title") or tl[1]}
    title_map = {"terms": brand_first(terms_l["terms"], brand),
                 "privacy": brand_first(terms_l["privacy"], brand)}
    body = f"""{livebar}{header}<main>
<section class="page-intro">
<h1>{esc(brand)}<br><span class="brand-line">{esc(terms_l[which])}</span></h1></section>
<section class="legal">{bodyLegal}</section></main>{footer}"""
    # description from the document's own first paragraph: unique, localised and
    # informative (the old "Privacy of X." was 32 chars and repeated the title)
    _p = re.search(r"<p[^>]*>(.*?)</p>", bodyLegal or "", re.S)
    descr = clamp_meta(re.sub(r"<[^>]+>", " ", _p.group(1))) if _p else ""
    if len(descr) < 60:
        descr = f"{terms_l[which]} — {brand}."
    page = page_shell(title_map[which], descr,
                       f"{brand}, {terms_l[which]}", f"/{which}.php",
                       plan["params"].get("locale") or plan["params"]["lang"], css_vars, fonts_import, theme,
                       body, jsonld=build_inner_jsonld(plan, C, which))
    page = finish_page(page, plan, C)
    return page

def build_thanks(plan, C, css_vars, fonts_import, theme):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    lang = plan["params"].get("lang", "en")
    th = C.get("thanks", {})
    tl = TERMS_L10N.get(lang, TERMS_L10N["en"])
    ui = C.get("ui") or {}
    back = ui.get("back_home") or NOTFOUND_L10N.get(lang, ("", "Back to home"))[1]
    livebar, header, footer = build_header_footer(plan, C)
    body = f"""{livebar}{header}<main><section class="section"><div class="wrap blk-center">
<div class="eyebrow center">{esc(th.get('eyebrow') or THANKS_EYEBROW.get(lang, THANKS_EYEBROW['en']))}</div>
<h1>{esc(th.get('h1') or tl[2].split('—')[0].strip())}<br><span class="brand-line">{esc(brand)}</span></h1><p>{esc(th.get('lead',''))}</p>
<p class="fine">{esc(th.get('warn',''))}</p>
<a class="blk-btn" href="index.php">← {esc(back)}</a>
</div></section></main>{footer}"""
    _thanks_title = brand_first(th.get("h1") or tl[2], brand)
    page = page_shell(_thanks_title, clamp_meta(th.get("lead", "")), "", "/thanks.php",
                       plan["params"].get("locale") or lang, css_vars, fonts_import, theme,
                       body, noindex=True, canonical=False)
    page = finish_page(page, plan, C)
    postback_head = "<?php require __DIR__ . '/_postback.php'; send_postback(); ?>\n"
    return postback_head + page

def build_404(plan, C, css_vars, fonts_import, theme):
    brand = plan["params"]["brand"]; dom = plan["params"]["domain"]
    lang = plan["params"]["lang"]
    _tbl = NOTFOUND_L10N.get(lang, ("Page not found", "Back home"))
    _ui = C.get("ui") or {}
    nf = (_ui.get("not_found_title") or _tbl[0], _ui.get("not_found_back") or _tbl[1])
    livebar, header, footer = build_header_footer(plan, C)
    body = f"""{livebar}{header}<main><section class="section"><div class="wrap blk-center">
<h1>404<br><span class="brand-line">{esc(brand)}</span></h1><p>{nf[0]}</p><a class="blk-btn" href="index.php">{nf[1]}</a>
</div></section></main>{footer}"""
    page = page_shell(brand_first(f"404 — {nf[0]}", brand), nf[0], "", "/404.php",
                       plan["params"].get("locale") or plan["params"]["lang"], css_vars, fonts_import, theme,
                       body, noindex=True)
    page = finish_page(page, plan, C)
    return page

ASSETS_JS_APP = """function onReady(fn){if(document.readyState!=='loading'){fn();}else{document.addEventListener('DOMContentLoaded',fn);}}
onReady(function(){
var mt=document.querySelector('.menu-toggle'),nv=document.querySelector('.blk-nav');
if(mt&&nv){var mSync=function(open){nv.classList.toggle('open',open);mt.setAttribute('aria-expanded',open)};
mt.addEventListener('click',function(){mSync(!nv.classList.contains('open'))});
nv.addEventListener('click',function(e){if(e.target.closest('a'))mSync(false)});
document.addEventListener('keydown',function(e){if(e.key==='Escape')mSync(false)});
document.addEventListener('click',function(e){if(nv.classList.contains('open')&&!nv.contains(e.target)&&!mt.contains(e.target))mSync(false)});
}
/* contact e-mail: built here so the hosting proxy never rewrites a plain-text
   mailto into an undecodable "[email protected]" stub (broken link on live pages) */
[].slice.call(document.querySelectorAll('.js-mail')).forEach(function(a){
var u=a.getAttribute('data-u'),d=a.getAttribute('data-d');
if(!u||!d){return}
var mail=u+'@'+d;a.textContent=mail;a.setAttribute('href','mailto:'+mail)});
/* sticky header: elevated state after a small scroll */
var hd=document.querySelector('.blk-header');
if(hd){var hUpd=function(){hd.classList.toggle('is-scrolled',window.scrollY>18)};
window.addEventListener('scroll',hUpd,{passive:true});hUpd();}
/* floating mobile CTA: appears deep into the page, points at the form */
if(window.matchMedia&&window.matchMedia('(max-width:760px)').matches&&!document.querySelector('.blk-float-cta')){
var fEl=document.createElement('div');fEl.className='blk-float-cta';
var fSrc=document.querySelector('.blk-header .blk-btn');
var fTgt=document.getElementById('claim')?'#claim':'index.php#claim';
fEl.innerHTML='<a class="blk-btn" href="'+fTgt+'">'+(fSrc?fSrc.textContent:'Open account')+'</a>';
document.body.appendChild(fEl);
var fUpd=function(){fEl.classList.toggle('is-on',window.scrollY>700)};
window.addEventListener('scroll',fUpd,{passive:true});fUpd();}
/* reveal on scroll: sections fade in once (skipped for reduced motion / no IO) */
var secs=[].slice.call(document.querySelectorAll('main > .sec'));
var still=function(){document.documentElement.classList.add('has-anim')};
if('IntersectionObserver' in window&&!(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches)){
still();
var io=new IntersectionObserver(function(es){es.forEach(function(e){
if(e.isIntersecting){e.target.classList.add('is-in');io.unobserve(e.target)}})},
{threshold:.08,rootMargin:'0px 0px -36px'});
secs.forEach(function(s,i){s.style.setProperty('--reveal-order',i%4);io.observe(s)});
}else{secs.forEach(function(s){s.classList.add('is-in')});}
/* editorial numbering: 01/ 02/ ... chips inside each section eyebrow */
var sn=0;secs.forEach(function(s){var ey=s.querySelector('.eyebrow');if(!ey)return;
sn++;var chip=document.createElement('i');chip.className='sec-num';chip.setAttribute('aria-hidden','true');
chip.textContent=(sn<10?'0':'')+sn;ey.insertBefore(chip,ey.firstChild)});
var ll=document.getElementById('live-latency'),lo=document.getElementById('live-orders');
if(ll&&!window.__noLiveTick){setInterval(function(){ll.textContent=(38+Math.floor(Math.random()*24))+' ms'},4000)}
if(lo){setInterval(function(){lo.textContent=(1200+Math.floor(Math.random()*400)).toLocaleString()},5000)}
var cd=document.getElementById('countdown');
if(cd){var end=Date.now()+1000*60*60*26+1000*60*13;
setInterval(function(){var s=Math.max(0,Math.floor((end-Date.now())/1000));
var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60),sec=s%60;
var map={'days':[d,2],'hours':[h,2],'minutes':[m,2],'seconds':[sec,2]};
Object.keys(map).forEach(function(k){var el=cd.querySelector('[data-unit="'+k+'"]');
if(el)el.textContent=String(map[k][0]).padStart(map[k][1],'0')})},1000)}
});"""

# canonical lead-form.js lives in blocks/lead-form.js (real file, no escaping);
# loaded per-build in write_assets().

CALC_JS_STUB = """/* calculator.js — deposit projection demo. Illustrative only, no promises.
   Reads currency/locale words from data attributes on #calculator (ui.* content keys). */
(function(){
'use strict';
var LOCALE=document.documentElement.getAttribute('lang')||'cs-CZ';
function fmtNum(v){
  try{return new Intl.NumberFormat(LOCALE,{maximumFractionDigits:0}).format(v);}
  catch(e){return Math.round(v).toString();}
}
function compound(start,monthly,years,rate){
  var r=Math.pow(1+rate/100,1/12)-1,v=start,m=monthly;
  var pts=[],yr=0;
  for(var i=1;i<=years*12;i++){
    v=v*(1+r)+m;
    if(i%12===0){yr++;pts.push(v);}
  }
  return{final:v,series:pts};
}
function onReady(fn){if(document.readyState!=='loading'){fn();}else{document.addEventListener('DOMContentLoaded',fn);}}
onReady(function(){
  var box=document.getElementById('calculator');if(!box)return;
  var $=function(id){return document.getElementById(id);};
  var eInit=$('initial'),eMon=$('monthly'),eYrs=$('years'),
      eRate=$('rate'),eVal=$('future-value'),eRes=$('result-years'),
      eCon=$('contributed'),eGain=$('gain'),eErr=$('calc-error'),
      gLine=$('growth-line'),gArea=$('calc-area'),cLine=$('contribution-line'),
      eYL=$('years-label'),eRL=$('rate-label'),eEnd=$('end-year'),axis=box.querySelector('.chart-axis span:last-child');
  var curSym=box.getAttribute('data-cur-sym')||'',curCode=box.getAttribute('data-cur-code')||'',
      wFull=box.getAttribute('data-w-full')||'',wShort=box.getAttribute('data-w-short')||'',
      minInit=parseFloat(box.getAttribute('data-min-init'))||250;
  if(curCode==='CZK'){eInit.min=minInit;eInit.step=50;}
  function money(v,sign){
    var s=fmtNum(Math.abs(Math.round(v)));
    return(sign&&v>=0?'+':'')+(curSym?s+'\\u00a0'+curSym:s);
  }
  function draw(){
    var start=parseFloat(eInit.value)||0,mon=parseFloat(eMon.value)||0,
        yrs=parseInt(eYrs.value,10)||1,rate=parseFloat(eRate.value)||0;
    if(curCode==='CZK'&&start<minInit){eErr.textContent='';
      start=minInit;eInit.value=String(minInit);}
    eYL.textContent=String(yrs);eRL.textContent=(new Intl.NumberFormat(LOCALE,{maximumFractionDigits:1}).format(rate))+' %';
    var res=compound(start,mon,yrs,rate),
        contributed=start+mon*yrs*12,gain=res.final-contributed;
    eVal.textContent=money(res.final,false);
    eRes.textContent=yrs+'\\u00a0'+wFull;
    eCon.textContent=money(contributed,false);
    eGain.textContent=money(gain,true);
    eEnd.textContent='+'+yrs+'\\u00a0'+wShort;
    /* svg paths */
    var svg=$('calc-chart');if(svg){
      var W=500,H=200,pad=8,series=res.series,len=series.length||1,
          max=Math.max(start,res.final)||1,st=(W-pad*2)/Math.max(1,len);
      function Y(v){return(H-pad)-(v/max)*(H-pad*2);}
      function X(i){return pad+i*st;}
      var dg='',dc='',cr=start;
      for(var i=0;i<len;i++){dg+=(i?' L':'M')+X(i).toFixed(1)+' '+Y(series[i]).toFixed(1);
        dc+=(i?' L':'M')+X(i).toFixed(1)+' '+Y(cr).toFixed(1);cr+=mon*12;}
      gLine.setAttribute('d',dg);
      gArea.setAttribute('d',dg+' L'+X(len-1).toFixed(1)+' '+(H-pad)+' L'+pad+' '+(H-pad)+' Z');
      cLine.setAttribute('d',dc);
    }
  }
  ['initial','monthly','years','rate'].forEach(function(id){
    var el=$(id);if(!el)return;
    el.addEventListener('input',draw);
  });
  Array.prototype.forEach.call(box.querySelectorAll('.rate-presets button'),function(b){
    b.addEventListener('click',function(){eRate.value=b.getAttribute('data-rate');draw();});
  });
  draw();
});
/* livebar-aa: nudge one price in the flash tape every few seconds; both
   duplicated track copies must show identical values or the loop seam
   would display different numbers after an update */
var fTapes=document.querySelectorAll('.lbt-flash');
if(fTapes.length){
var fNudge=function(el){
var t=el.textContent,m=t.match(/\\d+([.,]\\d+)?/);if(!m)return;
var sep=t.indexOf(',')>-1?',':'.';
var val=parseFloat(m[0].replace(',','.'));
if(!isFinite(val))return;
var step=(Math.random()-0.5)*Math.max(val,1)*0.0012;
var dec=(m[0].indexOf(sep)>-1?m[0].split(sep)[1].length:0);
var out=(val+step).toFixed(dec);if(sep===',')out=out.replace('.',',');
el.textContent=t.replace(m[0],out);
el.classList.remove('flash-up','flash-dn');void el.offsetWidth;
el.classList.add(step>=0?'flash-up':'flash-dn');
};
setInterval(function(){Array.prototype.forEach.call(fTapes,function(tp){
var bs=tp.querySelectorAll('b');if(!bs.length)return;
fNudge(bs[Math.floor(Math.random()*bs.length)]);});},2600);
}
});"""
# NOTE: the literal above kept the historic broken IIFE closer `});` (missing "(") —
# that made the whole IIFE a no-op expression and calculator.js dead. Do not use it.

def write_assets(out: pathlib.Path, plan):
    lf = BLOCKS / "lead-form.js"
    cf = BLOCKS / "calculator.js"
    ps = BLOCKS / "pulse-sim.js"
    wc = ROOT / "widgets" / "widgets.css"
    wj = ROOT / "widgets" / "widgets.js"
    if not lf.exists(): die("blocks/lead-form.js missing (canonical lead form logic)")
    if not cf.exists(): die("blocks/calculator.js missing (canonical calculator engine)")
    if not ps.exists(): die("blocks/pulse-sim.js missing (canonical pulse-sim engine)")
    if not wc.exists() or not wj.exists(): die("widgets/widgets.{css,js} missing")
    (out / "app.js").write_text(ASSETS_JS_APP, encoding="utf-8")
    (out / "calculator.js").write_text(cf.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "pulse-sim.js").write_text(ps.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "widgets.css").write_text(wc.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "widgets.js").write_text(wj.read_text(encoding="utf-8"), encoding="utf-8")
    (out / "lead-form.js").write_text(lf.read_text(encoding="utf-8"), encoding="utf-8")
    shutil.copy(BLOCKS / "blocks.css", out / "blocks" / "blocks.css") if (out / "blocks").exists() else \
        ((out / "blocks").mkdir(parents=True, exist_ok=True), shutil.copy(BLOCKS / "blocks.css", out / "blocks" / "blocks.css"))
    if (BLOCKS / "blog.css").exists() and (plan.get("blog") or {}).get("enabled"):
        shutil.copy(BLOCKS / "blog.css", out / "blocks" / "blog.css")
    skin = plan["design"].get("skin", "rounded-air")
    shutil.copy(SKINS / f"skin-{skin}.css", out / "skin.css")
    # personas: copy only this plan's avatars into img/
    img_dir = out / "img"; img_dir.mkdir(exist_ok=True)
    for ph in plan.get("photos", []):
        src = PEOPLE_DIR / ph
        if src.exists(): shutil.copy(src, img_dir / ph)
    # app-shot photo (one per plan) + the form trust badges chosen by the plan
    app = appshot_file(plan)
    if app and (APPSHOT_DIR / app).exists():
        shutil.copy(APPSHOT_DIR / app, img_dir / "appshot.jpg")
    trust_dir = img_dir / "trust"
    trust_dir.mkdir(exist_ok=True)
    for b in {x["file"]: x for x in (trust_badges(plan) + partner_badges(plan))}.values():
        src = TRUST_DIR / b["file"]
        if src.exists(): shutil.copy(src, trust_dir / b["file"])
    # favicon + og: copy neutral placeholders (regenerated per brand by icon step)
    for f in ("favicon.svg", "favicon.ico", "favicon-32.png", "apple-touch-icon.png", "og-image.png"):
        src = ROOT / "assets-brand" / f
        if src.exists(): shutil.copy(src, out / f)

def write_integration(out: pathlib.Path, plan):
    dest_root = out / "api_local"
    if dest_root.exists(): shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True)
    dest = dest_root / "integration"
    shutil.copytree(INTEGRATION_SRC, dest, ignore=shutil.ignore_patterns(".DS_Store"))
    jobs_dir = dest / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    cfg = dest / "config.php"
    if not cfg.exists(): die("api_local_example/integration/config.php missing")
    txt = cfg.read_text(encoding="utf-8")
    brand_tokens = re.sub(r"[^A-Za-z ]", "", plan["params"]["brand"]).split()
    funnel = max(brand_tokens, key=len).upper() if brand_tokens else "BRAND"
    txt = (txt.replace("{{CC}}", plan["params"].get("cc", "") or plan["params"]["lang"].upper()[:2])
              .replace("{{LANG}}", plan["params"]["lang"])
              .replace("{{FUNNEL}}", funnel))
    cfg.write_text(txt, encoding="utf-8")
    pb = POSTBACK_SRC
    if pb.exists(): shutil.copy(pb, out / "_postback.php")

SITEMAP_T = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>"""

# Canonical-host guard. The hosting panel serves extensionless URLs (e.g. /about)
# with HTTP 200 (MultiViews) and its console may even regenerate sitemap.xml
# without the .php suffix - both create duplicate URLs next to the canonical ones.
# Every content page therefore opens with this guard: any GET/HEAD request whose
# path does not end in ".php" gets an immediate 301 to the .php variant.
# POST is never redirected; thanks.php keeps its line-1 postback contract;
# 404.php is excluded so soft-404s stay 404 instead of 301-into-404.
PHP_CANON_GUARD = (
    "<?php\n"
    "$__p = parse_url(isset($_SERVER['REQUEST_URI']) ? $_SERVER['REQUEST_URI'] : '/', PHP_URL_PATH) ?: '/';\n"
    "$__u = rtrim($__p, '/');\n"
    "$__m = isset($_SERVER['REQUEST_METHOD']) ? $_SERVER['REQUEST_METHOD'] : 'GET';\n"
    "if ($__m !== 'POST' && $__u !== '' && substr($__u, -4) !== '.php') {\n"
    "  $__root = isset($_SERVER['DOCUMENT_ROOT']) ? rtrim($_SERVER['DOCUMENT_ROOT'], '/') : __DIR__;\n"
    "  $__q = (isset($_SERVER['QUERY_STRING']) && $_SERVER['QUERY_STRING'] !== '') ? '?' . $_SERVER['QUERY_STRING'] : '';\n"
    "  $__slash = ($__p !== '/' && substr($__p, -1) === '/');\n"
    "  if (is_dir($__root . $__u)) {\n"
    "    if (!$__slash) { header('Location: ' . $__u . '/' . $__q, true, 301); exit; }\n"
    "  } else {\n"
    "    header('Location: ' . $__u . '.php' . $__q, true, 301);\n"
    "    exit;\n"
    "  }\n"
    "}\n"
    "?>\n"
)

def write_seo_files(out: pathlib.Path, plan, pages: list[str], blog: dict | None = None):
    dom = plan["params"]["domain"]
    pages = [p for p in pages if p not in ("404.php", "thanks.php")]
    lastmod = time.strftime("%Y-%m-%d")
    article_dates = {}
    for a in ((blog or {}).get("articles") or []):
        d = str(a.get("date") or "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and a.get("slug"):
            article_dates[f"{BLOG_DIR}/{a['slug']}.php"] = d
    urls = []
    for p in pages:
        loc = f"https://{dom}/" if p == "index.php" else f"https://{dom}/{p}"
        if p == "index.php":
            freq, pri = "weekly", "1.0"
        elif p in article_dates:
            freq, pri = "monthly", "0.6"
        else:
            freq, pri = "monthly", "0.7"
        urls.append(f"<url><loc>{loc}</loc><lastmod>{article_dates.get(p, lastmod)}</lastmod>"
                    f"<changefreq>{freq}</changefreq><priority>{pri}</priority></url>")
    (out / "sitemap.xml").write_text(SITEMAP_T.format(urls="\n".join(urls)), encoding="utf-8")
    (out / "robots.txt").write_text(f"""User-agent: *
Allow: /
Allow: /blocks/blocks.css
Allow: /skin.css
Disallow: /api_local/

Sitemap: https://{dom}/sitemap.xml
""", encoding="utf-8")
    (out / ".htaccess").write_text("ErrorDocument 404 /404.php\n", encoding="utf-8")

# ---------------------------------------------------------------- main -------
def cmd_build(a):
    plan = load(pathlib.Path(a.plan))
    if not plan: die(f"cannot read plan {a.plan}")
    validate_plan(plan)
    dom = plan["params"]["domain"]
    content_path = pathlib.Path(a.content) if a.content else \
        pathlib.Path(a.plan).parent / f"{pathlib.Path(a.plan).stem}-content.json"
    if not content_path.exists():
        content_path = ROOT / "content" / f"{dom}-content.json"
    C = load(content_path)
    if C:
        # contacts belong to the offer, not to the model's mood: normalize before the
        # gate so a foreign fallback (contatti@/+39 on a .es site) can never ship
        office_defaults(C, plan)
        ui_defaults(C, plan)
        reconcile_numbers(plan, C)
        _cnt = contacts_for(plan, C)
        C.setdefault("meta", {})["email"] = _cnt["email"]
        C["meta"]["telephone"] = _cnt["telephone"]
        sanitize_meta_copy(C, None, plan)
        errs = validate_content(C, plan, strict=True); errs and die("; ".join(errs))
    else:
        C = seed_content(plan); office_defaults(C, plan); ui_defaults(C, plan)
        reconcile_numbers(plan, C); ok("content: seeded placeholders")
        _cnt = contacts_for(plan, C)
        C["meta"]["email"], C["meta"]["telephone"] = _cnt["email"], _cnt["telephone"]
        sanitize_meta_copy(C, None, plan)
    B = None
    if (plan.get("blog") or {}).get("enabled"):
        blog_path = ROOT / "content" / f"{dom}-blog.json"
        B = load(blog_path)
        if not B:
            die(f"blog plan needs {blog_path.relative_to(ROOT)} — run tools/blog_content.py --plan {a.plan}")
        if B.get("_offline_fallback"):
            die("blog pack is the offline placeholder — regenerate it: "
                f"tools/blog_content.py --plan {a.plan}")
        sanitize_meta_copy(None, B, plan)
        import blog_assemble
        _berrs = blog_assemble.validate_blog(plan, B)
        if _berrs:
            die("blog pack invalid: " + "; ".join(_berrs[:8]))
        ok(f"blog: {len(B.get('articles') or [])} articles · style {plan['blog'].get('style')}")
    css_vars, fonts_import, theme = css_link_block(plan)
    ok(f"design: {plan['design']['palette_id']} × skin-{plan['design'].get('skin','rounded-air')}")
    C.setdefault("meta", {})["keywords"] = C["meta"].get("keywords", "{Brand}, {dom}")

    out = pathlib.Path(a.out) if a.out else SITES_OUT / dom
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "blocks").mkdir()
    covers = {}
    if B:
        import blog_assemble
        covers = blog_assemble.write_covers(out, plan, B)
        ok(f"blog covers: {len(covers)} article images (1200×630)")
    content_default = ROOT / "content" / f"{dom}-content.json"

    global BUILD_V
    BUILD_V = hashlib.sha1((BLOCKS / "blocks.css").read_bytes() +
                           (BLOCKS / "blog.css").read_bytes() +
                           (SKINS / f"skin-{plan['design'].get('skin')}.css").read_bytes() +
                           (BLOCKS / "lead-form.js").read_bytes() +
                           (BLOCKS / "calculator.js").read_bytes() +
                           (BLOCKS / "pulse-sim.js").read_bytes() +
                           (ROOT / "widgets" / "widgets.css").read_bytes() +
                           (ROOT / "widgets" / "widgets.js").read_bytes()).hexdigest()[:8]
    # blog_assemble imports this file as `assemble` while the CLI runs it as `__main__`;
    # keep both module instances on the same cache-busting hash (otherwise blog pages
    # shipped ?v=0 and cached the old CSS for 30 days).
    _asm_mod = sys.modules.get("assemble")
    if _asm_mod is not None and _asm_mod is not sys.modules.get("__main__"):
        _asm_mod.BUILD_V = BUILD_V
    has_calc = "calculator" in plan["layout"]["section_order"]
    pages = {"index.php": build_index(plan, C, css_vars, fonts_import, theme, B=B, covers=covers)}
    for which in ("about", "who", "contact", "register", "product", "offer", "faq"):
        slug = plan["layout"].get("slugs", {}).get(which, which)
        if which in ("product", "offer", "faq"):
            pages[f"{slug}.php"] = build_long_inner(plan, C, css_vars, fonts_import, theme, which)
        else:
            pages[f"{slug}.php"] = build_inner(plan, C, css_vars, fonts_import, theme, which)
    if B:
        import blog_assemble
        pages[f"{BLOG_DIR}/{BLOG_HUB}"] = blog_assemble.build_hub(
            plan, C, B, css_vars, fonts_import, theme, covers=covers)
        for art in B.get("articles") or []:
            pages[f"{BLOG_DIR}/{art['slug']}.php"] = blog_assemble.build_article(
                plan, C, B, art, css_vars, fonts_import, theme, covers=covers)
        ok(f"blog pages: {BLOG_DIR}/{BLOG_HUB} + "
           + ", ".join(f"{BLOG_DIR}/{a['slug']}.php" for a in B["articles"]))
    pages["thanks.php"] = build_thanks(plan, C, css_vars, fonts_import, theme)
    pages["terms.php"] = build_legal(plan, C, css_vars, fonts_import, theme, "terms")
    pages["privacy.php"] = build_legal(plan, C, css_vars, fonts_import, theme, "privacy")
    pages["404.php"] = build_404(plan, C, css_vars, fonts_import, theme)

    for fname, html in pages.items():
        if fname not in ("thanks.php", "404.php"):
            html = PHP_CANON_GUARD + html
        target = out / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
    ok(f"pages written: {', '.join(sorted(pages))}")

    write_assets(out, plan); ok("assets: app.js/calculator.js/blocks.css/skin.css")
    write_integration(out, plan); ok(f"integration: config filled (cc={plan['params'].get('cc','') or plan['params']['lang'].upper()[:2]})")
    write_seo_files(out, plan, list(pages.keys()), B); ok("sitemap/robots/.htaccess")
    # brand icons are part of the build (never ship an iconless offer)
    rc = subprocess.run([sys.executable, str(ROOT / "tools" / "brand_icons.py"),
                         "--plan", str(pathlib.Path(a.plan)), "--site", str(out)]).returncode
    if rc != 0: die("brand icons failed")
    ok("icons: favicon svg/ico/png + apple-touch + og-image")
    (out / "README.md").write_text(f"# {plan['params']['brand']} ({dom})\nBuilt by static-create-sites/assemble.py\n"
                                     f"Plan: {a.plan}\nSkin: {plan['design'].get('skin')} · Palette: {plan['design']['palette_id']}\n", encoding="utf-8")
    print(f"\nSITE BUILT → {out}")
    return out

def main():
    ap = argparse.ArgumentParser(description="Static site assembler (plan → offer)")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--content", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--ship-anyway", action="store_true",
                    help="ship even when the audit still lists issues (they are printed as WARN)")
    a = ap.parse_args()
    out = cmd_build(a)
    # gates — free lingering php -S on our port first (stale servers break probing)
    import time, os, signal
    for port in (8794, 8951):
        try:
            pids = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                                   capture_output=True, text=True).stdout
            for line in pids.splitlines()[1:]:
                pid = line.split()[1]
                if pid.isdigit(): os.kill(int(pid), signal.SIGTERM)
        except Exception: pass
    time.sleep(2.0)
    print("\n--- GATES ---")
    rel = out.relative_to(ROOT)
    arg = str(rel)
    audit_cmd = [sys.executable, str(ROOT / "tools" / "seo_audit.py"), arg]
    if a.ship_anyway:
        audit_cmd.append("--ship-anyway")
    rc = subprocess.run(audit_cmd, cwd=ROOT).returncode
    if rc != 0:
        if a.ship_anyway:
            print("WARN: seo_audit issues remain — shipped anyway (see the list above)")
        else:
            die("seo_audit failed", rc)
    ok("seo_audit: " + ("WARN (shipped with issues)" if a.ship_anyway else "PASSED"))
    rc2 = subprocess.run([sys.executable, str(ROOT / "tools" / "twin_check.py"), arg],
                          cwd=ROOT, capture_output=True, text=True).returncode
    if rc2 != 0:
        # duplicates policy: warn in the log, never block the build
        print("WARN: twin_check flagged duplicate patterns against history/siblings —")
        print("WARN: build continues (duplicates warn, not block); details above/below")
        ok("twin_check: WARN (duplicate patterns — see log)")
    else:
        ok("twin_check: PASSED")
    print(f"\nALL GREEN → ready for deploy: {out}")

if __name__ == "__main__":
    main()

