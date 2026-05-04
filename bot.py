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

TELEGRAM_TOKEN = "8697674198:AAHKJdx5YYSe6g_mE5EwzsA5p-ALjalVkkg"
TELEGRAM_CHAT_ID = "1666214236"

CHECK_INTERVAL_SECONDS = 3600  # 1 heure
OFFRES_FILE = "offres_vues.json"
VIE_URL = "https://mon-vie-via.businessfrance.fr/offres/recherche?sort=0"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://mon-vie-via.businessfrance.fr/",
}

# ─── LOGGING ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ─── TELEGRAM ────────────────────────────────────────────────────────────────

def envoyer_telegram(texte):
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
        with open(OFFRES_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def sauvegarder_offres_vues(ids):
    with open(OFFRES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f)

# ─── SCRAPING ────────────────────────────────────────────────────────────────

def scraper_offres():
    offres = []
    try:
        api_url = "https://mon-vie-via.businessfrance.fr/api/offres"
        params = {"sort": 0, "page": 1, "size": 50, "typeVolontariat": "VIE"}
        r = requests.get(api_url, params=params, headers=HEADERS, timeout=15)

        if r.status_code == 200:
            data = r.json()
            items = data.get("content", data.get("offres", data.get("items", [])))
            for item in items:
                offre_id = str(item.get("id", item.get("offerId", "")))
                titre = item.get("titre", item.get("title", item.get("intitule", "N/A")))
                entreprise = item.get("entreprise", item.get("company", item.get("raisonSociale", "N/A")))
                if isinstance(entreprise, dict):
                    entreprise = entreprise.get("nom", entreprise.get("name", "N/A"))
                pays = item.get("pays", item.get("country", item.get("ville", "N/A")))
                if isinstance(pays, dict):
                    pays = pays.get("libelle", pays.get("name", "N/A"))
                lien = f"https://mon-vie-via.businessfrance.fr/offres/{offre_id}"
                if offre_id and titre:
                    offres.append({"id": offre_id, "titre": titre, "entreprise": entreprise, "pays": pays, "lien": lien})
            log.info(f"{len(offres)} offres récupérées via API JSON")
        else:
            raise Exception(f"API retourné {r.status_code}")

    except Exception as e:
        log.warning(f"API JSON échouée ({e}), tentative scraping HTML...")
        try:
            r = requests.get(VIE_URL, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            seen = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                m = re.search(r"/offres/(\d+)", href)
                if m:
                    offre_id = m.group(1)
                    if offre_id not in seen:
                        seen.add(offre_id)
                        titre = a.get_text(strip=True) or "Offre VIE"
                        lien = f"https://mon-vie-via.businessfrance.fr/offres/{offre_id}"
                        offres.append({"id": offre_id, "titre": titre, "entreprise": "N/A", "pays": "N/A", "lien": lien})
            log.info(f"{len(offres)} offres récupérées via scraping HTML")
        except Exception as e2:
            log.error(f"Erreur scraping HTML : {e2}")

    return offres

# ─── BOUCLE PRINCIPALE ───────────────────────────────────────────────────────

def main():
    log.info("🤖 Bot VIE démarré")
    envoyer_telegram("🤖 <b>Bot VIE Business France démarré !</b>\nJe vais vérifier les nouvelles offres toutes les heures.")

    offres_vues = charger_offres_vues()
    log.info(f"{len(offres_vues)} offres déjà mémorisées")

    while True:
        try:
            log.info("Vérification des offres...")
            offres = scraper_offres()
            nouvelles = [o for o in offres if o["id"] not in offres_vues]
            log.info(f"{len(nouvelles)} nouvelle(s) offre(s) détectée(s)")

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
            log.error(f"Erreur : {e}")

        log.info(f"Prochain contrôle dans {CHECK_INTERVAL_SECONDS // 60} minutes...")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
