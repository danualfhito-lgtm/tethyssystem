import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
import os
import threading
import random
from collections import deque
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='/', intents=intents)

config = {
    'guild_id': 1485973418401861653,
    'booster_role_id': 1491433511633162342,
    'booster_announce_channel_id': 1490032606945873980
}

activity_log = deque(maxlen=200)


# ── Embed builders ────────────────────────────────────────────────────────────

def build_booster_embed(member):
    guild = member.guild
    now = datetime.now(timezone.utc)
    footer_text = (
        f'Boost Level: {guild.premium_tier} | '
        f'Total Boosts: {guild.premium_subscription_count} | '
        f'{now.strftime("%m/%d/%Y %I:%M %p")}'
    )
    embed = discord.Embed(
        title=f'🤜 Terimakasih {member.display_name} udah boost server ini yaa!',
        description=(
            f'Hey {member.mention}! makasih ya dah boost server ini\U0001f60d\n'
            f'Semoga hari-harinya makin baik selalu! 🤜'
        ),
        color=0xF47FFF
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=footer_text)
    return embed


def build_cusrole_edit_embed(role):
    session_id = random.randint(10**18, 10**19 - 1)
    color_hex = f'#{role.color.value:06X}' if role.color.value else '#000000'
    icon_text = f'[Lihat Icon]({role.icon.url})' if role.icon else 'Tidak ada icon'

    embed = discord.Embed(
        title=f'✏️ Edit Custom Role: {role.name}',
        description=(
            f'Gunakan tombol di bawah untuk mengedit role {role.mention}.\n'
            f'Properties akan disimpan ke database setelah klik "Selesai".'
        ),
        color=role.color if role.color.value else discord.Color.blurple()
    )
    if role.icon:
        embed.set_thumbnail(url=role.icon.url)
    embed.add_field(name='📝 Nama', value=role.name, inline=False)
    embed.add_field(name='🎨 Warna', value=color_hex, inline=False)
    embed.add_field(name='🖼️ Icon', value=icon_text, inline=False)
    embed.add_field(name='✨ Style', value='Standard (Solid/Default)', inline=False)
    embed.add_field(name='⚖️ Posisi', value=str(role.position), inline=False)
    embed.add_field(name='👤 Members', value=str(len(role.members)), inline=False)
    embed.set_footer(text=f'Session ID: {session_id}')
    embed.timestamp = datetime.now(timezone.utc)
    return embed


# ── Modals ────────────────────────────────────────────────────────────────────

