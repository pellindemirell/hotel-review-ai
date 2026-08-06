using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Queries.AnalysisJobs;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Shared.Responses;
using MediatR;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace HotelReviewAI.Api.Controllers;

[ApiController]
[Route("api/system")]
[Authorize(Policy = "HotelAdminOrAbove")] // failed-jobs handler'ı ayrıca SuperAdmin kontrolü yapar
public class SystemController : ControllerBase
{
    private readonly IMediator _mediator;

    public SystemController(IMediator mediator)
    {
        _mediator = mediator;
    }

    [HttpGet("failed-jobs")]
    public async Task<IActionResult> GetFailedJobs()
    {
        var result = await _mediator.Send(new GetFailedJobsQuery());
        return Ok(BaseResponse<List<FailedJobDto>>.Ok(result));
    }

    /// <summary>
    /// Demo verisini yükler. Veri yazan bir bakım işlemi olduğu için yalnızca SuperAdmin'e açıktır
    /// (önceden [AllowAnonymous] idi ve kimlik doğrulaması olmadan tetiklenebiliyordu).
    /// </summary>
    [HttpPost("seed")]
    [Authorize(Roles = nameof(UserRole.SuperAdmin))]
    public async Task<IActionResult> SeedDatabase([FromServices] HotelReviewAI.Persistence.Contexts.AppDbContext context)
    {
        await HotelReviewAI.Persistence.Seed.DbSeeder.SeedAsync(context);
        return Ok(BaseResponse<object>.Ok(null!, "Database seeded successfully."));
    }
}
