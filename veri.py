from flask import Flask, render_template, jsonify, send_from_directory, request
import sqlite3
import os
import json
import shutil
import subprocess
import requests
import urllib.parse
import re
import hashlib
import html
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Google Drive API Kütüphaneleri
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    GOOGLE_API_MEVCUT = True
except ImportError:
    GOOGLE_API_MEVCUT = False

app = Flask(__name__, static_folder='static')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'KoboReaderData_Deneme.sqlite')
CONFIG_PATH = os.path.join(BASE_DIR, 'kobo_config.json')
GDRIVE_TOKEN_PATH = os.path.join(BASE_DIR, 'gdrive_token.json')

# Kitap Dosyaları ve Kapaklar Dizinleri
BOOKS_DIR = os.path.join(BASE_DIR, 'books')
if not os.path.exists(BOOKS_DIR):
    os.makedirs(BOOKS_DIR)

COVERS_DIR = os.path.join(BASE_DIR, 'static', 'covers')
if not os.path.exists(COVERS_DIR):
    os.makedirs(COVERS_DIR)

# Git ve Komut Satırı Yolları
LOCAL_GIT_CMD = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Git', 'cmd')
if os.path.exists(LOCAL_GIT_CMD) and LOCAL_GIT_CMD not in os.environ.get('PATH', ''):
    os.environ['PATH'] += os.pathsep + LOCAL_GIT_CMD

CACHE_SOZLUGU = {}

# Kitap kapağı için zengin gradyan renk paletleri
KAPAK_GRADYANLARI = [
    ('#1e3c72', '#2a5298'),
    ('#134E5E', '#71B280'),
    ('#4A00E0', '#8E2DE2'),
    ('#2C3E50', '#4CA1AF'),
    ('#3E5151', '#DECBA4'),
    ('#434343', '#191919'),
    ('#870000', '#2B0B00'),
    ('#5A3F37', '#2C7744'),
    ('#283048', '#859398'),
    ('#614385', '#516395'),
    ('#000428', '#004e92'),
    ('#780206', '#061161')
]


