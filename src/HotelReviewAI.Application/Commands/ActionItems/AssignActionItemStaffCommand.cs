using HotelReviewAI.Application.Commands.Staff;
using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Exceptions;
using MediatR;

namespace HotelReviewAI.Application.Commands.ActionItems;

/// <summary>
/// Görevi ekip üyesine "not düşer" — YALNIZCA KAYIT.
///
/// Bilinçli olarak hiçbir yan etkisi yoktur: görevin durumu değişmez,
/// bildirim gitmez, yetki/filtre etkilenmez. Amaç departman yöneticisinin
/// sonradan "bu işi kime vermiştim" diye bakabilmesidir. StaffId null
/// verilirse kayıt temizlenir.
/// </summary>
public record AssignActionItemStaffCommand(Guid ActionItemId, Guid? StaffId) : IRequest<bool>;

public class AssignActionItemStaffHandler : IRequestHandler<AssignActionItemStaffCommand, bool>
{
    private readonly IActionItemRepository _actionItemRepository;
    private readonly IStaffMemberRepository _staffRepository;
    private readonly ICurrentUserService _currentUser;

    public AssignActionItemStaffHandler(
        IActionItemRepository actionItemRepository,
        IStaffMemberRepository staffRepository,
        ICurrentUserService currentUser)
    {
        _actionItemRepository = actionItemRepository;
        _staffRepository = staffRepository;
        _currentUser = currentUser;
    }

    public async Task<bool> Handle(AssignActionItemStaffCommand request, CancellationToken cancellationToken)
    {
        var departmentId = StaffScope.RequireDepartment(_currentUser);

        var actionItem = await _actionItemRepository.GetByIdAsync(request.ActionItemId)
            ?? throw new DomainException("Görev bulunamadı.");

        if (actionItem.DepartmentId != departmentId)
        {
            throw new UnauthorizedAccessException("Bu görev sizin departmanınıza ait değil.");
        }

        if (request.StaffId is { } staffId)
        {
            var staff = await _staffRepository.GetByIdAsync(staffId)
                ?? throw new DomainException("Çalışan bulunamadı.");
            StaffScope.EnsureOwned(staff, departmentId);

            actionItem.AssignedStaffId = staffId;
        }
        else
        {
            actionItem.AssignedStaffId = null;
        }

        actionItem.MarkUpdated();
        await _actionItemRepository.UpdateAsync(actionItem);
        await _actionItemRepository.SaveChangesAsync();

        return true;
    }
}
