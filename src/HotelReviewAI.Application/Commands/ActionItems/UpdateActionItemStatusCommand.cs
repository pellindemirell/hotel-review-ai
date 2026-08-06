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
    private readonly ICurrentUserService _currentUserService;

    public UpdateActionItemStatusHandler(
        IActionItemRepository actionItemRepository,
        ICurrentUserService currentUserService)
    {
        _actionItemRepository = actionItemRepository;
        _currentUserService = currentUserService;
    }

    public async Task<bool> Handle(UpdateActionItemStatusCommand request, CancellationToken cancellationToken)
    {
        var actionItem = await _actionItemRepository.GetByIdAsync(request.Id);
        if (actionItem == null)
        {
            throw new DomainException("Güncellenecek görev bulunamadı.");
        }

        // HotelAdmin kendi otelinin, DepartmentManager kendi departmanının görevlerini güncelleyebilir.
        if (_currentUserService.Role is UserRole.HotelAdmin or UserRole.DepartmentManager)
        {
            if (actionItem.HotelId != _currentUserService.HotelId)
            {
                throw new UnauthorizedAccessException("Bu otelin görevlerini güncelleme yetkiniz yok.");
            }

            if (_currentUserService.Role == UserRole.DepartmentManager
                && actionItem.DepartmentId != _currentUserService.DepartmentId)
            {
                throw new UnauthorizedAccessException("Bu departmanın görevlerini güncelleme yetkiniz yok.");
            }
        }

        actionItem.Status = request.Status;
        await _actionItemRepository.UpdateAsync(actionItem);
        await _actionItemRepository.SaveChangesAsync();

        return true;
    }
}
