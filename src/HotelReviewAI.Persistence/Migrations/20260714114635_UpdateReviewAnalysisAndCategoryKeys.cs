using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace HotelReviewAI.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class UpdateReviewAnalysisAndCategoryKeys : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_ReviewAnalyses_ReviewCategories_CategoryId",
                table: "ReviewAnalyses");

            migrationBuilder.DropIndex(
                name: "IX_ReviewAnalyses_ReviewId",
                table: "ReviewAnalyses");

            migrationBuilder.DropColumn(
                name: "Keywords",
                table: "ReviewAnalyses");

            migrationBuilder.DropColumn(
                name: "Summary",
                table: "ReviewAnalyses");

            migrationBuilder.AddColumn<string>(
                name: "Key",
                table: "ReviewCategories",
                type: "character varying(100)",
                maxLength: 100,
                nullable: false,
                defaultValue: "");

            migrationBuilder.AlterColumn<string>(
                name: "Suggestion",
                table: "ReviewAnalyses",
                type: "character varying(500)",
                maxLength: 500,
                nullable: true,
                oldClrType: typeof(string),
                oldType: "text",
                oldNullable: true);

            migrationBuilder.AddColumn<int>(
                name: "ClauseIndex",
                table: "ReviewAnalyses",
                type: "integer",
                nullable: false,
                defaultValue: 0);

            migrationBuilder.AddColumn<string>(
                name: "ClauseText",
                table: "ReviewAnalyses",
                type: "text",
                nullable: false,
                defaultValue: "");

            migrationBuilder.AddColumn<int>(
                name: "Priority",
                table: "ReviewAnalyses",
                type: "integer",
                nullable: false,
                defaultValue: 0);

            migrationBuilder.AddColumn<string>(
                name: "Key",
                table: "Departments",
                type: "character varying(100)",
                maxLength: 100,
                nullable: false,
                defaultValue: "");

            migrationBuilder.CreateIndex(
                name: "IX_ReviewCategories_Key",
                table: "ReviewCategories",
                column: "Key",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ReviewAnalyses_ReviewId",
                table: "ReviewAnalyses",
                column: "ReviewId");

            migrationBuilder.CreateIndex(
                name: "IX_Departments_Key",
                table: "Departments",
                column: "Key",
                unique: true);

            migrationBuilder.AddForeignKey(
                name: "FK_ReviewAnalyses_ReviewCategories_CategoryId",
                table: "ReviewAnalyses",
                column: "CategoryId",
                principalTable: "ReviewCategories",
                principalColumn: "Id",
                onDelete: ReferentialAction.SetNull);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_ReviewAnalyses_ReviewCategories_CategoryId",
                table: "ReviewAnalyses");

            migrationBuilder.DropIndex(
                name: "IX_ReviewCategories_Key",
                table: "ReviewCategories");

            migrationBuilder.DropIndex(
                name: "IX_ReviewAnalyses_ReviewId",
                table: "ReviewAnalyses");

            migrationBuilder.DropIndex(
                name: "IX_Departments_Key",
                table: "Departments");

            migrationBuilder.DropColumn(
                name: "Key",
                table: "ReviewCategories");

            migrationBuilder.DropColumn(
                name: "ClauseIndex",
                table: "ReviewAnalyses");

            migrationBuilder.DropColumn(
                name: "ClauseText",
                table: "ReviewAnalyses");

            migrationBuilder.DropColumn(
                name: "Priority",
                table: "ReviewAnalyses");

            migrationBuilder.DropColumn(
                name: "Key",
                table: "Departments");

            migrationBuilder.AlterColumn<string>(
                name: "Suggestion",
                table: "ReviewAnalyses",
                type: "text",
                nullable: true,
                oldClrType: typeof(string),
                oldType: "character varying(500)",
                oldMaxLength: 500,
                oldNullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Keywords",
                table: "ReviewAnalyses",
                type: "jsonb",
                nullable: false,
                defaultValue: "");

            migrationBuilder.AddColumn<string>(
                name: "Summary",
                table: "ReviewAnalyses",
                type: "text",
                nullable: true);

            migrationBuilder.CreateIndex(
                name: "IX_ReviewAnalyses_ReviewId",
                table: "ReviewAnalyses",
                column: "ReviewId",
                unique: true);

            migrationBuilder.AddForeignKey(
                name: "FK_ReviewAnalyses_ReviewCategories_CategoryId",
                table: "ReviewAnalyses",
                column: "CategoryId",
                principalTable: "ReviewCategories",
                principalColumn: "Id");
        }
    }
}
