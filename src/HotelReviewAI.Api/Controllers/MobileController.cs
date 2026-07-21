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

[ApiController]
[Authorize]
[Route("api/mobile")]
public class MobileController : ControllerBase
{
    private readonly IMediator _mediator;
    private readonly IAiAnalysisService _aiAnalysisService;

    public MobileController(IMediator mediator, IAiAnalysisService aiAnalysisService)
    {
        _mediator = mediator;
        _aiAnalysisService = aiAnalysisService;
    }

    [HttpPost("reviews-with-photo")]
    [Consumes("multipart/form-data")]
    public async Task<IActionResult> CreateWithPhoto(
        [FromForm] string guestName,
        [FromForm] string comment,
        [FromForm] int rating,
        [FromForm] string language,
        IFormFile? photo)
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

            // 3. Fiziksel Fotoğraf Kaydetme (wwwroot/uploads klasörüne)
            var uploadDir = Path.Combine(Directory.GetCurrentDirectory(), "wwwroot", "uploads");
            if (!Directory.Exists(uploadDir))
            {
                Directory.CreateDirectory(uploadDir);
            }

            var fileName = $"{Guid.NewGuid()}{extension}";
            var filePath = Path.Combine(uploadDir, fileName);

            using (var stream = new FileStream(filePath, FileMode.Create))
            {
                await photo.CopyToAsync(stream);
            }

            photoUrl = $"/uploads/{fileName}";

            // 4. Python AI Servisine OCR için HTTP isteği gönderme (Service üzerinden)
            using var fileStream = photo.OpenReadStream();
            ocrText = await _aiAnalysisService.PerformOcrAsync(fileStream, photo.FileName, photo.ContentType);
        }

        var command = new CreateMobileReviewCommand(guestName, comment, rating, language, photoUrl, ocrText);
        var id = await _mediator.Send(command);

        return Ok(BaseResponse<Guid>.Ok(id, "Yorum ve görsel başarıyla yüklendi."));
    }
}
