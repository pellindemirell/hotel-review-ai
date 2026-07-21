using HotelReviewAI.Application.Queries.Dashboard;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace HotelReviewAI.Api.Controllers;

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
    /// Genel özet istatistikler: toplam yorum, ortalama puan, açık aksiyonlar, negatif oran.
    /// </summary>
    [HttpGet("summary")]
    public async Task<IActionResult> GetSummary(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo)
    {
        var result = await _mediator.Send(new GetDashboardSummaryQuery(dateFrom, dateTo));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Gün bazlı rating trendi — son 30 gün varsayılan.
    /// </summary>
    [HttpGet("trends")]
    public async Task<IActionResult> GetTrends(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo)
    {
        var result = await _mediator.Send(new GetTrendsQuery(dateFrom, dateTo));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Kategori bazlı yorum sayısı ve negatif oranı.
    /// </summary>
    [HttpGet("category-distribution")]
    public async Task<IActionResult> GetCategoryDistribution(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo)
    {
        var result = await _mediator.Send(new GetCategoryDistributionQuery(dateFrom, dateTo));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Negatif yorumlarda en çok geçen anahtar kelimeler.
    /// </summary>
    [HttpGet("top-keywords")]
    public async Task<IActionResult> GetTopKeywords(
        [FromQuery] int topN = 10,
        [FromQuery] DateTime? dateFrom = null,
        [FromQuery] DateTime? dateTo = null)
    {
        var result = await _mediator.Send(new GetTopKeywordsQuery(topN, dateFrom, dateTo));
        return Ok(BaseResponse<object>.Ok(result));
    }
}
