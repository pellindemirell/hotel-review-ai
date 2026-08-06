using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using MediatR;

namespace HotelReviewAI.Application.Queries.Categories;

public class GetCategoriesHandler : IRequestHandler<GetCategoriesQuery, List<CategoryDto>>
{
    private readonly IReviewCategoryRepository _categoryRepository;
    private readonly IDepartmentRepository _departmentRepository;
    private readonly ICurrentUserService _currentUserService;

    public GetCategoriesHandler(
        IReviewCategoryRepository categoryRepository,
        IDepartmentRepository departmentRepository,
        ICurrentUserService currentUserService)
    {
        _categoryRepository = categoryRepository;
        _departmentRepository = departmentRepository;
        _currentUserService = currentUserService;
    }

    public async Task<List<CategoryDto>> Handle(GetCategoriesQuery request, CancellationToken cancellationToken)
    {
        // SuperAdmin dışındaki roller için otel JWT'den zorunlu kılınır
        // (GetDepartmentsHandler ile aynı desen).
        var effectiveHotelId = _currentUserService.Role is UserRole.HotelAdmin or UserRole.DepartmentManager
            ? _currentUserService.HotelId
            : request.HotelId;

        var categories = await _categoryRepository.GetAllAsync();
        var departments = (await _departmentRepository.GetDepartmentsAsync(effectiveHotelId))
            .ToDictionary(d => d.Id);

        // Kategori otele, bağlı olduğu departman üzerinden aittir.
        if (effectiveHotelId.HasValue)
        {
            categories = categories.Where(c => departments.ContainsKey(c.DepartmentId)).ToList();
        }

        return categories.Select(c => new CategoryDto
        {
            Id = c.Id,
            Key = c.Key,
            Name = c.Name,
            Keywords = c.Keywords,
            DepartmentId = c.DepartmentId,
            DepartmentName = departments.TryGetValue(c.DepartmentId, out var dept) ? dept.Name : null
        }).ToList();
    }
}