# --- AYARLAR YÖNETİCİSİ ---
def ayarlari_yukle():
    """Kullanıcı tercihlerini kobo_config.json dosyasından okur."""
    varsayilan_ayarlar = {
        "bulut_yedek_aktif": True,
        "bulut_tipi": "google_drive_link",  # 'google_drive_link', 'otomatik', 'onedrive', 'ozel'
        "gdrive_klasor_linki": "",  # Web'deki Google Drive klasör linki
        "ozel_yedek_klasoru": "",
        "github_yedek_aktif": True,
        "sadece_indirilenler": True,  # Yalnızca Kobo'da yüklü gerçek kitapları göster
        "sayfa_hesap_modu": "kobo_kelime"  # 'kobo_kelime', 'internet', 'sadece_yuzde'
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                kayitli = json.load(f)
                varsayilan_ayarlar.update(kayitli)
        except Exception as e:
            print("Ayar dosyası okuma hatası:", e)
    return varsayilan_ayarlar


def ayarlari_kaydet(yeni_ayarlar):
    """Kullanıcı tercihlerini kobo_config.json dosyasına yazar."""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(yeni_ayarlar, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print("Ayar kaydetme hatası:", e)
        return False


def gdrive_linkinden_folder_id_al(url):
    """Google Drive web klasör linkinden (URL) doğrudan Folder ID'yi çıkarır."""
    if not url:
        return None
    url = url.strip()
    match = re.search(r'folders/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    match_id = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match_id:
        return match_id.group(1)
    if len(url) >= 15 and '/' not in url and ' ' not in url:
        return url
    return None


def gdrive_servisi_al():
    """Google Drive API yetkilendirme servisini döner."""
    if not GOOGLE_API_MEVCUT or not os.path.exists(GDRIVE_TOKEN_PATH):
        return None
    try:
        creds = Credentials.from_authorized_user_file(GDRIVE_TOKEN_PATH)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print("Google Drive yetki servisi hatası:", e)
        return None


def gdrive_web_yukle(dosya_yolu, folder_id, drive_service=None):
    """Google Drive web klasörüne dosyayı yükler; aynı isim ve boyuttaki dosyaları atlar."""
    if not drive_service:
        drive_service = gdrive_servisi_al()
    if not drive_service or not folder_id:
        return False, "Google Drive servisi veya klasör kimliği bulunamadı"

    dosya_adi = os.path.basename(dosya_yolu)
    dosya_boyutu = os.path.getsize(dosya_yolu)

    try:
        # Klasördeki mevcut dosyaları kontrol et (Mükerrer yüklemeyi engeller)
        q = f"'{folder_id}' in parents and name = '{dosya_adi}' and trashed = false"
        res = drive_service.files().list(q=q, fields="files(id, name, size)").execute()
        files = res.get('files', [])
        
        if files:
            mevcut_boyut = int(files[0].get('size', 0))
            if mevcut_boyut == dosya_boyutu:
                return True, "Zaten mevcut (atlandı)"

        # Yeni yükleme
        media = MediaFileUpload(dosya_yolu, resumable=True)
        file_metadata = {
            'name': dosya_adi,
            'parents': [folder_id]
        }
        drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return True, "Yüklendi"
    except Exception as e:
        return False, str(e)


def aktif_bulut_dizini_bul(ayarlar=None):
    """Yerel bulut senkronizasyon klasörünü döndürür (OneDrive vb.)."""
    if ayarlar is None:
        ayarlar = ayarlari_yukle()

    if not ayarlar.get("bulut_yedek_aktif", True):
        return None

    bulut_tipi = ayarlar.get("bulut_tipi", "otomatik")
    ozel_yol = ayarlar.get("ozel_yedek_klasoru", "").strip()
    kullanici_dizini = os.path.expanduser("~")

    if bulut_tipi == "ozel" and ozel_yol:
        try:
            os.makedirs(ozel_yol, exist_ok=True)
            return ozel_yol
        except Exception:
            pass

    onedrive_yollari = [
        os.path.join(kullanici_dizini, "OneDrive", "Kobo_Library_Books"),
        os.path.join(os.environ.get("OneDrive", ""), "Kobo_Library_Books")
    ]
    if bulut_tipi in ["onedrive", "otomatik"]:
        for y in onedrive_yollari:
            ana_dizin = os.path.dirname(y)
            if ana_dizin and os.path.exists(ana_dizin):
                try:
                    os.makedirs(y, exist_ok=True)
                    return y
                except Exception:
                    pass

    return None


# --- TARİH FORMATLAYICI (GG.AA.YYYY - SS:DK) ---
def tarih_formatla(tarih_metni):
    if not tarih_metni:
        return ""
    try:
        tarih_metni = tarih_metni.replace('Z', '').split('.')[0]
        dt = datetime.fromisoformat(tarih_metni)
        return dt.strftime("%d.%m.%Y - %H:%M")
    except Exception:
        return tarih_metni


def kobo_surucusu_bul():
    """Bağlı USB sürücülerinde Kobo kök dizinini ve veritabanını arar."""
    suruculer = [f"{chr(h)}:\\" for h in range(ord('D'), ord('Z') + 1)]
    for surucu in suruculer:
        if os.path.exists(surucu):
            olasi_yollar = [
                os.path.join(surucu, '.kobo', 'KoboReader.sqlite'),
                os.path.join(surucu, 'KoboReader.sqlite'),
                os.path.join(surucu, '.kobo', 'KoboReaderData.sqlite')
            ]
            for yol in olasi_yollar:
                if os.path.exists(yol):
                    return surucu, yol
    return None, None


def kobo_kitap_dosyalarini_kopyala(surucu_koku):
    """Kobo cihazındaki EPUB kitaplarını akıllıca yerel 'books/' ve belirlenen buluta aktarır."""
    if not surucu_koku:
        return 0, 0, []
    
    yeni_eklenen = 0
    zaten_var_olan = 0
    kopyalanan_listesi = []
    
    ayarlar = ayarlari_yukle()
    bulut_tipi = ayarlar.get("bulut_tipi", "google_drive_link")
    gdrive_linki = ayarlar.get("gdrive_klasor_linki", "").strip()
    folder_id = gdrive_linkinden_folder_id_al(gdrive_linki)
    
    drive_service = gdrive_servisi_al() if (bulut_tipi == "google_drive_link" and folder_id) else None
    bulut_yerel_dizini = aktif_bulut_dizini_bul(ayarlar)

    try:
        for root, dirs, files in os.walk(surucu_koku):
            dirs[:] = [d for d in dirs if not d.startswith('.kobo')]
            for file in files:
                ext = file.lower()
                if ext.endswith('.epub') or ext.endswith('.kepub.epub') or ext.endswith('.pdf') or ext.endswith('.mobi'):
                    kaynak = os.path.join(root, file)
                    hedef_yerel = os.path.join(BOOKS_DIR, file)
                    kaynak_boyut = os.path.getsize(kaynak)
                    
                    # 1. Yerel Kontrol: Dosya yoksa veya boyutu değişmişse kopyala
                    if not os.path.exists(hedef_yerel) or os.path.getsize(hedef_yerel) != kaynak_boyut:
                        shutil.copy2(kaynak, hedef_yerel)
                        yeni_eklenen += 1
                        kopyalanan_listesi.append(file)
                    else:
                        zaten_var_olan += 1

                    # 2. Google Drive Web Klasörüne Yükleme (Link ile)
                    if drive_service and folder_id:
                        try:
                            gdrive_web_yukle(kaynak, folder_id, drive_service)
                        except Exception as e:
                            print(f"Google Drive Web yükleme hatası ({file}):", e)

                    # 3. Varsa Yerel OneDrive / Özel Klasöre Kopyalama
                    if bulut_yerel_dizini:
                        try:
                            hedef_bulut = os.path.join(bulut_yerel_dizini, file)
                            if not os.path.exists(hedef_bulut) or os.path.getsize(hedef_bulut) != kaynak_boyut:
                                shutil.copy2(kaynak, hedef_bulut)
                        except Exception as e:
                            print(f"Yerel bulut klasörüne kopyalama uyarısı ({file}):", e)
    except Exception as e:
        print("Kitap dosyaları taranırken uyarı:", e)

    return yeni_eklenen, zaten_var_olan, kopyalanan_listesi


def kobo_cihaz_kapaklarini_kopyala(surucu_koku):
    """Kobo'nun cihaz içinde sakladığı .kobo-images/ altındaki orijinal kapakları projeye aktarır."""
    if not surucu_koku:
        return 0
    
    images_dir = os.path.join(surucu_koku, '.kobo-images')
    if not os.path.exists(images_dir):
        return 0
    
    kopyalanan = 0
    try:
        for root, _, files in os.walk(images_dir):
            for file in files:
                if file.endswith('.parsed') and ('N3_LIBRARY_GRID' in file or 'N3_FULL' in file or 'N3_LIBRARY_SHELF' in file):
                    base_id = file.split(' - ')[0].replace('file____mnt_onboard_', '').replace('.kepub.epub', '').replace('.epub', '')
                    safe_name = re.sub(r'[^\w]', '_', base_id).strip('_')
                    if safe_name:
                        hedef = os.path.join(COVERS_DIR, f"{safe_name}.jpg")
                        kaynak = os.path.join(root, file)
                        if not os.path.exists(hedef) or os.path.getsize(hedef) == 0:
                            shutil.copy2(kaynak, hedef)
                            kopyalanan += 1
    except Exception as e:
        print("Cihaz kapakları kopyalanırken uyarı:", e)
        
    return kopyalanan


def bulut_ve_git_yedekle():
    """Veritabanı güncellendiğinde GitHub ve seçilen bulut klasörüne veritabanını yedekler."""
    rapor = {"github": False, "cloud_drive": None, "gdrive_web": False}
    ayarlar = ayarlari_yukle()
    
    # 1. Google Drive Web Klasörüne Veritabanı Yükleme (Link ile)
    gdrive_linki = ayarlar.get("gdrive_klasor_linki", "").strip()
    folder_id = gdrive_linkinden_folder_id_al(gdrive_linki)
    if folder_id:
        drive_service = gdrive_servisi_al()
        if drive_service:
            basari, _ = gdrive_web_yukle(DB_PATH, folder_id, drive_service)
            rapor["gdrive_web"] = basari

    # 2. Yerel Bulut Klasörüne SQLite Yedeği (Varsa)
    bulut_dizini = aktif_bulut_dizini_bul(ayarlar)
    if bulut_dizini:
        try:
            yedek_db = os.path.join(bulut_dizini, "KoboReader.sqlite")
            shutil.copy2(DB_PATH, yedek_db)
            rapor["cloud_drive"] = yedek_db
        except Exception as e:
            print("Bulut klasörüne veritabanı kopyalama uyarısı:", e)

    # 3. GitHub Otomatik Commit & Push
    if ayarlar.get("github_yedek_aktif", True):
        try:
            zaman_damgasi = datetime.now().strftime("%d.%m.%Y %H:%M")
            subprocess.run(["git", "add", "."], cwd=BASE_DIR, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Kobo otomatik eşitleme: {zaman_damgasi}"], cwd=BASE_DIR, check=False, capture_output=True)
            push_sonuc = subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=False, capture_output=True)
            if push_sonuc.returncode == 0:
                rapor["github"] = True
        except Exception as e:
            print("GitHub push hatası:", e)

    return rapor


def normalize_text(text):
    """Arama karşılaştırması için Türkçe karakterleri normalize eder."""
    if not text:
        return ""
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    text = text.translate(tr_map).lower()
    return re.sub(r'[^a-z0-9\s]', ' ', text).strip()


def baslik_ve_yazar_temizle(raw_title, raw_author=""):
    """Sideloaded EPUB dosyalarındaki sürüm/etiket kalıntılarını temizler, başlıktaki yazarı ayrıştırır."""
    title = (raw_title or '').strip()
    author = (raw_author or '').strip()
    if author.lower() in ['bilinmeyen yazar', 'unknown', '']:
        author = ''

    # @ayisigikitap, @group gibi etiketleri kaldır
    title = re.sub(r'@[a-zA-Z0-9_-]+', '', title)
    # .m.N, .kepub.epub, .epub, .pdf eklerini kaldır
    title = re.sub(r'\.(m\.[A-Z0-9]+|kepub|epub|pdf)', '', title, flags=re.IGNORECASE)
    # (düzenleniyor), (tamamlandı) gibi durum notlarını kaldır
    title = re.sub(r'\((?:düzenleniyor|tamamlandı|taslak)[^\)]*\)', '', title, flags=re.IGNORECASE)
    
    # Yazar başlıktaysa ayrıştır (Örn: "Ben, Kirke - Madeline Miller", "Yarış Çizgisi-Simone Soltani.Lights Out #1")
    if not author:
        match_dash = re.search(r'^(.*?)\s*[-–—]\s*([A-Za-zÇĞİÖŞÜçğıöşü\s\.]+)(?:\.([^\.]+.*))?$', title)
        if match_dash:
            cand_title = match_dash.group(1).strip()
            cand_author = match_dash.group(2).strip()
            words = cand_author.split()
            if 1 <= len(words) <= 4 and not any(w.lower() in ['wattpad', 'epug', 'kepub', 'part', 'bölüm'] for w in words):
                title = cand_title
                author = cand_author
        else:
            match_complex = re.search(r'^([^\-]+)-([A-Za-zÇĞİÖŞÜçğıöşü\s]+)(?:\.(.*))?$', title)
            if match_complex:
                title = match_complex.group(1).strip()
                author = match_complex.group(2).strip()

    clean_search_title = re.sub(r'#\d+', '', title)
    clean_search_title = re.sub(r'[-–—].*$', '', clean_search_title).strip()

    return title.strip(), (author.strip() if author else 'Bilinmeyen Yazar'), clean_search_title


def internet_sayfa_ara(kitap_adi, yazar_adi):
    """Google Books ve Open Library üzerinden sayfa sayısı ve kapak arar."""
    temiz_baslik, temiz_yazar, arama_basligi = baslik_ve_yazar_temizle(kitap_adi, yazar_adi)
    norm_author = temiz_yazar if temiz_yazar != "Bilinmeyen Yazar" else ""
    sorgu = f"{arama_basligi} {norm_author}".strip()
    
    try:
        url = f"https://openlibrary.org/search.json?q={urllib.parse.quote(sorgu)}&limit=1"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
        if res.status_code == 200:
            docs = res.json().get('docs', [])
            if docs:
                d = docs[0]
                sayfa = d.get('number_of_pages_median')
                cover_id = d.get('cover_i')
                cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None
                if sayfa and isinstance(sayfa, int) and 30 <= sayfa <= 2500:
                    return sayfa, cover_url
                if cover_url:
                    return None, cover_url
    except Exception:
        pass

    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(sorgu)}&maxResults=1"
        headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }
        res = requests.get(url, headers=headers, timeout=2)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("items", []):
                v_info = item.get("volumeInfo", {})
                pc = v_info.get("pageCount")
                thumb = v_info.get("imageLinks", {}).get("thumbnail") or v_info.get("imageLinks", {}).get("smallThumbnail")
                if pc and isinstance(pc, int) and 30 <= pc <= 2500:
                    return pc, thumb
                if thumb:
                    return None, thumb
    except Exception:
        pass

    return None, None


def şık_svg_kapak_uret(kitap_adi, yazar_adi, dosya_yolu):
    """Kapağı internette bulunamayan veya Wattpad kitapları için şık bir vektörel kapak üretir."""
    try:
        h = int(hashlib.md5(kitap_adi.encode('utf-8')).hexdigest(), 16)
        c1, c2 = KAPAK_GRADYANLARI[h % len(KAPAK_GRADYANLARI)]
        
        clean_title = html.escape(kitap_adi)
        clean_author = html.escape(yazar_adi if yazar_adi else "Kobo Kitaplığı")
        
        words = clean_title.split()
        lines = []
        curr = ""
        for w in words:
            if len(curr + " " + w) <= 18:
                curr = (curr + " " + w).strip()
            else:
                if curr:
                    lines.append(curr)
                curr = w
        if curr:
            lines.append(curr)
        lines = lines[:4]
        
        tspan_list = []
        for i, l in enumerate(lines):
            dy = 28 if i > 0 else 0
            tspan_list.append(f'<tspan x="150" dy="{dy}">{l}</tspan>')
        title_tspans = "".join(tspan_list)
        
        svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 450" width="300" height="450">
  <defs>
    <linearGradient id="coverGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{c1}" />
      <stop offset="100%" stop-color="{c2}" />
    </linearGradient>
  </defs>
  <rect width="300" height="450" rx="8" fill="url(#coverGrad)" />
  <rect x="14" y="14" width="272" height="422" rx="4" fill="none" stroke="rgba(255,255,255,0.22)" stroke-width="1.5" />
  
  <text x="150" y="145" fill="#ffffff" font-family="Georgia, serif" font-size="19" font-weight="bold" text-anchor="middle">
    {title_tspans}
  </text>
  
  <line x1="90" y1="260" x2="210" y2="260" stroke="rgba(255,255,255,0.3)" stroke-width="1" />
  
  <text x="150" y="295" fill="rgba(255,255,255,0.85)" font-family="-apple-system, sans-serif" font-size="13" font-weight="500" text-anchor="middle">
    {clean_author}
  </text>
  
  <text x="150" y="415" fill="rgba(255,255,255,0.4)" font-family="-apple-system, sans-serif" font-size="9" text-anchor="middle" letter-spacing="2">
    KOBO LIBRARY
  </text>
</svg>'''
        with open(dosya_yolu, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        return True
    except Exception as e:
        print("SVG kapak üretme hatası:", e)
        return False


def kapak_indir_ve_yerel_yol_dondur(kitap_adi, yazar_adi, image_id=""):
    """Kitap kapağını yerelde, cihaz önbelleğinde, iTunes veya OpenLibrary'de doğrulanmış olarak arar; bulunamazsa SVG üretir."""
    safe_title = re.sub(r'[^\w]', '_', kitap_adi).strip('_')
    dosya_adi_jpg = f"{safe_title}.jpg"
    dosya_adi_svg = f"{safe_title}.svg"
    
    yerel_jpg = os.path.join(COVERS_DIR, dosya_adi_jpg)
    yerel_svg = os.path.join(COVERS_DIR, dosya_adi_svg)
    
    # 1. Yerelde daha önce doğrulanmış veya kullanıcı tarafından yüklenmiş kapak
    if os.path.exists(yerel_jpg) and os.path.getsize(yerel_jpg) > 0:
        return f"/static/covers/{dosya_adi_jpg}"
    if os.path.exists(yerel_svg) and os.path.getsize(yerel_svg) > 0:
        return f"/static/covers/{dosya_adi_svg}"

    # 2. Kobo Cihaz İçi Önbellek (.kobo-images)
    if image_id:
        img_id_clean = re.sub(r'[^\w]', '_', image_id).strip('_')
        img_id_path = os.path.join(COVERS_DIR, f"{img_id_clean}.jpg")
        if os.path.exists(img_id_path) and os.path.getsize(img_id_path) > 0:
            return f"/static/covers/{img_id_clean}.jpg"

    # Temizlenmiş başlık ve yazar bilgisi
    temiz_baslik, temiz_yazar, arama_basligi = baslik_ve_yazar_temizle(kitap_adi, yazar_adi)
    norm_title = normalize_text(arama_basligi)
    norm_author = normalize_text(temiz_yazar) if temiz_yazar != 'Bilinmeyen Yazar' else ''
    
    queries = []
    if norm_author:
        queries.append(f"{arama_basligi} {temiz_yazar}")
    queries.append(arama_basligi)
    
    # Bilinen çeviri kitap takma adları (Alias)
    if "marsli" in norm_title:
        queries.append("The Martian Andy Weir")
    if "yaris cizgisi" in norm_title:
        queries.append("Cross the Line Simone Soltani")

    resim_url = None
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    # 3. iTunes Store Doğrulanmış Arama (Yüksek Çözünürlük 600x600)
    for q in queries:
        if resim_url:
            break
        try:
            url = f"https://itunes.apple.com/search?term={urllib.parse.quote(q)}&entity=ebook&limit=3"
            r = requests.get(url, headers=headers, timeout=2.5).json()
            for item in r.get("results", []):
                t_name = item.get("trackName", "")
                a_name = item.get("artistName", "")
                art = item.get("artworkUrl100")
                norm_tn = normalize_text(t_name)
                norm_an = normalize_text(a_name)
                
                # Başlık ve Yazar Doğrulama Filtresi (Yanlış kapakları engeller)
                author_match = not norm_author or any(w in norm_an for w in norm_author.split() if len(w) > 2)
                title_match = (norm_title in norm_tn or norm_tn in norm_title or 
                               any(w in norm_tn for w in norm_title.split() if len(w) > 3))
                if "marsli" in norm_title and "martian" in norm_tn:
                    title_match = True
                if "yaris cizgisi" in norm_title and "cross the line" in norm_tn:
                    title_match = True
                    
                if title_match and author_match and art:
                    resim_url = art.replace("100x100bb", "600x600bb")
                    break
        except Exception:
            pass

    # 4. OpenLibrary Doğrulanmış Arama
    if not resim_url:
        for q in queries:
            if resim_url:
                break
            try:
                url = f"https://openlibrary.org/search.json?q={urllib.parse.quote(q)}&limit=3"
                r = requests.get(url, headers=headers, timeout=2.5).json()
                for d in r.get("docs", []):
                    ol_title = d.get("title", "")
                    ol_authors = d.get("author_name", [])
                    cover_id = d.get("cover_i")
                    norm_ot = normalize_text(ol_title)
                    norm_oa = normalize_text(" ".join(ol_authors) if ol_authors else '')
                    
                    author_match = not norm_author or any(w in norm_oa for w in norm_author.split() if len(w) > 2)
                    title_match = (norm_title in norm_ot or norm_ot in norm_title or 
                                   any(w in norm_ot for w in norm_title.split() if len(w) > 3))
                    if "marsli" in norm_title and "martian" in norm_ot:
                        title_match = True
                    if "yaris cizgisi" in norm_title and "cross the line" in norm_ot:
                        title_match = True
                        
                    if title_match and author_match and cover_id:
                        resim_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                        break
            except Exception:
                pass

    # 5. Resmi İndir ve Kaydet
    if resim_url:
        try:
            img_data = requests.get(resim_url, headers=headers, timeout=4).content
            if img_data and len(img_data) > 500:
                with open(yerel_jpg, 'wb') as handler:
                    handler.write(img_data)
                return f"/static/covers/{dosya_adi_jpg}"
        except Exception:
            pass

    # 6. Bulunamazsa / Wattpad ise Şık Vektörel SVG Kapak Üret
    if şık_svg_kapak_uret(temiz_baslik, temiz_yazar, yerel_svg):
        return f"/static/covers/{dosya_adi_svg}"

    return f"/static/covers/{dosya_adi_svg}"


def yerel_epub_dosyasi_bul(content_id, title):
    """'books/' klasöründe kitaba ait bir .epub / .kepub.epub dosyası var mı kontrol eder."""
    if not os.path.exists(BOOKS_DIR):
        return None
        
    if content_id and 'file://' in content_id:
        ham_isim = os.path.basename(urllib.parse.unquote(content_id.replace('file://', '').replace('/mnt/onboard/', '')))
        yerel_yol = os.path.join(BOOKS_DIR, ham_isim)
        if os.path.exists(yerel_yol):
            return ham_isim

    clean_title = re.sub(r'[^\w]', '', title).lower()
    for dosya in os.listdir(BOOKS_DIR):
        clean_file = re.sub(r'[^\w]', '', dosya).lower()
        if clean_title and (clean_title in clean_file or clean_file in clean_title):
            return dosya
            
    return None


def kitap_meta_cozumle(kitap_ham):
    """Tek bir kitap için sayfa sayısını, kapağını ve EPUB dosyasını hazırlar."""
    content_id, raw_title, raw_author, store_pages, num_pages, image_id, word_count, alinti_sayisi, not_sayisi, yer_imi_sayisi, idx = kitap_ham
    temiz_title, temiz_yazar, _ = baslik_ve_yazar_temizle(raw_title, raw_author)
    
    cache_key = f"{raw_title}_{raw_author}"
    ayarlar = ayarlari_yukle()
    hesap_modu = ayarlar.get("sayfa_hesap_modu", "kobo_kelime")
    
    sayfa_sayisi_sayi = 0
    
    if hesap_modu == "kobo_kelime":
        if store_pages and isinstance(store_pages, int) and store_pages > 0:
            sayfa_sayisi_sayi = store_pages
        elif num_pages and isinstance(num_pages, int) and num_pages > 0:
            sayfa_sayisi_sayi = num_pages
        elif word_count and isinstance(word_count, (int, float)) and word_count > 0:
            sayfa_sayisi_sayi = max(1, round(word_count / 260))
    elif hesap_modu == "internet":
        inet_sayfa, _ = internet_sayfa_ara(raw_title, raw_author)
        if inet_sayfa:
            sayfa_sayisi_sayi = inet_sayfa
        elif store_pages and store_pages > 0:
            sayfa_sayisi_sayi = store_pages
    else:
        sayfa_sayisi_sayi = 0

    if cache_key in CACHE_SOZLUGU:
        kapak_url = CACHE_SOZLUGU[cache_key]["kapak_url"]
    else:
        kapak_url = kapak_indir_ve_yerel_yol_dondur(raw_title, raw_author, image_id)
        CACHE_SOZLUGU[cache_key] = {
            "kapak_url": kapak_url,
            "sayfa_sayisi_sayi": sayfa_sayisi_sayi
        }

    if hesap_modu == "sadece_yuzde":
        sayfa_metni = "—"
    else:
        sayfa_metni = f"{sayfa_sayisi_sayi} sayfa" if sayfa_sayisi_sayi > 0 else "—"
        
    epub_dosyasi = yerel_epub_dosyasi_bul(content_id, raw_title)

    return {
        "id": idx,
        "volume_id": content_id,
        "ham_baslik": raw_title,
        "kitap_adi": temiz_title,
        "yazar": temiz_yazar,
        "kategori": "Edebiyat",
        "kapak_url": kapak_url,
        "sayfa_sayisi": sayfa_metni,
        "toplam_sayfa": sayfa_sayisi_sayi,
        "alinti_sayisi": alinti_sayisi,
        "not_sayisi": not_sayisi,
        "yer_imi_sayisi": yer_imi_sayisi,
        "epub_dosya_adi": epub_dosyasi,
        "epub_indir_url": f"/api/kitap-indir/{urllib.parse.quote(epub_dosyasi)}" if epub_dosyasi else None
    }


def kobo_kitaplarini_getir():
    if not os.path.exists(DB_PATH):
        return []

    ayarlar = ayarlari_yukle()
    sadece_indirilenler = ayarlar.get("sadece_indirilenler", True)

    baglanti = sqlite3.connect(DB_PATH)
    imlec = baglanti.cursor()
    
    filtre_sql = ""
    if sadece_indirilenler:
        filtre_sql = "AND (c.IsDownloaded = 'true' OR c.IsDownloaded = 1 OR c.IsDownloaded = '1' OR c.___FileSize > 0 OR c.ContentID LIKE 'file://%')"
    
    sorgu = f"""
    SELECT c.ContentID, c.Title, c.Attribution, c.StorePages, c.___NumPages, c.ImageId,
           (SELECT SUM(w.WordCount) FROM content w WHERE w.BookID = c.ContentID AND w.WordCount > 0) as total_words,
           COUNT(CASE WHEN LOWER(b.Type) = 'highlight' OR (b.Text IS NOT NULL AND b.Text != '' AND (b.Annotation IS NULL OR b.Annotation = '')) THEN 1 END) as alinti_sayisi,
           COUNT(CASE WHEN LOWER(b.Type) = 'note' OR (b.Annotation IS NOT NULL AND b.Annotation != '') THEN 1 END) as not_sayisi,
           COUNT(CASE WHEN LOWER(b.Type) = 'bookmark' OR LOWER(b.Type) = 'dogear' OR ((b.Text IS NULL OR b.Text = '') AND (b.Annotation IS NULL OR b.Annotation = '')) THEN 1 END) as yer_imi_sayisi
    FROM content c
    LEFT JOIN Bookmark b ON (b.VolumeID = c.ContentID OR b.VolumeID LIKE '%' || c.Title || '%')
    WHERE c.ContentType = 6 
      AND c.Title IS NOT NULL 
      AND c.BookID IS NULL
      {filtre_sql}
    GROUP BY c.ContentID
    ORDER BY c.Title ASC
    """
    
    try:
        imlec.execute(sorgu)
        satirlar = imlec.fetchall()
    except sqlite3.OperationalError:
        imlec.execute("""
            SELECT ContentID, Title, Attribution, StorePages, ___NumPages, ImageId, 0, 0, 0, 0
            FROM content 
            WHERE ContentType = 6 AND Title IS NOT NULL AND BookID IS NULL
            ORDER BY Title ASC
        """)
        satirlar = imlec.fetchall()
        
    baglanti.close()
    
    kitap_ham_listesi = []
    for idx, row in enumerate(satirlar, 1):
        content_id, title, author, store_pages, num_pages, image_id, word_count, alinti, notlar, yer_imi = row
        kitap_ham_listesi.append((content_id, title, author, store_pages, num_pages, image_id, word_count, alinti, notlar, yer_imi, idx))

    with ThreadPoolExecutor(max_workers=8) as executor:
        kitaplar = list(executor.map(kitap_meta_cozumle, kitap_ham_listesi))

    return kitaplar


@app.route('/')
def ana_sayfa():
    return render_template('kobo_project_index.html')


@app.route('/api/kitaplar')
def api_kitaplar():
    return jsonify(kobo_kitaplarini_getir())


@app.route('/api/istatistikler')
def api_istatistikler():
    """Kobo okuma süreleri, kitap durumları ve son 365 günün aktivite ısı haritasını döner."""
    if not os.path.exists(DB_PATH):
        return jsonify({"hata": "Veritabanı bulunamadı"}), 404

    ayarlar = ayarlari_yukle()
    sadece_indirilenler = ayarlar.get("sadece_indirilenler", True)

    filtre_sql = ""
    if sadece_indirilenler:
        filtre_sql = "AND (c.IsDownloaded = 'true' OR c.IsDownloaded = 1 OR c.IsDownloaded = '1' OR c.___FileSize > 0 OR c.ContentID LIKE 'file://%')"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. Kitap ve Okuma Durumları
    c.execute(f'''
        SELECT 
            COUNT(*),
            SUM(CASE WHEN c.ReadStatus = 2 OR c.___PercentRead = 100 THEN 1 ELSE 0 END) as bitti,
            SUM(CASE WHEN (c.ReadStatus = 1 OR (c.___PercentRead > 0 AND c.___PercentRead < 100)) AND (c.ReadStatus != 2 OR c.ReadStatus IS NULL) THEN 1 ELSE 0 END) as okunuyor,
            SUM(CASE WHEN (c.ReadStatus = 0 OR c.ReadStatus IS NULL) AND (c.___PercentRead = 0 OR c.___PercentRead IS NULL) THEN 1 ELSE 0 END) as okunmadi,
            SUM(COALESCE(c.TimeSpentReading, 0)) as total_seconds
        FROM content c
        WHERE c.ContentType = 6 AND c.Title IS NOT NULL AND c.BookID IS NULL
        {filtre_sql}
    ''')
    toplam_kitap, bitti, okunuyor, okunmadi, total_seconds = c.fetchone()
    toplam_kitap = toplam_kitap or 0
    bitti = bitti or 0
    okunuyor = okunuyor or 0
    okunmadi = okunmadi or 0
    total_seconds = total_seconds or 0

    toplam_saat = round(total_seconds / 3600, 1)
    toplam_dakika = int(total_seconds // 60)

    # 2. Alıntı, Not, Yer İmi Sayıları
    c.execute(f'''
        SELECT 
            COUNT(CASE WHEN LOWER(b.Type) = 'highlight' OR (b.Text IS NOT NULL AND b.Text != '' AND (b.Annotation IS NULL OR b.Annotation = '')) THEN 1 END) as alinti_sayisi,
            COUNT(CASE WHEN LOWER(b.Type) = 'note' OR (b.Annotation IS NOT NULL AND b.Annotation != '') THEN 1 END) as not_sayisi,
            COUNT(CASE WHEN LOWER(b.Type) = 'bookmark' OR LOWER(b.Type) = 'dogear' OR ((b.Text IS NULL OR b.Text = '') AND (b.Annotation IS NULL OR b.Annotation = '')) THEN 1 END) as yer_imi_sayisi
        FROM Bookmark b
        JOIN content c ON (b.VolumeID = c.ContentID OR b.VolumeID LIKE '%' || c.Title || '%')
        WHERE c.ContentType = 6 AND c.Title IS NOT NULL AND c.BookID IS NULL
        {filtre_sql}
    ''')
    toplam_alinti, toplam_not, toplam_yer_imi = c.fetchone()
    toplam_alinti = toplam_alinti or 0
    toplam_not = toplam_not or 0
    toplam_yer_imi = toplam_yer_imi or 0

    # 3. Günlük Aktivite Haritası (Son 365 Gün)
    c.execute(f'''
        SELECT SUBSTR(b.DateCreated, 1, 10) as gun, COUNT(*) as adet
        FROM Bookmark b
        JOIN content c ON (b.VolumeID = c.ContentID OR b.VolumeID LIKE '%' || c.Title || '%')
        WHERE b.DateCreated IS NOT NULL AND b.DateCreated != ''
          AND c.ContentType = 6 AND c.Title IS NOT NULL AND c.BookID IS NULL
          {filtre_sql}
        GROUP BY gun
        ORDER BY gun ASC
    ''')
    gunluk_aktivite = dict(c.fetchall())

    # 4. En Çok Alıntı/Not Alınan 5 Kitap
    c.execute(f'''
        SELECT c.Title, c.Attribution, COUNT(b.BookmarkID) as islem_sayisi
        FROM content c
        JOIN Bookmark b ON (b.VolumeID = c.ContentID OR b.VolumeID LIKE '%' || c.Title || '%')
        WHERE c.ContentType = 6 AND c.Title IS NOT NULL AND c.BookID IS NULL
        {filtre_sql}
        GROUP BY c.ContentID
        ORDER BY islem_sayisi DESC
        LIMIT 5
    ''')
    top_kitaplar = []
    for raw_title, raw_author, count in c.fetchall():
        temiz_t, temiz_a, _ = baslik_ve_yazar_temizle(raw_title, raw_author)
        top_kitaplar.append({
            "kitap_adi": temiz_t,
            "yazar": temiz_a,
            "islem_sayisi": count
        })

    conn.close()

    return jsonify({
        "toplam_kitap": toplam_kitap,
        "bitti": bitti,
        "okunuyor": okunuyor,
        "okunmadi": okunmadi,
        "toplam_saat": toplam_saat,
        "toplam_dakika": toplam_dakika,
        "toplam_alinti": toplam_alinti,
        "toplam_not": toplam_not,
        "toplam_yer_imi": toplam_yer_imi,
        "gunluk_aktivite": gunluk_aktivite,
        "top_kitaplar": top_kitaplar
    })


@app.route('/api/ayarlar', methods=['GET', 'POST'])
def api_ayarlar():
    if request.method == 'POST':
        gelen_veri = request.get_json() or {}
        ayarlar = ayarlari_yukle()
        ayarlar["bulut_yedek_aktif"] = bool(gelen_veri.get("bulut_yedek_aktif", True))
        ayarlar["bulut_tipi"] = gelen_veri.get("bulut_tipi", "google_drive_link")
        ayarlar["gdrive_klasor_linki"] = gelen_veri.get("gdrive_klasor_linki", "").strip()
        ayarlar["ozel_yedek_klasoru"] = gelen_veri.get("ozel_yedek_klasoru", "").strip()
        ayarlar["github_yedek_aktif"] = bool(gelen_veri.get("github_yedek_aktif", True))
        ayarlar["sadece_indirilenler"] = bool(gelen_veri.get("sadece_indirilenler", True))
        ayarlar["sayfa_hesap_modu"] = gelen_veri.get("sayfa_hesap_modu", "kobo_kelime")
        
        basarili = ayarlari_kaydet(ayarlar)
        folder_id = gdrive_linkinden_folder_id_al(ayarlar["gdrive_klasor_linki"])
        return jsonify({
            "basarili": basarili,
            "ayarlar": ayarlar,
            "gdrive_folder_id": folder_id,
            "gdrive_auth_mevcut": os.path.exists(GDRIVE_TOKEN_PATH)
        })
    else:
        ayarlar = ayarlari_yukle()
        folder_id = gdrive_linkinden_folder_id_al(ayarlar.get("gdrive_klasor_linki", ""))
        return jsonify({
            "ayarlar": ayarlar,
            "gdrive_folder_id": folder_id,
            "gdrive_auth_mevcut": os.path.exists(GDRIVE_TOKEN_PATH)
        })


@app.route('/api/gdrive-auth-durum')
def api_gdrive_auth_durum():
    """Google Drive oturum durumunu döner."""
    return jsonify({
        "oturum_acik": os.path.exists(GDRIVE_TOKEN_PATH)
    })


@app.route('/api/bulut-test', methods=['POST'])
def api_bulut_test():
    """Google Drive linkini veya özel klasörü test eder."""
    gelen = request.get_json() or {}
    link = gelen.get("link", "").strip()
    
    if link:
        folder_id = gdrive_linkinden_folder_id_al(link)
        if folder_id:
            return jsonify({
                "basarili": True, 
                "mesaj": f"Geçerli Google Drive Klasörü Algılandı (Folder ID: {folder_id})",
                "folder_id": folder_id
            })
        else:
            return jsonify({
                "basarili": False, 
                "mesaj": "Google Drive linki çözümlenemedi. Lütfen 'https://drive.google.com/drive/folders/...' formatında bir link yapıştırın."
            })
            
    return jsonify({"basarili": False, "mesaj": "Bir link girilmedi."})


@app.route('/api/cihaz-durumu')
def api_cihaz_durumu():
    surucu, kobo_yolu = kobo_surucusu_bul()
    return jsonify({
        "bagli": kobo_yolu is not None,
        "surucu_koku": surucu if surucu else "",
        "surucu_yolu": kobo_yolu if kobo_yolu else ""
    })


@app.route('/api/kitap-indir/<path:dosya_adi>')
def api_kitap_indir(dosya_adi):
    """'books/' klasöründeki EPUB / Kepub dosyasını doğrudan indirtir."""
    guvenli_dosya = urllib.parse.unquote(dosya_adi)
    return send_from_directory(BOOKS_DIR, guvenli_dosya, as_attachment=True)


@app.route('/api/kobo-esitle', methods=['POST', 'GET'])
def api_kobo_esitle():
    surucu, kobo_yolu = kobo_surucusu_bul()
    if not kobo_yolu:
        return jsonify({
            "basarili": False, 
            "mesaj": "Kobo cihazı bulunamadı. Lütfen cihazın USB ile bilgisayara bağlı olduğundan ve 'Bağlan' onayını verdiğinizden emin olun."
        }), 404

    try:
        # 1. Cihazdan projeye veritabanını kopyalama
        shutil.copy2(kobo_yolu, DB_PATH)
        
        # 2. Cihazın içindeki kapakları kopyalama
        kopyalanan_kapak = kobo_cihaz_kapaklarini_kopyala(surucu)
        
        # 3. Cihazdaki EPUB dosyalarını 'books/' klasörüne ve Bulut Klasörüne aktarma (Yalnızca yeni/değişenler)
        yeni_kitap_sayisi, atlanan_kitap_sayisi, kitap_listesi = kobo_kitap_dosyalarini_kopyala(surucu)
        
        # 4. Önbelleği temizleme
        CACHE_SOZLUGU.clear()
        
        # 5. Bulut ve GitHub senkronizasyonu
        yedek_raporu = bulut_ve_git_yedekle()
        
        ayarlar = ayarlari_yukle()
        gdrive_linki = ayarlar.get("gdrive_klasor_linki", "")
        
        if yeni_kitap_sayisi > 0:
            mesaj = f"Kobo veritabanı eşitlendi! 📚 {yeni_kitap_sayisi} yeni kitap dosyası aktarıldı ({atlanan_kitap_sayisi} mevcut kitap atlandı)."
        else:
            mesaj = f"Kobo veritabanı eşitlendi! Tüm kitap dosyalarınız ({atlanan_kitap_sayisi} kitap) güncel, mükerrer kopya oluşturulmadı."
            
        if gdrive_linki and gdrive_linkinden_folder_id_al(gdrive_linki):
            mesaj += " ☁️ Google Drive web klasörünüzle senkronize edildi."
        
        return jsonify({
            "basarili": True,
            "mesaj": mesaj,
            "kaynak": kobo_yolu,
            "yeni_kitap_sayisi": yeni_kitap_sayisi,
            "atlanan_kitap_sayisi": atlanan_kitap_sayisi,
            "github_yedek": yedek_raporu["github"],
            "gdrive_link": gdrive_linki if gdrive_linki else None
        })
    except Exception as e:
        return jsonify({
            "basarili": False,
            "mesaj": f"Eşitleme sırasında hata oluştu: {str(e)}"
        }), 500


@app.route('/api/kitap-detay/<path:volume_id>')
def api_kitap_detay(volume_id):
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Veritabanı bulunamadı"}), 404

    ayarlar = ayarlari_yukle()
    hesap_modu = ayarlar.get("sayfa_hesap_modu", "kobo_kelime")

    baglanti = sqlite3.connect(DB_PATH)
    imlec = baglanti.cursor()
    
    imlec.execute("""
        SELECT Title, Attribution, ___NumPages, StorePages,
               (SELECT SUM(w.WordCount) FROM content w WHERE w.BookID = c.ContentID AND w.WordCount > 0) as total_words
        FROM content c
        WHERE c.ContentID = ? OR c.ContentID LIKE ? OR c.Title = ?
        LIMIT 1
    """, (volume_id, f"%{volume_id}%", volume_id))
    kitap_bilgi = imlec.fetchone()
    
    toplam_sayfa = 0
    title = ""
    if kitap_bilgi:
        title, author, num_pages, store_pages, total_words = kitap_bilgi
        if hesap_modu == "kobo_kelime":
            if store_pages and isinstance(store_pages, int) and store_pages > 0:
                toplam_sayfa = store_pages
            elif num_pages and isinstance(num_pages, int) and num_pages > 0:
                toplam_sayfa = num_pages
            elif total_words and isinstance(total_words, (int, float)) and total_words > 0:
                toplam_sayfa = max(1, round(total_words / 260))
        elif hesap_modu == "internet":
            inet_sayfa, _ = internet_sayfa_ara(title, author)
            if inet_sayfa:
                toplam_sayfa = inet_sayfa
            elif store_pages and store_pages > 0:
                toplam_sayfa = store_pages

    sorgu = """
    SELECT Type, Text, Annotation, DateCreated, ChapterProgress
    FROM Bookmark
    WHERE VolumeID = ? OR VolumeID LIKE ?
    ORDER BY DateCreated DESC
    """
    imlec.execute(sorgu, (volume_id, f"%{volume_id}%"))
    satirlar = imlec.fetchall()
    baglanti.close()
    
    detay_listesi = []
    for item_type, text, annotation, date_created, progress in satirlar:
        item_type_lower = (item_type or "").lower()
        has_note = (annotation is not None and annotation.strip() != '') or item_type_lower == 'note'
        has_highlight = (text is not None and text.strip() != '') or item_type_lower == 'highlight'
        
        if has_note:
            tur = "not"
        elif has_highlight:
            tur = "alinti"
        else:
            tur = "yer_imi"
        
        ilerleme_metni = ""
        if progress is not None and isinstance(progress, (int, float)):
            yuzde = int(round(progress * 100))
            if hesap_modu != "sadece_yuzde" and toplam_sayfa > 0:
                hesaplanan_sayfa = max(1, int(round(progress * toplam_sayfa)))
                ilerleme_metni = f"%{yuzde} - Sayfa {hesaplanan_sayfa}"
            else:
                ilerleme_metni = f"%{yuzde}"

        detay_listesi.append({
            "tur": tur,
            "alinti_metni": text if text else "",
            "kullanici_notu": annotation if annotation else "",
            "tarih": tarih_formatla(date_created),
            "ilerleme": ilerleme_metni
        })
        
    temiz_baslik, temiz_yazar, _ = baslik_ve_yazar_temizle(title, author if kitap_bilgi else "")
    kapak_url = kapak_indir_ve_yerel_yol_dondur(title, author if kitap_bilgi else "")
    epub_dosyasi = yerel_epub_dosyasi_bul(volume_id, title)

    return jsonify({
        "kitap_adi": temiz_baslik,
        "yazar": temiz_yazar,
        "ham_baslik": title,
        "kapak_url": kapak_url,
        "toplam_sayfa": toplam_sayfa,
        "detaylar": detay_listesi,
        "epub_indir_url": f"/api/kitap-indir/{urllib.parse.quote(epub_dosyasi)}" if epub_dosyasi else None
    })


@app.route('/api/kapak-degistir', methods=['POST'])
def api_kapak_degistir():
    """Kullanıcının seçtiği bir kitap için özel kapak görseli (URL veya dosya yükleme) belirlemesini sağlar."""
    try:
        kitap_adi = request.form.get('kitap_adi') or ''
        volume_id = request.form.get('volume_id') or ''
        resim_url = request.form.get('resim_url') or ''
        
        # JSON formatında istek geldiyse
        if not kitap_adi and request.is_json:
            gelen = request.get_json() or {}
            kitap_adi = gelen.get('kitap_adi', '')
            volume_id = gelen.get('volume_id', '')
            resim_url = gelen.get('resim_url', '')

        if not kitap_adi and not volume_id:
            return jsonify({"basarili": False, "mesaj": "Kitap adı veya kimliği eksik."}), 400

        safe_title = re.sub(r'[^\w]', '_', kitap_adi).strip('_')
        if not safe_title and volume_id:
            safe_title = re.sub(r'[^\w]', '_', volume_id).strip('_')

        hedef_jpg = os.path.join(COVERS_DIR, f"{safe_title}.jpg")
        hedef_svg = os.path.join(COVERS_DIR, f"{safe_title}.svg")

        # 1. Dosya Yüklemesi Varsa
        if 'dosya' in request.files and request.files['dosya'].filename != '':
            dosya = request.files['dosya']
            dosya.save(hedef_jpg)
            if os.path.exists(hedef_svg):
                try: os.remove(hedef_svg)
                except Exception: pass
            
            yeni_kapak_url = f"/static/covers/{safe_title}.jpg?t={int(datetime.now().timestamp())}"
            for k in list(CACHE_SOZLUGU.keys()):
                if kitap_adi in k or safe_title in k:
                    CACHE_SOZLUGU[k]["kapak_url"] = yeni_kapak_url

            return jsonify({
                "basarili": True, 
                "mesaj": "Kapak görseli başarıyla yüklendi ve güncellendi!",
                "yeni_kapak_url": yeni_kapak_url
            })

        # 2. Resim URL'si Varsa
        if resim_url:
            resim_url = resim_url.strip()
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            resp = requests.get(resim_url, headers=headers, timeout=6)
            if resp.status_code == 200 and len(resp.content) > 500:
                with open(hedef_jpg, 'wb') as f:
                    f.write(resp.content)
                if os.path.exists(hedef_svg):
                    try: os.remove(hedef_svg)
                    except Exception: pass

                yeni_kapak_url = f"/static/covers/{safe_title}.jpg?t={int(datetime.now().timestamp())}"
                for k in list(CACHE_SOZLUGU.keys()):
                    if kitap_adi in k or safe_title in k:
                        CACHE_SOZLUGU[k]["kapak_url"] = yeni_kapak_url

                return jsonify({
                    "basarili": True, 
                    "mesaj": "Kapak görseli URL'den başarıyla indirildi ve kaydedildi!",
                    "yeni_kapak_url": yeni_kapak_url
                })
            else:
                return jsonify({"basarili": False, "mesaj": "Girilen bağlantıdan resim indirilemedi veya geçersiz."}), 400

        return jsonify({"basarili": False, "mesaj": "Lütfen bir resim bağlantısı veya dosya seçin."}), 400
    except Exception as e:
        return jsonify({"basarili": False, "mesaj": f"Kapak güncellenirken hata oluştu: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)