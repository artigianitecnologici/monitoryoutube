import pygame
import json
import threading
import time
import os
import random
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
DB_FILE = "database.json" 

# --- GESTIONE DATI ---
video_data_store = {}
global_subs = "---"

def load_data_store():
    global video_data_store, global_subs
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
                video_data_store = data.get("videos", {})
                global_subs = data.get("subs", "---")
        except: pass

def save_data_store():
    data = { "videos": video_data_store, "subs": global_subs, "last_update": datetime.now().isoformat() }
    try:
        with open(DB_FILE, 'w') as f: json.dump(data, f, indent=4)
    except: pass

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
    for url in CONFIG['target']['videos']:
        if url not in video_data_store:
            video_data_store[url] = { "title": "INITIALIZING...", "views": 0, "start_views": 0, "history": [] }

    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] SCANNING FREQUENCIES...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            for raw_url in CONFIG['target']['videos']:
                target_url = normalize_url(raw_url)
                try:
                    page.goto(target_url, wait_until="networkidle", timeout=60000)
                    
                    player_resp = page.evaluate("() => window.ytInitialPlayerResponse")
                    title = player_resp['videoDetails']['title']
                    views = int(player_resp['videoDetails']['viewCount'])
                    
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

                    if raw_url not in video_data_store: video_data_store[raw_url] = {"history": [], "start_views": views}
                    if video_data_store[raw_url].get("start_views", 0) == 0: video_data_store[raw_url]["start_views"] = views

                    history = video_data_store[raw_url]["history"]
                    history.append(views)
                    if len(history) > CONFIG['app_settings']['max_history_points']: history.pop(0)

                    video_data_store[raw_url].update({ "title": title.upper(), "views": views, "history": history })
                    
                except Exception as e: print(f"ERR: {e}")
                time.sleep(2)
            browser.close()
        
        save_data_store()
        
        base = CONFIG['app_settings']['update_interval_seconds']
        wait_time = base + random.randint(-600, 600)
        if wait_time < 60: wait_time = 60
        time.sleep(wait_time)

# --- GUI / FALLOUT STYLE ---

def get_font(size, bold=False):
    fonts = ["couriernew", "consolas", "lucidaconsole", "monaco", "fixedsys"]
    return pygame.font.SysFont(fonts, size, bold=bold)

def draw_header(screen, w, h):
    pygame.draw.line(screen, COLORS['text_secondary'], (0, h-2), (w, h-2), 2)
    
    font_clock = get_font(60, bold=True) 
    font_lbl = get_font(18, bold=True)
    font_val = get_font(40, bold=True)
    
    now_str = datetime.now().strftime("%H:%M:%S")
    clock_surf = font_clock.render(now_str, True, COLORS['text_primary'])
    glow_surf = font_clock.render(now_str, True, (0, 50, 0)) 
    screen.blit(glow_surf, (22, 17))
    screen.blit(clock_surf, (20, 15))

    status_surf = font_lbl.render("STATUS: ONLINE [REC]", True, COLORS['text_secondary'])
    screen.blit(status_surf, (20, 75))

    subs_lbl = font_lbl.render("SUBSCRIBERS", True, COLORS['text_secondary'])
    subs_val = font_val.render(global_subs, True, COLORS['subs_blue'])
    
    subs_lbl_w = subs_lbl.get_width()
    subs_val_w = subs_val.get_width()
    
    screen.blit(subs_lbl, (w - subs_lbl_w - 20, 20))
    screen.blit(subs_val, (w - subs_val_w - 20, 45))

