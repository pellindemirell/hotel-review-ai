using HotelReviewAI.Application.DTOs;
using HotelReviewAI.Application.Interfaces;
using MediatR;

namespace HotelReviewAI.Application.Queries.Categories;

public class GetCategoriesHandler : IRequestHandler<GetCategoriesQuery, List<CategoryDto>>
{
    private readonly IReviewCategoryRepository _categoryRepository;
    private readonly IDepartmentRepository _departmentRepository;

    public GetCategoriesHandler(IReviewCategoryRepository categoryRepository, IDepartmentRepository departmentRepository)
    {
        _categoryRepository = categoryRepository;
        _departmentRepository = departmentRepository;
    }

    public async Task<List<CategoryDto>> Handle(GetCategoriesQuery request, CancellationToken cancellationToken)
    {
        var categories = await _categoryRepository.GetAllAsync();
        var departments = (await _departmentRepository.GetAllAsync()).ToDictionary(d => d.Id);

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
