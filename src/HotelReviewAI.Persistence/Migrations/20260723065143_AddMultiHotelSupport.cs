using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HotelReviewAI.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddMultiHotelSupport : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<Guid>(
                name: "HotelId",
                table: "Users",
                type: "uuid",
                nullable: true);

            migrationBuilder.AddColumn<Guid>(
                name: "HotelId",
                table: "Reviews",
                type: "uuid",
                nullable: true);

            migrationBuilder.AddColumn<Guid>(
                name: "HotelId",
                table: "Departments",
                type: "uuid",
                nullable: true);

            migrationBuilder.AddColumn<Guid>(
                name: "HotelId",
                table: "ActionItems",
                type: "uuid",
                nullable: true);

            migrationBuilder.CreateTable(
                name: "Hotels",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "text", nullable: false),
                    Code = table.Column<string>(type: "text", nullable: false),
                    Address = table.Column<string>(type: "text", nullable: true),
                    IsActive = table.Column<bool>(type: "boolean", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Hotels", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Users_HotelId",
                table: "Users",
                column: "HotelId");

            migrationBuilder.CreateIndex(
                name: "IX_Reviews_HotelId",
                table: "Reviews",
                column: "HotelId");

            migrationBuilder.CreateIndex(
                name: "IX_Departments_HotelId",
                table: "Departments",
                column: "HotelId");

            migrationBuilder.CreateIndex(
                name: "IX_ActionItems_HotelId",
                table: "ActionItems",
                column: "HotelId");

            migrationBuilder.AddForeignKey(
                name: "FK_ActionItems_Hotels_HotelId",
                table: "ActionItems",
                column: "HotelId",
                principalTable: "Hotels",
                principalColumn: "Id");

            migrationBuilder.AddForeignKey(
                name: "FK_Departments_Hotels_HotelId",
                table: "Departments",
                column: "HotelId",
                principalTable: "Hotels",
                principalColumn: "Id");

            migrationBuilder.AddForeignKey(
                name: "FK_Reviews_Hotels_HotelId",
                table: "Reviews",
                column: "HotelId",
                principalTable: "Hotels",
                principalColumn: "Id");

            migrationBuilder.AddForeignKey(
                name: "FK_Users_Hotels_HotelId",
                table: "Users",
                column: "HotelId",
                principalTable: "Hotels",
                principalColumn: "Id");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_ActionItems_Hotels_HotelId",
                table: "ActionItems");

            migrationBuilder.DropForeignKey(
                name: "FK_Departments_Hotels_HotelId",
                table: "Departments");

            migrationBuilder.DropForeignKey(
                name: "FK_Reviews_Hotels_HotelId",
                table: "Reviews");

            migrationBuilder.DropForeignKey(
                name: "FK_Users_Hotels_HotelId",
                table: "Users");

            migrationBuilder.DropTable(
                name: "Hotels");

            migrationBuilder.DropIndex(
                name: "IX_Users_HotelId",
                table: "Users");

            migrationBuilder.DropIndex(
                name: "IX_Reviews_HotelId",
                table: "Reviews");

            migrationBuilder.DropIndex(
                name: "IX_Departments_HotelId",
                table: "Departments");

            migrationBuilder.DropIndex(
                name: "IX_ActionItems_HotelId",
                table: "ActionItems");

            migrationBuilder.DropColumn(
                name: "HotelId",
                table: "Users");

            migrationBuilder.DropColumn(
                name: "HotelId",
                table: "Reviews");

            migrationBuilder.DropColumn(
                name: "HotelId",
                table: "Departments");

            migrationBuilder.DropColumn(
                name: "HotelId",
                table: "ActionItems");
        }
    }
}
