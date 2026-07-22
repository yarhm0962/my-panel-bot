import discord
from discord import app_commands
import json
import random
import os
from datetime import datetime, timedelta
from flask import Flask
import threading

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

KEYS_FILE = "keys.json"
USERS_FILE = "users.json"

def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)

def generate_user_key():
    parts = []
    for _ in range(4):
        part = ''.join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(4))
        parts.append(part)
    return "-".join(parts)

def obfuscate_script(your_lua_code):
    obfuscator_key = random.randint(100000, 999999)
    key_str = str(obfuscator_key)
    hex_result = ""
    for i, char in enumerate(your_lua_code):
        k = ord(key_str[i % len(key_str)])
        mixed = ord(char) ^ k
        hex_result += f"{mixed:02x}"
    return hex_result, obfuscator_key

def build_protected_loadstring(your_lua_code, user_key):
    hex_data, obfuscator_key = obfuscate_script(your_lua_code)
    protected_script = f'''getgenv().SCRIPT_KEY = nil

local function Decrypt(data, key)
    local r = ""
    key = tostring(key)
    for i = 1, #data, 2 do
        local n = tonumber("0x" .. data:sub(i, i + 1))
        local k = string.byte(key, (((i - 1) // 2) % #key) + 1)
        r = r .. string.char(n ~ k)
    end
    return r
end

local function CheckKey()
    local key = getgenv().SCRIPT_KEY
    if not key or key == nil then
        return false
    end
    if key ~= "{user_key}" then
        return false
    end
    return true
end

if not CheckKey() then return end

local ENC = "{hex_data}"
local KEY = {obfuscator_key}
local OK, CODE = pcall(Decrypt, ENC, KEY)
if OK then
    loadstring(CODE)()
end
'''
    return protected_script, obfuscator_key

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Redeem Key", emoji="🔑", style=discord.ButtonStyle.Green, custom_id="redeem_btn")
    async def redeem_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Use `/redeem YOUR_KEY` command to redeem your key.", ephemeral=True)

    @discord.ui.button(label="Get Loadstring", emoji="📜", style=discord.ButtonStyle.Blurple, custom_id="loadstring_btn")
    async def loadstring_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        users = load_json(USERS_FILE)
        uid = str(interaction.user.id)
        if uid not in users:
            return await interaction.response.send_message("❌ Redeem your key first using `/redeem`.", ephemeral=True)
        user_key = users[uid]["key"]
        loadstring_code = f'loadstring(game:HttpGet("YOUR_HOSTED_LINK_HERE"))()\ngetgenv().SCRIPT_KEY = "{user_key}"'
        embed = discord.Embed(title="📜 Your Loadstring", color=discord.Color.green())
        embed.add_field(name="Copy this:", value=f"```lua\n{loadstring_code}\n```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Get Role", emoji="🎖️", style=discord.ButtonStyle.Grey, custom_id="role_btn")
    async def role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        users = load_json(USERS_FILE)
        uid = str(interaction.user.id)
        if uid not in users:
            return await interaction.response.send_message("❌ Redeem your key first using `/redeem`.", ephemeral=True)
        role = discord.utils.get(interaction.guild.roles, name="Verified User")
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Role assigned successfully!", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Role not found. Ask an admin to create it.", ephemeral=True)

@client.event
async def on_ready():
    await tree.sync()
    client.add_view(PanelView())

@tree.command(name="create-panel", description="Create control panel embed (Admin only)")
@app_commands.describe(script_title="Embed title", description="Embed description")
async def create_panel_cmd(interaction: discord.Interaction, script_title: str, description: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("No permission.", ephemeral=True)
    embed = discord.Embed(title=script_title, description=description, color=discord.Color.blue())
    embed.set_footer(text="M1rage Control Panel")
    await interaction.response.send_message(embed=embed, view=PanelView())

@tree.command(name="genkey", description="Generate new key (Admin only)")
@app_commands.describe(days="Days active")
async def genkey_cmd(interaction: discord.Interaction, days: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("No permission.", ephemeral=True)
    user_key = generate_user_key()
    keys = load_json(KEYS_FILE)
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
    keys[user_key] = {"active": True, "expires": expires, "owner": str(interaction.user.id)}
    save_json(KEYS_FILE, keys)
    await interaction.response.send_message(f"✅ Key Generated:\n`{user_key}`\nValid: {days} days", ephemeral=True)

@tree.command(name="redeem", description="Redeem your key")
@app_commands.describe(key="Your key")
async def redeem_cmd(interaction: discord.Interaction, key: str):
    keys = load_json(KEYS_FILE)
    users = load_json(USERS_FILE)
    uid = str(interaction.user.id)
    if key not in keys or not keys[key]["active"]:
        return await interaction.response.send_message("❌ Invalid or expired key.", ephemeral=True)
    users[uid] = {"key": key, "redeemed": datetime.utcnow().isoformat()}
    save_json(USERS_FILE, users)
    embed = discord.Embed(title="✅ Key Redeemed!", color=discord.Color.green())
    embed.add_field(name="Your Key", value=f"`{key}`", inline=False)
    embed.add_field(name="Status", value="Active ✅", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="protect", description="Protect script with key system (Admin only)")
@app_commands.describe(script="Your Lua script", user_key="User's key")
async def protect_cmd(interaction: discord.Interaction, script: str, user_key: str):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("No permission.", ephemeral=True)
    await interaction.response.defer()
    keys = load_json(KEYS_FILE)
    if user_key not in keys or not keys[user_key]["active"]:
        return await interaction.followup.send("❌ Invalid or inactive key.", ephemeral=True)
    protected, obfuscator_key = build_protected_loadstring(script, user_key)
    embed = discord.Embed(title="🔐 Script Protected", color=discord.Color.blue())
    embed.add_field(name="User Key", value=f"`{user_key}`", inline=False)
    embed.add_field(name="Obfuscator Key", value=f"`{obfuscator_key}`", inline=False)
    if len(protected) > 1900:
        with open("protected.lua", "w", encoding="utf-8") as f:
            f.write(protected)
        await interaction.followup.send(embed=embed, file=discord.File("protected.lua"))
    else:
        await interaction.followup.send(embed=embed)
        await interaction.followup.send(f"```lua\n{protected}\n```")

@tree.command(name="panel", description="View your personal panel")
async def panel_cmd(interaction: discord.Interaction):
    users = load_json(USERS_FILE)
    uid = str(interaction.user.id)
    if uid not in users:
        return await interaction.response.send_message("❌ Redeem your key first using `/redeem`.", ephemeral=True)
    embed = discord.Embed(title="🎛️ M1rage Control Panel", color=discord.Color.blue())
    embed.add_field(name="Your Key", value=f"`{users[uid]['key']}`", inline=False)
    embed.add_field(name="Status", value="✅ Active", inline=True)
    embed.add_field(name="How To Use", value="```lua\ngetgenv().SCRIPT_KEY = \"YOUR_KEY\"\nloadstring(\"LINK\")()\n```", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

app = Flask(__name__)
@app.route("/")
def home():
    return "Bot Online"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask, daemon=True).start()

client.run(TOKEN)
