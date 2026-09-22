from flask import Flask, render_template, jsonify
import sqlite3
import os
import requests
import urllib.parse
import re
from datetime import datetime

app = Flask(__name__, static_folder='static')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'KoboReaderData_Deneme.sqlite')

COVERS_DIR = os.path.join(BASE_DIR, 'static', 'covers')
if not os.path.exists(COVERS_DIR):
    os.makedirs(COVERS_DIR)

CACHE_SOZLUGU = {}


# --- TARİH FORMATLAYICI (GG.AA.YYYY - SS:DK) ---
def tarih_formatla(tarih_metni):
    if not tarih_metni:
        return ""
    try:
        # Kobo veritabanındaki iso formatı parse etme
        tarih_metni = tarih_metni.replace('Z', '').split('.')[0]
        dt = datetime.fromisoformat(tarih_metni)
        return dt.strftime("%d.%m.%Y - %H:%M")
    except Exception:
        return tarih_metni


def canlı_google_sayfa_ara(kitap_adi, yazar_adi):
    try:
        clean_title = re.sub(r'[^\w\s]', '', kitap_adi)
        sorgu = f"{clean_title} {yazar_adi}" if yazar_adi else clean_title
        url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(sorgu)}&maxResults=5"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("items", []):
                pc = item.get("volumeInfo", {}).get("pageCount")
                if pc and isinstance(pc, int) and 50 <= pc <= 1500:
                    return pc
    except Exception as e:
        print(f"Google Arama Hatası ({kitap_adi}):", e)

    try:
        clean_title = re.sub(r'[^\w\s]', '', kitap_adi)
        url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(clean_title)}&maxResults=5"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            for item in res.json().get("items", []):
                pc = item.get("volumeInfo", {}).get("pageCount")
                if pc and isinstance(pc, int) and 50 <= pc <= 1500:
                    return pc
    except:
        pass

    return "Bilinmiyor"


def kapak_indir_ve_yerel_yol_dondur(kitap_adi, yazar_adi):
    safe_title = re.sub(r'[^\w]', '_', kitap_adi).strip('_')
    dosya_adi = f"{safe_title}.jpg"
    yerel_dosya_yolu = os.path.join(COVERS_DIR, dosya_adi)
    web_resim_yolu = f"/static/covers/{dosya_adi}"

    if os.path.exists(yerel_dosya_yolu):
        return web_resim_yolu

    resim_url = None
    try:
        sorgu = f"{kitap_adi} {yazar_adi}"
        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(sorgu)}&entity=ebook&limit=1"
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if results and results[0].get("artworkUrl100"):
                resim_url = results[0]["artworkUrl100"].replace("100x100bb", "600x600bb")
    except:
        pass

    if resim_url:
        try:
            img_data = requests.get(resim_url, timeout=5).content
            with open(yerel_dosya_yolu, 'wb') as handler:
                handler.write(img_data)
            return web_resim_yolu
        except:
            pass

    return f"https://placehold.co/400x600/2C2A29/FFFFFF?text={urllib.parse.quote(kitap_adi)}"


def kobo_kitaplarini_getir():
    if not os.path.exists(DB_PATH):
        return []

    baglanti = sqlite3.connect(DB_PATH)
    imlec = baglanti.cursor()
    
    sorgu = """
    SELECT Title, Attribution, StorePages, ContentID
    FROM content 
    WHERE ContentType = 6 
      AND Title IS NOT NULL 
      AND BookID IS NULL
      AND (IsDownloaded IS NULL OR LOWER(IsDownloaded) = 'true' OR IsDownloaded = 1 OR IsDownloaded = '1')
    ORDER BY Title ASC
    """
    
    try:
        imlec.execute(sorgu)
        satirlar = imlec.fetchall()
    except sqlite3.OperationalError:
        yedek_sorgu = """
        SELECT Title, Attribution, StorePages, ContentID
        FROM content 
        WHERE ContentType = 6 
          AND Title IS NOT NULL 
          AND BookID IS NULL
        ORDER BY Title ASC
        """
        imlec.execute(yedek_sorgu)
        satirlar = imlec.fetchall()
    
    kitaplar = []
    id_counter = 1
    
    for title, author, store_pages, content_id in satirlar:
        yazar = author if author else "Bilinmeyen Yazar"
        cache_key = f"{title}_{yazar}"
        
        imlec.execute("""
            SELECT 
                COUNT(CASE WHEN LOWER(Type) = 'highlight' OR (Text IS NOT NULL AND Text != '' AND (Annotation IS NULL OR Annotation = '')) THEN 1 END) as alinti_sayisi,
                COUNT(CASE WHEN LOWER(Type) = 'note' OR (Annotation IS NOT NULL AND Annotation != '') THEN 1 END) as not_sayisi
            FROM Bookmark 
            WHERE VolumeID = ? OR VolumeID LIKE ?
        """, (content_id, f"%{title}%"))
        
        stats = imlec.fetchone()
        alinti_sayisi = stats[0] if stats else 0
        not_sayisi = stats[1] if stats else 0

        if cache_key in CACHE_SOZLUGU:
            kapak_url = CACHE_SOZLUGU[cache_key]["kapak_url"]
            sayfa_sayisi = CACHE_SOZLUGU[cache_key]["sayfa_sayisi"]
        else:
            kapak_url = kapak_indir_ve_yerel_yol_dondur(title, yazar)
            internet_sayfa = canlı_google_sayfa_ara(title, yazar)
            
            if internet_sayfa != "Bilinmiyor":
                sayfa_sayisi = f"{internet_sayfa} sayfa"
            elif store_pages and isinstance(store_pages, int) and store_pages > 0:
                sayfa_sayisi = f"{store_pages} sayfa (Kobo)"
            else:
                sayfa_sayisi = "—"
            
            CACHE_SOZLUGU[cache_key] = {
                "kapak_url": kapak_url,
                "sayfa_sayisi": sayfa_sayisi
            }
        
        kitaplar.append({
            "id": id_counter,
            "volume_id": content_id,
            "kitap_adi": title,
            "yazar": yazar,
            "kategori": "Edebiyat",
            "kapak_url": kapak_url,
            "sayfa_sayisi": sayfa_sayisi,
            "alinti_sayisi": alinti_sayisi,
            "not_sayisi": not_sayisi
        })
        id_counter += 1
        
    baglanti.close()
    return kitaplar


@app.route('/')
def ana_sayfa():
    return render_template('kobo_project_index.html')


@app.route('/api/kitaplar')
def api_kitaplar():
    return jsonify(kobo_kitaplarini_getir())


@app.route('/api/kitap-detay/<path:volume_id>')
def api_kitap_detay(volume_id):
    if not os.path.exists(DB_PATH):
        return jsonify({"error": "Veritabanı bulunamadı"}), 404

    baglanti = sqlite3.connect(DB_PATH)
    imlec = baglanti.cursor()
    
    # DateCreated DESC ile kronolojik sıralama (en yeni en üstte)
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
        is_note = (item_type and item_type.lower() == 'note') or (annotation is not None and annotation.strip() != '')
        tur = "not" if is_note else "alinti"
        
        detay_listesi.append({
            "tur": tur,
            "alinti_metni": text if text else "",
            "kullanici_notu": annotation if annotation else "",
            "tarih": tarih_formatla(date_created), # GG.AA.YYYY - SS:DK formatı
            "ilerleme": f"%{int(progress * 100)}" if progress else ""
        })
        
    return jsonify(detay_listesi)


if __name__ == '__main__':
    app.run(debug=True, port=5000)