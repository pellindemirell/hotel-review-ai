-- ============================================================================
--  purge_absa_platform.sql — absa_platform korpusunu kalıcı olarak siler
-- ============================================================================
--
--  KAPSAM
--  Aynı `stajor` veritabanında yaşayan, absa_platform'a (etiketleme aracı) ait
--  KÜÇÜK HARFLİ tablolar. Bunlar .NET tarafındaki büyük harfli "Reviews"/"Users"
--  tablolarından TAMAMEN AYRIDIR ve analiz hattı (POST /analyze-review) onları
--  hiç kullanmaz — o uç nokta durumsuzdur, hiçbir şey kaydetmez.
--
--  Silinecek (13-16 Temmuz'da yüklenmiş korpus):
--      absa_auto            ~23.606   otomatik ABSA etiketleri
--      absa_corrections          ~0   insan düzeltmeleri
--      review_assignments     ~5.000  etiketleme kuyruğu (tamamı 'pending')
--      reviews               ~23.606  korpus (%64 booking.com, ağırlıklı Londra otelleri)
--      gold_reviews               ~1  altın (eğitim) veri seti
--
--  DOKUNULMAYAN
--      users (küçük harfli) — etiketleyici hesapları; yorum verisi değil,
--      review_assignments/absa_corrections tarafından referans alınıyordu ama
--      o satırlar silindiği için artık serbest. Silinmesi istenirse en sona
--      "DELETE FROM public.users;" eklenmesi yeterli.
--      Büyük harfli .NET tablolarının hiçbiri.
--
--  ÖNCE
--    Tam yedek alın (purge_reviews.sql ile aynı yedek iki iş için de yeterlidir):
--      pg_dump -h 192.168.40.140 -p 5432 -U stajor1 -d stajor \
--              --format=custom --no-owner --no-privileges -f ~/backups/<ad>.dump
--
--  KULLANIM
--    psql -h 192.168.40.140 -p 5432 -U stajor1 -d stajor -f purge_absa_platform.sql
--    Önce ROLLBACK ile prova edin, sonra COMMIT'e çevirin.
-- ============================================================================

\set ON_ERROR_STOP on
\timing on

BEGIN;

\echo ''
\echo '=== ÖNCESİ ==='
SELECT 'reviews'            AS tablo, count(*) AS satir FROM public.reviews
UNION ALL SELECT 'absa_auto',          count(*) FROM public.absa_auto
UNION ALL SELECT 'absa_corrections',   count(*) FROM public.absa_corrections
UNION ALL SELECT 'review_assignments', count(*) FROM public.review_assignments
UNION ALL SELECT 'gold_reviews',       count(*) FROM public.gold_reviews
UNION ALL SELECT 'users (korunacak)',  count(*) FROM public.users
ORDER BY 1;

-- ---------------------------------------------------------------------------
-- FK sırası: hepsi reviews(id)'ye bakıyor, önce çocuklar.
--   absa_auto.review_id          -> reviews.id
--   absa_corrections.review_id   -> reviews.id,  .user_id -> users.id
--   review_assignments.review_id -> reviews.id,  .user_id -> users.id
--   gold_reviews                 -> FK yok, bağımsız
-- ---------------------------------------------------------------------------
\echo ''
\echo '--- absa_auto ---'
DELETE FROM public.absa_auto;
\echo '--- absa_corrections ---'
DELETE FROM public.absa_corrections;
\echo '--- review_assignments ---'
DELETE FROM public.review_assignments;
\echo '--- reviews ---'
DELETE FROM public.reviews;
\echo '--- gold_reviews ---'
DELETE FROM public.gold_reviews;

\echo ''
\echo '=== SONRASI (users hariç hepsi 0 olmalı) ==='
SELECT 'reviews'            AS tablo, count(*) AS satir FROM public.reviews
UNION ALL SELECT 'absa_auto',          count(*) FROM public.absa_auto
UNION ALL SELECT 'absa_corrections',   count(*) FROM public.absa_corrections
UNION ALL SELECT 'review_assignments', count(*) FROM public.review_assignments
UNION ALL SELECT 'gold_reviews',       count(*) FROM public.gold_reviews
UNION ALL SELECT 'users (korunacak)',  count(*) FROM public.users
ORDER BY 1;

\echo ''
\echo '=== .NET TABLOLARI (DEĞİŞMEMELİ) ==='
SELECT 'Reviews'          AS tablo, count(*) AS satir FROM public."Reviews"
UNION ALL SELECT 'Hotels',           count(*) FROM public."Hotels"
UNION ALL SELECT 'ReviewCategories', count(*) FROM public."ReviewCategories"
UNION ALL SELECT 'Users',            count(*) FROM public."Users"
ORDER BY 1;

-- ############################################################################
--  PROVA İÇİN: ROLLBACK bırakın.  GERÇEK SİLME İÇİN: COMMIT'e çevirin.
-- ############################################################################
ROLLBACK;
-- COMMIT;
