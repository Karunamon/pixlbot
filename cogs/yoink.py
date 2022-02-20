import re
from typing import List, Optional

import discord
import requests
from discord.ext import commands


class Yoink(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.logger.info("yo ho fiddle dee dee!")

    def _get_emojis(self, msg: discord.Message) -> List[dict]:
        content = msg.content
        res = re.finditer(r'<(?P<animated>a)?:(?P<name>\w+):(?P<snowflake>\d+)>', content)
        if not res:
            return []
        outputs = []
        for r in res:
            rd = r.groupdict()
            ext = 'gif' if rd.get('animated') else 'png'
            emo = {
                'name': rd['name'],
                'id': rd['snowflake'],
                'url': f"https://cdn.discordapp.com/emojis/{rd['snowflake']}.{ext}",
                'data': None,
                'animated': rd.get('animated')
            }
            self.bot.logger.debug(emo)
            outputs.append(emo)
        return outputs

    def _download_emoji(self, e: dict) -> Optional[dict]:
        self.bot.logger.debug(f"Downloading emoji from {e['url']}")
        r = requests.get(e['url'])
        if r.ok:
            e['data'] = r.content
            return e
        else:
            return None

    @commands.message_command(name="Yoink emojis", guild_ids=[709655247357739048])
    async def yoink(self, ctx: discord.ApplicationContext, message: discord.Message):
        await ctx.defer(ephemeral=True)
        emos = self._get_emojis(message)
        if not emos:
            await ctx.respond("Nothing to do here :(")
            return
        emos = [self._download_emoji(e) for e in emos]
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
        await ctx.respond(content=f"{length} new emoji{'s' if length > 1 else ''} yoinked")


def setup(bot):
    bot.add_cog(Yoink(bot))
