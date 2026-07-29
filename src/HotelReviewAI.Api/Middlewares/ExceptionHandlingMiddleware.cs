using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Text.Json;
using System.Threading.Tasks;
using FluentValidation;
using HotelReviewAI.Domain.Exceptions;
using HotelReviewAI.Shared.Responses;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;

namespace HotelReviewAI.Api.Middlewares;

public class ExceptionHandlingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<ExceptionHandlingMiddleware> _logger;

    public ExceptionHandlingMiddleware(RequestDelegate next, ILogger<ExceptionHandlingMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await _next(context);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "An unhandled exception occurred: {Message}", ex.Message); // Hatayı log kaydı olarak kaydet
            await HandleExceptionAsync(context, ex); // Hata detaylarını istemciye uygun formatta dön
        }
    }

    private static async Task HandleExceptionAsync(HttpContext context, Exception exception)
    {
        context.Response.ContentType = "application/json";
        
        var statusCode = HttpStatusCode.InternalServerError;
        var errors = new List<string>();
        string message = "Sunucuda beklenmeyen bir hata oluştu.";

        if (exception is ValidationException validationException)
        {
            statusCode = HttpStatusCode.BadRequest;
            message = "Validasyon hatası.";
            errors.AddRange(validationException.Errors.Select(e => e.ErrorMessage));
        }
        else if (exception is DomainException domainException)
        {
            statusCode = HttpStatusCode.BadRequest;
            message = "İş kuralı ihlali.";
            errors.Add(domainException.Message);
        }
        else
        {
            errors.Add("Beklenmeyen bir hata oluştu.");
        }

        context.Response.StatusCode = (int)statusCode;

        var response = new BaseResponse<object>(false, message, null, errors);
        var jsonResponse = JsonSerializer.Serialize(response, new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        });

        await context.Response.WriteAsync(jsonResponse);
    }
}
