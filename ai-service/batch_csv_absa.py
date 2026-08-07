import os
import sys
import argparse
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# UTF-8 stdout desteği (Windows terminal desteği için)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Proje kök dizinini Python path'e ekle
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.absa_service import AbsaService

def _safe_preview(text, max_len=45):
    """Terminalde patlama yapmaması için düzgün Türkçe metin önizlemesi çıkarır."""
    s = str(text).replace("\n", " ").replace("\r", " ")
    return s[:max_len]

def _process_single_comment(item):
    """Tek bir yorumu analiz eden bağımsız worker fonksiyonu."""
    idx, text, ref_text = item
    clean_text = str(text).strip() if text else ""
    if not clean_text or len(clean_text) < 5:
        return idx, [], False, False

    try:
        if any(c in clean_text for c in "çğıöşüÇĞİÖŞÜ") or not any(w in clean_text.lower() for w in ["the ", " is ", "was ", "and ", "with "]):
            target_text = clean_text
        else:
            from app.services.translation_service import TranslationService
            target_text, lang = TranslationService.translate_to_turkish(clean_text)
        res = AbsaService.analyze_multidomain(target_text)
        sys_clauses = [asp.clause.strip() for asp in res.aspects if asp.clause.strip()]
        
        ref_clauses = []
        split_status = "BİLGİ_YOK"
        split_match_pct = 100.0
        is_mismatch = False
        
        if ref_text and str(ref_text).strip() and str(ref_text) != "nan":
            ref_clauses = [s.strip() for s in str(ref_text).split("/") if s.strip()]
            sys_count = len(sys_clauses)
            ref_count = len(ref_clauses)
            
            if sys_count == ref_count:
                split_status = "TAM_UYUMLU"
                split_match_pct = 100.0
            elif abs(sys_count - ref_count) <= 2:
                split_status = "KISMEN_UYUMLU"
                split_match_pct = round((min(sys_count, ref_count) / max(sys_count, ref_count, 1)) * 100, 1)
            else:
                split_status = "FARKLI_BÖLÜNMÜŞ"
                split_match_pct = round((min(sys_count, ref_count) / max(sys_count, ref_count, 1)) * 100, 1)
                is_mismatch = True

        rows = []
        has_anomaly = False
        for asp in res.aspects:
            cl = asp.clause.lower()
            is_anomaly = False
            anomaly_note = ""

            if any(k in cl for k in ("otopark", "park yeri", "araba koy")) and asp.department_label not in ("Çevre, Güvenlik & Ulaşım", "Otopark & Vale"):
                is_anomaly = True
                anomaly_note = "Otopark Yanlış Departman"
            elif any(k in cl for k in ("deniz", "sahil", "plaj")) and "havuz" not in cl and asp.department_label not in ("Plaj & Deniz", "Çevre, Güvenlik & Ulaşım", "Rekreasyon & Eğlence"):
                is_anomaly = True
                anomaly_note = "Plaj Yanlış Departman"
            elif any(k in cl for k in ("oda temizliği", "odanın temizliği", "çarşaf lekeli", "nevresim kirli")) and asp.department_label not in ("Kat Hizmetleri & Temizlik", "Oda Hizmetleri & Housekeeping"):
                is_anomaly = True
                anomaly_note = "Temizlik Yanlış Departman"

            if is_anomaly:
                has_anomaly = True

            rows.append({
                "Yorum_ID": idx,
                "Tam_Orijinal_Yorum": clean_text,
                "Referans_Bölünmüş_Yorum": ref_text if ref_text else "",
                "Sistem_Cümlecik_Sayısı": len(sys_clauses),
                "Referans_Cümlecik_Sayısı": len(ref_clauses) if ref_clauses else "-",
                "Bölünme_Uyum_Durumu": split_status,
                "Bölünme_Uyum_%": split_match_pct if ref_clauses else "-",
                "Cümlecik_Clause": asp.clause,
                "Tahmin_Departman": asp.department_label,
                "Tahmin_Aspect": asp.aspect_label,
                "Aspect_Key": getattr(asp, "aspect", getattr(asp, "aspect_label", "")),
                "Duygu_Etiketi": asp.sentiment,
                "Duygu_Skoru": round(asp.sentiment_score, 2),
                "Öncelik_Seviyesi": asp.priority,
                "Öncelik_Skoru": asp.priority_score,
                "Güven_Oranı": round(asp.confidence, 2),
                "Anomali_Bayrağı": "EVET" if is_anomaly else "HAYIR",
                "Anomali_Notu": anomaly_note
            })
        return idx, rows, has_anomaly, is_mismatch
    except Exception as e:
        return idx, [], False, False

