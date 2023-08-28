from util import split_content, MAX_MESSAGE_LENGTH, mkembed
import discord
import pytest


class TestSplitContent:
    #  Tests that the function correctly splits a content string that is shorter than MAX_MESSAGE_LENGTH.
    def test_short_content(self):
        content = "This is a short content string."
        result = list(split_content(content))
        assert len(result) == 1
        assert result[0] == content

    #  Tests that the function correctly splits a content string that is exactly MAX_MESSAGE_LENGTH.
    def test_exact_content(self):
        content = "A" * MAX_MESSAGE_LENGTH
        result = list(split_content(content))
        assert len(result) == 1
        assert result[0] == content

    #  Tests that the function correctly splits a content string that is longer than MAX_MESSAGE_LENGTH.
    def test_long_content(self):
        content = "A" * (MAX_MESSAGE_LENGTH + 1)
        result = list(split_content(content))
        assert len(result) == 2
        assert result[0] == "A" * MAX_MESSAGE_LENGTH
        assert result[1] == "A"

    #  Tests that the function correctly splits a content string that has multiple newlines.
    def test_multiple_newlines(self):
        content = "Line 1\nLine 2\nLine 3\nLine 4"
        result = list(split_content(content))
        assert len(result) == 1
        assert result[0] == content

        #  Tests that the function correctly handles an empty content string.

    def test_empty_content(self):
        content = ""
        result = list(split_content(content))
        assert len(result) == 0

    #  Tests that the function correctly handles a content string that has only one character.
    def test_single_character_content(self):
        content = "A"
        result = list(split_content(content))
        assert len(result) == 1
        assert result[0] == content


class TestMkembed:
    #  Tests that the function creates an embed with "done" kind and the provided description
    def test_embed_with_done_kind_and_description(self):
        kind = "done"
        description = "This is a done embed"
        embed = mkembed(kind, description)
        assert embed.title == "Done"
        assert embed.description == description
        assert embed.color == discord.Color.green()

    #  Tests that the function creates an embed with "error" kind and the provided description
    def test_embed_with_error_kind_and_description(self):
        kind = "error"
        description = "This is an error embed"
        embed = mkembed(kind, description)
        assert embed.title == "Error"
        assert embed.description == description
        assert embed.color == discord.Color.red()

    #  Tests that the function creates an embed with "info" kind and the provided description
    def test_embed_with_info_kind_and_description(self):
        kind = "info"
        description = "This is an info embed"
        embed = mkembed(kind, description)
        assert embed.title == "Info"
        assert embed.description == description
        assert embed.color == discord.Color.blue()

    #  Tests that the function creates an embed with a custom title and the provided fields
    def test_embed_with_custom_title_and_fields(self):
        kind = "done"
        description = "This is a done embed"
        title = "Custom Title"
        fields = {"Field 1": "Value 1", "Field 2": "Value 2"}
        embed = mkembed(kind, description, title=title, **fields)
        assert embed.title == title
        assert embed.description == description
        assert embed.color == discord.Color.green()
        for name, value in fields.items():
            assert any(
                field.name == name and field.value == value for field in embed.fields
            )

    #  Tests that the function raises a ValueError when an invalid kind is provided
    def test_embed_with_invalid_kind(self):
        kind = "invalid"
        description = "This is an invalid kind"
        with pytest.raises(ValueError):
            mkembed(kind, description)
