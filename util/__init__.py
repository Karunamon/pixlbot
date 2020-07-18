import discord


def mkembed(kind: str, description: str, **kwargs) -> discord.Embed:
    """Creates a discordpy Embed with some sane defaults. "Kind" must be "done", "error", or "info"."""
    kindmap = {'done': discord.Color.green(), 'error': discord.Color.red(), 'info': discord.Color.blue()}
    if kind not in kindmap:
        raise ValueError(f"kind must be one of {kindmap}")
    e = discord.Embed(
        title=kind.capitalize(),
        description=description,
        color=kindmap[kind]
    )
    for k, v in kwargs.items():
        e.add_field(name=k, value=v)
    return e
