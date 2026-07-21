using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;

namespace HotelReviewAI.Persistence.Interceptors;

/// <summary>
/// EF Core SaveChanges interceptor'ı.
/// Added/Modified/Deleted durumundaki her entity için AuditLog kaydı oluşturur.
/// </summary>
public class AuditInterceptor : SaveChangesInterceptor
{
    private readonly ICurrentUserService _currentUserService;

    public AuditInterceptor(ICurrentUserService currentUserService)
    {
        _currentUserService = currentUserService;
    }

    public override async ValueTask<InterceptionResult<int>> SavingChangesAsync(
        DbContextEventData eventData,
        InterceptionResult<int> result,
        CancellationToken cancellationToken = default)
    {
        if (eventData.Context is null)
            return await base.SavingChangesAsync(eventData, result, cancellationToken);

        var auditLogs = CreateAuditLogs(eventData.Context);

        if (auditLogs.Any())
        {
            await eventData.Context.Set<AuditLog>().AddRangeAsync(auditLogs, cancellationToken);
        }

        return await base.SavingChangesAsync(eventData, result, cancellationToken);
    }

    private List<AuditLog> CreateAuditLogs(DbContext context)
    {
        var logs = new List<AuditLog>();
        var userId = _currentUserService.UserId ?? Guid.Empty;

        var entries = context.ChangeTracker.Entries()
            .Where(e => e.State is EntityState.Added or EntityState.Modified or EntityState.Deleted)
            .Where(e => e.Entity is not AuditLog); // Döngü önleme

        foreach (var entry in entries)
        {
            var entityName = entry.Entity.GetType().Name;
            var entityId = entry.Entity is BaseEntity baseEntity ? baseEntity.Id : Guid.Empty;

            var action = entry.State switch
            {
                EntityState.Added => "CREATE",
                EntityState.Modified => "UPDATE",
                EntityState.Deleted => "DELETE",
                _ => "UNKNOWN"
            };

            logs.Add(new AuditLog
            {
                UserId = userId,
                Action = action,
                EntityName = entityName,
                EntityId = entityId
            });
        }

        return logs;
    }
}
