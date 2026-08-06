using Npgsql;

var connStr = "Host=192.168.40.140;Port=5432;Database=stajor;Username=stajor1;Password=stajor1*-";
await using var conn = new NpgsqlConnection(connStr);
await conn.OpenAsync();

var action = args.Length > 0 ? args[0] : "help";

if (action == "check")
{
    // 1. AuditLogs - yetim (orphan) UserId'leri kontrol et
    Console.WriteLine("=== AuditLogs: Yetim UserId kontrol ===");
    await using (var cmd = conn.CreateCommand())
    {
        cmd.CommandText = """
            SELECT COUNT(*) FROM public."AuditLogs" a
            WHERE NOT EXISTS (SELECT 1 FROM public."Users" u WHERE u."Id" = a."UserId")
            """;
        var orphanCount = await cmd.ExecuteScalarAsync();
        Console.WriteLine($"  Yetim AuditLog kaydi: {orphanCount}");
    }

    // 2. ActionItems - yetim AssignedTo kontrol et
    Console.WriteLine("=== ActionItems: Yetim AssignedTo kontrol ===");
    await using (var cmd = conn.CreateCommand())
    {
        cmd.CommandText = """
            SELECT COUNT(*) FROM public."ActionItems" a
            WHERE a."AssignedTo" IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM public."Users" u WHERE u."Id" = a."AssignedTo")
            """;
        var orphanCount = await cmd.ExecuteScalarAsync();
        Console.WriteLine($"  Yetim ActionItem kaydi: {orphanCount}");
    }

    // 3. Reviews - yetim CreatedBy kontrol et
    Console.WriteLine("=== Reviews: Yetim CreatedBy kontrol ===");
    await using (var cmd = conn.CreateCommand())
    {
        cmd.CommandText = """
            SELECT COUNT(*) FROM public."Reviews" r
            WHERE r."CreatedBy" IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM public."Users" u WHERE u."Id" = r."CreatedBy")
            """;
        var orphanCount = await cmd.ExecuteScalarAsync();
        Console.WriteLine($"  Yetim Review kaydi: {orphanCount}");
    }

    // 4. Toplam kullanıcı sayısı
    Console.WriteLine("\n=== Users ozet ===");
    await using (var cmd = conn.CreateCommand())
    {
        cmd.CommandText = """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE "Email" LIKE '%@demo.com') AS demo,
                COUNT(*) FILTER (WHERE "Email" NOT LIKE '%@demo.com') AS personnel
            FROM public."Users"
            """;
        await using var reader = await cmd.ExecuteReaderAsync();
        if (await reader.ReadAsync())
        {
            Console.WriteLine($"  Toplam: {reader.GetInt64(0)}, Demo: {reader.GetInt64(1)}, Personel: {reader.GetInt64(2)}");
        }
    }
}
else if (action == "fix")
{
    // 1. Yetim AuditLog kayıtlarını sil (referansı kırık olanlar)
    Console.WriteLine("=== AuditLogs: Yetim kayitlari siliniyor ===");
    await using (var cmd = conn.CreateCommand())
    {
        cmd.CommandText = """
            DELETE FROM public."AuditLogs" a
            WHERE NOT EXISTS (SELECT 1 FROM public."Users" u WHERE u."Id" = a."UserId")
            """;
        var rows = await cmd.ExecuteNonQueryAsync();
        Console.WriteLine($"  Silinen yetim AuditLog: {rows}");
    }

    // 2. Yetim ActionItems.AssignedTo'yu NULL'a çek
    Console.WriteLine("=== ActionItems: Yetim AssignedTo NULL yapiliyor ===");
    await using (var cmd = conn.CreateCommand())
    {
        cmd.CommandText = """
            UPDATE public."ActionItems" a
            SET "AssignedTo" = NULL
            WHERE a."AssignedTo" IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM public."Users" u WHERE u."Id" = a."AssignedTo")
            """;
        var rows = await cmd.ExecuteNonQueryAsync();
        Console.WriteLine($"  Duzeltilen ActionItem: {rows}");
    }

    // 3. Yetim Reviews.CreatedBy'yi NULL'a çek
    Console.WriteLine("=== Reviews: Yetim CreatedBy NULL yapiliyor ===");
    await using (var cmd = conn.CreateCommand())
    {
        cmd.CommandText = """
            UPDATE public."Reviews" r
            SET "CreatedBy" = NULL
            WHERE r."CreatedBy" IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM public."Users" u WHERE u."Id" = r."CreatedBy")
            """;
        var rows = await cmd.ExecuteNonQueryAsync();
        Console.WriteLine($"  Duzeltilen Review: {rows}");
    }

    // 4. Personel kullanıcılarından (demo harici) PasswordHash ve Role'ü temizle
    Console.WriteLine("=== Personel: PasswordHash ve Role temizleniyor ===");
    await using (var cmd = conn.CreateCommand())
    {
        cmd.CommandText = """
            UPDATE public."Users"
            SET "PasswordHash" = '',
                "Role" = ''
            WHERE "Email" NOT LIKE '%@demo.com'
            """;
        var rows = await cmd.ExecuteNonQueryAsync();
        Console.WriteLine($"  Guncellenen personel: {rows}");
    }

    Console.WriteLine("\n=== Tum duzeltmeler tamamlandi! ===");
}
else if (action == "query")
{
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = """
        SELECT "FullName", "HotelName", "DepartmentName", "Role", "Email"
        FROM public."Users"
        ORDER BY "HotelName", "DepartmentName", "FullName"
        LIMIT 15
        """;
    await using var reader = await cmd.ExecuteReaderAsync();
    Console.WriteLine($"{"FullName",-25} {"HotelName",-35} {"DepartmentName",-30} {"Role",-16} {"Email"}");
    Console.WriteLine(new string('-', 130));
    while (await reader.ReadAsync())
    {
        Console.WriteLine($"{reader.GetString(0),-25} {(reader.IsDBNull(1) ? "NULL" : reader.GetString(1)),-35} {(reader.IsDBNull(2) ? "NULL" : reader.GetString(2)),-30} {reader.GetString(3),-16} {reader.GetString(4)}");
    }
}
else if (action == "count")
{
    await using var cmd = conn.CreateCommand();
    cmd.CommandText = """SELECT COUNT(*) FROM public."Users" """;
    var count = await cmd.ExecuteScalarAsync();
    Console.WriteLine($"Users tablosundaki toplam kayit: {count}");
}
else
{
    Console.WriteLine("Kullanim: dotnet run -- [check|fix|query|count]");
}
