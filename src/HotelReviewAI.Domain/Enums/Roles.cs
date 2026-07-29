namespace HotelReviewAI.Domain.Enums;

public static class Roles
{
    public const string Admin = "Admin";
    public const string Manager = "Manager";
    public const string DepartmentUser = "DepartmentUser";
    public const string MobileUser = "MobileUser";

    public static readonly string[] All = [Admin, Manager, DepartmentUser, MobileUser];
}
