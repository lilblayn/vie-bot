"""
Bot Telegram - Alertes offres VIE Business France
Vérifie toutes les heures les nouvelles offres sur mon-vie-via.businessfrance.fr
et envoie un message Telegram pour chaque nouvelle offre détectée.
"""

import json
import time
import logging
import os
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

# ─── CONFIGURATION ───────────────────────────────────────────────────────────

TELEGRAM_TOKEN = "8697674198:AAHKJdx5YYSe6g_mE5EwzsA5p-ALjalVkkg"   # obtenu via @BotFather
TELEGRAM_CHAT_ID = "1666214236"  # ton ID ou celui d'un groupe

CHECK_INTERVAL_SECONDS = 3600  # 1 heure
OFFRES_FILE = "offres_vues.json"  # fichier local de mémoire

VIE_URL = "https://mon-vie-via.businessfrance.fr/offres/recherche?sort=0"

# ─── LOGGING ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ─── TELEGRAM ────────────────────────────────────────────────────────────────

def envoyer_telegram(texte: str) -> bool:
    """Envoie un message Telegram. Retourne True si succès."""
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

# ─── MÉMOIRE DES OFFRES VUES ─────────────────────────────────────────────────

def charger_offres_vues() -> set:
    if os.path.exists(OFFRES_FILE):
        with open(OFFRES_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def sauvegarder_offres_vues(ids: set):
    with open(OFFRES_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f)

# ─── SCRAPING AVEC PLAYWRIGHT ────────────────────────────────────────────────

def scraper_offres() -> list[dict]:
    """
    Ouvre le site avec un navigateur headless et extrait les offres VIE.
    Retourne une liste de dicts : {id, titre, entreprise, pays, lien}
    """
    offres = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        log.info(f"Chargement de la page : {VIE_URL}")
        page.goto(VIE_URL, timeout=30000)

        # Attendre que les offres soient chargées (React SPA)
        page.wait_for_selector("article, .offre-card, [class*='offer'], [class*='mission']", timeout=20000)
        page.wait_for_timeout(2000)  # laisser le JS finir de rendre

        # Extraire les données depuis le DOM
        offres = page.evaluate("""
            () => {
                const results = [];
                // Sélecteurs probables — à affiner si nécessaire
                const cards = document.querySelectorAll(
                    'article, .offer-card, [class*="OfferCard"], [class*="MissionCard"], [class*="offer-item"]'
                );

                cards.forEach(card => {
                    const lienEl = card.querySelector('a[href*="/offres/"]');
                    const titre = card.querySelector('h2, h3, [class*="title"], [class*="titre"]')?.innerText?.trim();
                    const entreprise = card.querySelector('[class*="company"], [class*="entreprise"]')?.innerText?.trim();
                    const pays = card.querySelector('[class*="country"], [class*="pays"], [class*="location"]')?.innerText?.trim();
                    const href = lienEl?.getAttribute('href') || '';

                    // Extraire l'ID depuis l'URL (ex: /offres/123456)
                    const idMatch = href.match(/\\/offres\\/(\\d+)/);
                    const id = idMatch ? idMatch[1] : null;

                    if (id && titre) {
                        results.push({
                            id,
                            titre,
                            entreprise: entreprise || 'N/A',
                            pays: pays || 'N/A',
                            lien: 'https://mon-vie-via.businessfrance.fr' + href
                        });
                    }
                });
                return results;
            }
        """)

        browser.close()

    log.info(f"{len(offres)} offres récupérées")
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
                time.sleep(1)  # éviter le spam Telegram

            sauvegarder_offres_vues(offres_vues)

            if not nouvelles:
                log.info("Aucune nouvelle offre pour l'instant.")

        except Exception as e:
            log.error(f"Erreur lors de la vérification : {e}")
            envoyer_telegram(f"⚠️ Erreur bot VIE : {e}")

        log.info(f"Prochain contrôle dans {CHECK_INTERVAL_SECONDS // 60} minutes...")
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
