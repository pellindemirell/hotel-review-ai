using HotelReviewAI.Domain.Entities;

namespace HotelReviewAI.Application.Interfaces;

public interface IStaffMemberRepository : IGenericRepository<StaffMember>
{
    /// <summary>Departmanın aktif çalışanları, ada göre sıralı.</summary>
    Task<IEnumerable<StaffMember>> GetByDepartmentIdAsync(Guid departmentId);

    /// <summary>
    /// Verilen kimlikler için ad-soyad eşlemesi — ekipten ÇIKARILMIŞ
    /// (soft-delete) kayıtlar dahil.
    ///
    /// Görevdeki "kime verdim" notunun tek amacı sonradan hatırlamaktır;
    /// çalışan ekipten çıkarıldığında bu bilgi kaybolursa not anlamsızlaşır.
    /// Global IsActive filtresi bu sorguda bilerek devre dışı bırakılır.
    /// </summary>
    Task<Dictionary<Guid, string>> GetNamesByIdsAsync(IEnumerable<Guid> ids);
}
