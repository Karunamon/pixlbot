import re
from typing import List, Optional

import discord
import requests
from discord.ext import commands


def _get_emojis(msg: discord.Message) -> List[dict]:
    content = msg.content
    res = re.findall(r'<a?:(?P<name>\w+):(?P<snowflake>\d+)>', content)
    if not res:
        return []
    outputs = []
    for r in res:
        outputs.append(
            {
                'name': r[0],
                'id': r[1],
                'url': f"https://cdn.discordapp.com/emojis/{r[1]}.png",
                'aurl': f"https://cdn.discordapp.com/emojis/{r[1]}.gif",
                'data': None,
                'animated': None
            }
        )
    return outputs


def _download_emoji(e: dict) -> Optional[dict]:
    r = requests.get(e['aurl'])
    if r.ok:
        e['data'] = r.content
        e['animated'] = True
        return e
    else:
        r = requests.get(e['url'])
        if r.ok:
            e['data'] = r.content
            return e
        else:
            return None


class Yoink(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.logger.info("yo ho fiddle dee dee!")

    @commands.message_command(name="Yoink emojis", guild_ids=[709655247357739048])
    async def bonk(self, ctx: discord.ApplicationContext, message: discord.Message):
        await ctx.defer()
        emos = _get_emojis(message)
        if not emos:
            await ctx.respond("Nothing to do here :(", ephemeral=True)
            return
        emos = [_download_emoji(e) for e in emos]
        emos = [e for e in emos if e]  # strip nones
        newemos = []
        length = len(emos)
        for e in emos:
            newemos.append(await ctx.guild.create_custom_emoji(
                name=e['name'],
                image=e['data'],
                reason=f"yoinked by {ctx.author} from {message.author}"
            ))
        ymsg = ""
        for e in newemos:
            ymsg += f"<{'a' if e.animated else ''}:{e.name}:{e.id}> "

        await message.reply(f"Yoink! {ymsg}")
        await ctx.respond(f"{length} new emojis yoinked", ephemeral=True)


def setup(bot):
    bot.add_cog(Yoink(bot))
