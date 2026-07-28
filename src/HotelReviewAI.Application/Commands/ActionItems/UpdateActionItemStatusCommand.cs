using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Enums;
using HotelReviewAI.Domain.Exceptions;
using MediatR;
using System;
using System.Threading;
using System.Threading.Tasks;

namespace HotelReviewAI.Application.Commands.ActionItems;

public record UpdateActionItemStatusCommand(Guid Id, ActionItemStatus Status) : IRequest<bool>;

public class UpdateActionItemStatusHandler : IRequestHandler<UpdateActionItemStatusCommand, bool>
{
    private readonly IActionItemRepository _actionItemRepository;

    public UpdateActionItemStatusHandler(IActionItemRepository actionItemRepository)
    {
        _actionItemRepository = actionItemRepository;
    }

    public async Task<bool> Handle(UpdateActionItemStatusCommand request, CancellationToken cancellationToken)
    {
        var actionItem = await _actionItemRepository.GetByIdAsync(request.Id);
        if (actionItem == null)
        {
            throw new DomainException("Güncellenecek görev bulunamadı.");
        }

        actionItem.Status = request.Status;
        await _actionItemRepository.UpdateAsync(actionItem);
        await _actionItemRepository.SaveChangesAsync();

        return true;
    }
}
