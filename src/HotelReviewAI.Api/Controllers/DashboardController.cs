using HotelReviewAI.Application.Queries.Dashboard;
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
[Route("api/dashboard")]
public class DashboardController : ControllerBase
{
    private readonly IMediator _mediator;

    public DashboardController(IMediator mediator)
    {
        this._mediator = mediator;
    }

    /// <summary>
    /// Genel özet istatistikler - Target Clients: Mobile (Flutter) & Web Panel (Angular)
    /// </summary>
    [HttpGet("summary")]
    [Tags("Common (Shared)")]
    public async Task<IActionResult> GetSummary(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo,
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveHotelId = hotelIdHeader ?? hotelId;
        var result = await _mediator.Send(new GetDashboardSummaryQuery(dateFrom, dateTo, effectiveHotelId));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Gün bazlı rating trendi - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpGet("trends")]
    [Tags("Web Panel (Angular) - Dashboard")]
    public async Task<IActionResult> GetTrends(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo,
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveHotelId = hotelIdHeader ?? hotelId;
        var result = await _mediator.Send(new GetTrendsQuery(dateFrom, dateTo, effectiveHotelId));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Kategori bazlı yorum sayısı ve negatif oranı - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpGet("category-distribution")]
    [Tags("Web Panel (Angular) - Dashboard")]
    public async Task<IActionResult> GetCategoryDistribution(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo,
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveHotelId = hotelIdHeader ?? hotelId;
        var result = await _mediator.Send(new GetCategoryDistributionQuery(dateFrom, dateTo, effectiveHotelId));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Olumsuz yorumlarda öne çıkan şikayet konuları - Target Client: Web Panel (Angular)
    /// </summary>
    /// <remarks>
    /// Eski /top-keywords ucunun yerini aldı. O uç, Python tarafındaki kelime
    /// çıkarıcısının ürettiği çekimli/bozuk kökleri (ör. "tavsiy", "dah", "asl")
    /// ve dolgu kelimeleri sıralıyordu; yerine ABSA'nın zaten ürettiği kanonik
    /// aspect etiketleri kullanılıyor.
    /// </remarks>
    [HttpGet("complaint-topics")]
    [Tags("Web Panel (Angular) - Dashboard")]
    public async Task<IActionResult> GetComplaintTopics(
        [FromQuery] int topN = 8,
        [FromQuery] DateTime? dateFrom = null,
        [FromQuery] DateTime? dateTo = null,
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveHotelId = hotelIdHeader ?? hotelId;
        var result = await _mediator.Send(new GetComplaintTopicsQuery(topN, dateFrom, dateTo, effectiveHotelId));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Bir şikayet konusunun olumsuz cümleleri ve çözüm önerileri - Target Client: Web Panel (Angular)
    /// </summary>
    /// <remarks>
    /// Konu adı ROTA SEGMENTİ DEĞİL query parametresi: canlı etiketlerden biri
    /// "Servis / Kuyruk" ve içinde '/' var; %2F ile kodlansa bile Kestrel varsayılan
    /// olarak reddedeceği için tam olarak o etikette 404 alınırdı.
    /// </remarks>
    [HttpGet("complaint-topics/clauses")]
    [Tags("Web Panel (Angular) - Dashboard")]
    public async Task<IActionResult> GetComplaintTopicClauses(
        [FromQuery] string topic,
        [FromQuery] int take = 10,
        [FromQuery] DateTime? dateFrom = null,
        [FromQuery] DateTime? dateTo = null,
        [FromQuery] Guid? hotelId = null,
        [FromHeader(Name = "X-Hotel-Id")] Guid? hotelIdHeader = null)
    {
        var effectiveHotelId = hotelIdHeader ?? hotelId;
        var result = await _mediator.Send(
            new GetComplaintTopicClausesQuery(topic, take, dateFrom, dateTo, effectiveHotelId));
        return Ok(BaseResponse<object>.Ok(result));
    }
}
