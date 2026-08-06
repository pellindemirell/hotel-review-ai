-- ============================================================================
--  purge_reviews.sql — tüm yorum verisini kalıcı olarak siler
-- ============================================================================
--
--  AMAÇ
--  Sistemdeki karışık kaynaklı (seed / elle yazılmış / eski scraper) yorumları
--  ve bunlardan türeyen her şeyi temizlemek; yerine gerçek Google Maps verisi
--  aktarılacak.
--
--  ÖNCE YAPILACAKLAR
--    1) TAM yedek alın (tablo alt kümesi DEĞİL — yanlış bir WHERE'e karşı tek
--       koruma budur):
--         pg_dump -h 192.168.40.140 -p 5432 -U stajor1 -d stajor \
--                 --format=custom --no-owner --no-privileges \
--                 -f ~/backups/stajor_$(date +%Y%m%d_%H%M%S).dump
--         pg_restore --list ~/backups/stajor_*.dump | head -40    # okunabilirlik
--    2) API'yi (:5012) DURDURUN. AnalysisBackgroundWorker 10 sn'de bir yokluyor;
--       çalışır durumdayken sildiğiniz satırlar için analiz yazabilir.
--    3) Bu script'i ÖNCE prova olarak çalıştırın: en alttaki COMMIT'i ROLLBACK
--       yapın, öncesi/sonrası sayımları okuyun, ancak ondan sonra gerçeğini
--       çalıştırın.
--
--  KULLANIM
--    psql -h 192.168.40.140 -p 5432 -U stajor1 -d stajor -f purge_reviews.sql
--
--  KAPSAM
--  Varsayılan: TÜM yorumlar (HotelId IS NULL olan otelsiz test satırları dahil).
--  Amaç "tüm yorumları değiştirmek" olduğu için ebeveyn tabloda WHERE yok —
--  bu, kapsamı yanlış yazmayı imkânsız kılar. Yalnızca 5 oteli hedeflemek
--  isterseniz aşağıdaki _t_reviews tanımındaki WHERE satırının yorumunu kaldırın.
--
--  NEYE DOKUNULMAZ
--    Hotels, Departments, ReviewCategories, Users, __EFMigrationsHistory.
--    Şemanın kendisi: bir TEMP TABLE dışında hiç DDL yok — DROP/TRUNCATE/ALTER
--    yok, kolon tipleri ve indeksler aynen kalır. Tüm PK'lar istemci tarafında
--    üretilen Guid olduğu için sıfırlanacak sequence de yok.
--    Bu güvenlidir çünkü şemadaki her yabancı anahtar çocuktan ebeveyne bakar:
--    Hotels/Departments/ReviewCategories/Users tablolarından Reviews'a giden
--    hiçbir FK yoktur, dolayısıyla çocuk silmek ebeveyni silemez.
--
--  KÜÇÜK HARFLİ absa_platform TABLOLARI (reviews, absa_auto, review_assignments,
--  gold_reviews, absa_corrections) BU SCRIPT'İN KAPSAMINDA DEĞİLDİR. Onlar ayrı
--  bir korpus; .NET hattı onları kullanmıyor. Ayrı karar, ayrı yedek.
-- ============================================================================

\set ON_ERROR_STOP on
\timing on

BEGIN;

\echo ''
\echo '=== ÖNCESİ ==='
SELECT 'Reviews'           AS tablo, count(*) AS satir FROM public."Reviews"
UNION ALL SELECT 'ReviewAnalyses',    count(*) FROM public."ReviewAnalyses"
UNION ALL SELECT 'ActionItems',       count(*) FROM public."ActionItems"
UNION ALL SELECT 'ReviewAttachments', count(*) FROM public."ReviewAttachments"
UNION ALL SELECT 'AnalysisJobs',      count(*) FROM public."AnalysisJobs"
UNION ALL SELECT 'AuditLogs',         count(*) FROM public."AuditLogs"
ORDER BY 1;

