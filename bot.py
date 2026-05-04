"""
Bot Telegram - Alertes offres VIE Business France
Vérifie toutes les heures les nouvelles offres sur mon-vie-via.businessfrance.fr
"""

import json
import time
import logging
import os
import re
import requests
from bs4 import BeautifulSoup

# ─── CONFIGURATION ───────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.getenv("8697674198:AAHKJdx5YYSe6g_mE5EwzsA5p-ALjalVkkg")
TELEGRAM_CHAT_ID = os.getenv("1666214236")

CHECK_INTERVAL_SECONDS = 3600
OFFRES_FILE = "offres_vues.json"

VIE_URL = "https://mon-vie-via.businessfrance.fr/offres/recherche?sort=0"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://mon-vie-via.businessfrance.fr/",
}

# ─── LOGGING ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

log = logging.getLogger(__name__)

# ─── TELEGRAM ────────────────────────────────────────────────────────────────

def envoyer_telegram(texte):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID manquant dans les variables d'environnement.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": texte,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        log.error(f"Erreur envoi Telegram : {e}")
        return False

# ─── MÉMOIRE ─────────────────────────────────────────────────────────────────

def charger_offres_vues():
    if os.path.exists(OFFRES_FILE):
        try:
            with open(OFFRES_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            log.warning(f"Impossible de charger {OFFRES_FILE} : {e}")
            return set()

    return set()


def sauvegarder_offres_vues(ids):
    try:
        with open(OFFRES_FILE, "w", encoding="utf-8") as f:
            json.dump(list(ids), f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Impossible de sauvegarder {OFFRES_FILE} : {e}")

# ─── SCRAPING ────────────────────────────────────────────────────────────────

def scraper_api_json():
    offres = []

    api_url = "https://mon-vie-via.businessfrance.fr/api/offres"
    params = {
        "sort": 0,
        "page": 1,
        "size": 50,
        "typeVolontariat": "VIE",
    }

    r = requests.get(api_url, params=params, headers=HEADERS, timeout=15)

    log.warning(f"API URL finale: {r.url}")
    log.warning(f"API status: {r.status_code}")
    log.warning(f"API réponse début: {r.text[:500]}")

    if r.status_code != 200:
        raise Exception(f"API retourné {r.status_code}")

    data = r.json()

    items = (
        data.get("content")
        or data.get("offres")
        or data.get("items")
        or data.get("results")
        or []
    )

    for item in items:
        offre_id = str(
            item.get("id")
            or item.get("offerId")
            or item.get("reference")
            or ""
        )

        titre = (
            item.get("titre")
            or item.get("title")
            or item.get("intitule")
            or "Offre VIE"
        )

        entreprise = (
            item.get("entreprise")
            or item.get("company")
            or item.get("raisonSociale")
            or "N/A"
        )

        if isinstance(entreprise, dict):
            entreprise = entreprise.get("nom") or entreprise.get("name") or "N/A"

        pays = (
            item.get("pays")
            or item.get("country")
            or item.get("ville")
            or "N/A"
        )

        if isinstance(pays, dict):
            pays = pays.get("libelle") or pays.get("name") or "N/A"

        if offre_id:
            lien = f"https://mon-vie-via.businessfrance.fr/offres/{offre_id}"

            offres.append({
                "id": offre_id,
                "titre": titre,
                "entreprise": entreprise,
                "pays": pays,
                "lien": lien,
            })

    log.info(f"{len(offres)} offres récupérées via API JSON")
    return offres


def scraper_html():
    offres = []

    urls = [
        "https://mon-vie-via.businessfrance.fr/offres/recherche?sort=0",
        "https://mon-vie-via.businessfrance.fr/offres/recherche?latest=true",
        "https://mon-vie-via.businessfrance.fr/offres",
    ]

    seen = set()

    for url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)

            log.warning(f"HTML URL: {url}")
            log.warning(f"HTML status: {r.status_code}")
            log.warning(f"HTML début: {r.text[:500]}")

            soup = BeautifulSoup(r.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"]

                if "/offres/" not in href:
                    continue

                lien = href if href.startswith("http") else f"https://mon-vie-via.businessfrance.fr{href}"

                match = re.search(r"/offres/([^/?#]+)", lien)
                if not match:
                    continue

                offre_id = match.group(1)

                if offre_id in seen:
                    continue

                seen.add(offre_id)

                titre = a.get_text(" ", strip=True) or "Offre VIE"

                offres.append({
                    "id": offre_id,
                    "titre": titre,
                    "entreprise": "N/A",
                    "pays": "N/A",
                    "lien": lien,
                })

        except Exception as e:
            log.warning(f"Erreur scraping HTML sur {url} : {e}")

    log.info(f"{len(offres)} offres récupérées via scraping HTML")
    return offres


def scraper_offres():
    try:
        return scraper_api_json()
    except Exception as e:
        log.warning(f"API JSON échouée ({e}), tentative scraping HTML...")
        return scraper_html()

# ─── BOUCLE PRINCIPALE ───────────────────────────────────────────────────────

def main():
    log.info("🤖 Bot VIE démarré")

    envoyer_telegram(
        "🤖 <b>Bot VIE Business France démarré !</b>\n"
        "Je vais vérifier les nouvelles offres toutes les heures."
    )

    offres_vues = charger_offres_vues()
    log.info(f"{len(offres_vues)} offres déjà mémorisées")

    premier_lancement = len(offres_vues) == 0

    while True:
        try:
            log.info("Vérification des offres...")

            offres = scraper_offres()

            if not offres:
                log.info("Aucune offre récupérée. Source probablement bloquée ou endpoint modifié.")
            else:
                log.info(f"{len(offres)} offre(s) récupérée(s) au total.")

            nouvelles = [o for o in offres if o["id"] not in offres_vues]

            log.info(f"{len(nouvelles)} nouvelle(s) offre(s) détectée(s)")

            if premier_lancement:
                for offre in offres:
                    offres_vues.add(offre["id"])

                sauvegarder_offres_vues(offres_vues)

                log.info("Premier lancement : offres mémorisées sans notification massive.")
                envoyer_telegram(
                    f"✅ <b>Initialisation terminée</b>\n"
                    f"{len(offres)} offre(s) mémorisée(s).\n"
                    f"Je t'alerterai seulement pour les prochaines nouvelles offres."
                )

                premier_lancement = False

            else:
                for offre in nouvelles:
                    message = (
                        f"🆕 <b>Nouvelle offre VIE !</b>\n\n"
                        f"📌 <b>{offre['titre']}</b>\n"
                        f"🏢 {offre['entreprise']}\n"
                        f"🌍 {offre['pays']}\n\n"
                        f"🔗 <a href='{offre['lien']}'>Voir l'offre</a>"
                    )

                    envoyer_telegram(message)
                    offres_vues.add(offre["id"])

                    time.sleep(1)

                sauvegarder_offres_vues(offres_vues)

                if not nouvelles:
                    log.info("Aucune nouvelle offre pour l'instant.")

        except Exception as e:
            log.error(f"Erreur générale : {e}")

        log.info(f"Prochain contrôle dans {CHECK_INTERVAL_SECONDS // 60} minutes...")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
