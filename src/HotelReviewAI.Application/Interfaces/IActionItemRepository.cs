using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IActionItemRepository : IGenericRepository<ActionItem>
{
    Task<IEnumerable<ActionItem>> GetByReviewIdAsync(Guid reviewId);
    Task<IEnumerable<ActionItem>> GetByDepartmentIdAsync(Guid departmentId);
    Task<IEnumerable<ActionItem>> GetByUserIdAsync(Guid userId);
    Task<IEnumerable<ActionItem>> GetFilteredAsync(Guid? departmentId, Guid? assignedTo, Guid? hotelId);

    /// <summary>
    /// Bir ekip üyesine not düşülmüş görevler (ActionItem.AssignedStaffId).
    /// Yalnızca kayıt amaçlı bir bağdır; yetkilendirmede kullanılmaz.
    /// </summary>
    Task<IEnumerable<ActionItem>> GetByAssignedStaffIdAsync(Guid staffId);
}
