using HotelReviewAI.Application.Interfaces;
using Microsoft.AspNetCore.SignalR;
using System.Threading.Tasks;

namespace HotelReviewAI.Api.Hubs;

public class AnalysisHub : Hub<IAnalysisClient>
{
    public async Task JoinHotelGroup(string hotelId)
    {
        await Groups.AddToGroupAsync(Context.ConnectionId, $"Hotel_{hotelId}");
    }

    public async Task LeaveHotelGroup(string hotelId)
    {
        await Groups.RemoveFromGroupAsync(Context.ConnectionId, $"Hotel_{hotelId}");
    }
}
