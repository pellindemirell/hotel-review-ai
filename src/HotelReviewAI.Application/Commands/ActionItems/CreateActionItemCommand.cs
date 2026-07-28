using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;
using MediatR;
using System;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Commands.ActionItems;

public record CreateActionItemCommand(
    Guid ReviewId,
    Guid DepartmentId,
    Guid? AssignedTo,
    string Title,
    DateTime? DueDate
) : IRequest<Guid>;

public class CreateActionItemHandler : IRequestHandler<CreateActionItemCommand, Guid>
{
    private readonly IActionItemRepository _actionItemRepository;
    private readonly IReviewRepository _reviewRepository;

    public CreateActionItemHandler(
        IActionItemRepository actionItemRepository,
        IReviewRepository reviewRepository)
    {
        _actionItemRepository = actionItemRepository;
        _reviewRepository = reviewRepository;
    }

    public async Task<Guid> Handle(CreateActionItemCommand request, CancellationToken cancellationToken)
    {
        var review = await _reviewRepository.GetByIdAsync(request.ReviewId);
        if (review == null)
        {
            throw new DomainException("İlişkilendirilecek yorum bulunamadı.");
        }

        if (string.IsNullOrWhiteSpace(request.Title))
        {
            throw new DomainException("Görev başlığı boş bırakılamaz.");
        }

        var actionItem = new ActionItem
        {
            ReviewId = request.ReviewId,
            DepartmentId = request.DepartmentId,
            AssignedTo = request.AssignedTo,
            Title = request.Title,
            Status = ActionItemStatus.Open,
            DueDate = request.DueDate,
            HotelId = review.HotelId
        };

        await _actionItemRepository.AddAsync(actionItem);
        await _actionItemRepository.SaveChangesAsync();
        return actionItem.Id;
    }
}