def draw_list_row(screen, x, y, w, h, data, color_idx):
    pygame.draw.rect(screen, COLORS['panel_bg'], (x, y, w, h))
    pygame.draw.rect(screen, COLORS['text_secondary'], (x, y, w, h), 1)

    # Colore specifico per questo video
    specific_color = LINE_COLORS[color_idx % len(LINE_COLORS)]
    
    # Pallino colorato
    pygame.draw.rect(screen, specific_color, (x + 10, y + h//2 - 6, 12, 12)) 

    font_title = get_font(18, bold=True)
    font_big = get_font(30, bold=True)
    font_small = get_font(14)

    title_text = data.get('title', 'LOADING...').upper()[:45]
    title_surf = font_title.render(title_text, True, COLORS['text_primary'])
    screen.blit(title_surf, (x + 40, y + 15))

    views = data.get('views', 0)
    v_str = f"{views:,}".replace(",", ".")
    views_surf = font_big.render(v_str, True, COLORS['views_green'])
    screen.blit(views_surf, (x + w - 220, y + 15))

    history = data.get("history", [])
    pct_str = "DATA: N/A"
    if len(history) >= 2:
        start_h = history[0]
        curr_h = history[-1]
        if start_h > 0:
            diff = curr_h - start_h
            pct = (diff / start_h) * 100
            symbol = "+" if pct >= 0 else ""
            pct_str = f"DELTA: {symbol}{pct:.2f}%"
    
    screen.blit(font_small.render(pct_str, True, COLORS['text_secondary']), (x + w - 220, y + 50))

def draw_time_graph(screen, rect):
    x, y, w, h = rect
    pygame.draw.rect(screen, (0, 0, 0), rect)
    pygame.draw.rect(screen, COLORS['text_secondary'], rect, 2)
    
    # Griglia verde scuro
    for gx in range(x, x+w, 50):
        pygame.draw.line(screen, (0, 30, 0), (gx, y), (gx, y+h), 1)
    for gy in range(y, y+h, 50):
        pygame.draw.line(screen, (0, 30, 0), (x, gy), (x+w, gy), 1)

    font_axis = get_font(12)
    screen.blit(font_axis.render("HISTORY BUFFER [24H] - ABSOLUTE SCALE", True, COLORS['text_secondary']), (x + w - 300, y + h - 20))

    urls = CONFIG['target']['videos']
    if not urls: return

    # 1. TROVA MINIMO E MASSIMO GLOBALI (Tra tutti i video)
    all_values = []
    for u in urls:
        hist = video_data_store.get(u, {}).get("history", [])
        all_values.extend(hist)
    
    if not all_values: return

    global_min = min(all_values)
    global_max = max(all_values)
    global_diff = global_max - global_min
    if global_diff == 0: global_diff = 1

    # Stampa etichette scala Min/Max
    max_lbl = font_axis.render(f"MAX: {global_max:,}", True, COLORS['text_secondary'])
    min_lbl = font_axis.render(f"MIN: {global_min:,}", True, COLORS['text_secondary'])
    screen.blit(max_lbl, (x + 10, y + 10))
    screen.blit(min_lbl, (x + 10, y + h - 20))

    # 2. DISEGNA I GRAFICI
    for idx, url in enumerate(urls):
        data = video_data_store.get(url, {})
        history = data.get("history", [])
        if len(history) < 2: continue

        # Colore specifico
        color = LINE_COLORS[idx % len(LINE_COLORS)]
        
        points = []
        step_x = (w - 40) / (CONFIG['app_settings']['max_history_points'] - 1)
        
        for i, val in enumerate(history):
            px = x + 20 + (i * step_x)
            # Normalizzazione basata su GLOBAL MIN/MAX
            norm_y = (val - global_min) / global_diff 
            py = (y + h - 30) - (norm_y * (h - 60))
            points.append((px, py))

        if len(points) > 1:
            pygame.draw.lines(screen, color, False, points, 3)
            for p in points:
                pygame.draw.rect(screen, color, (int(p[0])-3, int(p[1])-3, 6, 6))

def main():
    pygame.init()
    load_data_store()

    W, H = CONFIG['app_settings']['window_width'], CONFIG['app_settings']['window_height']
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption(CONFIG['app_settings']['window_title'])
    clock = pygame.time.Clock()

    t = threading.Thread(target=scraper_worker, daemon=True)
    t.start()

    header_h = 100
    list_h = int((H - header_h) * 0.45) 
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
    
    save_data_store()
    pygame.quit()

if __name__ == "__main__":
    main()