-- ---------------------------------------------------------------------------
-- 1) Hedef kimlik kümeleri ÖNCE yakalanır.
--    Zorunlu: AuditLogs temizliği çocuk kimliklerine ihtiyaç duyuyor ve o adıma
--    gelindiğinde satırlar çoktan silinmiş oluyor.
-- ---------------------------------------------------------------------------
CREATE TEMP TABLE _t_reviews ON COMMIT DROP AS
    SELECT "Id" FROM public."Reviews";
    -- Yalnızca 5 otel isteniyorsa yukarıdaki satırı şununla değiştirin:
    -- SELECT "Id" FROM public."Reviews" WHERE "HotelId" IS NOT NULL;

CREATE TEMP TABLE _t_analyses ON COMMIT DROP AS
    SELECT "Id" FROM public."ReviewAnalyses"
     WHERE "ReviewId" IN (SELECT "Id" FROM _t_reviews);

CREATE TEMP TABLE _t_actions ON COMMIT DROP AS
    SELECT "Id" FROM public."ActionItems"
     WHERE "ReviewId" IN (SELECT "Id" FROM _t_reviews);

CREATE TEMP TABLE _t_attach ON COMMIT DROP AS
    SELECT "Id" FROM public."ReviewAttachments"
     WHERE "ReviewId" IN (SELECT "Id" FROM _t_reviews);

-- Hedef işler + önceden kalmış yetimler birlikte yakalanır; böylece 5. adımdaki
-- AuditLogs temizliği yetim işlerin denetim kayıtlarını da alır.
CREATE TEMP TABLE _t_jobs ON COMMIT DROP AS
    SELECT "Id" FROM public."AnalysisJobs"
     WHERE "ReviewId" IN (SELECT "Id" FROM _t_reviews)
        OR NOT EXISTS (SELECT 1 FROM public."Reviews" r
                        WHERE r."Id" = public."AnalysisJobs"."ReviewId");

\echo ''
\echo '=== SİLİNECEK ==='
SELECT 'Reviews'           AS tablo, count(*) AS silinecek FROM _t_reviews
UNION ALL SELECT 'ReviewAnalyses',    count(*) FROM _t_analyses
UNION ALL SELECT 'ActionItems',       count(*) FROM _t_actions
UNION ALL SELECT 'ReviewAttachments', count(*) FROM _t_attach
UNION ALL SELECT 'AnalysisJobs',      count(*) FROM _t_jobs
ORDER BY 1;

-- ---------------------------------------------------------------------------
-- 2) Çocuklar. FK'ları zaten CASCADE ama her biri ayrı ayrı silinir ki
--    psql her adımın satır sayısını yazsın ve beklenmedik bir sayı görülsün.
-- ---------------------------------------------------------------------------
\echo ''
\echo '--- ReviewAnalyses ---'
DELETE FROM public."ReviewAnalyses"    WHERE "Id" IN (SELECT "Id" FROM _t_analyses);
\echo '--- ActionItems ---'
DELETE FROM public."ActionItems"       WHERE "Id" IN (SELECT "Id" FROM _t_actions);
\echo '--- ReviewAttachments ---'
DELETE FROM public."ReviewAttachments" WHERE "Id" IN (SELECT "Id" FROM _t_attach);

-- ---------------------------------------------------------------------------
-- 3) AnalysisJobs: ReviewId düz bir Guid kolonu, YABANCI ANAHTAR YOK.
--    Cascade ile gitmez, açıkça silinmesi gerekir.
-- ---------------------------------------------------------------------------
\echo '--- AnalysisJobs (hedef + yetimler) ---'
DELETE FROM public."AnalysisJobs" WHERE "Id" IN (SELECT "Id" FROM _t_jobs);

-- ---------------------------------------------------------------------------
-- 4) Ebeveyn
-- ---------------------------------------------------------------------------
\echo '--- Reviews ---'
DELETE FROM public."Reviews" WHERE "Id" IN (SELECT "Id" FROM _t_reviews);

