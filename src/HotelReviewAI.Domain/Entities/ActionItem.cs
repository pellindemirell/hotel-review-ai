using HotelReviewAI.Domain.Enums;

namespace HotelReviewAI.Domain.Entities;

public class ActionItem : BaseEntity
{
    public Guid ReviewId { get; set; }
    public Review Review { get; set; } = null!;

    public Guid DepartmentId { get; set; }
    public Department Department { get; set; } = null!;

    public Guid? AssignedTo { get; set; }
    public User? AssignedUser { get; set; }

    /// <summary>
    /// Departman yöneticisinin bu işi verdiği ekip üyesi — YALNIZCA KAYIT.
    /// Hiçbir iş mantığını etkilemez: yetki, filtre, bildirim ve durum akışı
    /// bu alandan bağımsızdır. Amaç yöneticinin "bu işi kime vermiştim"
    /// sorusuna sonradan bakabilmesi. Çalışanın sistemde hesabı yoktur.
    /// </summary>
    public Guid? AssignedStaffId { get; set; }
    public StaffMember? AssignedStaff { get; set; }

    public Guid? HotelId { get; set; }
    public Hotel? Hotel { get; set; }

    public Guid? CategoryId { get; set; }
    public ReviewCategory? Category { get; set; }

    public string Title { get; set; } = string.Empty;
    public ActionItemStatus Status { get; set; } = ActionItemStatus.Open;
    public DateTime? DueDate { get; set; }
}
