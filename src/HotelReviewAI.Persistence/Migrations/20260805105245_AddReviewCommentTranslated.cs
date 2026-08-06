using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HotelReviewAI.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddReviewCommentTranslated : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "CommentTranslated",
                table: "Reviews",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<DateTime>(
                name: "TranslatedAt",
                table: "Reviews",
                type: "timestamp with time zone",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "CommentTranslated",
                table: "Reviews");

            migrationBuilder.DropColumn(
                name: "TranslatedAt",
                table: "Reviews");
        }
    }
}
