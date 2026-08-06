FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src

# Copy project files for restoring dependencies
COPY ["src/HotelReviewAI.Api/HotelReviewAI.Api.csproj", "src/HotelReviewAI.Api/"]
COPY ["src/HotelReviewAI.Application/HotelReviewAI.Application.csproj", "src/HotelReviewAI.Application/"]
COPY ["src/HotelReviewAI.Domain/HotelReviewAI.Domain.csproj", "src/HotelReviewAI.Domain/"]
COPY ["src/HotelReviewAI.Infrastructure/HotelReviewAI.Infrastructure.csproj", "src/HotelReviewAI.Infrastructure/"]
COPY ["src/HotelReviewAI.Persistence/HotelReviewAI.Persistence.csproj", "src/HotelReviewAI.Persistence/"]
COPY ["src/HotelReviewAI.Shared/HotelReviewAI.Shared.csproj", "src/HotelReviewAI.Shared/"]

RUN dotnet restore "src/HotelReviewAI.Api/HotelReviewAI.Api.csproj"

# Copy the entire source code
COPY . .

# Build and publish the application in Release mode
WORKDIR "/src/src/HotelReviewAI.Api"
RUN dotnet publish "HotelReviewAI.Api.csproj" -c Release -o /app/publish /p:UseAppHost=false

# Runtime stage using ASP.NET Core runtime image
FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .

# Expose HTTP port 5012 inside the container
ENV ASPNETCORE_URLS=http://+:5012
EXPOSE 5012

ENTRYPOINT ["dotnet", "HotelReviewAI.Api.dll"]
