using CloudinaryDotNet;
using CloudinaryDotNet.Actions;
using HotelReviewAI.Application.Interfaces;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using System;
using System.IO;
using System.Threading.Tasks;

namespace HotelReviewAI.Infrastructure.Services;

public class CloudinaryService : ICloudinaryService
{
    private readonly Cloudinary? _cloudinary;
    private readonly ILogger<CloudinaryService> _logger;

    public CloudinaryService(IConfiguration configuration, ILogger<CloudinaryService> logger)
    {
        _logger = logger;
        var cloudinaryUrl = configuration["CloudinarySettings:Url"];
        var cloudName = configuration["CloudinarySettings:CloudName"]?.Trim();
        var apiKey = configuration["CloudinarySettings:ApiKey"]?.Trim();
        var apiSecret = configuration["CloudinarySettings:ApiSecret"]?.Trim();

        if (!string.IsNullOrEmpty(cloudinaryUrl))
        {
            _cloudinary = new Cloudinary(cloudinaryUrl);
            _cloudinary.Api.Secure = true;
        }
        else if (!string.IsNullOrEmpty(cloudName) && !string.IsNullOrEmpty(apiKey) && !string.IsNullOrEmpty(apiSecret))
        {
            var account = new Account(cloudName, apiKey, apiSecret);
            _cloudinary = new Cloudinary(account);
            _cloudinary.Api.Secure = true;
        }
        else
        {
            _logger.LogWarning("Cloudinary credentials are missing in configuration.");
        }
    }

    public async Task<string?> UploadImageAsync(Stream fileStream, string fileName, string folder = "hotel_reviews")
    {
        if (fileStream == null || fileStream.Length == 0 || _cloudinary == null)
        {
            _logger.LogWarning("Upload cancelled: fileStream is null/empty or _cloudinary is unconfigured.");
            return null;
        }

        try
        {
            fileStream.Position = 0;
            var uploadParams = new ImageUploadParams
            {
                File = new FileDescription(fileName, fileStream),
                Folder = folder,
                PublicId = $"{Guid.NewGuid()}"
            };

            var uploadResult = await _cloudinary.UploadAsync(uploadParams);

            if (uploadResult.StatusCode == System.Net.HttpStatusCode.OK)
            {
                _logger.LogInformation("Cloudinary upload successful: {Url}", uploadResult.SecureUrl);
                return uploadResult.SecureUrl.ToString();
            }

            _logger.LogError("Cloudinary upload failed: StatusCode={StatusCode}, Error={Error}", 
                uploadResult.StatusCode, uploadResult.Error?.Message);
            return null;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Exception during Cloudinary upload for file: {FileName}", fileName);
            return null;
        }
    }
}
