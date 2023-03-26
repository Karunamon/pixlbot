from typing import TYPE_CHECKING

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

import util

if TYPE_CHECKING:
    from main import PixlBot


class RoleConcat(commands.Cog):
    roleconcat = SlashCommandGroup(
        name="roleconcat",
        description="Takes all the people here and puts them over there",
        guild_ids=util.guilds,
    )

    def __init__(self, bot):
        self.bot: PixlBot = bot
        self.config = bot.config["RoleConcat"]
        self.bot.logger.info("ready")

    @roleconcat.command(
        name="reconcile_roles",
        description="Re-evaluate all roleconcat rules",
        guild_ids=util.guilds,
    )
    async def rereconcile(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        chgcount = await self.reconcile_roles(ctx.guild) or "no"
        await ctx.send(
            f"Reconciled, made {chgcount} change{'s' if chgcount > 1 else ''}"
        )

    async def reconcile_roles(self, server: discord.Guild) -> int:
        if server.id not in self.config["servers"]:
            return 0

        changes = 0

        for parent_role in self.config["servers"][server.id].keys():
            d_parent_role: discord.Role = server.get_role(int(parent_role))
            parent_members = set(d_parent_role.members)
            all_child_members = []
            for child_role in self.config["servers"][server.id][parent_role]:
                d_child_role: discord.Role = server.get_role(int(child_role))
                all_child_members = all_child_members + d_child_role.members
            all_child_members = set(all_child_members)

            # Remove anyone not in a child from the parent
            member: discord.Member
            for member in parent_members.difference(all_child_members):
                changes += 1
                self.bot.logger.info(f"Removing {member} from {d_parent_role}")
                await member.remove_roles(
                    d_parent_role, reason="roleconcat: user not in any child roles"
                )

            # Add anyone in a child to the parent
            for member in all_child_members.difference(parent_members):
                changes += 1
                self.bot.logger.info(f"Adding {member} to {d_parent_role}")
                await member.add_roles(
                    d_parent_role, reason="roleconcat: user found in a child role"
                )

        return changes

    @commands.Cog.listener()
    async def on_member_update(self, _, after: discord.Member):
        await self.reconcile_roles(after.guild)


def setup(bot):
    bot.add_cog(RoleConcat(bot))
