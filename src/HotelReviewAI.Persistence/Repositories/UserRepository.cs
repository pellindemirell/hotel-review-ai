using HotelReviewAI.Application.Interfaces;
using HotelReviewAI.Domain.Entities;
using HotelReviewAI.Persistence.Contexts;
using Microsoft.EntityFrameworkCore;

namespace HotelReviewAI.Persistence.Repositories;

public class UserRepository : GenericRepository<User>, IUserRepository
{
    public UserRepository(AppDbContext context) : base(context)
    {
    }

    // E-posta karşılaştırması büyük/küçük harfe duyarsız olmalı: "Admin@Adora.com" ile
    // kayıtlı hesaba giriş yapılamıyordu ve aynı adresin farklı yazımıyla ikinci bir
    // hesap oluşturulabiliyordu (benzersizlik indeksi de harfe duyarlı).
    public async Task<User?> GetByEmailAsync(string email)
    {
        if (string.IsNullOrWhiteSpace(email))
        {
            return null;
        }

        // ToLowerInvariant zorunlu: Türkçe kültürde "I" harfi "ı"ya dönüşüyor ve
        // "ADMIN@..." adresi "admın@..." olarak aranıp hiçbir kayıtla eşleşmiyordu.
        // Sorgu içindeki ToLower() ise C# değil, SQL lower() olarak çalışır.
        var normalized = email.Trim().ToLowerInvariant();
        return await DbSet.FirstOrDefaultAsync(u => u.Email.ToLower() == normalized);
    }

    public async Task<List<User>> GetUsersAsync(Guid? hotelId = null, Guid? departmentId = null)
    {
        var query = DbSet.AsQueryable();
        
        if (hotelId.HasValue)
        {
            query = query.Where(u => u.HotelId == hotelId.Value);
        }

        if (departmentId.HasValue)
        {
            query = query.Where(u => u.DepartmentId == departmentId.Value);
        }

        return await query.ToListAsync();
    }
}
