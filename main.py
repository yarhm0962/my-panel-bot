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

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("Commands Synced")

client = MyBot()

KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
PANEL_FILE = "panel.json"

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

def obfuscate_script(your_lua_code, user_key):
    obfuscator_key = random.randint(100000, 999999)
    key_str = str(obfuscator_key)
    hex_result = ""
    for i, char in enumerate(your_lua_code):
        k = ord(key_str[i % len(key_str)])
        mixed = ord(char) ^ k
        hex_result += f"{mixed:02x}"
    
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

local ENC = "{hex_result}"
local KEY = {obfuscator_key}
local OK, CODE = pcall(Decrypt, ENC, KEY)
if OK then
    loadstring(CODE)()
end
'''
    return protected_script, obfuscator_key

class RedeemModal(discord.ui.Modal, title="Redeem Your Key"):
    key_input = discord.ui.TextInput(
        label="Key to Redeem",
        placeholder="Enter your key...",
        required=True,
        min_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        key = self.key_input.value.strip()
        keys = load_json(KEYS_FILE)
        users = load_json(USERS_FILE)
        uid = str(interaction.user.id)
        
        if key not in keys or not keys[key]["active"]:
            return await interaction.response.send_message("❌ Invalid or expired key.", ephemeral=True)
        
        users[uid] = {"key": key, "redeemed": datetime.utcnow().isoformat()}
        save_json(USERS_FILE, users)
        
        embed = discord.Embed(title="✅ Key Redeemed Successfully!", color=discord.Color.green())
        embed.add_field(name="Your Key", value=f"`{key}`", inline=False)
        embed.add_field(name="Status", value="Active ✅", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Redeem Key", emoji="🔑", style=discord.ButtonStyle.green, custom_id="redeem_btn")
    async def redeem_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        users = load_json(USERS_FILE)
        uid = str(interaction.user.id)
        if uid in users:
            return await interaction.response.send_message("✅ Your key is already redeemed!", ephemeral=True)
        await interaction.response.send_modal(RedeemModal())

    @discord.ui.button(label="Get Loadstring", emoji="📜", style=discord.ButtonStyle.blurple, custom_id="loadstring_btn")
    async def loadstring_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        users = load_json(USERS_FILE)
        panel = load_json(PANEL_FILE)
        uid = str(interaction.user.id)
        if uid not in users:
            return await interaction.response.send_message("❌ Redeem your key first using the button above.", ephemeral=True)
        if "script_link" not in panel or not panel["script_link"]:
            return await interaction.response.send_message("⚠️ No script has been added yet.", ephemeral=True)
        user_key = users[uid]["key"]
        loadstring_code = f'loadstring(game:HttpGet("{panel["script_link"]}"))()\ngetgenv().SCRIPT_KEY = "{user_key}"'
        embed = discord.Embed(title="📜 Your Loadstring", color=discord.Color.green())
        embed.add_field(name="Copy this:", value=f"```lua\n{loadstring_code}\n```", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Get Role", emoji="🎖️", style=discord.ButtonStyle.grey, custom_id="role_btn")
    async def role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        users = load_json(USERS_FILE)
        uid = str(interaction.user.id)
        if uid not in users:
            return await interaction.response.send_message("❌ Redeem your key first using the button above.", ephemeral=True)
        role = discord.utils.get(interaction.guild.roles, name="Verified User")
        if role:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("✅ Role assigned successfully!", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ Role 'Verified User' not found.", ephemeral=True)

@client.event
async def on_ready():
    print(f"Bot Online: {client.user}")
    client.add_view(PanelView())

@client.tree.command(name="create-panel", description="Create control panel")
@app_commands.describe(script_title="Embed title", description="Embed description (optional)")
async def create_panel(interaction: discord.Interaction, script_title: str, description: str = None):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("No permission.", ephemeral=True)
    
    if not description:
        description = f"This control panel is for the project: **{script_title}**\n\nIf you're a buyer, click on the buttons below to redeem your key, get the script or get your role."
    
    embed = discord.Embed(title=script_title, description=description, color=discord.Color.blue())
    embed.set_footer(text="M1rage Control Panel")
    
    panel = load_json(PANEL_FILE)
    panel["title"] = script_title
    panel["description"] = description
    panel["channel_id"] = str(interaction.channel_id)
    save_json(PANEL_FILE, panel)
    
    await interaction.response.send_message(embed=embed, view=PanelView())

@client.tree.command(name="genkey", description="Generate new key")
@app_commands.describe(days="Days active")
async def genkey(interaction: discord.Interaction, days: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("No permission.", ephemeral=True)
    user_key = generate_user_key()
    keys = load_json(KEYS_FILE)
    expires = (datetime.utcnow() + timedelta(days=days)).isoformat()
    keys[user_key] = {"active": True, "expires": expires, "owner": str(interaction.user.id)}
    save_json(KEYS_FILE, keys)
    await interaction.response.send_message(f"✅ Key Generated:\n`{user_key}`\nValid: {days} days", ephemeral=True)

@client.tree.command(name="add-script", description="Add Lua script file (Admin only)")
@app_commands.describe(file="Upload .lua or .txt file")
async def add_script(interaction: discord.Interaction, file: discord.Attachment):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("No permission.", ephemeral=True)
    
    panel = load_json(PANEL_FILE)
    if not panel or "channel_id" not in panel:
        return await interaction.response.send_message("⚠️ No panel found. Create one first with `/create-panel`.", ephemeral=True)
    
    if not (file.filename.endswith(".lua") or file.filename.endswith(".txt")):
        return await interaction.response.send_message("❌ Only .lua or .txt files accepted.", ephemeral=True)
    
    await interaction.response.send_message("🔄 Script is being obfuscated...", ephemeral=True)
    
    content = await file.read()
    lua_code = content.decode("utf-8")
    
    all_keys = load_json(KEYS_FILE)
    first_key = None
    for k, v in all_keys.items():
        if v["active"]:
            first_key = k
            break
    if not first_key:
        return await interaction.followup.send("❌ No active keys found. Generate a key first.", ephemeral=True)
    
    protected, obf_key = obfuscate_script(lua_code, first_key)
    
    with open("protected_script.lua", "w", encoding="utf-8") as f:
        f.write(protected)
    
    panel["script_link"] = "UPLOAD_THIS_FILE_TO_GET_LINK"
    save_json(PANEL_FILE, panel)
    
    embed = discord.Embed(title="✅ Script Added Successfully!", color=discord.Color.green())
    embed.add_field(name="Obfuscator Key", value=f"`{obf_key}`", inline=False)
    embed.add_field(name="Status", value="Ready ✅", inline=True)
    await interaction.followup.send(embed=embed, file=discord.File("protected_script.lua"))

@client.tree.command(name="panel", description="Your personal panel")
async def panel_cmd(interaction: discord.Interaction):
    users = load_json(USERS_FILE)
    uid = str(interaction.user.id)
    if uid not in users:
        return await interaction.response.send_message("❌ Redeem your key first using the button on the panel.", ephemeral=True)
    panel = load_json(PANEL_FILE)
    embed = discord.Embed(title="🎛️ M1rage Control Panel", color=discord.Color.blue())
    embed.add_field(name="Your Key", value=f"`{users[uid]['key']}`", inline=False)
    embed.add_field(name="Script Status", value="✅ Ready" if "script_link" in panel else "⚠️ No script yet", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

app = Flask(__name__)
@app.route("/")
def home():
    return "Bot Online"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask, daemon=True).start()

client.run(TOKEN)
