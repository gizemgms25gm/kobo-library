from flask import Flask, render_template, jsonify, send_from_directory
import sqlite3
import os
import shutil
import subprocess
import requests
import urllib.parse
import re
import hashlib
import html
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

app = Flask(__name__, static_folder='static')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'KoboReaderData_Deneme.sqlite')

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
    """Kobo cihazındaki tüm .epub, .kepub.epub ve kitap dosyalarını yerel 'books/' klasörüne ve buluta kopyalar."""
    if not surucu_koku:
        return 0, []
    
    kopyalanan = 0
    kopyalanan_listesi = []
    
    # Bulut klasörleri tespiti
    kullanici_dizini = os.path.expanduser("~")
    bulut_kitap_dizinleri = [
        os.path.join(kullanici_dizini, "Google Drive", "Kobo_Library_Books"),
        os.path.join(kullanici_dizini, "OneDrive", "Kobo_Library_Books"),
        os.path.join("G:\\", "My Drive", "Kobo_Library_Books")
    ]
    aktif_bulut_dizini = None
    for b_dizin in bulut_kitap_dizinleri:
        try:
            ana_dizin = os.path.dirname(b_dizin)
            if os.path.exists(ana_dizin):
                if not os.path.exists(b_dizin):
                    os.makedirs(b_dizin)
                aktif_bulut_dizini = b_dizin
                break
        except Exception:
            pass

    try:
        for root, dirs, files in os.walk(surucu_koku):
            # Sistem klasörlerini (.kobo) atla
            dirs[:] = [d for d in dirs if not d.startswith('.kobo')]
            for file in files:
                ext = file.lower()
                if ext.endswith('.epub') or ext.endswith('.kepub.epub') or ext.endswith('.pdf') or ext.endswith('.mobi'):
                    kaynak = os.path.join(root, file)
                    hedef_yerel = os.path.join(BOOKS_DIR, file)
                    
                    # Yerel 'books/' klasörüne kopyala
                    if not os.path.exists(hedef_yerel) or os.path.getsize(hedef_yerel) != os.path.getsize(kaynak):
                        shutil.copy2(kaynak, hedef_yerel)
                        kopyalanan += 1
                        kopyalanan_listesi.append(file)
                    
                    # Bulut Drive klasörüne kopyala (Google Drive / OneDrive)
                    if aktif_bulut_dizini:
                        try:
                            hedef_bulut = os.path.join(aktif_bulut_dizini, file)
                            if not os.path.exists(hedef_bulut) or os.path.getsize(hedef_bulut) != os.path.getsize(kaynak):
                                shutil.copy2(kaynak, hedef_bulut)
                        except Exception as e:
                            print(f"Buluta dosya kopyalama uyarısı ({file}):", e)
    except Exception as e:
        print("Kitap dosyaları taranırken uyarı:", e)

    return kopyalanan, kopyalanan_listesi


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
    """Veritabanı güncellendiğinde GitHub ve varsa Google Drive / OneDrive'a yedekler."""
    rapor = {"github": False, "cloud_drive": None}
    
    kullanici_dizini = os.path.expanduser("~")
    olasi_bulut_dizinleri = [
        os.path.join(kullanici_dizini, "Google Drive", "Kobo_Backup"),
        os.path.join(kullanici_dizini, "OneDrive", "Kobo_Backup"),
        os.path.join("G:\\", "My Drive", "Kobo_Backup")
    ]
    
    for hedef_dizin in olasi_bulut_dizinleri:
        try:
            ana_dizin = os.path.dirname(hedef_dizin)
            if os.path.exists(ana_dizin):
                if not os.path.exists(hedef_dizin):
                    os.makedirs(hedef_dizin)
                yedek_hedef = os.path.join(hedef_dizin, "KoboReader.sqlite")
                shutil.copy2(DB_PATH, yedek_hedef)
                rapor["cloud_drive"] = yedek_hedef
                break
        except Exception as e:
            print("Bulut klasörü kopyalama uyarısı:", e)

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


