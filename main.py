import pygame
import json
import threading
import time
import os
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

# Store globale
# Struttura: { "url": { "title": "...", "views": 0, "subs": "...", "history": [v1, v2, v3] } }
video_data_store = {}
global_subs = "---" # Variabile per l'header

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
    
    # Init store
    for url in CONFIG['target']['videos']:
        if url not in video_data_store:
            video_data_store[url] = {
                "title": "Loading...", "views": 0, "start_views": 0,
                "history": [] # Qui salviamo lo storico delle views per il grafico
            }

    while True:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            for raw_url in CONFIG['target']['videos']:
                target_url = normalize_url(raw_url)
                print(f"Aggiornamento: {target_url}")
                
                try:
                    page.goto(target_url, wait_until="networkidle", timeout=60000)
                    
                    # 1. Dati Video
                    player_resp = page.evaluate("() => window.ytInitialPlayerResponse")
                    title = player_resp['videoDetails']['title']
                    views = int(player_resp['videoDetails']['viewCount'])
                    
                    # 2. Iscritti (Aggiorniamo la variabile globale solo se valida)
                    try:
                        init_data = page.evaluate("() => window.ytInitialData")
                        r1 = init_data['contents']['twoColumnWatchNextResults']['results']['results']['contents']
                        owner = next((x for x in r1 if 'videoSecondaryInfoRenderer' in x), None)['videoSecondaryInfoRenderer']['owner']['videoOwnerRenderer']
                        subs_text = owner.get('subscriberCountText', {}).get('simpleText')
                        if not subs_text: subs_text = owner.get('subscriberCountText', {}).get('accessibility', {}).get('accessibilityData', {}).get('label')
                        if subs_text: 
                            clean_subs = subs_text.replace("iscritti", "").replace("subscribers", "").strip()
                            global_subs = clean_subs # Aggiorna l'header
                    except: pass

                    # 3. Aggiornamento Store & Storico
                    if video_data_store[raw_url]["start_views"] == 0:
                        video_data_store[raw_url]["start_views"] = views

                    history = video_data_store[raw_url]["history"]
                    history.append(views)
                    # Mantieni max N punti
                    if len(history) > CONFIG['app_settings']['max_history_points']: 
                        history.pop(0)

                    video_data_store[raw_url].update({
                        "title": title, "views": views, "history": history
                    })

                except Exception as e:
                    print(f"Errore {raw_url}: {e}")
                
                time.sleep(1)

            browser.close()
        time.sleep(CONFIG['app_settings']['update_interval_seconds'])

# --- GUI ---

def draw_header(screen, w, h):
    """Disegna la barra superiore con gli iscritti"""
    pygame.draw.rect(screen, COLORS['panel_bg'], (0, 0, w, h))
    
    font_title = pygame.font.SysFont("Arial", 24, bold=True)
    font_subs = pygame.font.SysFont("Arial", 40, bold=True)
    
    # Titolo App
    screen.blit(font_title.render("YOUTUBE LIVE MONITOR", True, COLORS['text_secondary']), (20, 20))
    
    # Iscritti Totali (Destra)
    subs_lbl = font_title.render("ISCRITTI :", True, COLORS['text_secondary'])
    subs_val = font_subs.render(global_subs, True, COLORS['subs_blue'])
    
    # Posizionamento dinamico a destra
    screen.blit(subs_lbl, (w - 350, 25))
    screen.blit(subs_val, (w - 150, 15))

