using System;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Interfaces;

public interface IAnalysisClient
{
    Task AnalysisCompleted(object notificationData);
}