def internet_sayfa_ara(kitap_adi, yazar_adi):
    """Google Books ve Open Library üzerinden sayfa sayısı ve kapak arar."""
    clean_title = re.sub(r'[^\w\s]', '', kitap_adi).strip()
    
    # 1. Open Library Arama
    try:
        sorgu = f"{clean_title} {yazar_adi}" if (yazar_adi and yazar_adi != "Bilinmeyen yazar") else clean_title
        url = f"https://openlibrary.org/search.json?q={urllib.parse.quote(sorgu)}&limit=1"
        res = requests.get(url, timeout=2)
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

    # 2. Google Books Arama
    try:
        sorgu = f"{clean_title} {yazar_adi}" if (yazar_adi and yazar_adi != "Bilinmeyen yazar") else clean_title
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
    """Kitap kapağını yerelde, cihaz önbelleğinde, iTunes veya OpenLibrary'de arar; bulunamazsa SVG üretir."""
    safe_title = re.sub(r'[^\w]', '_', kitap_adi).strip('_')
    dosya_adi_jpg = f"{safe_title}.jpg"
    dosya_adi_svg = f"{safe_title}.svg"
    
    yerel_jpg = os.path.join(COVERS_DIR, dosya_adi_jpg)
    yerel_svg = os.path.join(COVERS_DIR, dosya_adi_svg)
    
    if os.path.exists(yerel_jpg) and os.path.getsize(yerel_jpg) > 0:
        return f"/static/covers/{dosya_adi_jpg}"
    if os.path.exists(yerel_svg) and os.path.getsize(yerel_svg) > 0:
        return f"/static/covers/{dosya_adi_svg}"

    if image_id:
        img_id_clean = re.sub(r'[^\w]', '_', image_id).strip('_')
        img_id_path = os.path.join(COVERS_DIR, f"{img_id_clean}.jpg")
        if os.path.exists(img_id_path) and os.path.getsize(img_id_path) > 0:
            return f"/static/covers/{img_id_clean}.jpg"

    # 1. iTunes Arama
    resim_url = None
    try:
        clean_title = re.sub(r'[^\w\s]', '', kitap_adi).strip()
        sorgu = f"{clean_title} {yazar_adi}" if (yazar_adi and yazar_adi != "Bilinmeyen yazar") else clean_title
        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(sorgu)}&entity=ebook&limit=1"
        res = requests.get(url, timeout=1.5)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if results and results[0].get("artworkUrl100"):
                resim_url = results[0]["artworkUrl100"].replace("100x100bb", "600x600bb")
    except Exception:
        pass

    # 2. Open Library / Google Arama
    if not resim_url:
        _, inet_thumb = internet_sayfa_ara(kitap_adi, yazar_adi)
        if inet_thumb:
            resim_url = inet_thumb

    # Resmi indir ve kaydet
    if resim_url:
        try:
            img_data = requests.get(resim_url, timeout=3).content
            if img_data and len(img_data) > 500:
                with open(yerel_jpg, 'wb') as handler:
                    handler.write(img_data)
                return f"/static/covers/{dosya_adi_jpg}"
        except Exception:
            pass

    # 3. Bulunamadıysa (Örn: Wattpad kitapları) şık bir SVG kapak üret
    if şık_svg_kapak_uret(kitap_adi, yazar_adi, yerel_svg):
        return f"/static/covers/{dosya_adi_svg}"

    return f"https://placehold.co/400x600/2C2A29/FFFFFF?text={urllib.parse.quote(kitap_adi)}"


def yerel_epub_dosyasi_bul(content_id, title):
    """'books/' klasöründe kitaba ait bir .epub / .kepub.epub dosyası var mı kontrol eder."""
    if not os.path.exists(BOOKS_DIR):
        return None
        
    # ContentID'deki dosya adı (Örn: file:///mnt/onboard/...)
    if content_id and 'file://' in content_id:
        ham_isim = os.path.basename(urllib.parse.unquote(content_id.replace('file://', '').replace('/mnt/onboard/', '')))
        yerel_yol = os.path.join(BOOKS_DIR, ham_isim)
        if os.path.exists(yerel_yol):
            return ham_isim

    # Başlık üzerinden arama
    clean_title = re.sub(r'[^\w]', '', title).lower()
    for dosya in os.listdir(BOOKS_DIR):
        clean_file = re.sub(r'[^\w]', '', dosya).lower()
        if clean_title and (clean_title in clean_file or clean_file in clean_title):
            return dosya
            
    return None