class EditNamaModal(discord.ui.Modal, title='✏️ Edit Nama Role'):
    nama = discord.ui.TextInput(label='Nama Baru', placeholder='Masukkan nama role baru...', max_length=100)

    def __init__(self, role):
        super().__init__()
        self.role = role
        self.nama.default = role.name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            old_name = self.role.name
            await self.role.edit(name=self.nama.value, reason=f'CusRole edit by {interaction.user}')
            embed = build_cusrole_edit_embed(self.role)
            await interaction.response.edit_message(
                content=f'✅ Nama diubah: **{old_name}** → **{self.nama.value}**',
                embed=embed,
                view=CusRoleEditView(self.role, interaction.user.id)
            )
        except discord.Forbidden:
            await interaction.response.send_message('❌ Bot tidak memiliki izin untuk mengedit role ini.', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ Error: {e}', ephemeral=True)


class EditWarnaModal(discord.ui.Modal, title='🎨 Edit Warna Role'):
    warna = discord.ui.TextInput(label='Warna (Hex)', placeholder='#FF0000', max_length=7)

    def __init__(self, role):
        super().__init__()
        self.role = role
        self.warna.default = f'#{role.color.value:06X}' if role.color.value else '#000000'

    async def on_submit(self, interaction: discord.Interaction):
        try:
            hex_val = self.warna.value.lstrip('#')
            color = discord.Color(int(hex_val, 16))
            await self.role.edit(color=color, reason=f'CusRole edit by {interaction.user}')
            embed = build_cusrole_edit_embed(self.role)
            await interaction.response.edit_message(
                content=f'✅ Warna diubah ke `#{hex_val.upper()}`',
                embed=embed,
                view=CusRoleEditView(self.role, interaction.user.id)
            )
        except ValueError:
            await interaction.response.send_message('❌ Format warna tidak valid. Gunakan hex seperti #FF0000', ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message('❌ Bot tidak memiliki izin untuk mengedit role ini.', ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f'❌ Error: {e}', ephemeral=True)


class EditIconModal(discord.ui.Modal, title='🖼️ Edit Icon Role'):
    icon_url = discord.ui.TextInput(
        label='URL Icon', placeholder='https://... (kosongkan untuk hapus icon)', required=False
    )

    def __init__(self, role):
        super().__init__()
        self.role = role

    async def on_submit(self, interaction: discord.Interaction):
        try:
            import aiohttp
            if self.icon_url.value.strip():
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.icon_url.value.strip()) as resp:
                        icon_bytes = await resp.read()
                await self.role.edit(display_icon=icon_bytes, reason=f'CusRole edit by {interaction.user}')
            else:
                await self.role.edit(display_icon=None, reason=f'CusRole edit by {interaction.user}')
            embed = build_cusrole_edit_embed(self.role)
            await interaction.response.edit_message(
                content='✅ Icon berhasil diubah!',
                embed=embed,
                view=CusRoleEditView(self.role, interaction.user.id)
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                '❌ Bot tidak memiliki izin. Server perlu level 2 boost untuk icon role.', ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f'❌ Error: {e}', ephemeral=True)


# ── Views ─────────────────────────────────────────────────────────────────────

class CusRoleEditView(discord.ui.View):
    def __init__(self, role, user_id):
        super().__init__(timeout=300)
        self.role = role
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Ini bukan sesi editmu.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Edit Nama', emoji='📝', style=discord.ButtonStyle.secondary, row=0)
    async def edit_nama(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditNamaModal(self.role))

    @discord.ui.button(label='Edit Warna', emoji='🎨', style=discord.ButtonStyle.secondary, row=0)
    async def edit_warna(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditWarnaModal(self.role))

    @discord.ui.button(label='Edit Icon', emoji='🖼️', style=discord.ButtonStyle.secondary, row=1)
    async def edit_icon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditIconModal(self.role))

    @discord.ui.button(label='Ganti Style', emoji='✨', style=discord.ButtonStyle.primary, row=1)
    async def ganti_style(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            '✨ Fitur ganti style belum tersedia. Hubungi admin server.', ephemeral=True
        )

    @discord.ui.button(label='Selesai', style=discord.ButtonStyle.success, row=2)
    async def selesai(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content=f'✅ Perubahan pada role **{self.role.name}** telah disimpan!',
            embed=None, view=None
        )

    @discord.ui.button(label='Batal', style=discord.ButtonStyle.danger, row=2)
    async def batal(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content='❌ Editing role dibatalkan.', embed=None, view=None
        )


# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    guild = bot.get_guild(config['guild_id'])
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=config['guild_id']))
        await bot.tree.sync()
        print(f'🔄 Synced {len(synced)} slash commands')
    except Exception as e:
        print(f'❌ Sync error: {e}')
    print('✅ Tetys System ONLINE!')
    print(f'📊 Server: {guild.name}')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="members"))


@bot.event
async def on_member_update(before, after):
    if after.guild.id != config['guild_id']:
        return
    role = after.guild.get_role(config['booster_role_id'])
    if role and after.premium_since and not before.premium_since:
        await after.add_roles(role)
        channel = bot.get_channel(config['booster_announce_channel_id'])
        await channel.send(content=after.mention, embed=build_booster_embed(after))


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.application_command:
        return
    data = interaction.data or {}
    cmd_name = data.get('name', 'unknown')
    options = data.get('options', [])

    def parse_options(opts, prefix=''):
        parts = []
        for o in opts:
            if o.get('type') == 1:
                sub = parse_options(o.get('options', []))
                parts.append(f"{o['name']} {sub}".strip())
            elif o.get('type') == 2:
                sub = parse_options(o.get('options', []))
                parts.append(f"{o['name']} {sub}".strip())
            else:
                parts.append(f"{o['name']}: {o.get('value', '')}")
        return ' '.join(parts)

    args_str = parse_options(options)
    channel_name = getattr(interaction.channel, 'name', 'DM')

    activity_log.appendleft({
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'user_name': interaction.user.display_name,
        'user_tag': str(interaction.user),
        'user_avatar': str(interaction.user.display_avatar.url),
        'command': f'/{cmd_name}',
        'args': args_str,
        'channel': f'#{channel_name}',
    })


