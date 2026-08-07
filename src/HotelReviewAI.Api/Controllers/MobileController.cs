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
    private readonly IReviewPhotoStorage _photoStorage;

    public MobileController(IMediator mediator, IReviewPhotoStorage photoStorage)
    {
        _mediator = mediator;
        _photoStorage = photoStorage;
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

        if (photo is { Length: > 0 })
        {
            // Doğrulama ve yükleme web paneliyle ortak (IReviewPhotoStorage):
            // Cloudinary önce denenir, yapılandırılmamışsa yerel diske düşülür.
            var validationError = _photoStorage.Validate(photo.Length, photo.FileName, photo.ContentType);
            if (validationError is not null)
            {
                return BadRequest(BaseResponse<object>.Fail(validationError));
            }

            byte[] photoBytes;
            using (var buffer = new MemoryStream())
            {
                await photo.CopyToAsync(buffer);
                photoBytes = buffer.ToArray();
            }

            photoUrl = await _photoStorage.SaveAsync(photoBytes, photo.FileName);

            // NOT: Burada bir OCR adımı vardı, kaldırıldı. Okunan metin analiz
            // hattına hiç beslenmiyordu ve arayüzde hiçbir yerde gösterilmiyordu;
            // yani her yüklemede ai-service'e fazladan bir istek atılıp sonuç
            // veritabanına yazılıyor ama kimse okumuyordu. Üstelik istek, alan adı
            // uyuşmazlığı (istemci "file", uç "image" bekliyordu) yüzünden zaten
            // 422 ile reddediliyor, hata yutulduğu için OcrText hep boş kalıyordu.
            // Misafirler kirli oda / bozuk klima fotoğrafı çekiyor, metin değil.
            // ReviewAttachment.OcrText kolonu ileride gerçek bir ihtiyaç doğarsa
            // (ör. fatura görseli) diye şemada bırakıldı.
        }

        var command = new CreateMobileReviewCommand(guestName, comment, rating, language, photoUrl, null, hotelIdHeader);
        var id = await _mediator.Send(command);

        return Ok(BaseResponse<Guid>.Ok(id, "Yorum ve görsel başarıyla yüklendi."));
    }
}
