import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd

# UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

script_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(script_dir, "app")):
    sys.path.insert(0, script_dir)
elif os.path.exists(os.path.join(script_dir, "ai-service", "app")):
    sys.path.insert(0, os.path.join(script_dir, "ai-service"))
else:
    sys.path.insert(0, script_dir)

from app.services.absa_service import AbsaService

class OtelAbsaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🏨 Otel ABSA Yorum Analiz Programı v2.0")
        self.root.geometry("800x640")
        self.root.minsize(700, 500)
        self.root.resizable(True, True)

        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        self.bg_color = "#1E1E2E"
        self.card_bg = "#2A2A3D"
        self.accent_color = "#74C7EC"
        self.text_color = "#CDD6F4"
        self.btn_bg = "#89B4FA"
        self.btn_hover = "#B4BEFE"

        self.root.configure(bg=self.bg_color)

        self.input_file_path = ""
        self.output_file_path = ""
        self.is_running = False

        self._create_widgets()

    def _create_widgets(self):
        # Top Header
        header_frame = tk.Frame(self.root, bg=self.bg_color)
        header_frame.pack(fill="x", padx=15, pady=(10, 4))

        title_lbl = tk.Label(
            header_frame, 
            text="🏨 Otel Restoran ABSA Akıllı Yorum Analiz Aracı", 
            font=("Segoe UI", 14, "bold"), 
            bg=self.bg_color, 
            fg=self.accent_color
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            header_frame, 
            text="Excel (.xlsx) veya CSV dosyanızı seçin ve analizi başlatın.", 
            font=("Segoe UI", 9), 
            bg=self.bg_color, 
            fg="#A6ADC8"
        )
        subtitle_lbl.pack(anchor="w", pady=(1, 0))

        # File selection box
        file_frame = tk.LabelFrame(
            self.root, 
            text=" 📁 Dosya Seçimi ", 
            font=("Segoe UI", 9, "bold"), 
            bg=self.card_bg, 
            fg=self.text_color, 
            bd=1, 
            relief="solid"
        )
        file_frame.pack(fill="x", padx=15, pady=4, ipady=2)

        self.file_entry = tk.Entry(
            file_frame, 
            font=("Segoe UI", 9), 
            bg="#181825", 
            fg=self.text_color, 
            insertbackground=self.text_color,
            bd=1, 
            relief="flat"
        )
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(8, 6), pady=5, ipady=3)

        btn_browse = tk.Button(
            file_frame, 
            text="📂 Dosya Seç...", 
            font=("Segoe UI", 9, "bold"), 
            bg=self.btn_bg, 
            fg="#11111B", 
            activebackground=self.btn_hover,
            bd=0, 
            padx=10, 
            pady=3, 
            cursor="hand2",
            command=self._browse_file
        )
        btn_browse.pack(side="right", padx=(0, 8), pady=5)

        # Progress bar frame
        prog_frame = tk.LabelFrame(
            self.root, 
            text=" ⚡ Analiz Durumu ve İlerleme ", 
            font=("Segoe UI", 9, "bold"), 
            bg=self.card_bg, 
            fg=self.text_color, 
            bd=1, 
            relief="solid"
        )
        prog_frame.pack(fill="x", padx=15, pady=4, ipady=2)

        self.status_lbl = tk.Label(
            prog_frame, 
            text="Hazır - Lütfen analiz edilecek dosyayı seçip ▶️ Analizi Başlat butonuna basın.", 
            font=("Segoe UI", 9, "bold"), 
            bg=self.card_bg, 
            fg="#A6E3A1"
        )
        self.status_lbl.pack(anchor="w", padx=10, pady=(4, 1))

        self.progress_bar = ttk.Progressbar(prog_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", padx=10, pady=4)

        # Action Buttons right above log area so they are ALWAYS VISIBLE!
        btn_action_frame = tk.Frame(self.root, bg=self.bg_color)
        btn_action_frame.pack(fill="x", padx=15, pady=4)

        self.btn_start = tk.Button(
            btn_action_frame, 
            text="▶️ Analizi Başlat", 
            font=("Segoe UI", 10, "bold"), 
            bg="#A6E3A1", 
            fg="#11111B", 
            activebackground="#94E2D5",
            bd=0, 
            padx=16, 
            pady=6, 
            cursor="hand2",
            command=self._start_analysis_thread
        )
        self.btn_start.pack(side="left")

        self.btn_open_result = tk.Button(
            btn_action_frame, 
            text="📊 Sonuç Excel Dosyasını Aç", 
            font=("Segoe UI", 10, "bold"), 
            bg="#FAB387", 
            fg="#11111B", 
            activebackground="#F9E2AF",
            bd=0, 
            padx=14, 
            pady=6, 
            cursor="hand2",
            state="disabled",
            command=self._open_result_file
        )
        self.btn_open_result.pack(side="right")

        # Flexible Live Log Text Box (Expands to fill available window space)
        log_frame = tk.LabelFrame(
            self.root, 
            text=" 📺 Canlı Analiz Akış Ekranı ", 
            font=("Segoe UI", 9, "bold"), 
            bg=self.card_bg, 
            fg=self.text_color, 
            bd=1, 
            relief="solid"
        )
        log_frame.pack(fill="both", expand=True, padx=15, pady=(4, 10))

        self.log_text = tk.Text(
            log_frame, 
            font=("Consolas", 9), 
            bg="#11111B", 
            fg="#CDD6F4", 
            bd=0, 
            relief="flat", 
            wrap="word"
        )
        self.log_text.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y", pady=4)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def _log(self, message):
        if threading.current_thread() is threading.main_thread():
            self.log_text.insert("end", str(message) + "\n")
            self.log_text.see("end")
        else:
            self.root.after(0, lambda: self._log(message))

    def _browse_file(self):
        file_selected = filedialog.askopenfilename(
            title="Analiz Edilecek Yorum Dosyasını Seçin",
            filetypes=[("Excel ve CSV Dosyaları", "*.xlsx *.xls *.csv"), ("Tüm Dosyalar", "*.*")]
        )
        if file_selected:
            self.input_file_path = file_selected
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, file_selected)
            self._log(f"📁 Dosya Seçildi: {file_selected}")

    def _open_result_file(self):
        if self.output_file_path and os.path.exists(self.output_file_path):
            try:
                os.startfile(self.output_file_path)
            except AttributeError:
                import subprocess
                subprocess.call(["open" if sys.platform == "darwin" else "xdg-open", self.output_file_path])
        else:
            messagebox.showwarning("Uyarı", "Sonuç dosyası henüz oluşturulmadı!")

    def _start_analysis_thread(self):
        path = self.file_entry.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("Hata", "Lütfen geçerli bir Excel veya CSV dosyası seçin!")
            return

        if self.is_running:
            return

        self.is_running = True
        self.btn_start.config(state="disabled", bg="#6C7086")
        self.btn_open_result.config(state="disabled")
        self.progress_bar["value"] = 0
        self.status_lbl.config(text="Analiz Başlatılıyor...", fg="#F9E2AF")

        threading.Thread(target=self._run_analysis, args=(path,), daemon=True).start()

    def _run_analysis(self, input_path):
        start_time = time.time()
        try:
            self._log("\n" + "="*50)
            self._log(f"=== TOPLU ABSA YORUM ANALİZİ BAŞLATILDI ===")
            self._log(f"Girdi Dosyası: {input_path}")

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

            self._log(f"Kaynak Yorum Sütunu: '{comment_col}'")
            if ref_col:
                self._log(f"Referans Bölünmüş Sütun: '{ref_col}' (Cümlecik Doğrulaması Aktif)")

            raw_comments = df[comment_col].dropna().astype(str).tolist()
            ref_comments = df[ref_col].astype(str).tolist() if ref_col and ref_col in df.columns else [None] * len(raw_comments)

            total_comments = len(raw_comments)
            self._log(f"Toplam Analiz Edilecek Yorum Sayısı: {total_comments}\n")

            base, ext = os.path.splitext(input_path)
            out_ext = ".xlsx" if is_excel else ".csv"
            self.output_file_path = f"{base}_absa_analiz_sonuclari{out_ext}"

            output_rows = []
            processed_ids = set()

            if os.path.exists(self.output_file_path):
                try:
                    exist_df = pd.read_excel(self.output_file_path) if is_excel else pd.read_csv(self.output_file_path)
                    if "Yorum_ID" in exist_df.columns:
                        processed_ids = set(exist_df["Yorum_ID"].dropna().astype(int).tolist())
                        output_rows = exist_df.to_dict("records")
                        self._log(f"🔄 [KALDIĞI YERDEN DEVAM] Önceden işlenen {len(processed_ids)} yorum algılandı!")
                except Exception as e:
                    self._log(f"Uyarı: Mevcut çıktı okunurken durum oluştu: {e}")

            def _save_progress():
                if output_rows:
                    out_df = pd.DataFrame(output_rows)
                    if "Yorum_ID" in out_df.columns:
                        out_df = out_df.sort_values(by="Yorum_ID")
                    if self.output_file_path.endswith(".xlsx"):
                        out_df.to_excel(self.output_file_path, index=False, engine="openpyxl")
                    else:
                        out_df.to_csv(self.output_file_path, index=False, encoding="utf-8-sig")

            anomalies_found = sum(1 for r in output_rows if r.get("Anomali_Bayrağı") == "EVET")
            split_mismatches = sum(1 for r in output_rows if r.get("Bölünme_Uyum_Durumu") == "FARKLI_BÖLÜNMÜŞ")
            completed_count = len(processed_ids)

            # Cold-start warmup
            try:
                AbsaService.analyze_multidomain("Warmup otel yorumu harika bir yer.")
            except Exception:
                pass

            for idx, (text, ref_text) in enumerate(zip(raw_comments, ref_comments), 1):
                clean_text = text.strip()
                if not clean_text or len(clean_text) < 5:
                    continue

                if idx in processed_ids:
                    continue

                completed_count += 1
                pct = (completed_count / total_comments) * 100
                preview = clean_text[:40].replace("\n", " ")

                self.root.after(0, self._update_progress_ui, completed_count, total_comments, pct, idx, preview)

                try:
                    res = AbsaService.analyze_multidomain(clean_text)
                    sys_clauses = [asp.clause.strip() for asp in res.aspects if asp.clause.strip()]

                    ref_clauses = []
                    split_status = "BİLGİ_YOK"
                    split_match_pct = 100.0

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
                            split_mismatches += 1

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
                            anomalies_found += 1

                        output_rows.append({
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
                except Exception as e:
                    self._log(f"Hata [Yorum {idx}]: {e}")

                if completed_count % 10 == 0:
                    _save_progress()

            _save_progress()
            elapsed = time.time() - start_time
            self.root.after(0, self._analysis_completed_ui, len(output_rows), split_mismatches, anomalies_found, elapsed)

        except Exception as e:
            self.root.after(0, self._analysis_failed_ui, str(e))

    def _update_progress_ui(self, count, total, pct, idx, text):
        self.progress_bar["value"] = pct
        self.status_lbl.config(text=f"⚡ Analiz Ediliyor: [{count}/{total}] (%{pct:.1f}) - Yorum #{idx}", fg="#74C7EC")
        preview = text.replace("\n", " ").replace("\r", " ")
        self._log(f"[{count}/{total}] (%{pct:.1f}) Yorum #{idx} -> '{preview}...'")

    def _analysis_completed_ui(self, total_clauses, mismatches, anomalies, elapsed):
        self.is_running = False
        self.progress_bar["value"] = 100
        self.status_lbl.config(text="✅ Analiz Tamamlandı!", fg="#A6E3A1")
        self.btn_start.config(state="normal", bg="#A6E3A1")
        self.btn_open_result.config(state="normal", bg="#FAB387")

        self._log("\n" + "="*50)
        self._log("🎉 ANALİZ BAŞARIYLA TAMAMLANDI!")
        self._log(f"⏱️ Toplam Süre: {elapsed:.1f} saniye")
        self._log(f"📊 Toplam Cümlecik: {total_clauses}")
        self._log(f"⚠️ Anomali Sayısı: {anomalies}")
        self._log(f"💾 Sonuç Excel: {self.output_file_path}")
        self._log("="*50 + "\n")

        messagebox.showinfo("Başarılı", f"Analiz Tamamlandı!\n\nToplam Cümlecik: {total_clauses}\nHarcanan Süre: {elapsed:.1f} sn\n\nSonuç dosyası kaydedildi:\n{self.output_file_path}")

    def _analysis_failed_ui(self, err_msg):
        self.is_running = False
        self.status_lbl.config(text="❌ Hata Oluştu!", fg="#F38BA8")
        self.btn_start.config(state="normal", bg="#A6E3A1")
        self._log(f"\nHATA: {err_msg}")
        messagebox.showerror("Hata", f"Analiz sırasında bir hata oluştu:\n{err_msg}")

if __name__ == "__main__":
    root = tk.Tk()
    app = OtelAbsaApp(root)
    root.mainloop()
