using HotelReviewAI.Application.Commands.Reviews;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Target Client: Mobile (Flutter)
/// </summary>
[ApiController]
[Tags("Mobile (Flutter)")]
[Authorize]
[Route("api/mobile")]
public class MobileController : ControllerBase
{
    private readonly IMediator _mediator;
    private readonly IAiAnalysisService _aiAnalysisService;
    private readonly ICloudinaryService _cloudinaryService;
    private readonly ILogger<MobileController> _logger;

    public MobileController(
        IMediator mediator,
        IAiAnalysisService aiAnalysisService,
        ICloudinaryService cloudinaryService,
        ILogger<MobileController> logger)
    {
        _mediator = mediator;
        _aiAnalysisService = aiAnalysisService;
        _cloudinaryService = cloudinaryService;
        _logger = logger;
    }

    [HttpPost("reviews-with-photo")]
    [Consumes("multipart/form-data")]
    public async Task<IActionResult> CreateWithPhoto(
        [FromForm] string guestName,
        [FromForm] string comment,
        [FromForm] int rating,
        [FromForm] string language,
        IFormFile? photo,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        string? photoUrl = null;
        string? ocrText = null;

        if (photo != null && photo.Length > 0)
        {
            // 1. Dosya boyutu kontrolü (Maksimum 5 MB)
            if (photo.Length > 5 * 1024 * 1024)
            {
                return BadRequest(BaseResponse<object>.Fail("Dosya boyutu 5 MB'dan fazla olamaz."));
            }

            // 2. Uzantı ve İçerik Türü (Content-Type) Kontrolü
            var extension = Path.GetExtension(photo.FileName).ToLowerInvariant();
            var allowedExtensions = new[] { ".jpg", ".jpeg", ".png" };
            var allowedContentTypes = new[] { "image/jpeg", "image/png", "image/pjpeg" };

            if (!allowedExtensions.Contains(extension) || !allowedContentTypes.Contains(photo.ContentType.ToLowerInvariant()))
            {
                return BadRequest(BaseResponse<object>.Fail("Yalnızca .jpg, .jpeg veya .png formatında görseller yüklenebilir."));
            }

            // Dosya bir kez baytlara alınır. Tampon stream PAYLAŞILMAZ, her tüketiciye
            // baytlardan yeni bir stream verilir: CloudinaryDotNet, FileDescription'a
            // geçirilen stream'i yükleme bitince kapatıyor. Tek bir MemoryStream
            // paylaşıldığında sonraki OCR adımı "Cannot access a closed Stream" ile
            // patlıyordu — üstelik görsel Cloudinary'ye çıktıktan SONRA, yani yorum
            // kaydedilmeden sahipsiz bir asset bırakarak.
            byte[] photoBytes;
            using (var buffer = new MemoryStream())
            {
                await photo.CopyToAsync(buffer);
                photoBytes = buffer.ToArray();
            }

            // 3. Görseli kalıcı depoya yükle.
            // Önce Cloudinary denenir: ekip ortak bir veritabanı kullanıyor ama
            // API'yi herkes kendi makinesinde çalıştırıyor. Diske yazılan dosya
            // yalnızca o makinede bulunduğundan, kaydı başka biri açtığında görsel
            // 404 veriyordu. Cloudinary mutlak (https) bir adres döndürür ve her
            // makineden açılır.
            using (var uploadStream = new MemoryStream(photoBytes))
            {
                photoUrl = await _cloudinaryService.UploadImageAsync(uploadStream, photo.FileName);
            }

            if (string.IsNullOrEmpty(photoUrl))
            {
                // Cloudinary yapılandırılmamış ya da yükleme başarısız: yerel diske
                // düşülür. Tek makinede çalışan geliştirme kurulumunu bozmamak için
                // bu yol korunuyor; üretimde Cloudinary bilgileri tanımlı olmalı.
                _logger.LogWarning(
                    "Cloudinary yüklemesi yapılamadı, görsel yerel diske kaydediliyor. "
                    + "Ortak veritabanı kullanılıyorsa bu dosya diğer makinelerden açılamaz.");

                var uploadDir = Path.Combine(Directory.GetCurrentDirectory(), "wwwroot", "uploads");
                if (!Directory.Exists(uploadDir))
                {
                    Directory.CreateDirectory(uploadDir);
                }

                var fileName = $"{Guid.NewGuid()}{extension}";
                var filePath = Path.Combine(uploadDir, fileName);

                await System.IO.File.WriteAllBytesAsync(filePath, photoBytes);

                photoUrl = $"/uploads/{fileName}";
            }

            // 4. Python AI Servisine OCR için HTTP isteği gönderme (Service üzerinden)
            using (var ocrStream = new MemoryStream(photoBytes))
            {
                ocrText = await _aiAnalysisService.PerformOcrAsync(ocrStream, photo.FileName, photo.ContentType);
            }
        }

        var command = new CreateMobileReviewCommand(guestName, comment, rating, language, photoUrl, ocrText, hotelIdHeader);
        var id = await _mediator.Send(command);

        return Ok(BaseResponse<Guid>.Ok(id, "Yorum ve görsel başarıyla yüklendi."));
    }
}
