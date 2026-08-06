using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Persistence.Contexts;
using HotelReviewAI.Shared.Responses;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Api.Controllers;

/// <summary>
/// Target Clients: Mobile (Flutter) & Web Panel (Angular) - İşletme / Otel Seçimi
/// </summary>
[ApiController]
[Tags("Common (Shared)")]
[Authorize]
[Route("api/hotels")]
public class HotelsController : ControllerBase
{
    private readonly AppDbContext _dbContext;

    public HotelsController(AppDbContext dbContext)
    {
        _dbContext = dbContext;
    }

    /// <summary>
    /// Aktif otel / işletmelerin listesini döner (Dropdown seçimi için)
    /// </summary>
    [HttpGet]
    public async Task<IActionResult> GetAll()
    {
        var hotels = await _dbContext.Hotels
            .Where(h => h.IsActive)
            .Select(h => new HotelDto
            {
                Id = h.Id,
                Name = h.Name,
                Code = h.Code,
                Address = h.Address
            })
            .ToListAsync();

        return Ok(BaseResponse<List<HotelDto>>.Ok(hotels));
    }
}