def kitap_meta_cozumle(kitap_ham):
    """Tek bir kitap için sayfa sayısını, kapağını ve varsa indirilebilir EPUB dosyasını hazırlar."""
    content_id, title, author, store_pages, num_pages, image_id, word_count, alinti_sayisi, not_sayisi, yer_imi_sayisi, idx = kitap_ham
    yazar = author if author and author.strip() else "Bilinmeyen Yazar"
    cache_key = f"{title}_{yazar}"
    
    # 1. Sayfa Sayısı Hesaplama Mantığı
    sayfa_sayisi_sayi = 0
    if store_pages and isinstance(store_pages, int) and store_pages > 0:
        sayfa_sayisi_sayi = store_pages
    elif num_pages and isinstance(num_pages, int) and num_pages > 0:
        sayfa_sayisi_sayi = num_pages
    elif word_count and isinstance(word_count, (int, float)) and word_count > 0:
        sayfa_sayisi_sayi = max(1, round(word_count / 260))

    if cache_key in CACHE_SOZLUGU:
        kapak_url = CACHE_SOZLUGU[cache_key]["kapak_url"]
        if sayfa_sayisi_sayi == 0 and CACHE_SOZLUGU[cache_key]["sayfa_sayisi_sayi"] > 0:
            sayfa_sayisi_sayi = CACHE_SOZLUGU[cache_key]["sayfa_sayisi_sayi"]
    else:
        kapak_url = kapak_indir_ve_yerel_yol_dondur(title, yazar, image_id)
        
        if sayfa_sayisi_sayi == 0:
            inet_sayfa, _ = internet_sayfa_ara(title, yazar)
            if inet_sayfa:
                sayfa_sayisi_sayi = inet_sayfa
        
        CACHE_SOZLUGU[cache_key] = {
            "kapak_url": kapak_url,
            "sayfa_sayisi": f"{sayfa_sayisi_sayi} sayfa" if sayfa_sayisi_sayi > 0 else "—",
            "sayfa_sayisi_sayi": sayfa_sayisi_sayi
        }

    sayfa_metni = f"{sayfa_sayisi_sayi} sayfa" if sayfa_sayisi_sayi > 0 else "—"
    epub_dosyasi = yerel_epub_dosyasi_bul(content_id, title)

    return {
        "id": idx,
        "volume_id": content_id,
        "kitap_adi": title,
        "yazar": yazar,
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

    baglanti = sqlite3.connect(DB_PATH)
    imlec = baglanti.cursor()
    
    sorgu = """
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
        
        # 2. Cihazın içindeki kapakları (Wattpad/özel kitaplar dahil) kopyalama
        kopyalanan_kapak = kobo_cihaz_kapaklarini_kopyala(surucu)
        
        # 3. Cihazdaki tüm EPUB dosyalarını 'books/' klasörüne ve Bulut Klasörüne aktarma
        kopyalanan_kitap_sayisi, kitap_listesi = kobo_kitap_dosyalarini_kopyala(surucu)
        
        # 4. Önbelleği temizleme
        CACHE_SOZLUGU.clear()
        
        # 5. Bulut ve GitHub senkronizasyonu
        yedek_raporu = bulut_ve_git_yedekle()
        
        mesaj = f"Kobo veritabanı eşitlendi! 📚 {kopyalanan_kitap_sayisi} kitap dosyası (EPUB) ve {kopyalanan_kapak} kapak yedeklendi."
        
        return jsonify({
            "basarili": True,
            "mesaj": mesaj,
            "kaynak": kobo_yolu,
            "kopyalanan_kitap_sayisi": kopyalanan_kitap_sayisi,
            "github_yedek": yedek_raporu["github"],
            "cloud_drive_yedek": yedek_raporu["cloud_drive"]
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

    baglanti = sqlite3.connect(DB_PATH)
    imlec = baglanti.cursor()
    
    # Kitabın toplam sayfa sayısını bul
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
        if store_pages and isinstance(store_pages, int) and store_pages > 0:
            toplam_sayfa = store_pages
        elif num_pages and isinstance(num_pages, int) and num_pages > 0:
            toplam_sayfa = num_pages
        elif total_words and isinstance(total_words, (int, float)) and total_words > 0:
            toplam_sayfa = max(1, round(total_words / 260))
        else:
            cache_key = f"{title}_{author}"
            if cache_key in CACHE_SOZLUGU and CACHE_SOZLUGU[cache_key]["sayfa_sayisi_sayi"] > 0:
                toplam_sayfa = CACHE_SOZLUGU[cache_key]["sayfa_sayisi_sayi"]
            else:
                inet_sayfa, _ = internet_sayfa_ara(title, author)
                if inet_sayfa:
                    toplam_sayfa = inet_sayfa

    # Alıntıları ve notları kronolojik çek
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
        
        # Konum formatlama: "%58 - Sayfa 677" veya "%58"
        ilerleme_metni = ""
        if progress is not None and isinstance(progress, (int, float)):
            yuzde = int(round(progress * 100))
            if toplam_sayfa > 0:
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
        
    epub_dosyasi = yerel_epub_dosyasi_bul(volume_id, title)
    
    return jsonify({
        "detaylar": detay_listesi,
        "epub_indir_url": f"/api/kitap-indir/{urllib.parse.quote(epub_dosyasi)}" if epub_dosyasi else None
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)