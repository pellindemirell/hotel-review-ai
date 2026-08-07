using HotelReviewAI.Application;
using HotelReviewAI.Infrastructure;
using HotelReviewAI.Persistence;
using HotelReviewAI.Persistence.Contexts;
using HotelReviewAI.Persistence.Seed;
using HotelReviewAI.Shared.Responses;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Mvc;
using Microsoft.IdentityModel.Tokens;
using Scalar.AspNetCore;
using Serilog;
using System.Text;
using System.Text.Json;
using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

// Configure Serilog
Log.Logger = new LoggerConfiguration()
    .WriteTo.Console()
    .WriteTo.File("logs/log-.txt", rollingInterval: RollingInterval.Day)
    .CreateLogger();

builder.Host.UseSerilog();

// Add services to the container.
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.CamelCase;
        options.JsonSerializerOptions.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter());
    })
    .ConfigureApiBehaviorOptions(options =>
    {
        // Model binding / [ApiController] doğrulama hataları varsayılan olarak RFC7807
        // ProblemDetails döndürüyor; istemci ise her yerde BaseResponse bekliyor.
        // Aynı zarfa çeviriyoruz ki hata mesajları tek bir yerden okunabilsin.
        options.InvalidModelStateResponseFactory = context =>
        {
            var errors = context.ModelState
                .Where(entry => entry.Value?.Errors.Count > 0)
                .SelectMany(entry => entry.Value!.Errors
                    .Select(error => DescribeModelError(entry.Key, error.ErrorMessage)))
                .Where(message => message is not null)
                .Select(message => message!)
                .Distinct()
                .ToList();

            if (errors.Count == 0)
            {
                errors.Add("Gönderilen veri geçersiz.");
            }

            return new BadRequestObjectResult(
                BaseResponse<object>.Fail(errors, "Gönderilen veri doğrulanamadı."));
        };
    });

//  Katman DI Extension Metotları 
builder.Services.AddApplication();
builder.Services.AddInfrastructure(builder.Configuration);
builder.Services.AddPersistence(builder.Configuration);


// Configure SignalR and Notification Services
builder.Services.AddSignalR();
builder.Services.AddScoped<HotelReviewAI.Application.Interfaces.IAnalysisNotificationService, HotelReviewAI.Api.Services.SignalRAnalysisNotificationService>();

// Configure CORS (Web & Mobile)
// Önceden AllowAnyOrigin() vardı: herhangi bir sitedeki JavaScript API'ye istek
// atabiliyordu. İzinli origin listesi Cors:AllowedOrigins ile verilir
// (appsettings.Development.json veya Cors__AllowedOrigins__0 ortam değişkeni).
var allowedOrigins = builder.Configuration
    .GetSection("Cors:AllowedOrigins")
    .Get<string[]>() ?? [];

if (allowedOrigins.Length == 0)
{
    throw new InvalidOperationException(
        "Cors:AllowedOrigins boş. En az bir origin verilmelidir (ör. \"http://localhost:4200\"). " +
        "appsettings.Development.json veya Cors__AllowedOrigins__0 ortam değişkeni ile tanımlayın.");
}

builder.Services.AddCors(options =>
{
    options.AddPolicy("Default", policy =>
    {
        policy.WithOrigins(allowedOrigins)
              .AllowAnyMethod()
              .AllowAnyHeader()
              // SignalR tarayıcıdan credential'lı bağlanıyor; AllowAnyOrigin ile
              // birlikte kullanılamadığı için bu ancak liste daraltılınca mümkün.
              .AllowCredentials();
    });
});