-- ---------------------------------------------------------------------------
-- 5) AuditLogs: kayıtlara (EntityName, EntityId) ikilisiyle bağlı, FK yok.
--    IX_AuditLogs_EntityName sayesinde ucuz.
--    User / ReviewCategory / Department kayıtları KORUNUR.
-- ---------------------------------------------------------------------------
\echo '--- AuditLogs ---'
DELETE FROM public."AuditLogs" a
 WHERE (a."EntityName" = 'Review'           AND a."EntityId" IN (SELECT "Id" FROM _t_reviews))
    OR (a."EntityName" = 'ReviewAnalysis'   AND a."EntityId" IN (SELECT "Id" FROM _t_analyses))
    OR (a."EntityName" = 'ActionItem'       AND a."EntityId" IN (SELECT "Id" FROM _t_actions))
    OR (a."EntityName" = 'ReviewAttachment' AND a."EntityId" IN (SELECT "Id" FROM _t_attach))
    OR (a."EntityName" = 'AnalysisJob'      AND a."EntityId" IN (SELECT "Id" FROM _t_jobs));

-- ---------------------------------------------------------------------------
-- 6) Önceki silmelerden kalmış YETİM denetim kayıtları.
--    Yukarıdaki adım yalnızca bu çalıştırmada var olan kayıtların loglarını
--    siliyor; veritabanında bunlardan bağımsız ~22.800 satır daha vardı
--    (artık var olmayan yorum/analiz/aksiyon kayıtlarına işaret ediyorlar).
--    Yalnızca yorum ailesi temizlenir; User / ReviewCategory / Department
--    denetim geçmişine DOKUNULMAZ.
-- ---------------------------------------------------------------------------
\echo '--- AuditLogs (yetim yorum ailesi kayıtları) ---'
DELETE FROM public."AuditLogs" a
 WHERE a."EntityName" IN ('Review', 'ReviewAnalysis', 'ActionItem', 'ReviewAttachment', 'AnalysisJob')
   AND NOT EXISTS (SELECT 1 FROM public."Reviews"           x WHERE x."Id" = a."EntityId")
   AND NOT EXISTS (SELECT 1 FROM public."ReviewAnalyses"    x WHERE x."Id" = a."EntityId")
   AND NOT EXISTS (SELECT 1 FROM public."ActionItems"       x WHERE x."Id" = a."EntityId")
   AND NOT EXISTS (SELECT 1 FROM public."ReviewAttachments" x WHERE x."Id" = a."EntityId")
   AND NOT EXISTS (SELECT 1 FROM public."AnalysisJobs"      x WHERE x."Id" = a."EntityId");

\echo ''
\echo '=== SONRASI (yorum ailesi sıfırlanmalı) ==='
SELECT 'Reviews'           AS tablo, count(*) AS satir FROM public."Reviews"
UNION ALL SELECT 'ReviewAnalyses',    count(*) FROM public."ReviewAnalyses"
UNION ALL SELECT 'ActionItems',       count(*) FROM public."ActionItems"
UNION ALL SELECT 'ReviewAttachments', count(*) FROM public."ReviewAttachments"
UNION ALL SELECT 'AnalysisJobs',      count(*) FROM public."AnalysisJobs"
UNION ALL SELECT 'AuditLogs',         count(*) FROM public."AuditLogs"
ORDER BY 1;

\echo ''
\echo '=== REFERANS VERİ (DEĞİŞMEMELİ) ==='
SELECT 'Hotels'           AS tablo, count(*) AS satir FROM public."Hotels"
UNION ALL SELECT 'Departments',      count(*) FROM public."Departments"
UNION ALL SELECT 'ReviewCategories', count(*) FROM public."ReviewCategories"
UNION ALL SELECT 'Users',            count(*) FROM public."Users"
ORDER BY 1;

-- ############################################################################
--  PROVA İÇİN: aşağıyı ROLLBACK yapın.
--  GERÇEK SİLME İÇİN: COMMIT bırakın.
-- ############################################################################
ROLLBACK;
-- COMMIT;

-- Silme sonrası (transaction DIŞINDA) çalıştırılabilir:
--   VACUUM ANALYZE public."AuditLogs", public."ReviewAnalyses", public."Reviews";
