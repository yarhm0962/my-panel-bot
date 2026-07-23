import discord
from discord import app_commands
import json
import random
import os
import base64
from datetime import datetime, timedelta
from flask import Flask, Response, request
import threading
import sys
import traceback

TOKEN = os.getenv("TOKEN")
WEBSITE_DOMAIN = os.getenv("WEBSITE_DOMAIN", "my-panel-bot.onrender.com")
WEBSITE_DOMAIN = WEBSITE_DOMAIN.replace("http://", "").replace("https://", "")

if not TOKEN:
    print("ERROR: TOKEN environment variable not set.")
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        try:
            await self.tree.sync()
            print("Commands Synced")
        except Exception as e:
            print(f"Error syncing commands: {e}")
            traceback.print_exc()

client = MyBot()

KEYS_FILE = "keys.json"
USERS_FILE = "users.json"
PANEL_FILE = "panel.json"
SCRIPTS_FILE = "scripts.json"

def load_json(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return {}

def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving {filename}: {e}")

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
local _ENV = _G
local getgenv = getgenv or function() return _ENV end
local env = getgenv()
env.SCRIPT_KEY = env.SCRIPT_KEY or nil
if not env.SCRIPT_KEY or env.SCRIPT_KEY == "" then
    game:GetService("Players").LocalPlayer:Kick('Pls Put Your getgenv().SCRIPT_KEY = "<KEY HERE>" to execute this script or contact the owner')
    return
end
local key = env.SCRIPT_KEY

local function b64decode(data)
    local b = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    data = string.gsub(data, '[^'..b..'=]', '')
    local result = {{}}
    for i = 1, #data, 4 do
        local chunk = data:sub(i, i+3)
        local a, c, d, e = chunk:byte(1, 4)
        local x = (b:find(string.char(a)) or 2) - 1
        local y = (b:find(string.char(c)) or 2) - 1
        local z = (b:find(string.char(d)) or 2) - 1
        local w = (b:find(string.char(e)) or 2) - 1
        local n1 = (x * 4) + math.floor(y / 16)
        local n2 = ((y % 16) * 16) + math.floor(z / 4)
        local n3 = ((z % 4) * 64) + w
        table.insert(result, string.char(n1))
        if c and c ~= 61 then table.insert(result, string.char(n2)) end
        if d and d ~= 61 then table.insert(result, string.char(n3)) end
    end
    return table.concat(result)
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
local fn = loadstring(decoded)
if not fn then
    game:GetService("Players").LocalPlayer:Kick('Failed to load script: invalid code')
    return
end
fn()
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
        try:
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
        except Exception as e:
            print(f"RedeemModal error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Redeem Key", emoji="🔑", style=discord.ButtonStyle.green, custom_id="redeem_btn")
    async def redeem_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            users = load_json(USERS_FILE)
            uid = str(interaction.user.id)
            if uid in users:
                return await interaction.response.send_message("✅ Your key is already redeemed!", ephemeral=True)
            await interaction.response.send_modal(RedeemModal())
        except Exception as e:
            print(f"redeem_btn error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Get Script", emoji="📜", style=discord.ButtonStyle.blurple, custom_id="loadstring_btn")
    async def get_script_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
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

            embed = discord.Embed(title="📜 Your Script", color=discord.Color.green())
            embed.add_field(name="Copy this FULL code:", value=f"```lua\n{loadstring_code}\n```", inline=False)
            embed.set_footer(text="SCRIPT_KEY is REQUIRED — script will NOT work without it!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"get_script_btn error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Get Role", emoji="👤", style=discord.ButtonStyle.blurple, custom_id="role_btn")
    async def role_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
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
        except Exception as e:
            print(f"role_btn error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Reset HWID", emoji="⚙️", style=discord.ButtonStyle.grey, custom_id="reset_hwid_btn")
    async def reset_hwid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            users = load_json(USERS_FILE)
            uid = str(interaction.user.id)
            if uid not in users:
                return await interaction.response.send_message("❌ Redeem your key first using the button above.", ephemeral=True)
            # Placeholder: In a real HWID system, you'd clear the HWID for this user.
            # For now, we just acknowledge.
            await interaction.response.send_message("⚙️ HWID reset feature is coming soon. For now, contact support.", ephemeral=True)
        except Exception as e:
            print(f"reset_hwid_btn error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Get Stats", emoji="📊", style=discord.ButtonStyle.grey, custom_id="stats_btn")
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            users = load_json(USERS_FILE)
            uid = str(interaction.user.id)
            if uid not in users:
                return await interaction.response.send_message("❌ Redeem your key first using the button above.", ephemeral=True)
            user_data = users[uid]
            key = user_data["key"]
            redeemed = user_data.get("redeemed", "Unknown")
            keys = load_json(KEYS_FILE)
            key_info = keys.get(key, {})
            expires = key_info.get("expires", "Unknown")
            embed = discord.Embed(title="📊 Your Stats", color=discord.Color.dark_purple())
            embed.add_field(name="Key", value=f"`{key}`", inline=False)
            embed.add_field(name="Redeemed On", value=redeemed, inline=True)
            embed.add_field(name="Expires", value=expires, inline=True)
            embed.set_footer(text="M1rage Control Panel")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"stats_btn error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.event
async def on_ready():
    print(f"Bot Online: {client.user}")
    client.add_view(PanelView())

@client.tree.command(name="create-panel", description="Create control panel")
@app_commands.describe(script_title="Embed title", description="Embed description (optional)")
async def create_panel(interaction: discord.Interaction, script_title: str, description: str = None):
    try:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("No permission.", ephemeral=True)

        # Default description without extra spaces
        if not description:
            description = "This control panel is for the project: **{}**\n\nClick the buttons below to redeem your key, get the script, or get your role.".format(script_title)

        embed = discord.Embed(title=script_title, description=description, color=discord.Color.dark_purple())
        embed.set_footer(text="M1rage Control Panel")

        panel = load_json(PANEL_FILE)
        panel["title"] = script_title
        panel["description"] = description
        panel["channel_id"] = str(interaction.channel_id)
        panel["created_at"] = datetime.utcnow().isoformat()
        save_json(PANEL_FILE, panel)

        await interaction.response.send_message(embed=embed, view=PanelView())
    except Exception as e:
        print(f"create_panel error: {e}")
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.tree.command(name="genkey", description="Generate new key")
@app_commands.describe(days="Days active")
async def genkey(interaction: discord.Interaction, days: int):
    try:
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
    except Exception as e:
        print(f"genkey error: {e}")
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.tree.command(name="view-all-keys", description="View all keys (Admin only)")
async def view_all_keys(interaction: discord.Interaction):
    try:
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
    except Exception as e:
        print(f"view_all_keys error: {e}")
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.tree.command(name="delete-keys", description="Delete one or more keys (Admin only)")
@app_commands.describe(key="Specific key to delete", user="Delete all keys for this user")
async def delete_keys(interaction: discord.Interaction, key: str = None, user: discord.User = None):
    try:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("No permission.", ephemeral=True)

        if not key and not user:
            return await interaction.response.send_message("You must specify either a key or a user.", ephemeral=True)

        keys = load_json(KEYS_FILE)
        if not keys:
            return await interaction.response.send_message("No keys exist.", ephemeral=True)

        deleted_count = 0
        if key:
            if key in keys:
                del keys[key]
                deleted_count = 1
            else:
                return await interaction.response.send_message(f"Key `{key}` not found.", ephemeral=True)
        elif user:
            uid = str(user.id)
            to_delete = [k for k, v in keys.items() if v.get("owner") == uid]
            if not to_delete:
                return await interaction.response.send_message(f"No keys found for user {user.mention}.", ephemeral=True)
            for k in to_delete:
                del keys[k]
            deleted_count = len(to_delete)

        save_json(KEYS_FILE, keys)
        await interaction.response.send_message(f"✅ Deleted {deleted_count} key(s).", ephemeral=True)
    except Exception as e:
        print(f"delete_keys error: {e}")
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.tree.command(name="add-script", description="Add Lua script file (Admin only)")
@app_commands.describe(file="Upload .lua or .txt file")
async def add_script(interaction: discord.Interaction, file: discord.Attachment):
    try:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("No permission.", ephemeral=True)

        panel = load_json(PANEL_FILE)
        if not panel or "channel_id" not in panel:
            return await interaction.response.send_message("⚠️ No panel found. Create one first with `/create-panel`.", ephemeral=True)

        if not (file.filename.endswith(".lua") or file.filename.endswith(".txt")):
            return await interaction.response.send_message("❌ Only .lua or .txt files accepted.", ephemeral=True)

        await interaction.response.send_message("🔄 Obfuscating and securing script...", ephemeral=True)

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
        print(f"add_script error: {e}")
        traceback.print_exc()
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

app = Flask(__name__)

@app.route("/<script_id>")
def get_script(script_id):
    try:
        scripts = load_json(SCRIPTS_FILE)
        if script_id in scripts:
            return Response(scripts[script_id], mimetype="text/plain")
        return "Script Not Found", 404
    except Exception as e:
        print(f"get_script error: {e}")
        return "Internal Server Error", 500

@app.route("/checkkey")
def check_key():
    try:
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
    except Exception as e:
        print(f"check_key error: {e}")
        return {"valid": False, "reason": "Server error"}

@app.route("/")
def home():
    return "M1rage Lua Service Online | Protected by server‑side key validation"

def run_flask():
    try:
        port = int(os.getenv("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        print(f"Flask error: {e}")
        traceback.print_exc()

threading.Thread(target=run_flask, daemon=True).start()

if __name__ == "__main__":
    try:
        client.run(TOKEN)
    except Exception as e:
        print(f"FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
