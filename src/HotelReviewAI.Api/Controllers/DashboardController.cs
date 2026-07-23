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
        [FromQuery] DateTime? dateTo)
    {
        var result = await _mediator.Send(new GetDashboardSummaryQuery(dateFrom, dateTo));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Gün bazlı rating trendi - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpGet("trends")]
    [Tags("Web Panel (Angular) - Dashboard")]
    public async Task<IActionResult> GetTrends(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo)
    {
        var result = await _mediator.Send(new GetTrendsQuery(dateFrom, dateTo));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Kategori bazlı yorum sayısı ve negatif oranı - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpGet("category-distribution")]
    [Tags("Web Panel (Angular) - Dashboard")]
    public async Task<IActionResult> GetCategoryDistribution(
        [FromQuery] DateTime? dateFrom,
        [FromQuery] DateTime? dateTo)
    {
        var result = await _mediator.Send(new GetCategoryDistributionQuery(dateFrom, dateTo));
        return Ok(BaseResponse<object>.Ok(result));
    }

    /// <summary>
    /// Negatif yorumlarda en çok geçen anahtar kelimeler - Target Client: Web Panel (Angular)
    /// </summary>
    [HttpGet("top-keywords")]
    [Tags("Web Panel (Angular) - Dashboard")]
    public async Task<IActionResult> GetTopKeywords(
        [FromQuery] int topN = 10,
        [FromQuery] DateTime? dateFrom = null,
        [FromQuery] DateTime? dateTo = null)
    {
        var result = await _mediator.Send(new GetTopKeywordsQuery(topN, dateFrom, dateTo));
        return Ok(BaseResponse<object>.Ok(result));
    }
}
