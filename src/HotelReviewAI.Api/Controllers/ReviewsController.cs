using HotelReviewAI.Application.Commands.Reviews;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Application.Queries.Reviews;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

using Microsoft.AspNetCore.Http;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Target Clients: Mobile (Flutter) & Web Panel (Angular)
/// </summary>
[ApiController]
[Authorize]
[Route("api/reviews")]
public class ReviewsController : ControllerBase
{
    private readonly IMediator _mediator;
    private readonly IReviewPhotoStorage _photoStorage;

    public ReviewsController(IMediator mediator, IReviewPhotoStorage photoStorage)
    {
        _mediator = mediator;
        _photoStorage = photoStorage;
    }

    /// <summary>
    /// Masaüstünden manuel yorum girişi - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpPost]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> Create(
        [FromBody] CreateReviewCommand command,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveCommand = command with { HotelId = hotelIdHeader ?? command.HotelId };
        var id = await _mediator.Send(effectiveCommand);
        return Accepted(BaseResponse<Guid>.Ok(id, "Yorum kaydedildi ve AI analizi için kuyruğa alındı."));
    }

    /// <summary>
    /// Görselli manuel yorum girişi - Target Client: Web Panel (Angular)
    /// </summary>
    /// <remarks>
    /// Ayrı bir uç: <c>POST /api/reviews</c> JSON gövdesi alıyor ve sözleşmesi
    /// korunuyor. Dosya yüklemek multipart/form-data gerektirdiğinden aynı
    /// action ikisini birden karşılayamaz. Görsel yükleme mantığı mobil uçla
    /// ortak (IReviewPhotoStorage), böylece Cloudinary/yerel yedek davranışı
    /// iki yerde ayrışmaz.
    /// </remarks>
    [HttpPost("with-photo")]
    [Consumes("multipart/form-data")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> CreateWithPhoto(
        [FromForm] string guestName,
        [FromForm] string comment,
        [FromForm] int rating,
        [FromForm] string language,
        [FromForm] string source,
        IFormFile? photo,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null,
        CancellationToken ct = default)
    {
        string? photoUrl = null;

        if (photo is { Length: > 0 })
        {
            var validationError = _photoStorage.Validate(photo.Length, photo.FileName, photo.ContentType);
            if (validationError is not null)
            {
                return BadRequest(BaseResponse<object>.Fail(validationError));
            }

            byte[] bytes;
            using (var buffer = new MemoryStream())
            {
                await photo.CopyToAsync(buffer, ct);
                bytes = buffer.ToArray();
            }

            photoUrl = await _photoStorage.SaveAsync(bytes, photo.FileName, ct);
        }

        if (!Enum.TryParse<ReviewSource>(source, ignoreCase: true, out var parsedSource))
        {
            parsedSource = ReviewSource.Manual;
        }

        var command = new CreateReviewCommand(
            GuestName: guestName,
            Comment: comment,
            Rating: rating,
            Language: language,
            Source: parsedSource,
            ReviewDate: DateTime.UtcNow,
            HotelId: hotelIdHeader,
            PhotoUrl: photoUrl);

        var id = await _mediator.Send(command, ct);
        return Accepted(BaseResponse<Guid>.Ok(id, "Yorum kaydedildi ve AI analizi için kuyruğa alındı."));
    }

    /// <summary>
    /// Yorum listeleme - Target Clients: Mobile (Flutter) & Web Panel (Angular)
    /// </summary>
    [HttpGet]
    [Tags("Common (Shared)")]
    public async Task<IActionResult> GetAll(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo,
        [FromQuery] Sentiment? sentiment,
        [FromQuery] Guid? categoryId,
        [FromQuery] Guid? departmentId,
        [FromQuery] ReviewSource? source,
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null,
        [FromQuery] int pageNumber = 1,
        [FromQuery] int pageSize = 20,
        [FromQuery] string sortBy = "newest")
    {
        // Otel/departman kısıtı GetReviewsHandler içinde ICurrentUserService üzerinden zorunlu kılınır.
        var effectiveHotelId = hotelIdHeader ?? hotelId;
        var query = new GetReviewsQuery(dateFrom, dateTo, sentiment, categoryId, departmentId, source, pageNumber, pageSize, sortBy, effectiveHotelId);
        var result = await _mediator.Send(query);
        return Ok(result);
    }

    /// <summary>
    /// Yorum detay/analiz ekranı - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpGet("{id:guid}")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> GetById(Guid id)
    {
        var result = await _mediator.Send(new GetReviewByIdQuery(id));
        if (result is null)
        {
            return NotFound(BaseResponse<object>.Fail("Yorum bulunamadı"));
        }

        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Yorum silme - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpDelete("{id:guid}")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> Delete(Guid id)
    {
        var deleted = await _mediator.Send(new DeleteReviewCommand(id));
        if (!deleted)
        {
            return NotFound(BaseResponse<object>.Fail("Yorum bulunamadı"));
        }

        return Ok(BaseResponse<object>.Ok(null!, "Yorum silindi"));
    }

    /// <summary>
    /// CSV ile toplu yorum yükleme - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpPost("import")]
    [Consumes("multipart/form-data")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> Import(
        IFormFile file,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null,
        [FromQuery] Guid? hotelId = null)
    {
        if (file == null || file.Length == 0)
        {
            return BadRequest(BaseResponse<object>.Fail("Lütfen geçerli bir CSV dosyası seçin."));
        }

        var effectiveHotelId = hotelIdHeader ?? hotelId;

        using var stream = file.OpenReadStream();
        var result = await _mediator.Send(new ImportReviewsCsvCommand(stream, effectiveHotelId));

        return Ok(BaseResponse<ImportResultDto>.Ok(result, $"{result.SuccessCount} yorum başarıyla içe aktarıldı."));
    }

    /// <summary>
    /// Yorum yeniden analizi - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpPost("{id:guid}/reanalyze")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> Reanalyze(Guid id)
    {
        var success = await _mediator.Send(new ReanalyzeReviewCommand(id));
        if (!success)
        {
            return BadRequest(BaseResponse<object>.Fail("Yorum yeniden analiz edilemedi."));
        }

        return Ok(BaseResponse<object>.Ok(null!, "Yorum yeniden analiz edildi"));
    }

    /// <summary>
    /// Yorumu Türkçeye çevirir - Target Client: Web Panel (Angular)
    /// </summary>
    /// <remarks>
    /// Çeviri ilk istekte yapılıp saklanır; sonraki istekler veritabanından
    /// döner ve AI servisine hiç gidilmez.
    /// </remarks>
    [HttpPost("{id:guid}/translate")]
    [Tags("Web Panel (Angular) - Reviews")]
    public async Task<IActionResult> Translate(Guid id)
    {
        var result = await _mediator.Send(new TranslateReviewCommand(id));
        return Ok(BaseResponse<ReviewTranslationDto>.Ok(result));
    }
}
