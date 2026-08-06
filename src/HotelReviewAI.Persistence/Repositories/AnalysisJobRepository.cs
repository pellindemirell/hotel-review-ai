using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class AnalysisJobRepository : GenericRepository<AnalysisJob>, IAnalysisJobRepository
{
    private readonly AppDbContext _dbContext;

    public AnalysisJobRepository(AppDbContext dbContext) : base(dbContext)
    {
        _dbContext = dbContext;
    }

    public async Task<AnalysisJob?> GetNextPendingAsync()
    {
        return await _dbContext.AnalysisJobs
            .Where(j => j.Status == AnalysisJobStatus.Pending)
            .OrderBy(j => j.CreatedAt)
            .FirstOrDefaultAsync();
    }

    // Kapma tek bir CTE + UPDATE ... RETURNING ifadesiyle yapılır:
    //  - FOR UPDATE SKIP LOCKED, aynı satırı iki worker'ın almasını imkânsız kılar
    //    (ileride birden fazla API örneği çalıştırılsa bile güvenli).
    //  - Tek ifade olduğu için ayrıca transaction gerekmiyor.
    //  - EF Core bu SQL'i üretemiyor (FOR UPDATE SKIP LOCKED yok, ExecuteUpdateAsync
    //    da etkilenen kimlikleri döndüremiyor), bu yüzden ham SQL.
    //  - DİKKAT: Ham SQL, AppDbContext'teki global "IsActive == true" query filter'ını
    //    atlar. GetNextPendingAsync ile aynı davranmak için filtre elle yazılıyor.
    //  - UpdatedAt'e "now()" yazılıyor, "now() AT TIME ZONE 'utc'" DEĞİL: kolon
    //    timestamptz ve ikincisi timestamp (tz'siz) üretiyor; timestamptz'ye
    //    atanınca oturum saat dilimine göre yeniden yorumlanıp UTC+3'te 3 saat
    //    geriye kayıyor. O durumda kapılan iş anında "takılı" görünüp reaper
    //    tarafından işlenirken Pending'e döndürülüyor ve yorum iki kez analiz
    //    ediliyordu (mükerrer ReviewAnalyses + ActionItems).
    private const string ClaimSql = """
        WITH claimed AS (
            SELECT "Id"
              FROM "AnalysisJobs"
             WHERE "Status" = {0} AND "IsActive"
             ORDER BY "CreatedAt"
             LIMIT {1}
             FOR UPDATE SKIP LOCKED
        )
        UPDATE "AnalysisJobs" j
           SET "Status" = {2},
               "UpdatedAt" = now()
          FROM claimed c
         WHERE j."Id" = c."Id"
        RETURNING j."Id" AS "Value"
        """;
    // "AS \"Value\"" şart: EF Core skaler SqlQuery/SqlQueryRaw sonuçlarını
    // "Value" adlı kolondan okur, aksi halde çalışma anında eşleme hatası verir.

    public async Task<IReadOnlyList<Guid>> ClaimPendingAsync(int batchSize, CancellationToken cancellationToken = default)
    {
        if (batchSize < 1)
        {
            batchSize = 1;
        }

        return await _dbContext.Database
            .SqlQueryRaw<Guid>(
                ClaimSql,
                (int)AnalysisJobStatus.Pending,
                batchSize,
                (int)AnalysisJobStatus.Processing)
            .ToListAsync(cancellationToken);
    }

    public async Task<int> ReapStuckProcessingAsync(TimeSpan olderThan, CancellationToken cancellationToken = default)
    {
        var cutoff = DateTime.UtcNow - olderThan;

        // UpdatedAt, ClaimPendingAsync tarafından kapma anında yazılıyor.
        // Hiç güncellenmemiş eski satırlar için CreatedAt'e düşülür.
        return await _dbContext.AnalysisJobs
            .Where(j => j.Status == AnalysisJobStatus.Processing
                        && (j.UpdatedAt ?? j.CreatedAt) < cutoff)
            .ExecuteUpdateAsync(
                setters => setters.SetProperty(j => j.Status, AnalysisJobStatus.Pending),
                cancellationToken);
    }

    public async Task<IEnumerable<AnalysisJob>> GetFailedJobsAsync()
    {
        return await _dbContext.AnalysisJobs
            .Where(j => j.Status == AnalysisJobStatus.Failed)
            .OrderByDescending(j => j.CreatedAt)
            .ToListAsync();
    }

    public async Task<int> DeleteCompletedBeforeAsync(System.DateTime cutoffDate)
    {
        var jobsToDelete = await _dbContext.AnalysisJobs
            .Where(j => j.Status == AnalysisJobStatus.Completed && j.ProcessedAt < cutoffDate)
            .ToListAsync();
            
        if (jobsToDelete.Any())
        {
            _dbContext.AnalysisJobs.RemoveRange(jobsToDelete);
            await _dbContext.SaveChangesAsync();
        }
        
        return jobsToDelete.Count;
    }
}
