import streamlit as st
from googleapiclient.discovery import build
import datetime
from dateutil import parser
from collections import Counter
import requests
from io import BytesIO
import re

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="CEKINGONES RADAR", layout="wide", page_icon="📡")

# --- CSS CUSTOM ---
st.markdown("""
    <style>
    .stButton>button {width: 100%; border-radius: 5px;}
    div[data-testid="stMetricValue"] {font-size: 1.1rem;}
    div[data-testid="stAlert"] {padding: 0.5rem 1rem;}
    </style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'results_cache' not in st.session_state:
    st.session_state['results_cache'] = []
if 'tags_cache' not in st.session_state:
    st.session_state['tags_cache'] = []
if 'quota_used' not in st.session_state:
    st.session_state['quota_used'] = 0
if 'search_performed' not in st.session_state:
    st.session_state['search_performed'] = False

# --- KAMUS GENRE SUPER LENGKAP (V7) ---
GENRE_DB = {
    "reggae": [
        "dub", "roots", "dancehall", "ska", "rocksteady", "raggamuffin", 
        "lovers rock", "steppers", "jungle", "sound system", "culture", 
        "bob marley", "dubwise", "rub-a-dub", "early reggae", "skinhead reggae",
        "reggae cover", "indonesian reggae", "brazilian reggae", "dub mix"
    ],
    "jazz": [
        "smooth", "bebop", "fusion", "acid", "swing", "bossa nova", 
        "instrumental", "coffee", "relax", "lounge", "piano jazz", 
        "sax", "cool jazz", "vocal jazz", "japanese jazz", "city pop"
    ],
    "rock": [
        "metal", "punk", "grunge", "indie", "psychedelic", "alternative", 
        "blues", "slow", "classic", "hard", "soft", "ballad", "pop rock", 
        "90s", "2000s", "acoustic", "cover", "live", "progressive", "emo", 
        "numetal", "glam", "stoner", "post-rock", "math rock", "garage"
    ],
    "hip hop": [
        "trap", "boom bap", "lofi", "drill", "old school", "gangsta", 
        "rap", "rnb", "freestyle", "beat", "instrumental", "underground", 
        "west coast", "east coast", "type beat", "phonk", "grime", "soul"
    ],
    "electronic": [
        "house", "techno", "trance", "dubstep", "dnb", "drum and bass", 
        "ambient", "synthwave", "edm", "lo-fi", "bass", "workout", 
        "deep house", "tech house", "progressive", "hardstyle", "garage", 
        "vaporwave", "chill", "gaming music", "remix"
    ],
    "pop": [
        "k-pop", "indie pop", "synth-pop", "ballad", "disco", "acoustic", 
        "top 40", "viral", "tiktok", "mashup", "boyband", "girlband", 
        "j-pop", "mandopop", "latin pop", "bedroom pop", "karaoke"
    ],
    "dangdut": [
        "koplo", "orkes", "campursari", "remix", "saweran", "koplo java", 
        "kendang", "pantura", "dangdut lawas", "koplo time", "pallapa", 
        "adella", "ambyar", "cover", "viral", "dj dangdut"
    ],
    "metal": [
        "thrash", "death", "black", "doom", "power", "heavy", "metalcore",
        "djent", "industrial", "gothic", "symphonic", "folk metal", "sludge"
    ],
    "indie": [
        "folk", "acoustic", "singer-songwriter", "alternative", "bedroom",
        "dream pop", "shoegaze", "lo-fi", "chill", "coffee shop"
    ]
}

ALLOWED_CATEGORIES = {'10': 'Music 🎵', '22': 'People & Blogs 🤳'}

# --- SIDEBAR ---
with st.sidebar:
    st.header("🔋 Monitor Kuota API")
    quota_placeholder = st.empty()
    
    st.divider()
    st.header("🎛️ Konfigurasi")
    api_key = st.text_input("API Key Google:", type="password")
    
    with st.expander("ℹ️ Cara dapat API Key"):
        st.markdown("""
        1. Buka [Google Cloud Console](https://console.cloud.google.com/).
        2. Cari & Enable **YouTube Data API v3**.
        3. Buat **API Key** (Public Data).
        4. Paste di sini.
        """)
    
    st.divider()
    keyword = st.text_input("Genre / Keyword:", value="Rock")
    
    country_list = [
        "ID Indonesia", "BR Brazil", "US USA", "JM Jamaica",
        "GB United Kingdom", "FR France", "DE Germany", 
        "IT Italy", "ES Spain", "RU Russia", "AL Albania",
        "JP Japan", "MX Mexico", "CA Canada", "AU Australia",
        "IN India", "PH Philippines", "KR South Korea"
    ]
    
    region_display = st.selectbox("Wilayah Target:", country_list, index=0)
    region_code = region_display.split()[0]
    
    days_filter = st.slider("Hari Terakhir:", 1, 90, 7)
    
    st.caption("Filter Format:")
    video_type = st.radio("Tipe Video:", ["Semua", "Video Panjang (>1m)", "Shorts (<1m)"], index=1)
    
    st.caption("Filter Kategori:")
    filter_option = st.radio("Kategori:", ["Semua (Music + Blog)", "Hanya Music", "Hanya Blog"], index=0)
    
    tombol_cari = st.button("🚀 MULAI RADAR", type="primary")
    
    st.divider()
    st.header("☕ Support Developer")
    st.write("Bantu aplikasi ini tetap jalan & update terus!")
    st.link_button("🎁 Traktir CekingOnes", "https://saweria.co/CekingOnes", type="secondary", use_container_width=True)

# --- UPDATE KUOTA UI ---
def update_quota_ui():
    limit = 10000
    used = st.session_state['quota_used']
    percent = min(used / limit, 1.0)
    with quota_placeholder.container():
        st.progress(percent, text=f"Terpakai: {used} / {limit}")
        if percent > 0.9: st.error("⚠️ Kritis!")
        else: st.success("✅ Aman")

update_quota_ui()

# --- UTILS ---
def parse_duration(pt_string):
    hours = re.search(r'(\d+)H', pt_string)
    minutes = re.search(r'(\d+)M', pt_string)
    seconds = re.search(r'(\d+)S', pt_string)
    h = int(hours.group(1)) if hours else 0
    m = int(minutes.group(1)) if minutes else 0
    s = int(seconds.group(1)) if seconds else 0
    return h*3600 + m*60 + s

def format_duration_display(seconds):
    if seconds < 60: return f"{seconds}s"
    elif seconds < 3600: return f"{seconds//60}m {seconds%60}s"
    else: return f"{seconds//3600}h {(seconds%3600)//60}m"

def download_image_bytes(url):
    try:
        response = requests.get(url, timeout=5)
        return BytesIO(response.content)
    except:
        return None

def convert_to_local_time(iso_date_str):
    dt_utc = parser.parse(iso_date_str)
    dt_local = dt_utc + datetime.timedelta(hours=7)
    return dt_local

# --- CORE LOGIC ---
def fetch_youtube_data(api_key, query, region, days, cat_filter, v_type):
    youtube = build("youtube", "v3", developerKey=api_key)
    publish_date = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat("T") + "Z"
    
    video_duration_param = 'any'
    if v_type == "Shorts (<1m)":
        video_duration_param = 'short'
    
    search_resp = youtube.search().list(
        q=query, part="id,snippet", maxResults=50, type="video", 
        regionCode=region, 
        publishedAfter=publish_date, order="viewCount",
        videoDuration=video_duration_param 
    ).execute()
    st.session_state['quota_used'] += 100
    update_quota_ui()
    
    video_ids = [item['id']['videoId'] for item in search_resp['items']]
    if not video_ids: return [], []

    video_resp = youtube.videos().list(id=','.join(video_ids), part="snippet,statistics,contentDetails").execute()
    st.session_state['quota_used'] += 1
    
    channel_ids = [item['snippet']['channelId'] for item in video_resp['items']]
    channel_ids = list(set(channel_ids))
    
    channel_resp = youtube.channels().list(id=','.join(channel_ids[:50]), part="statistics").execute()
    st.session_state['quota_used'] += 1
    update_quota_ui()
    
    subs_map = {item['id']: int(item['statistics']['subscriberCount']) for item in channel_resp['items']}
    
    data = []
    tags_all = []
    
    progress_text = "Memfilter Durasi & Kategori..."
    my_bar = st.progress(0, text=progress_text)
    total_raw_items = len(video_resp['items'])
    
    for i, item in enumerate(video_resp['items']):
        percent_complete = int(((i + 1) / total_raw_items) * 100)
        my_bar.progress(percent_complete / 100)
        
        snip = item['snippet']
        content = item['contentDetails']
        
        cat_id = snip.get('categoryId')
        is_music = cat_id == '10'
        is_blog = cat_id == '22'
        
        if cat_filter == "Hanya Music" and not is_music: continue
        if cat_filter == "Hanya Blog" and not is_blog: continue
        if cat_filter == "Semua (Music + Blog)" and (cat_id not in ['10', '22']): continue
        
        duration_sec = parse_duration(content['duration'])
        if v_type == "Shorts (<1m)" and duration_sec > 60: continue
        if v_type == "Video Panjang (>1m)" and duration_sec <= 60: continue
        
        stats = item['statistics']
        tags = snip.get('tags', [])
        tags_all.extend(tags)
        
        views = int(stats.get('viewCount', 0))
        subs = subs_map.get(snip['channelId'], 1)
        
        upload_dt_local = convert_to_local_time(snip['publishedAt'])
        hours_age = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=7) - upload_dt_local).total_seconds() / 3600
        
        thumb_url = snip['thumbnails'].get('maxres', snip['thumbnails']['high'])['url']
        img_bytes = download_image_bytes(thumb_url)
        
        data.append({
            "id": item['id'],
            "title": snip['title'],
            "description": snip.get('description', 'Tidak ada deskripsi.'),
            "thumb_bytes": img_bytes,
            "views": views,
            "vph": int(views/hours_age) if hours_age > 0 else views,
            "score": round(views/subs, 1) if subs > 0 else 0,
            "channel": snip['channelTitle'],
            "date": upload_dt_local.strftime("%d %b %Y"),
            "hour": upload_dt_local.strftime("%H:%M"),
            "duration": format_duration_display(duration_sec),
            "cat_name": ALLOWED_CATEGORIES.get(cat_id, "Unknown"),
            "url": f"https://youtu.be/{item['id']}",
            "tags": tags
        })
    
    my_bar.empty()
    return data, tags_all

# --- SMART SUB-GENRE (V2: REVERSE LOOKUP) ---
def smart_subgenre_analysis(tags, main_genre):
    main_key = main_genre.lower()
    known_subgenres = []
    parent_name = None
    
    # 1. Direct Match (Cari Bapak)
    if main_key in GENRE_DB:
        known_subgenres = GENRE_DB[main_key]
        parent_name = main_key.title()
        
    # 2. Reverse Lookup (Cari Anak -> Temukan Bapak)
    else:
        for genre, subs in GENRE_DB.items():
            if any(main_key in s for s in subs) or main_key in genre or genre in main_key:
                known_subgenres = subs
                parent_name = genre.title()
                break
    
    valid_subs = []
    
    if known_subgenres:
        for tag in tags:
            clean_tag = tag.lower().strip()
            if any(sub in clean_tag for sub in known_subgenres):
                matched_sub = next((sub for sub in known_subgenres if sub in clean_tag), clean_tag)
                # Filter biar gak dobel sama keyword search
                if matched_sub not in main_key and main_key not in matched_sub:
                    valid_subs.append(matched_sub)
    
    # FALLBACK
    if not valid_subs:
        fallback_tags = [t.lower() for t in tags if len(t) > 3 and main_key not in t.lower()]
        return Counter(fallback_tags).most_common(8), False, None
    
    return Counter(valid_subs).most_common(8), True, parent_name

# --- MAIN UI ---
st.title("📡 CEKINGONES RADAR")

if tombol_cari and api_key:
    st.session_state['results_cache'] = []
    st.session_state['tags_cache'] = []
    st.session_state['search_performed'] = False
    
    try:
        data_baru, tags_baru = fetch_youtube_data(api_key, keyword, region_code, days_filter, filter_option, video_type)
        st.session_state['results_cache'] = data_baru
        st.session_state['tags_cache'] = tags_baru
        st.session_state['search_performed'] = True
    except Exception as e:
        st.error(f"Error API: {e}")

elif tombol_cari and not api_key:
    st.error("⚠️ Masukkan API Key dulu!")

# --- RENDER HASIL ---
if st.session_state['search_performed']:
    results = st.session_state['results_cache']
    raw_tags = st.session_state['tags_cache']
    
    if not results:
        st.warning(f"Tidak ditemukan video. Coba perluas filter hari atau ganti kata kunci.")
    else:
        smart_subs, is_strict, parent_name = smart_subgenre_analysis(raw_tags, keyword)
        
        if is_strict:
            if parent_name and parent_name.lower() != keyword.lower():
                st.subheader(f"🧬 Keluarga Genre: {parent_name}")
                st.caption(f"Sistem mendeteksi '{keyword}' adalah bagian dari **{parent_name}**. Menampilkan sub-genre terkait:")
            else:
                st.subheader(f"🧬 Sub-Genre Terdeteksi ({keyword})")
                st.caption("✅ Mode Kamus Aktif")
        else:
            st.subheader(f"🏷️ Top Tags Terkait (Mode Fallback)")
            st.caption("⚠️ Mode Fallback: Menampilkan tag terbanyak dari video.")
            
        if smart_subs:
            cols = st.columns(8)
            for i, (genre_name, count) in enumerate(smart_subs):
                if i < 8:
                    if is_strict: cols[i].info(f"#{genre_name}")
                    else: cols[i].warning(f"#{genre_name}")
        else:
            st.caption("Tidak ada data tags yang relevan.")
        
        with st.expander(f"📚 Intip Kamus: Apa yang dicari sistem?"):
            if parent_name:
                 st.write(f"Keyword '{keyword}' terhubung dengan Database '{parent_name}': {GENRE_DB.get(parent_name.lower(), [])}")
            else:
                 st.warning("Kata kunci ini belum ada di Kamus Database kita. Sistem berjalan manual.")

        st.divider()
        st.write(f"Ditemukan: **{len(results)} Video** di wilayah **{region_code}**")

        sort_option = st.radio("Urutkan:", ["🔥 Viralitas (VPH)", "💎 Hidden Gem (Score)"], horizontal=True)
        if "Viralitas" in sort_option: results.sort(key=lambda x: x['vph'], reverse=True)
        else: results.sort(key=lambda x: x['score'], reverse=True)
        
        grid = st.columns(3)
        for i, vid in enumerate(results):
            with grid[i % 3]:
                if vid['thumb_bytes']: st.image(vid['thumb_bytes'], use_container_width=True)
                else: st.warning("No Image")
                
                st.markdown(f"**{vid['title'][:60]}...**")
                st.caption(f"{vid['cat_name']} | ⏱️ {vid['duration']} | 📺 {vid['channel']}")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("VPH", f"{vid['vph']:,}")
                c2.metric("Score", f"{vid['score']}x")
                c3.metric("Upload", f"{vid['hour']}") 
                
                with st.expander("📝 Bedah Data"):
                    tab1, tab2 = st.tabs(["🏷️ Tags", "📄 Deskripsi"])
                    with tab1:
                        if vid['tags']: st.code(", ".join(vid['tags']), language="text")
                        else: st.info("Tidak ada tags.")
                    with tab2:
                        st.text_area("Ket:", value=vid['description'], height=150, key=f"desc_{vid['id']}")

                col_btn1, col_btn2 = st.columns([1, 1])
                with col_btn1:
                    if vid['thumb_bytes']:
                        st.download_button("📥 Save", vid['thumb_bytes'], file_name=f"thumb_{vid['id']}.jpg", mime="image/jpeg", key=f"dl_{vid['id']}")
                with col_btn2:
                    st.link_button("▶️", vid['url'])
                
                st.write("---")
