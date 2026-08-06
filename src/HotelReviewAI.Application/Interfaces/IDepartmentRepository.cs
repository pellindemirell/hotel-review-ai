using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IDepartmentRepository : IGenericRepository<Department>
{
    Task<List<Department>> GetDepartmentsAsync(Guid? hotelId = null);
}
