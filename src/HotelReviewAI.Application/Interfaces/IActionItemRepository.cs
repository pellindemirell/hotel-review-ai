using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IActionItemRepository : IGenericRepository<ActionItem>
{
    Task<IEnumerable<ActionItem>> GetByDepartmentIdAsync(Guid departmentId);
    Task<IEnumerable<ActionItem>> GetByUserIdAsync(Guid userId);
}
