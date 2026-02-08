import pygame
import json
import threading
import time
import os
import random  # Aggiunto per la variazione di tempo
from datetime import datetime
from playwright.sync_api import sync_playwright

# --- CONFIGURAZIONE ---
def load_config():
    with open('config.json', 'r') as f: return json.load(f)

def hex_to_rgb(hex_color):
    return tuple(int(hex_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

CONFIG = load_config()
COLORS = {k: hex_to_rgb(v) for k, v in CONFIG['colors'].items() if k != "line_colors"}
LINE_COLORS = [hex_to_rgb(c) for c in CONFIG['colors']['line_colors']]
DB_FILE = "database.json" # File per salvare lo storico

# --- GESTIONE DATI (Store & Persistenza) ---
video_data_store = {}
global_subs = "---"

def load_data_store():
    """Carica lo storico salvato per non perdere il grafico al riavvio"""
    global video_data_store, global_subs
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                video_data_store = data.get("videos", {})
                global_subs = data.get("subs", "---")
                print("Storico caricato con successo.")
        except Exception as e:
            print(f"Errore caricamento storico: {e}")

def save_data_store():
    """Salva lo storico su file"""
    data = {
        "videos": video_data_store,
        "subs": global_subs,
        "last_update": datetime.now().isoformat()
    }
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        print("Storico salvato su database.json")
    except Exception as e:
        print(f"Errore salvataggio storico: {e}")

# --- UTILS ---
def normalize_url(url):
    video_id = ""
    if "youtu.be/" in url: video_id = url.split("youtu.be/")[1].split("?")[0]
    elif "shorts/" in url: video_id = url.split("shorts/")[1].split("?")[0]
    elif "v=" in url:
        try: video_id = url.split("v=")[1].split("&")[0]
        except: pass
    if video_id: return f"https://www.youtube.com/watch?v={video_id}"
    return url

# --- SCRAPER ---
def scraper_worker():
    global video_data_store, global_subs
    
    # Init store (se non caricato dal DB)
    for url in CONFIG['target']['videos']:
        if url not in video_data_store:
            video_data_store[url] = {
                "title": "In attesa...", "views": 0, "start_views": 0,
                "history": [] 
            }

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Avvio scansione...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            for raw_url in CONFIG['target']['videos']:
                target_url = normalize_url(raw_url)
                
                try:
                    page.goto(target_url, wait_until="networkidle", timeout=60000)
                    
                    # 1. Dati Video
                    player_resp = page.evaluate("() => window.ytInitialPlayerResponse")
                    title = player_resp['videoDetails']['title']
                    views = int(player_resp['videoDetails']['viewCount'])
                    
                    # 2. Iscritti
                    try:
                        init_data = page.evaluate("() => window.ytInitialData")
                        r1 = init_data['contents']['twoColumnWatchNextResults']['results']['results']['contents']
                        owner = next((x for x in r1 if 'videoSecondaryInfoRenderer' in x), None)['videoSecondaryInfoRenderer']['owner']['videoOwnerRenderer']
                        subs_text = owner.get('subscriberCountText', {}).get('simpleText')
                        if not subs_text: subs_text = owner.get('subscriberCountText', {}).get('accessibility', {}).get('accessibilityData', {}).get('label')
                        if subs_text: 
                            clean_subs = subs_text.replace("iscritti", "").replace("subscribers", "").strip()
                            global_subs = clean_subs
                    except: pass

                    # 3. Aggiornamento Store
                    if raw_url not in video_data_store:
                         video_data_store[raw_url] = {"history": [], "start_views": views}

                    if video_data_store[raw_url].get("start_views", 0) == 0:
                        video_data_store[raw_url]["start_views"] = views

                    history = video_data_store[raw_url]["history"]
                    history.append(views)
                    
                    # Mantieni max N punti (come da config, es. 24)
                    max_pts = CONFIG['app_settings']['max_history_points']
                    if len(history) > max_pts: 
                        history.pop(0)

                    video_data_store[raw_url].update({
                        "title": title, "views": views, "history": history
                    })
                    
                    print(f" -> {title[:20]}... : {views}")

                except Exception as e:
                    print(f"Errore {raw_url}: {e}")
                
                time.sleep(2) # Piccola pausa tra un video e l'altro

            browser.close()
        
        # Salva su disco dopo ogni aggiornamento
        save_data_store()

        # CALCOLO PROSSIMO AGGIORNAMENTO
        # Base: 1 ora (3600 sec) +/- 10 min (600 sec)
        base_interval = CONFIG['app_settings']['update_interval_seconds']
        variance = 600 # 10 minuti in secondi
        
        # Genera numero casuale tra -600 e +600
        jitter = random.randint(-variance, variance)
        wait_time = base_interval + jitter
        
        # Sicurezza: mai meno di 60 secondi
        if wait_time < 60: wait_time = 60

        print(f"Scansione completata. Prossimo aggiornamento tra {wait_time/60:.1f} minuti.")
        time.sleep(wait_time)

# --- GUI ---

def draw_header(screen, w, h):
    pygame.draw.rect(screen, COLORS['panel_bg'], (0, 0, w, h))
    font_title = pygame.font.SysFont("Arial", 24, bold=True)
    font_subs = pygame.font.SysFont("Arial", 40, bold=True)
    screen.blit(font_title.render("YOUTUBE MONITOR 24H", True, COLORS['text_secondary']), (20, 20))
    
    subs_lbl = font_title.render("ISCRITTI :", True, COLORS['text_secondary'])
    subs_val = font_subs.render(global_subs, True, COLORS['subs_blue'])
    screen.blit(subs_lbl, (w - 350, 25))
    screen.blit(subs_val, (w - 150, 15))

def draw_list_row(screen, x, y, w, h, data, color_idx):
    pygame.draw.rect(screen, COLORS['panel_bg'], (x, y, w, h), border_radius=8)
    line_color = LINE_COLORS[color_idx % len(LINE_COLORS)]
    pygame.draw.circle(screen, line_color, (x + 20, y + h//2), 8)

    font_title = pygame.font.SysFont("Arial", 18)
    font_big = pygame.font.SysFont("Arial", 28, bold=True)
    font_small = pygame.font.SysFont("Arial", 14)

    title_surf = font_title.render(data.get('title', 'Loading...')[:50], True, COLORS['text_primary'])
    screen.blit(title_surf, (x + 50, y + 15))

    views = data.get('views', 0)
    v_str = f"{views:,}".replace(",", ".")
    views_surf = font_big.render(v_str, True, COLORS['views_green'])
    screen.blit(views_surf, (x + w - 200, y + 15))

    # Calcolo delta ultime 24h (primo punto vs ultimo punto)
    history = data.get("history", [])
    pct_str = "N/A"
    if len(history) >= 2:
        start_h = history[0]
        curr_h = history[-1]
        if start_h > 0:
            diff = curr_h - start_h
            pct = (diff / start_h) * 100
            symbol = "+" if pct >= 0 else ""
            pct_str = f"24h: {symbol}{pct:.2f}% ({diff:+})"
    
    screen.blit(font_small.render(pct_str, True, COLORS['text_secondary']), (x + w - 200, y + 45))

def draw_time_graph(screen, rect):
    x, y, w, h = rect
    pygame.draw.rect(screen, (20, 20, 20), rect, border_radius=10)
    
    font_axis = pygame.font.SysFont("Arial", 12)
    screen.blit(font_axis.render("ULTIME 24 LETTURE -->", True, COLORS['text_secondary']), (x + w - 200, y + h - 20))

    urls = CONFIG['target']['videos']
    if not urls: return

    for idx, url in enumerate(urls):
        data = video_data_store.get(url, {})
        history = data.get("history", [])
        if len(history) < 2: continue

        color = LINE_COLORS[idx % len(LINE_COLORS)]
        
        # Normalizzazione locale (Sparkline) per vedere il trend
        local_min = min(history)
        local_max = max(history)
        diff = local_max - local_min
        if diff == 0: diff = 1

        points = []
        # Spalma i punti sulla larghezza disponibile
        step_x = (w - 40) / (CONFIG['app_settings']['max_history_points'] - 1)
        
        for i, val in enumerate(history):
            px = x + 20 + (i * step_x)
            norm_y = (val - local_min) / diff 
            py = (y + h - 30) - (norm_y * (h - 60))
            points.append((px, py))

        if len(points) > 1:
            pygame.draw.lines(screen, color, False, points, 3)
            for p in points:
                pygame.draw.circle(screen, color, (int(p[0]), int(p[1])), 4)

def main():
    pygame.init()
    
    # Carica dati salvati precedentemente
    load_data_store()

    W, H = CONFIG['app_settings']['window_width'], CONFIG['app_settings']['window_height']
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption(CONFIG['app_settings']['window_title'])
    clock = pygame.time.Clock()

    t = threading.Thread(target=scraper_worker, daemon=True)
    t.start()

    header_h = 80
    list_h = int((H - header_h) * 0.4) 
    graph_h = H - header_h - list_h

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

        screen.fill(COLORS['background'])
        draw_header(screen, W, header_h)

        video_urls = CONFIG['target']['videos']
        row_h = (list_h - 20) / len(video_urls) if video_urls else 50
        if row_h > 100: row_h = 100

        for i, url in enumerate(video_urls):
            data = video_data_store.get(url, {"title": "Loading...", "views": 0, "history": []})
            draw_list_row(screen, 20, header_h + 10 + (i * (row_h + 5)), W - 40, row_h, data, i)

        graph_rect = (20, header_h + list_h + 10, W - 40, graph_h - 30)
        draw_time_graph(screen, graph_rect)

        pygame.display.flip()
        clock.tick(30)
    
    # Salvataggio finale alla chiusura
    save_data_store()
    pygame.quit()

if __name__ == "__main__":
    main()