# ── Slash commands ────────────────────────────────────────────────────────────

async def natural_send(interaction: discord.Interaction, **kwargs):
    """Send a message naturally without the 'X used /command' banner, but showing who used it."""
    if 'embed' in kwargs:
        kwargs['embed'].set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url
        )
    await interaction.response.defer(ephemeral=True)
    await interaction.delete_original_response()
    await interaction.channel.send(**kwargs)


@bot.tree.command(name='tetys', description='Check if Tetys System is online')
async def tetys(interaction: discord.Interaction):
    embed = discord.Embed(title='✅ Tetys System OK!', color=0x00FF00)
    embed.set_footer(text='Tetys System')
    embed.timestamp = datetime.now(timezone.utc)
    await natural_send(interaction, embed=embed)


@bot.tree.command(name='mute', description='Server mute a member in voice channels')
@app_commands.describe(member='The member to mute', reason='Reason for muting')
@app_commands.default_permissions(mute_members=True)
async def mute(interaction: discord.Interaction, member: discord.Member, reason: str = 'No reason provided'):
    await interaction.response.defer(ephemeral=True)
    try:
        await member.edit(mute=True, reason=reason)
        embed = discord.Embed(title='🔇 Member Muted', color=0xFF6600)
        embed.add_field(name='Member', value=member.mention, inline=True)
        embed.add_field(name='Reason', value=reason, inline=True)
        embed.add_field(name='Moderator', value=interaction.user.mention, inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send('❌ I do not have permission to mute this member.', ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f'❌ Failed to mute: {e}', ephemeral=True)


@bot.tree.command(name='unmute', description='Remove server mute from a member in voice channels')
@app_commands.describe(member='The member to unmute', reason='Reason for unmuting')
@app_commands.default_permissions(mute_members=True)
async def unmute(interaction: discord.Interaction, member: discord.Member, reason: str = 'No reason provided'):
    await interaction.response.defer(ephemeral=True)
    try:
        await member.edit(mute=False, reason=reason)
        embed = discord.Embed(title='🔊 Member Unmuted', color=0x00FF00)
        embed.add_field(name='Member', value=member.mention, inline=True)
        embed.add_field(name='Reason', value=reason, inline=True)
        embed.add_field(name='Moderator', value=interaction.user.mention, inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send('❌ I do not have permission to unmute this member.', ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f'❌ Failed to unmute: {e}', ephemeral=True)


@bot.tree.command(name='timeout', description='Timeout a member (prevents messaging & joining VC)')
@app_commands.describe(member='The member to timeout', duration='Duration in minutes', reason='Reason for timeout')
@app_commands.default_permissions(moderate_members=True)
async def timeout_cmd(interaction: discord.Interaction, member: discord.Member, duration: int = 10, reason: str = 'No reason provided'):
    await interaction.response.defer(ephemeral=True)
    try:
        until = datetime.now(timezone.utc) + timedelta(minutes=duration)
        await member.timeout(until, reason=reason)
        embed = discord.Embed(title='⏱️ Member Timed Out', color=0xFF9900)
        embed.add_field(name='Member', value=member.mention, inline=True)
        embed.add_field(name='Duration', value=f'{duration} minute(s)', inline=True)
        embed.add_field(name='Expires', value=f'<t:{int(until.timestamp())}:R>', inline=True)
        embed.add_field(name='Reason', value=reason, inline=False)
        embed.add_field(name='Moderator', value=interaction.user.mention, inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send('❌ I do not have permission to timeout this member.', ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f'❌ Failed to timeout: {e}', ephemeral=True)


@bot.tree.command(name='untimeout', description='Remove timeout from a member')
@app_commands.describe(member='The member to remove timeout from')
@app_commands.default_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    try:
        await member.timeout(None)
        embed = discord.Embed(title='✅ Timeout Removed', color=0x00FF00)
        embed.add_field(name='Member', value=member.mention, inline=True)
        embed.add_field(name='Moderator', value=interaction.user.mention, inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send('❌ I do not have permission to remove this timeout.', ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f'❌ Failed to remove timeout: {e}', ephemeral=True)


@bot.tree.command(name='ban', description='Ban a member from the server')
@app_commands.describe(member='The member to ban', reason='Reason for ban', delete_days='Days of messages to delete (0-7)')
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = 'No reason provided', delete_days: int = 0):
    await interaction.response.defer(ephemeral=True)
    try:
        embed = discord.Embed(title='🔨 Member Banned', color=0xFF0000)
        embed.add_field(name='Member', value=f'{member} ({member.id})', inline=True)
        embed.add_field(name='Reason', value=reason, inline=True)
        embed.add_field(name='Moderator', value=interaction.user.mention, inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
        await member.ban(reason=reason, delete_message_days=max(0, min(7, delete_days)))
    except discord.Forbidden:
        await interaction.followup.send('❌ I do not have permission to ban this member.', ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f'❌ Failed to ban: {e}', ephemeral=True)


@bot.tree.command(name='unban', description='Unban a user by their ID')
@app_commands.describe(user_id='The user ID to unban', reason='Reason for unban')
@app_commands.default_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str, reason: str = 'No reason provided'):
    await interaction.response.defer(ephemeral=True)
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason=reason)
        embed = discord.Embed(title='✅ Member Unbanned', color=0x00FF00)
        embed.add_field(name='User', value=f'{user} ({user.id})', inline=True)
        embed.add_field(name='Reason', value=reason, inline=True)
        embed.add_field(name='Moderator', value=interaction.user.mention, inline=True)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except discord.NotFound:
        await interaction.followup.send('❌ User not found or not banned.', ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send('❌ I do not have permission to unban this user.', ephemeral=True)
    except ValueError:
        await interaction.followup.send('❌ Invalid user ID.', ephemeral=True)


# ── /cusrole command group ────────────────────────────────────────────────────

cusrole = app_commands.Group(name='cusrole', description='Custom role management')


@cusrole.command(name='create', description='Buat custom role baru')
@app_commands.describe(name='Nama role', color='Warna hex (contoh: FF73FA)')
async def cusrole_create(interaction: discord.Interaction, name: str, color: str = '5865F2'):
    await interaction.response.defer(ephemeral=True)
    try:
        hex_val = color.lstrip('#')
        role_color = discord.Color(int(hex_val, 16))
        new_role = await interaction.guild.create_role(
            name=name, color=role_color, reason=f'CusRole created by {interaction.user}'
        )
        await interaction.user.add_roles(new_role)
        embed = discord.Embed(
            title='✅ Custom Role Dibuat!',
            description=f'Role {new_role.mention} berhasil dibuat dan diberikan kepada {interaction.user.mention}.',
            color=role_color
        )
        embed.add_field(name='📝 Nama', value=new_role.name, inline=True)
        embed.add_field(name='🎨 Warna', value=f'#{hex_val.upper()}', inline=True)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text='Gunakan /cusrole edit untuk mengedit role.')
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except ValueError:
        await interaction.followup.send('❌ Format warna tidak valid.', ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send('❌ Bot tidak memiliki izin untuk membuat role.', ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f'❌ Error: {e}', ephemeral=True)


@cusrole.command(name='edit', description='Edit custom role kamu')
@app_commands.describe(role='Role yang ingin diedit')
async def cusrole_edit(interaction: discord.Interaction, role: discord.Role):
    embed = build_cusrole_edit_embed(role)
    view = CusRoleEditView(role, interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@cusrole.command(name='transfer', description='Pinjamkan role ke user lain')
@app_commands.describe(role='Role yang ingin ditransfer', target='User penerima')
async def cusrole_transfer(interaction: discord.Interaction, role: discord.Role, target: discord.Member):
    await interaction.response.defer(ephemeral=True)
    try:
        await target.add_roles(role)
        embed = discord.Embed(title='🔁 Role Ditransfer', color=0x5865F2)
        embed.add_field(name='Role', value=role.mention, inline=True)
        embed.add_field(name='Dari', value=interaction.user.mention, inline=True)
        embed.add_field(name='Ke', value=target.mention, inline=True)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text='Gunakan /cusrole reclaim untuk mengambil kembali.')
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send('❌ Bot tidak memiliki izin.', ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f'❌ Error: {e}', ephemeral=True)


@cusrole.command(name='reclaim', description='Ambil kembali role dari user lain')
@app_commands.describe(role='Role yang ingin diambil kembali', target='User yang sedang memegang role')
async def cusrole_reclaim(interaction: discord.Interaction, role: discord.Role, target: discord.Member):
    await interaction.response.defer(ephemeral=True)
    try:
        await target.remove_roles(role)
        await interaction.user.add_roles(role)
        embed = discord.Embed(title='↩️ Role Diambil Kembali', color=0x5865F2)
        embed.add_field(name='Role', value=role.mention, inline=True)
        embed.add_field(name='Dari', value=target.mention, inline=True)
        embed.add_field(name='Ke', value=interaction.user.mention, inline=True)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send('❌ Bot tidak memiliki izin.', ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f'❌ Error: {e}', ephemeral=True)


@cusrole.command(name='list', description='Lihat daftar custom role di server')
async def cusrole_list(interaction: discord.Interaction):
    guild = interaction.guild
    roles_list = [r for r in guild.roles if r.name != '@everyone' and not r.managed]
    if not roles_list:
        await interaction.response.send_message('❌ Tidak ada role yang ditemukan.', ephemeral=True)
        return
    desc = '\n'.join([f'{r.mention} — **{len(r.members)}** member(s)' for r in reversed(roles_list[:20])])
    embed = discord.Embed(title='📋 Daftar Role', description=desc, color=0x5865F2)
    embed.set_footer(text=f'Menampilkan {min(20, len(roles_list))} dari {len(roles_list)} role')
    embed.timestamp = datetime.now(timezone.utc)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@cusrole.command(name='info', description='Lihat info detail sebuah role')
@app_commands.describe(role='Role yang ingin dilihat infonya')
async def cusrole_info(interaction: discord.Interaction, role: discord.Role):
    color_hex = f'#{role.color.value:06X}' if role.color.value else '#000000'
    embed = discord.Embed(title=f'ℹ️ Info Role: {role.name}', color=role.color if role.color.value else discord.Color.blurple())
    embed.add_field(name='📝 Nama', value=role.name, inline=True)
    embed.add_field(name='🆔 ID', value=str(role.id), inline=True)
    embed.add_field(name='🎨 Warna', value=color_hex, inline=True)
    embed.add_field(name='⚖️ Posisi', value=str(role.position), inline=True)
    embed.add_field(name='👤 Members', value=str(len(role.members)), inline=True)
    embed.add_field(name='🖼️ Icon', value=f'[Lihat]({role.icon.url})' if role.icon else 'Tidak ada', inline=True)
    embed.timestamp = datetime.now(timezone.utc)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@cusrole.command(name='refund', description='Hapus role dan slot kembali')
@app_commands.describe(role='Role yang ingin dihapus')
async def cusrole_refund(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    try:
        role_name = role.name
        await role.delete(reason=f'CusRole refund by {interaction.user}')
        embed = discord.Embed(
            title='♻️ Role Dihapus — Slot Kembali',
            description=f'Role **{role_name}** telah dihapus. Slot boost kamu dikembalikan.',
            color=0xFAA61A
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send('❌ Bot tidak memiliki izin untuk menghapus role ini.', ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f'❌ Error: {e}', ephemeral=True)


@cusrole.command(name='delete', description='Hapus role permanen, slot hangus')
@app_commands.describe(role='Role yang ingin dihapus permanen')
async def cusrole_delete(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    try:
        role_name = role.name
        await role.delete(reason=f'CusRole permanent delete by {interaction.user}')
        embed = discord.Embed(
            title='🗑️ Role Dihapus Permanen',
            description=f'Role **{role_name}** telah dihapus permanen. Slot boost **hangus**.',
            color=0xFF0000
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await interaction.delete_original_response()
        await interaction.channel.send(embed=embed)
    except discord.Forbidden:
        await interaction.followup.send('❌ Bot tidak memiliki izin untuk menghapus role ini.', ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f'❌ Error: {e}', ephemeral=True)


bot.tree.add_command(cusrole)


# ── Flask web dashboard ───────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/channels')
def get_channels():
    guild = bot.get_guild(config['guild_id'])
    if not guild:
        return jsonify({'error': 'Guild not found'}), 404
    channels = [{'id': str(c.id), 'name': c.name} for c in guild.text_channels]
    return jsonify(channels)


@app.route('/send_embed', methods=['POST'])
def send_embed():
    import asyncio
    data = request.json
    channel_id = data.get('channel_id')
    if not channel_id:
        return jsonify({'error': 'No channel selected'}), 400

    title = data.get('title', '')
    description = data.get('description', '')
    raw_color = data.get('color', '#5865F2').lstrip('#')
    color = int(raw_color, 16)
    fields = data.get('fields', [])
    footer = data.get('footer', '')
    image_url = data.get('image_url', '')
    thumbnail_url = data.get('thumbnail_url', '')
    author = data.get('author', '')

    async def do_send():
        channel = bot.get_channel(int(channel_id))
        if not channel:
            return False
        embed = discord.Embed(title=title or None, description=description or None, color=color)
        for field in fields:
            if field.get('name') and field.get('value'):
                embed.add_field(name=field['name'], value=field['value'], inline=field.get('inline', False))
        if footer:
            embed.set_footer(text=footer)
        if image_url:
            embed.set_image(url=image_url)
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        if author:
            embed.set_author(name=author)
        embed.timestamp = datetime.now(timezone.utc)
        await channel.send(embed=embed)
        return True

    future = asyncio.run_coroutine_threadsafe(do_send(), bot.loop)
    try:
        success = future.result(timeout=10)
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Channel not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/send_booster_embed', methods=['POST'])
def send_booster_embed():
    import asyncio
    data = request.json
    channel_id = data.get('channel_id')
    member_id = data.get('member_id', '').strip()
    if not channel_id or not member_id:
        return jsonify({'error': 'Channel and member ID required'}), 400

    async def do_send():
        guild = bot.get_guild(config['guild_id'])
        channel = bot.get_channel(int(channel_id))
        if not channel:
            return None, 'Channel not found'
        try:
            member = await guild.fetch_member(int(member_id))
        except discord.NotFound:
            return None, 'Member not found in this server'
        except ValueError:
            return None, 'Invalid member ID'
        embed = build_booster_embed(member)
        await channel.send(content=member.mention, embed=embed)
        return member.display_name, None

    future = asyncio.run_coroutine_threadsafe(do_send(), bot.loop)
    try:
        name, error = future.result(timeout=10)
        if error:
            return jsonify({'error': error}), 404
        return jsonify({'success': True, 'member_name': name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/activity')
def get_activity():
    return jsonify(list(activity_log))


@app.route('/activity/clear', methods=['POST'])
def clear_activity():
    activity_log.clear()
    return jsonify({'success': True})


@app.route('/ping')
def ping():
    return jsonify({'status': 'online', 'bot': bot.is_ready()}), 200


def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ Set DISCORD_TOKEN in environment!")
        exit(1)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🔥 Starting Tetys System...")
    bot.run(token)
