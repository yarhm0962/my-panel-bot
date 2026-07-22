import discord
from discord import app_commands
import json
import random
import os
import base64
from datetime import datetime, timedelta
from flask import Flask, Response, request
import threading

TOKEN = os.getenv("TOKEN")
WEBSITE_DOMAIN = "my-panel-bot.onrender.com"

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
SCRIPTS_FILE = "scripts.json"

def load_json(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def generate_user_key():
    parts = []
    for _ in range(4):
        part = ''.join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(4))
        parts.append(part)
    return "-".join(parts)

def generate_script_id():
    return ''.join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(8))

def obfuscate_script(lua_code):
    encoded = base64.b64encode(lua_code.encode()).decode()

    wrapper = f'''
getgenv().SCRIPT_KEY = getgenv().SCRIPT_KEY or nil
if not getgenv().SCRIPT_KEY or getgenv().SCRIPT_KEY == "" then
    game:GetService("Players").LocalPlayer:Kick('Pls Put Your getgenv().SCRIPT_KEY = "<KEY HERE>" to execute this script or contact the owner')
    return
end

local key = getgenv().SCRIPT_KEY

local function b64decode(data)
    local b='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    data = string.gsub(data, '[^'..b..'=]', '')
    return (string.gsub(data, '.(.)?.?(.)?', function(x,y,z)
        if not y then return '' end
        local a,b,c = b:find(x)-1, b:find(y)-1, z and b:find(z)-1 or 0
        return string.char((a*4 + math.floor(b/16)) % 256, (b%16*16 + math.floor(c/4)) % 256, (c%4*64 + d) % 256)
    end))
end

local url = "https://{WEBSITE_DOMAIN}/checkkey?key=" .. key
local success, response = pcall(function()
    return game:GetService("HttpService"):JSONDecode(game:HttpGet(url))
end)

if not success or not response.valid then
    local msg = response and response.reason or "Key validation failed"
    game:GetService("Players").LocalPlayer:Kick('Invalid or expired key: ' .. msg)
    return
end

local decoded = b64decode("{encoded}")
loadstring(decoded)()
'''
    return wrapper

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

        expires = datetime.fromisoformat(keys[key]["expires"])
        if datetime.utcnow() > expires:
            return await interaction.response.send_message("❌ This key has expired.", ephemeral=True)

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
        if "script_id" not in panel or not panel["script_id"]:
            return await interaction.response.send_message("⚠️ No script has been added yet.", ephemeral=True)

        user_key = users[uid]["key"]
        script_url = f"https://{WEBSITE_DOMAIN}/{panel['script_id']}"

        loadstring_code = f'getgenv().SCRIPT_KEY = "{user_key}"\n\nloadstring(game:HttpGet("{script_url}"))()'

        embed = discord.Embed(title="📜 Your Loadstring", color=discord.Color.green())
        embed.add_field(name="Copy this FULL code:", value=f"```lua\n{loadstring_code}\n```", inline=False)
        embed.set_footer(text="SCRIPT_KEY is REQUIRED — script will NOT work without it!")
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
    keys[user_key] = {
        "active": True,
        "expires": expires,
        "owner": str(interaction.user.id),
        "owner_name": interaction.user.name
    }
    save_json(KEYS_FILE, keys)
    await interaction.response.send_message(f"✅ Key Generated:\n`{user_key}`\nValid: {days} days", ephemeral=True)

@client.tree.command(name="view-all-keys", description="View all keys (Admin only)")
async def view_all_keys(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("No permission.", ephemeral=True)

    keys = load_json(KEYS_FILE)
    if not keys:
        return await interaction.response.send_message("No keys found.", ephemeral=True)

    lines = []
    for k, v in keys.items():
        status = "🟢 Active" if v["active"] else "🔴 Inactive"
        expires = datetime.fromisoformat(v["expires"])
        if datetime.utcnow() > expires:
            status = "🔴 Expired"
        owner = v.get("owner_name", v.get("owner", "Unknown"))
        lines.append(f"**{k}** — {status} — expires: {v['expires']} — owner: {owner}")

    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > 1900:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current:
        chunks.append(current)

    if not chunks:
        return await interaction.response.send_message("No keys to display.", ephemeral=True)

    await interaction.response.send_message(f"**All Keys:**\n{chunks[0]}", ephemeral=True)
    for chunk in chunks[1:]:
        await interaction.followup.send(chunk, ephemeral=True)

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

    await interaction.response.send_message("🔄 Obfuscating and securing script...", ephemeral=True)

    try:
        content = await file.read()
        lua_code = content.decode("utf-8")

        obfuscated_code = obfuscate_script(lua_code)

        script_id = generate_script_id()

        scripts = load_json(SCRIPTS_FILE)
        scripts[script_id] = obfuscated_code
        save_json(SCRIPTS_FILE, scripts)

        panel["script_id"] = script_id
        save_json(PANEL_FILE, panel)

        direct_link = f"https://{WEBSITE_DOMAIN}/{script_id}"

        embed = discord.Embed(title="✅ Script Added Successfully!", color=discord.Color.green())
        embed.add_field(name="Script ID", value=f"`{script_id}`", inline=False)
        embed.add_field(name="Direct Link", value=f"{direct_link}", inline=False)
        embed.add_field(name="Protection", value="Server‑validated key + Base64 encoding", inline=False)
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

app = Flask(__name__)

@app.route("/<script_id>")
def get_script(script_id):
    scripts = load_json(SCRIPTS_FILE)
    if script_id in scripts:
        return Response(scripts[script_id], mimetype="text/plain")
    return "Script Not Found", 404

@app.route("/checkkey")
def check_key():
    key = request.args.get("key")
    if not key:
        return {"valid": False, "reason": "No key provided"}

    keys = load_json(KEYS_FILE)
    if key not in keys or not keys[key]["active"]:
        return {"valid": False, "reason": "Invalid key"}

    expires = datetime.fromisoformat(keys[key]["expires"])
    if datetime.utcnow() > expires:
        return {"valid": False, "reason": "Key expired"}

    return {"valid": True, "expires": keys[key]["expires"]}

@app.route("/")
def home():
    return "M1rage Lua Service Online | Protected by server‑side key validation"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask, daemon=True).start()

client.run(TOKEN)
