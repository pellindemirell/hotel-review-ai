using System.IO;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Interfaces;

public interface ICloudinaryService
{
    Task<string?> UploadImageAsync(Stream fileStream, string fileName, string folder = "hotel_reviews");
}