def draw_list_row(screen, x, y, w, h, data, color_idx):
    """Disegna la riga del video"""
    pygame.draw.rect(screen, COLORS['panel_bg'], (x, y, w, h), border_radius=8)
    
    # Pallino colorato (Legenda grafico)
    line_color = LINE_COLORS[color_idx % len(LINE_COLORS)]
    pygame.draw.circle(screen, line_color, (x + 20, y + h//2), 8)

    font_title = pygame.font.SysFont("Arial", 18)
    font_big = pygame.font.SysFont("Arial", 28, bold=True)
    font_small = pygame.font.SysFont("Arial", 14)

    # Titolo
    title_surf = font_title.render(data['title'][:50], True, COLORS['text_primary'])
    screen.blit(title_surf, (x + 50, y + 15))

    # Views (Verde)
    v_str = f"{data['views']:,}".replace(",", ".")
    views_surf = font_big.render(v_str, True, COLORS['views_green'])
    screen.blit(views_surf, (x + w - 200, y + 15))

    # Percentuale
    start = data.get("start_views", 0)
    curr = data.get("views", 0)
    pct_str = "+0.00%"
    if start > 0 and curr >= start:
        diff = curr - start
        pct = (diff / start) * 100
        if pct > 0: pct_str = f"+{pct:.4f}%"
    
    screen.blit(font_small.render(pct_str, True, COLORS['text_secondary']), (x + w - 200, y + 45))

def draw_time_graph(screen, rect):
    """Disegna il grafico a linee temporali"""
    x, y, w, h = rect
    pygame.draw.rect(screen, (20, 20, 20), rect, border_radius=10) # Sfondo scuro grafico
    
    # Titolo Assi
    font_axis = pygame.font.SysFont("Arial", 12)
    screen.blit(font_axis.render("TEMPO (Ultime rilevazioni) -->", True, COLORS['text_secondary']), (x + w - 200, y + h - 20))
    screen.blit(font_axis.render("VISUALIZZAZIONI (Scala relativa)", True, COLORS['text_secondary']), (x + 10, y + 10))

    urls = CONFIG['target']['videos']
    if not urls: return

    # Troviamo min e max globale per scalare il grafico
    all_values = []
    for u in urls:
        all_values.extend(video_data_store.get(u, {}).get("history", []))
    
    if not all_values: return
    
    # Normalizzazione Globale o Relativa? 
    # Usiamo normalizzazione "per video" per vedere le tendenze anche se un video ha 1M views e l'altro 100.
    # Se vuoi scala assoluta, usa min(all_values) e max(all_values) qui fuori.
    
    for idx, url in enumerate(urls):
        data = video_data_store.get(url, {})
        history = data.get("history", [])
        if len(history) < 2: continue

        # Colore linea
        color = LINE_COLORS[idx % len(LINE_COLORS)]
        
        # Calcolo scala locale per questo video (Sparkline sovrapposte)
        # Questo permette di confrontare la CRESCITA (pendenza) anche se i volumi sono diversi
        local_min = min(history)
        local_max = max(history)
        diff = local_max - local_min
        if diff == 0: diff = 1

        points = []
        step_x = (w - 40) / (len(history) - 1)
        
        for i, val in enumerate(history):
            px = x + 20 + (i * step_x)
            # Normalizziamo tra 0 e 1, poi scaliamo all'altezza
            # Lasciamo 30px di margine sopra e sotto
            norm_y = (val - local_min) / diff 
            py = (y + h - 30) - (norm_y * (h - 60))
            points.append((px, py))

        if len(points) > 1:
            pygame.draw.lines(screen, color, False, points, 3)
            # Pallini sui punti
            for p in points:
                pygame.draw.circle(screen, color, (int(p[0]), int(p[1])), 4)

def main():
    pygame.init()
    W, H = CONFIG['app_settings']['window_width'], CONFIG['app_settings']['window_height']
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("YouTube Live Stats")
    clock = pygame.time.Clock()

    t = threading.Thread(target=scraper_worker, daemon=True)
    t.start()

    # Layout: Header 80px, Lista 50%, Grafico Resto
    header_h = 80
    list_h = int((H - header_h) * 0.5) # Metà dello spazio rimanente
    graph_h = H - header_h - list_h

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

        screen.fill(COLORS['background'])

        # 1. Header
        draw_header(screen, W, header_h)

        # 2. Lista Video
        video_urls = CONFIG['target']['videos']
        row_h = (list_h - 20) / len(video_urls) if video_urls else 50
        if row_h > 100: row_h = 100

        for i, url in enumerate(video_urls):
            data = video_data_store.get(url, {"title": "Loading...", "views": 0, "history": []})
            # Passiamo 'i' per assegnare il colore corretto alla legenda
            draw_list_row(screen, 20, header_h + 10 + (i * (row_h + 5)), W - 40, row_h, data, i)

        # 3. Grafico Temporale
        graph_rect = (20, header_h + list_h + 10, W - 40, graph_h - 30)
        draw_time_graph(screen, graph_rect)

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()

if __name__ == "__main__":
    main()