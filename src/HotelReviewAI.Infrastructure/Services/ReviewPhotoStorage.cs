using HotelReviewAI.Application.Interfaces;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Infrastructure.Services;

/// <inheritdoc />
public class ReviewPhotoStorage : IReviewPhotoStorage
{
    private const long MaxBytes = 5 * 1024 * 1024;
    private static readonly string[] AllowedExtensions = [".jpg", ".jpeg", ".png"];
    private static readonly string[] AllowedContentTypes = ["image/jpeg", "image/png", "image/pjpeg"];

    private readonly ICloudinaryService _cloudinaryService;
    private readonly ILogger<ReviewPhotoStorage> _logger;

    public ReviewPhotoStorage(ICloudinaryService cloudinaryService, ILogger<ReviewPhotoStorage> logger)
    {
        _cloudinaryService = cloudinaryService;
        _logger = logger;
    }

    public string? Validate(long lengthBytes, string fileName, string contentType)
    {
        if (lengthBytes > MaxBytes)
        {
            return "Dosya boyutu 5 MB'dan fazla olamaz.";
        }

        var extension = Path.GetExtension(fileName).ToLowerInvariant();
        if (!AllowedExtensions.Contains(extension)
            || !AllowedContentTypes.Contains(contentType.ToLowerInvariant()))
        {
            return "Yalnızca .jpg, .jpeg veya .png formatında görseller yüklenebilir.";
        }

        return null;
    }

    public async Task<string> SaveAsync(byte[] content, string fileName, CancellationToken ct = default)
    {
        // Cloudinary önce denenir: ekip ortak bir veritabanı kullanıyor ama API'yi
        // herkes kendi makinesinde çalıştırıyor. Diske yazılan dosya yalnızca o
        // makinede bulunduğundan, kaydı başka biri açtığında görsel 404 veriyordu.
        // Cloudinary mutlak (https) bir adres döndürür ve her makineden açılır.
        // Not: CloudinaryDotNet kendisine verilen stream'i kapattığı için her
        // çağrıya baytlardan yeni bir stream verilir.
        using (var uploadStream = new MemoryStream(content))
        {
            var url = await _cloudinaryService.UploadImageAsync(uploadStream, fileName);
            if (!string.IsNullOrEmpty(url))
            {
                return url;
            }
        }

        // Cloudinary yapılandırılmamış ya da yükleme başarısız: yerel diske düşülür.
        // Tek makinede çalışan geliştirme kurulumunu bozmamak için bu yol korunuyor;
        // üretimde Cloudinary bilgileri tanımlı olmalı.
        _logger.LogWarning(
            "Cloudinary yüklemesi yapılamadı, görsel yerel diske kaydediliyor. "
            + "Ortak veritabanı kullanılıyorsa bu dosya diğer makinelerden açılamaz.");

        var uploadDir = Path.Combine(Directory.GetCurrentDirectory(), "wwwroot", "uploads");
        if (!Directory.Exists(uploadDir))
        {
            Directory.CreateDirectory(uploadDir);
        }

        var storedName = $"{Guid.NewGuid()}{Path.GetExtension(fileName).ToLowerInvariant()}";
        await File.WriteAllBytesAsync(Path.Combine(uploadDir, storedName), content, ct);

        return $"/uploads/{storedName}";
    }
}
