using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using System;
using System.Threading.Tasks;

namespace HotelReviewAI.Api.Hubs;

/// <summary>
/// Analiz tamamlanma bildirimlerini taşır. Bildirimler otel bazlı gruplara gider;
/// bir otelin kullanıcısı başka otelin bildirimini almaz.
/// </summary>
[Authorize]
public class AnalysisHub : Hub<IAnalysisClient>
{
    public static string GroupName(Guid hotelId) => $"Hotel_{hotelId}";

    // Bağlanan kullanıcı, JWT'deki hotelId claim'ine göre kendi otel grubuna otomatik eklenir.
    // SuperAdmin'in sabit bir oteli olmadığı için JoinHotelGroup ile otel değiştirebilir.
    public override async Task OnConnectedAsync()
    {
        var hotelId = GetClaimHotelId();
        if (hotelId.HasValue)
        {
            await Groups.AddToGroupAsync(Context.ConnectionId, GroupName(hotelId.Value));
        }

        await base.OnConnectedAsync();
    }

    public async Task JoinHotelGroup(string hotelId)
    {
        if (!Guid.TryParse(hotelId, out var requestedHotelId))
        {
            throw new HubException("Geçersiz otel kimliği.");
        }

        // SuperAdmin dışındaki roller yalnızca kendi otellerinin grubuna katılabilir;
        // aksi hâlde istemci istediği otelin bildirimlerini dinleyebilirdi.
        if (!IsSuperAdmin() && GetClaimHotelId() != requestedHotelId)
        {
            throw new HubException("Bu otelin bildirimlerini dinleme yetkiniz yok.");
        }

        await Groups.AddToGroupAsync(Context.ConnectionId, GroupName(requestedHotelId));
    }

    public async Task LeaveHotelGroup(string hotelId)
    {
        if (Guid.TryParse(hotelId, out var requestedHotelId))
        {
            await Groups.RemoveFromGroupAsync(Context.ConnectionId, GroupName(requestedHotelId));
        }
    }

    private bool IsSuperAdmin()
    {
        var role = Context.User?.FindFirst("role")?.Value;
        return string.Equals(role, nameof(UserRole.SuperAdmin), StringComparison.OrdinalIgnoreCase);
    }

    private Guid? GetClaimHotelId()
    {
        var value = Context.User?.FindFirst("hotelId")?.Value;
        return Guid.TryParse(value, out var hotelId) ? hotelId : null;
    }
}
