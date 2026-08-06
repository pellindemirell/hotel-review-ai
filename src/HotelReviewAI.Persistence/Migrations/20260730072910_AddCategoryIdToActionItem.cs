using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HotelReviewAI.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddCategoryIdToActionItem : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<Guid>(
                name: "CategoryId",
                table: "ActionItems",
                type: "uuid",
                nullable: true);

            migrationBuilder.CreateIndex(
                name: "IX_ActionItems_CategoryId",
                table: "ActionItems",
                column: "CategoryId");

            migrationBuilder.AddForeignKey(
                name: "FK_ActionItems_ReviewCategories_CategoryId",
                table: "ActionItems",
                column: "CategoryId",
                principalTable: "ReviewCategories",
                principalColumn: "Id",
                onDelete: ReferentialAction.SetNull);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_ActionItems_ReviewCategories_CategoryId",
                table: "ActionItems");

            migrationBuilder.DropIndex(
                name: "IX_ActionItems_CategoryId",
                table: "ActionItems");

            migrationBuilder.DropColumn(
                name: "CategoryId",
                table: "ActionItems");
        }
    }
}