// Configure JWT Authentication
var jwtSecret = builder.Configuration["JwtSettings:Secret"];
if (string.IsNullOrWhiteSpace(jwtSecret))
{
    throw new InvalidOperationException(
        "JwtSettings:Secret is missing. appsettings.Development.json, ortam değişkeni (JwtSettings__Secret) " +
        "veya user-secrets ile en az 32 karakterlik bir değer verilmelidir.");
}

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        // 401/403 varsayılan olarak gövdesiz döndüğü için istemci hiçbir mesaj gösteremiyordu.
        options.Events = new JwtBearerEvents
        {
            // Tarayıcıdaki WebSocket bağlantıları Authorization header'ı gönderemez;
            // SignalR token'ı access_token query parametresinde taşır. Bu olmadan
            // [Authorize] işaretli hub'a WebSocket transportuyla hiç bağlanılamaz.
            OnMessageReceived = context =>
            {
                var accessToken = context.Request.Query["access_token"];
                if (!string.IsNullOrEmpty(accessToken)
                    && context.HttpContext.Request.Path.StartsWithSegments("/hubs"))
                {
                    context.Token = accessToken;
                }

                return Task.CompletedTask;
            },
            OnChallenge = async context =>
            {
                context.HandleResponse();
                await WriteAuthErrorAsync(
                    context.Response,
                    StatusCodes.Status401Unauthorized,
                    "Oturumunuz geçersiz veya süresi dolmuş. Lütfen tekrar giriş yapın.");
            },
            OnForbidden = async context =>
                await WriteAuthErrorAsync(
                    context.Response,
                    StatusCodes.Status403Forbidden,
                    "Bu işlem için yetkiniz yok.")
        };

        options.MapInboundClaims = false;
        options.TokenValidationParameters = new TokenValidationParameters
        {
            // JwtProvider rolü düz "role" claim'i olarak yazıyor ve MapInboundClaims=false olduğu için
            // ClaimTypes.Role'a map edilmiyor. Bu olmadan [Authorize(Roles=...)] ve User.IsInRole()
            // hiçbir kullanıcı için eşleşmez.
            RoleClaimType = "role",
            NameClaimType = "name",
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            // Varsayılan 5 dakikalık tolerans, süresi dolmuş token'ların bir süre daha
            // kabul edilmesine yol açıyordu.
            ClockSkew = TimeSpan.FromSeconds(30),
            ValidIssuer = builder.Configuration["JwtSettings:Issuer"],
            ValidAudience = builder.Configuration["JwtSettings:Audience"],
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtSecret))
        };
    });

builder.Services.AddAuthorization(options =>
{
    // Hiçbir yetki metadata'sı olmayan endpoint'ler varsayılan olarak kimlik doğrulaması ister.
    // Böylece [Authorize] eklemeyi unutan yeni bir controller açıkta kalmaz; anonim erişmesi
    // gerekenler ([AllowAnonymous]) açıkça işaretlenir.
    options.FallbackPolicy = new AuthorizationPolicyBuilder()
        .RequireAuthenticatedUser()
        .Build();

    options.AddPolicy("HotelAdminOrAbove", policy =>
        policy.RequireClaim("role", 
            nameof(HotelReviewAI.Domain.Enums.UserRole.SuperAdmin), 
            nameof(HotelReviewAI.Domain.Enums.UserRole.HotelAdmin)));
});

// Login için hız sınırı: parola deneme saldırılarını yavaşlatır.
// IP başına dakikada 10 deneme; aşan istekler 429 + BaseResponse gövdesiyle reddedilir.
builder.Services.AddRateLimiter(options =>
{
    options.AddPolicy("login", context => RateLimitPartition.GetFixedWindowLimiter(
        partitionKey: context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
        factory: _ => new FixedWindowRateLimiterOptions
        {
            PermitLimit = 10,
            Window = TimeSpan.FromMinutes(1),
            QueueLimit = 0
        }));

    options.OnRejected = async (context, cancellationToken) =>
    {
        context.HttpContext.Response.StatusCode = StatusCodes.Status429TooManyRequests;
        context.HttpContext.Response.ContentType = "application/json";

        var payload = JsonSerializer.Serialize(
            BaseResponse<object>.Fail("Çok fazla giriş denemesi yapıldı. Lütfen bir dakika sonra tekrar deneyin."),
            new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });

        await context.HttpContext.Response.WriteAsync(payload, cancellationToken);
    };
});

// Configure OpenAPI (replaces Swashbuckle)
builder.Services.AddOpenApi();

var app = builder.Build();

// Seed data
// Seed:Enabled false ise demo verisi yazılmaz; paylaşılan bir veritabanına bağlanırken
// (ör. ekip sunucusu) istenmeyen INSERT/UPDATE'leri önlemek için kullanılır. Varsayılan true.
using (var scope = app.Services.CreateScope())
{
    var dbContext = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    await dbContext.Database.MigrateAsync();

    if (app.Configuration.GetValue("Seed:Enabled", true))
    {
        await DbSeeder.SeedAsync(dbContext);
    }
    else
    {
        Log.Information("Seed:Enabled=false — DbSeeder atlandı.");
    }
}

