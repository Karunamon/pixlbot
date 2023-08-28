import discord

guilds = []
MAX_MESSAGE_LENGTH = 2000


discord_color_mapping = {
    "done": discord.Color.green(),
    "error": discord.Color.red(),
    "info": discord.Color.blue(),
}


def mkembed(kind: str, description: str, **kwargs) -> discord.Embed:
    """Creates a discord.py rich embed with sane defaults
    :param kind: The kind of embed to create. Must be one of "done", "error", or "info".
    :param description: The description of the embed.
    :param kwargs: Additional key-value pairs to add as fields to the embed.
    :return: A discord.Embed object representing the specified embed.
    """
    if kind not in discord_color_mapping:
        raise ValueError(f"kind must be one of {discord_color_mapping.keys()}")
    e = discord.Embed(
        title=kwargs.pop("title", kind.capitalize()),
        description=description,
        color=discord_color_mapping[kind],
    )
    for k, v in kwargs.items():
        e.add_field(name=k, value=v)
    return e


def has_role(user: discord.Member, rolename: str) -> bool:
    return bool(discord.utils.get(user.roles, name=rolename))


def has_roles(user: discord.Member, roles: list[str]) -> bool:
    return any(has_role(user, rolestr) for rolestr in roles)


def update_guilds(guildlist: list):
    global guilds
    guilds = guildlist


def split_content(content: str):
    """
    Split the given content string into chunks that fit within Discord's max message length.

    :param content: The content to split.
    :return: A generator that yields each chunk of the split content.
    """

    while content:
        split_index = min(len(content), MAX_MESSAGE_LENGTH)
        newline_index = content[:split_index].rfind("\n")

        if newline_index != -1 and len(content) > MAX_MESSAGE_LENGTH:
            split_index = newline_index

        chunk, content = content[:split_index], content[split_index:].lstrip("\n")
        yield chunk
