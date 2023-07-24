import discord

guilds = []


def mkembed(kind: str, description: str, **kwargs) -> discord.Embed:
    """Creates a discordpy Embed with some sane defaults. "Kind" must be "done", "error", or "info"."""
    kindmap = {
        "done": discord.Color.green(),
        "error": discord.Color.red(),
        "info": discord.Color.blue(),
    }
    if kind not in kindmap:
        raise ValueError(f"kind must be one of {kindmap}")
    e = discord.Embed(
        title=kwargs.pop("title", None) or kind.capitalize(),
        description=description,
        color=kindmap[kind],
    )
    for k, v in kwargs.items():
        e.add_field(name=k, value=v)
    return e


def has_role(user: discord.Member, rolename: str) -> bool:
    return bool(discord.utils.get(user.roles, name=rolename))


def has_roles(user: discord.Member, roles: list[str]) -> bool:
    return any(
        has_role(user, rolestr)
        for rolestr in roles
    )


def update_guilds(guildlist: list):
    global guilds
    guilds = guildlist
