using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IReviewAttachmentRepository : IGenericRepository<ReviewAttachment>
{
    Task<IEnumerable<ReviewAttachment>> GetByReviewIdAsync(Guid reviewId);
}
