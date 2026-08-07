namespace HotelReviewAI.Domain.Entities;

/// <summary>
/// Departman yöneticisinin ekibindeki çalışan.
///
/// Kasıtlı olarak <see cref="User"/>'dan ayrıdır: bu kayıtların sisteme girişi
/// yoktur, parolası/rolü/yetkisi yoktur. Yalnızca yöneticinin kendi ekibini
/// kayıt altında tutması ve bir görevi kime verdiğini hatırlaması içindir.
/// </summary>
public class StaffMember : BaseEntity
{
    public string FirstName { get; set; } = string.Empty;
    public string LastName { get; set; } = string.Empty;

    /// <summary>İşe giriş tarihi.</summary>
    public DateTime? HireDate { get; set; }

    /// <summary>
    /// Doğum tarihi. Yaş bundan hesaplanır — yaşın kendisi saklanmaz, çünkü
    /// sayı olarak tutulsa her yıl eskir ve kimse güncellemeyi hatırlamaz.
    /// </summary>
    public DateTime? BirthDate { get; set; }

    /// <summary>Görev/unvan (ör. "Kat Görevlisi"). Serbest metin, opsiyonel.</summary>
    public string? Title { get; set; }

    /// <summary>Çalışanın bağlı olduğu departman — yöneticinin departmanı.</summary>
    public Guid DepartmentId { get; set; }
    public Department Department { get; set; } = null!;

    public Guid? HotelId { get; set; }
    public Hotel? Hotel { get; set; }

    public string FullName => $"{FirstName} {LastName}".Trim();
}