// UseCors, exception middleware'inden ÖNCE olmalı: CORS header'ları isteğin giriş yolunda
// yazılır. Ters sırada, exception'dan üretilen 4xx/5xx yanıtlarında header'lar bulunmadığı
// için tarayıcı gövdeyi okuyamıyor ve kullanıcı hata mesajı yerine CORS hatası görüyordu.
app.UseCors("Default");

app.UseMiddleware<HotelReviewAI.Api.Middlewares.ExceptionHandlingMiddleware>();

if (app.Environment.IsDevelopment())
{
    // OpenAPI JSON endpoint: /openapi/v1.json
    app.MapOpenApi().AllowAnonymous();
    // Scalar UI: /scalar/v1
    app.MapScalarApiReference().AllowAnonymous();
}

app.UseStaticFiles(new StaticFileOptions
{
    OnPrepareResponse = ctx =>
    {
        ctx.Context.Response.Headers["Access-Control-Allow-Origin"] = "*";
        ctx.Context.Response.Headers["Cache-Control"] = "no-cache, no-store, must-revalidate";
    }
});
app.UseRateLimiter();
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();
app.MapHub<HotelReviewAI.Api.Hubs.AnalysisHub>("/hubs/analysis");

// Eşleşmeyen route'lar gövdesiz 404 döndürüyordu; istemci hiçbir mesaj gösteremiyordu.
app.MapFallback(async context =>
{
    context.Response.StatusCode = StatusCodes.Status404NotFound;
    context.Response.ContentType = "application/json";

    var payload = JsonSerializer.Serialize(
        BaseResponse<object>.Fail("İstenen kaynak bulunamadı."),
        new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });

    await context.Response.WriteAsync(payload);
});

app.Run();

// System.Text.Json'ın ham hata metinleri hem kullanıcıya anlamsız hem de iç tip
// isimlerini ("...Commands.Reviews.CreateReviewCommand") dışarı sızdırıyor.
// Bunları alan adına indirgenmiş, okunabilir mesajlara çeviriyoruz.
static string? DescribeModelError(string key, string? errorMessage)
{
    var fieldName = ExtractFieldName(key);

    if (string.IsNullOrWhiteSpace(errorMessage))
    {
        return fieldName is null ? "Gönderilen veri geçersiz." : $"'{fieldName}' alanı geçersiz.";
    }

    // Gövde hiç okunamadığında ("The X field is required.") alan adı, action parametresinin
    // adıdır (ör. "command") — kullanıcı için anlamsız olduğundan genel mesaja çeviriyoruz.
    if (fieldName is null)
    {
        var bodyMissing = errorMessage.Contains("field is required", StringComparison.OrdinalIgnoreCase)
            || errorMessage.Contains("non-empty request body", StringComparison.OrdinalIgnoreCase);

        return bodyMissing ? "İstek gövdesi okunamadı veya eksik." : errorMessage;
    }

    if (errorMessage.Contains("could not be converted", StringComparison.OrdinalIgnoreCase)
        || errorMessage.Contains("is not a valid", StringComparison.OrdinalIgnoreCase)
        || errorMessage.Contains("JSON", StringComparison.OrdinalIgnoreCase))
    {
        return $"'{fieldName}' alanı beklenen türde değil.";
    }

    return errorMessage;
}

// ModelState anahtarı "$.rating" / "$.items[0].name" / "command" biçiminde gelebilir.
// Gövdenin tamamına ait hatalarda ("$", "command") alan adı yoktur.
static string? ExtractFieldName(string key)
{
    if (string.IsNullOrWhiteSpace(key) || key == "$")
    {
        return null;
    }

    var name = key.StartsWith("$.", StringComparison.Ordinal) ? key[2..] : null;
    return string.IsNullOrWhiteSpace(name) ? null : name;
}

// Kimlik doğrulama/yetki hatalarını da BaseResponse zarfıyla döndürür.
static async Task WriteAuthErrorAsync(HttpResponse response, int statusCode, string message)
{
    if (response.HasStarted)
    {
        return;
    }

    response.StatusCode = statusCode;
    response.ContentType = "application/json";

    var payload = JsonSerializer.Serialize(
        BaseResponse<object>.Fail(message),
        new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });

    await response.WriteAsync(payload);
}
