import json
import time
import random
from playwright.sync_api import sync_playwright

def normalize_url(url):
    """Converte short link e shorts in link video standard."""
    video_id = ""
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
    elif "shorts/" in url:
        video_id = url.split("shorts/")[1].split("?")[0]
    elif "v=" in url:
        try:
            video_id = url.split("v=")[1].split("&")[0]
        except:
            pass
            
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url

def extract_json_data(page):
    """
    Estrae i dati direttamente dalla variabile Javascript interna di YouTube.
    Questo metodo è immune ai cambiamenti di layout grafico (CSS).
    """
    try:
        # Recuperiamo l'oggetto JSON nascosto 'ytInitialPlayerResponse'
        # Questo contiene TUTTI i dati tecnici del video
        data = page.evaluate("() => window.ytInitialPlayerResponse")
        
        if not data:
            return None, None, None

        # 1. Estrazione Visualizzazioni e Titolo (Dati molto affidabili qui)
        details = data.get('videoDetails', {})
        title = details.get('title', 'N/D')
        views = details.get('viewCount', '0')
        
        # 2. Estrazione Iscritti
        # Gli iscritti non sono sempre nel playerResponse, proviamo a cercarli
        # nella variabile 'ytInitialData' che gestisce il layout della pagina
        subs = "N/D"
        try:
            initial_data = page.evaluate("() => window.ytInitialData")
            
            # Percorso tortuoso per arrivare al numero di iscritti nel JSON
            # YouTube annida i dati molto in profondità
            results = initial_data['contents']['twoColumnWatchNextResults']['results']['results']['contents']
            
            # Cerchiamo la sezione "videoSecondaryInfoRenderer" che contiene il canale
            secondary_info = next((item for item in results if 'videoSecondaryInfoRenderer' in item), None)
            
            if secondary_info:
                owner = secondary_info['videoSecondaryInfoRenderer']['owner']['videoOwnerRenderer']
                # Il testo può essere "1.2 M iscritti" o simile
                subs_text = owner.get('subscriberCountText', {}).get('simpleText')
                
                # Fallback se è in un formato diverso (accessibility data)
                if not subs_text:
                    subs_text = owner.get('subscriberCountText', {}).get('accessibility', {}).get('accessibilityData', {}).get('label')
                
                if subs_text:
                    # Puliamo la stringa (es: "1230 iscritti" -> "1230")
                    subs = subs_text.replace("iscritti", "").replace("subscribers", "").strip()
        except Exception as e:
            print(f"⚠️ Warning iscritti: {e}")
            pass

        return title, views, subs

    except Exception as e:
        print(f"❌ Errore estrazione JSON: {e}")
        return None, None, None

def get_yt_data():
    try:
        with open('video_list.json', 'r') as f:
            config = json.load(f)
            urls = config.get("videos", [])
    except FileNotFoundError:
        print("Errore: video_list.json non trovato!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            locale="it-IT"
        )
        page = context.new_page()

        results = []

        for raw_url in urls:
            url = normalize_url(raw_url)
            print(f"\n{'='*40}\nAnalisi: {url}")

            success = False
            for attempt in range(1, 4):
                try:
                    # networkidle è importante qui per assicurarsi che il JS sia caricato
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    
                    # Gestione cookie rapida (opzionale ma aiuta)
                    try:
                        btn = page.locator("button[aria-label*='Accetta'], button[aria-label*='Accept']").first
                        if btn.is_visible():
                            btn.click()
                            time.sleep(2)
                    except:
                        pass
                    
                    success = True
                    break
                except Exception as e:
                    print(f"⚠️ Tentativo {attempt} fallito. Riprovo...")
                    time.sleep(3)

            if not success:
                print("❌ Saltato dopo 3 tentativi.")
                continue

            # --- ESTRAZIONE TRAMITE JSON (Metodo Nuovo) ---
            title, views, subs = extract_json_data(page)

            # Fallback visivo disperato (se il JSON fallisce per qualche motivo strano)
            if not title or title == "N/D":
                 title = page.title().replace(" - YouTube", "")
            
            print(f"✅ RECUPERATO: {title[:30]}... | Views: {views} | Subs: {subs}")

            results.append({
                "url": raw_url,
                "titolo": title,
                "visualizzazioni": views,
                "iscritti": subs
            })
            
            time.sleep(random.uniform(2, 4))

        browser.close()

        with open('results.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        print("\nProcesso completato.")

if __name__ == "__main__":
    get_yt_data()