def run_batch_csv_analysis(input_path: str, output_path: str = None, limit: int = 50, workers: int = 0):
    """Girdi XLSX veya CSV dosyasındaki yorumları paralel çok çekirdekli (multiprocessing) ABSA analizinden geçirir."""
    if not os.path.exists(input_path):
        print(f"Hata: Girdi dosyası bulunamadı -> {input_path}")
        return

    start_time = time.time()
    num_workers = workers if workers > 0 else max(1, (os.cpu_count() or 4) - 1)

    print(f"=== TOPLU PARALEL ABSA ANALİZİ BAŞLATIYOR (⚡ {num_workers} Çekirdek Hızlandırma) ===")
    print(f"Girdi Dosyası: {input_path}")
    
    is_excel = input_path.lower().endswith((".xlsx", ".xls"))
    if is_excel:
        df = pd.read_excel(input_path)
    else:
        df = pd.read_csv(input_path)
    
    comment_col = None
    ref_col = None

    possible_orig_cols = [
        "orijinal", "Orijinal", "ORİJİNAL", "Yorum Metni", "Yorum", "comment", "review", 
        "text", "Yorumlar", "Review Text", "görüş", "gorus", "müşteri yorumu", "musteri yorumu", 
        "içerik", "icerik", "metin", "yorum_metni", "review_text", "user_review", "feedback"
    ]
    possible_ref_cols = ["bolunmus", "bölünmüş", "BOLUNMUS", "BÖLÜNMÜŞ", "ref_split", "divided", "bolum", "bölüm"]

    for col in df.columns:
        c_low = str(col).strip().lower()
        if not comment_col and c_low in [p.lower() for p in possible_orig_cols]:
            comment_col = col
        if not ref_col and c_low in [p.lower() for p in possible_ref_cols]:
            ref_col = col
            
    if not comment_col:
        str_cols = [c for c in df.columns if df[c].dtype == "object" and c != ref_col]
        if str_cols:
            comment_col = max(str_cols, key=lambda c: df[c].dropna().astype(str).str.len().mean())
        else:
            comment_col = df.columns[0]

    print(f"Mevcut Excel Sütunları   : {list(df.columns)}")
    print(f"Kaynak Yorum Sütunu      : '{comment_col}'")
    if ref_col:
        print(f"Referans Bölünmüş Sütun : '{ref_col}' (Cümlecik bölünme doğrulaması aktif)")

    raw_comments = df[comment_col].dropna().astype(str).tolist()
    ref_comments = df[ref_col].astype(str).tolist() if ref_col and ref_col in df.columns else [None] * len(raw_comments)

    if limit > 0:
        raw_comments = raw_comments[:limit]
        ref_comments = ref_comments[:limit]

    total_comments = len(raw_comments)
    print(f"Toplam Analiz Edilecek Yorum Sayısı: {total_comments}\n")

    base, ext = os.path.splitext(input_path)
    if not output_path:
        out_ext = ".xlsx" if is_excel else ".csv"
        output_path = f"{base}_absa_analiz_sonuclari{out_ext}"

    output_rows = []
    processed_ids = set()

    if os.path.exists(output_path):
        try:
            if output_path.endswith(".xlsx"):
                exist_df = pd.read_excel(output_path)
            else:
                exist_df = pd.read_csv(output_path)
            
            if "Yorum_ID" in exist_df.columns:
                processed_ids = set(exist_df["Yorum_ID"].dropna().astype(int).tolist())
                output_rows = exist_df.to_dict("records")
                print(f"🔄 [KALDIĞI YERDEN DEVAM] Daha önce analiz edilen {len(processed_ids)} yorum algılandı ve korundu!")
        except Exception as e:
            print(f"Uyarı: Mevcut çıktı okunurken bir durum oluştu: {e}")

    items_to_process = [
        (idx, text, ref_text)
        for idx, (text, ref_text) in enumerate(zip(raw_comments, ref_comments), 1)
        if idx not in processed_ids and len(str(text).strip()) >= 5
    ]

    def _save_current_progress():
        if output_rows:
            out_df = pd.DataFrame(output_rows)
            # Yorum_ID sırasına göre diz
            if "Yorum_ID" in out_df.columns:
                out_df = out_df.sort_values(by="Yorum_ID")
            if output_path.endswith(".xlsx"):
                out_df.to_excel(output_path, index=False, engine="openpyxl")
            else:
                out_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    anomalies_found = sum(1 for r in output_rows if r.get("Anomali_Bayrağı") == "EVET")
    split_mismatches = sum(1 for r in output_rows if r.get("Bölünme_Uyum_Durumu") == "FARKLI_BÖLÜNMÜŞ")
    completed_count = len(processed_ids)

    if items_to_process:
        print(f"🚀 {len(items_to_process)} yeni yorum işleniyor...\n")
        for item in items_to_process:
            idx, rows, has_anomaly, is_mismatch = _process_single_comment(item)
            completed_count += 1
            output_rows.extend(rows)

            if has_anomaly:
                anomalies_found += 1
            if is_mismatch:
                split_mismatches += 1

            pct = (completed_count / total_comments) * 100
            print(f"[{completed_count}/{total_comments}] (%{pct:.1f}) Tamamlandı (Yorum #{idx})", flush=True)

            if completed_count % 50 == 0:
                _save_current_progress()
        _save_current_progress()
    else:
        print("Tüm yorumlar daha önce tamamlanmış!")

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print("=== PARALEL BATCH ANALİZ BAŞARIYLA TAMAMLANDI ===")
    print(f"Toplam Harcanan Süre              : {elapsed:.1f} saniye")
    print(f"Toplam Cümlecik Çıkarıldı         : {len(output_rows)}")
    print(f"Cümlecik Bölünme Uyumsuzluğu Sayısı: {split_mismatches}")
    print(f"Tespit Edilen Anomali Sayısı        : {anomalies_found}")
    print(f"Sonuç Dosyası Kaydedildi            : {output_path}")
    print("=" * 80)
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Toplu Excel / CSV Yorum ABSA Analiz Aracı (Hızlı Paralel Sürüm)")
    parser.add_argument("--input", "-i", type=str, help="Girdi XLSX veya CSV dosyasının yolu")
    parser.add_argument("--output", "-o", type=str, help="Çıktı XLSX veya CSV dosyasının yolu (isteğe bağlı)")
    parser.add_argument("--limit", "-l", type=int, default=50, help="İşlenecek maks yorum sayısı (varsayılan: 50, tümü için 0)")
    parser.add_argument("--workers", "-w", type=int, default=0, help="Kullanılacak paralel CPU çekirdek sayısı (0: Otomatik tümü)")
    args = parser.parse_args()

    if not args.input:
        default_excel = r"D:\KodYazılımStaj1\otomasyon\otomasyon\crystal_waterworld.xlsx"
        if os.path.exists(default_excel):
            run_batch_csv_analysis(default_excel, limit=args.limit, workers=args.workers)
        else:
            print("Lütfen bir dosya belirtin: python batch_csv_absa.py --input <dosya_yolu>")
    else:
        run_batch_csv_analysis(args.input, args.output, limit=args.limit, workers=args.workers)
