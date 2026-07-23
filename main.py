import discord
from discord import app_commands
import json
import random
import os
import base64
from datetime import datetime, timedelta, timezone
from flask import Flask, Response, request
import threading
import sys
import traceback
import pymongo

TOKEN = os.getenv("TOKEN")
WEBSITE_DOMAIN = os.getenv("WEBSITE_DOMAIN", "my-panel-bot.onrender.com")
WEBSITE_DOMAIN = WEBSITE_DOMAIN.replace("http://", "").replace("https://", "")

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    print("ERROR: MONGODB_URI environment variable not set.")
    sys.exit(1)

mongo_client = pymongo.MongoClient(MONGODB_URI)
db = mongo_client.get_database("bot_data")
keys_col = db["keys"]
users_col = db["users"]
panel_col = db["panel"]
scripts_col = db["scripts"]

def load_json(filename):
    if filename == "keys":
        col = keys_col
    elif filename == "users":
        col = users_col
    elif filename == "panel":
        col = panel_col
    elif filename == "scripts":
        col = scripts_col
    else:
        return {}
    docs = list(col.find({}))
    result = {}
    for doc in docs:
        if filename == "panel":
            result[doc['_id']] = doc
        else:
            result[doc['key']] = doc['value']
    return result

def save_json(filename, data):
    if filename == "keys":
        col = keys_col
    elif filename == "users":
        col = users_col
    elif filename == "panel":
        col = panel_col
    elif filename == "scripts":
        col = scripts_col
    else:
        return
    col.delete_many({})
    if filename == "panel":
        for key, value in data.items():
            value['_id'] = key
            col.insert_one(value)
    else:
        for key, value in data.items():
            col.insert_one({"key": key, "value": value})

KEYS_FILE = "keys"
USERS_FILE = "users"
PANEL_FILE = "panel"
SCRIPTS_FILE = "scripts"

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

def generate_user_key():
    parts = []
    for _ in range(4):
        part = ''.join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(4))
        parts.append(part)
    return "-".join(parts)

def generate_script_id():
    return ''.join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(8))

# ============================================================
# OBFUSCATION – TABLE-BASED WITH HWID CHECK
# ============================================================
def obfuscate_script(lua_code, panel_id):
    encoded = base64.b64encode(lua_code.encode()).decode()
    
    chunks = []
    i = 0
    while i < len(encoded):
        size = random.randint(3, 8)
        chunks.append(encoded[i:i+size])
        i += size
    
    table_str = "{" + ",".join(f'"{chunk}"' for chunk in chunks) + "}"
    
    wrapper = f'''
return(function(...)
    local L = {table_str}
    local key = _G.SCRIPT_KEY or getgenv().SCRIPT_KEY
    if not key or key == "" then
        game:GetService("Players").LocalPlayer:Kick('Missing SCRIPT_KEY')
        return nil
    end

    local function b64decode(data)
        local b='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
        data=string.gsub(data,'[^'..b..'=]','')
        local r={{}}
        for i=1,#data,4 do
            local chunk=data:sub(i,i+3)
            local a,c,d,e=chunk:byte(1,4)
            local x=(a and a~=61)and(b:find(string.char(a),1,true)-1)or 0
            local y=(c and c~=61)and(b:find(string.char(c),1,true)-1)or 0
            local z=(d and d~=61)and(b:find(string.char(d),1,true)-1)or 0
            local w=(e and e~=61)and(b:find(string.char(e),1,true)-1)or 0
            local n1=(x*4)+math.floor(y/16)
            local n2=((y%16)*16)+math.floor(z/4)
            local n3=((z%4)*64)+w
            table.insert(r,string.char(n1))
            if c and c~=61 then table.insert(r,string.char(n2)) end
            if d and d~=61 then table.insert(r,string.char(n3)) end
        end
        return table.concat(r)
    end

    local b64 = table.concat(L)
    local decoded = b64decode(b64)

    -- HWID = Roblox UserId (unique per account)
    local hwid = game.Players.LocalPlayer.UserId

    local url = "https://{WEBSITE_DOMAIN}/validate?key=" .. key .. "&panel={panel_id}&hwid=" .. hwid
    local success, response = pcall(function()
        return game:GetService("HttpService"):JSONDecode(game:HttpGet(url))
    end)

    if not success then
        game:GetService("Players").LocalPlayer:Kick('Server error')
        return nil
    end

    if not response or not response.valid then
        local msg = response and response.reason or "Invalid key or HWID mismatch"
        game:GetService("Players").LocalPlayer:Kick('Access denied: ' .. msg)
        return nil
    end

    local fn = loadstring(decoded)
    if not fn then
        game:GetService("Players").LocalPlayer:Kick('Invalid code')
        return nil
    end
    fn()

    _G.SCRIPT_KEY = nil
    if getgenv then getgenv().SCRIPT_KEY = nil end
end)()
'''
    wrapper = wrapper.replace("{WEBSITE_DOMAIN}", WEBSITE_DOMAIN)
    wrapper = wrapper.replace("{panel_id}", panel_id)
    return wrapper

# ============================================================
# REST OF THE BOT – UNCHANGED EXCEPT NEW COMMANDS/BUTTONS
# ============================================================

def ensure_panel_guild(panel_data, guild_id):
    if panel_data and not panel_data.get("guild_id"):
        panel_data["guild_id"] = guild_id
        return True
    return False

def find_panel(panels, lookup_id):
    if lookup_id in panels:
        return lookup_id, panels[lookup_id]
    for pid, pdata in panels.items():
        if pdata.get("message_id") == lookup_id:
            return pid, pdata
    for pid, pdata in panels.items():
        if str(pid) == lookup_id:
            return pid, pdata
    return None, None

def get_user_keys_for_panel(user_data, panel_id, keys_db):
    if not user_data or not isinstance(user_data, dict):
        return []
    if "panels" in user_data:
        panel_entry = user_data["panels"].get(panel_id)
        if panel_entry and isinstance(panel_entry, dict):
            return panel_entry.get("keys", [])
        return []
    if "key" in user_data:
        return [user_data["key"]] if user_data["key"] in keys_db else []
    return []

def migrate_user_data(user_data, panel_id, key):
    if isinstance(user_data, str):
        old_key = user_data
        new_data = {"panels": {panel_id: {"keys": [old_key]}}}
        if key and key != old_key:
            new_data["panels"][panel_id]["keys"].append(key)
        return new_data
    elif isinstance(user_data, dict) and "key" in user_data:
        old_key = user_data["key"]
        new_data = {"panels": {panel_id: {"keys": [old_key]}}}
        if key and key != old_key:
            new_data["panels"][panel_id]["keys"].append(key)
        return new_data
    else:
        return {"panels": {panel_id: {"keys": [key]}} if key else {panel_id: {"keys": []}}}

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
            guild_id = str(interaction.guild.id)

            panels = load_json(PANEL_FILE)
            panel = None
            panel_id = None
            for pid, pdata in panels.items():
                if pdata.get("message_id") == str(interaction.message.id) or pdata.get("channel_id") == str(interaction.channel_id):
                    panel = pdata
                    panel_id = pid
                    break
            if not panel:
                return await interaction.response.send_message("❌ Panel not found.", ephemeral=True)

            if ensure_panel_guild(panel, guild_id):
                panels[panel_id] = panel
                save_json(PANEL_FILE, panels)

            key_data = keys.get(key)
            if not key_data or not key_data.get("active"):
                return await interaction.response.send_message("❌ Invalid or expired key.", ephemeral=True)

            if key_data.get("guild_id") != guild_id or key_data.get("panel_id") != panel_id:
                return await interaction.response.send_message("❌ This key is not valid for this panel.", ephemeral=True)

            expires = datetime.fromisoformat(key_data["expires"])
            if datetime.now(timezone.utc) > expires:
                return await interaction.response.send_message("❌ This key has expired.", ephemeral=True)

            user_data = users.get(uid)
            if user_data is None:
                user_data = {"panels": {}}
            elif not isinstance(user_data, dict):
                user_data = migrate_user_data(user_data, panel_id, key)
            elif "panels" not in user_data:
                user_data = migrate_user_data(user_data, panel_id, key)
            else:
                if panel_id not in user_data["panels"]:
                    user_data["panels"][panel_id] = {"keys": []}
                if key in user_data["panels"][panel_id]["keys"]:
                    return await interaction.response.send_message("✅ You already redeemed this key for this panel.", ephemeral=True)
                user_data["panels"][panel_id]["keys"].append(key)

            users[uid] = user_data
            save_json(USERS_FILE, users)

            embed = discord.Embed(title="✅ Key Redeemed Successfully!", color=discord.Color.green())
            embed.add_field(name="Your Key", value=f"`{key}`", inline=False)
            embed.add_field(name="Panel", value=panel.get("title", "Unknown"), inline=False)
            embed.add_field(name="Status", value="Active ✅", inline=True)
            embed.add_field(name="HWID", value="Not set (will be set on first execution)", inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"RedeemModal error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

class StatsView(discord.ui.View):
    def __init__(self, user, keys_data, panel_title):
        super().__init__(timeout=120)
        self.user = user
        self.keys_data = keys_data
        self.panel_title = panel_title

        options = []
        for k, data in self.keys_data:
            label = k[:12] + "..." if len(k) > 15 else k
            expiry = datetime.fromisoformat(data["expires"])
            is_active = data["active"] and datetime.now(timezone.utc) <= expiry
            status = "🟢 Active" if is_active else "🔴 Expired"
            hwid = data.get("hwid", "Not set")
            hwid_display = hwid if hwid != "Not set" else "Not set"
            options.append(discord.SelectOption(label=label, value=k, description=f"{status} - HWID: {hwid_display[:12]}..."))

        self.select = discord.ui.Select(placeholder="Choose a key to view stats", options=options, custom_id="stats_select")
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_key = interaction.data["values"][0]
        selected_data = None
        for k, data in self.keys_data:
            if k == selected_key:
                selected_data = data
                break
        if not selected_data:
            await interaction.response.send_message("Key not found.", ephemeral=True)
            return
        embed = self.build_stats_embed(selected_key, selected_data)
        await interaction.response.edit_message(embed=embed, view=self)

    def build_stats_embed(self, key, data):
        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(data["expires"])
        is_active = data["active"] and now <= expires

        if is_active:
            time_left = expires - now
            days = time_left.days
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            if days > 0:
                time_left_str = f"{days} day{'s' if days > 1 else ''} {hours} hour{'s' if hours != 1 else ''}"
            elif hours > 0:
                time_left_str = f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"
            else:
                time_left_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            time_left_str = "Expired"

        status_str = "🟢 Active" if is_active else "🔴 Expired"
        created = data.get("created_at", "Unknown")
        if created != "Unknown":
            try:
                created_dt = datetime.fromisoformat(created)
                created = created_dt.strftime("%Y-%m-%d %H:%M UTC")
            except:
                pass

        hwid = data.get("hwid", "Not set")
        embed = discord.Embed(
            title=f"🗝️ {self.user.display_name}'s Key",
            color=discord.Color.dark_purple()
        )
        embed.add_field(name="Panel", value=self.panel_title, inline=False)
        embed.add_field(name="Key", value=f"`{key}`", inline=False)
        embed.add_field(name="Status", value=status_str, inline=True)
        embed.add_field(name="Type", value="Multi‑use", inline=True)
        embed.add_field(name="HWID", value=f"`{hwid}`", inline=True)
        embed.add_field(name="Created", value=created, inline=True)
        embed.add_field(name="Expires", value=expires.strftime("%Y-%m-%d %H:%M UTC") if is_active else "Expired", inline=True)
        embed.add_field(name="Time Left", value=time_left_str, inline=True)
        embed.set_footer(text="M1rage Control Panel")
        return embed

class PanelView(discord.ui.View):
    def __init__(self, channel_id, message_id=None):
        super().__init__(timeout=None)
        self.channel_id = channel_id
        self.message_id = message_id

    @discord.ui.button(label="Redeem Key", emoji="🔑", style=discord.ButtonStyle.green, custom_id="redeem_btn")
    async def redeem_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(RedeemModal())
        except Exception as e:
            print(f"redeem_btn error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Get Script", emoji="📜", style=discord.ButtonStyle.blurple, custom_id="loadstring_btn")
    async def get_script_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            users = load_json(USERS_FILE)
            keys = load_json(KEYS_FILE)
            uid = str(interaction.user.id)
            guild_id = str(interaction.guild.id)

            panels = load_json(PANEL_FILE)
            panel = None
            panel_id = None
            if self.message_id:
                for pid, pdata in panels.items():
                    if pdata.get("message_id") == self.message_id:
                        panel = pdata
                        panel_id = pid
                        break
            if not panel:
                panel = panels.get(self.channel_id)
                panel_id = self.channel_id

            if not panel:
                return await interaction.response.send_message("⚠️ Panel not found.", ephemeral=True)

            if ensure_panel_guild(panel, guild_id):
                panels[panel_id] = panel
                save_json(PANEL_FILE, panels)

            user_data = users.get(uid)
            panel_keys = get_user_keys_for_panel(user_data, panel_id, keys)
            if not panel_keys:
                return await interaction.response.send_message("❌ You have no redeemed keys for this panel. Redeem one using the button above.", ephemeral=True)

            active_keys = [k for k in panel_keys if k in keys and keys[k]["active"] and keys[k].get("guild_id") == guild_id and keys[k].get("panel_id") == panel_id]
            if not active_keys:
                return await interaction.response.send_message("❌ All your keys for this panel are invalid or expired. Please redeem a new key.", ephemeral=True)

            user_key = active_keys[-1]

            if not panel or "script_id" not in panel or not panel["script_id"]:
                return await interaction.response.send_message("⚠️ No script has been added to this panel yet.", ephemeral=True)

            script_id = panel["script_id"]
            scripts = load_json(SCRIPTS_FILE)
            if script_id in scripts:
                script_url = f"https://{WEBSITE_DOMAIN}/raw/{script_id}"
            else:
                script_url = f"https://api.pastes.dev/{script_id}"  # fallback

            loadstring_code = f'_G.SCRIPT_KEY = "{user_key}"\n\nloadstring(game:HttpGet("{script_url}"))()'

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
            keys = load_json(KEYS_FILE)
            uid = str(interaction.user.id)
            guild_id = str(interaction.guild.id)

            panels = load_json(PANEL_FILE)
            panel = None
            panel_id = None
            if self.message_id:
                for pid, pdata in panels.items():
                    if pdata.get("message_id") == self.message_id:
                        panel = pdata
                        panel_id = pid
                        break
            if not panel:
                panel = panels.get(self.channel_id)
                panel_id = self.channel_id

            if not panel:
                return await interaction.response.send_message("⚠️ Panel not found.", ephemeral=True)

            if ensure_panel_guild(panel, guild_id):
                panels[panel_id] = panel
                save_json(PANEL_FILE, panels)

            user_data = users.get(uid)
            panel_keys = get_user_keys_for_panel(user_data, panel_id, keys)
            if not panel_keys:
                return await interaction.response.send_message("❌ You must redeem a key for this panel first.", ephemeral=True)

            active_keys = [k for k in panel_keys if k in keys and keys[k]["active"] and keys[k].get("guild_id") == guild_id and keys[k].get("panel_id") == panel_id]
            if not active_keys:
                return await interaction.response.send_message("❌ Your keys for this panel are invalid or expired. Please redeem a valid key.", ephemeral=True)

            if not panel or "role_id" not in panel:
                return await interaction.response.send_message("⚠️ No role has been configured for this panel. Contact an admin.", ephemeral=True)

            role = interaction.guild.get_role(int(panel["role_id"]))
            if not role:
                return await interaction.response.send_message("⚠️ The configured role no longer exists. Contact an admin.", ephemeral=True)

            bot_member = interaction.guild.me
            if not bot_member.guild_permissions.manage_roles:
                return await interaction.response.send_message("❌ I don't have permission to manage roles. Please give me the 'Manage Roles' permission.", ephemeral=True)

            if role >= bot_member.top_role:
                return await interaction.response.send_message("❌ I cannot assign this role because it is above or equal to my highest role. Please move my role higher.", ephemeral=True)

            if role in interaction.user.roles:
                return await interaction.response.send_message("✅ You already have this role.", ephemeral=True)

            await interaction.user.add_roles(role)
            embed = discord.Embed(title="✅ Role Assigned!", color=discord.Color.green())
            embed.add_field(name="Role", value=role.mention, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to assign roles. Please give me the 'Manage Roles' permission and ensure my role is higher than the target role.", ephemeral=True)
        except Exception as e:
            print(f"role_btn error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Reset HWID", emoji="⚙️", style=discord.ButtonStyle.grey, custom_id="reset_hwid_btn")
    async def reset_hwid_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            users = load_json(USERS_FILE)
            keys = load_json(KEYS_FILE)
            uid = str(interaction.user.id)
            guild_id = str(interaction.guild.id)

            panels = load_json(PANEL_FILE)
            panel = None
            panel_id = None
            if self.message_id:
                for pid, pdata in panels.items():
                    if pdata.get("message_id") == self.message_id:
                        panel = pdata
                        panel_id = pid
                        break
            if not panel:
                panel = panels.get(self.channel_id)
                panel_id = self.channel_id

            if not panel:
                return await interaction.response.send_message("⚠️ Panel not found.", ephemeral=True)

            if ensure_panel_guild(panel, guild_id):
                panels[panel_id] = panel
                save_json(PANEL_FILE, panels)

            user_data = users.get(uid)
            panel_keys = get_user_keys_for_panel(user_data, panel_id, keys)
            if not panel_keys:
                return await interaction.response.send_message("❌ You have no redeemed keys for this panel.", ephemeral=True)

            # Filter active keys
            active_keys = [k for k in panel_keys if k in keys and keys[k]["active"] and keys[k].get("guild_id") == guild_id and keys[k].get("panel_id") == panel_id]
            if not active_keys:
                return await interaction.response.send_message("❌ No active keys found to reset HWID.", ephemeral=True)

            # Reset HWID for all active keys
            reset_count = 0
            for k in active_keys:
                if "hwid" in keys[k]:
                    del keys[k]["hwid"]
                    reset_count += 1
            save_json(KEYS_FILE, keys)

            embed = discord.Embed(title="✅ HWID Reset Successful!", color=discord.Color.green())
            embed.add_field(name="Panel", value=panel.get("title", "Unknown"), inline=False)
            embed.add_field(name="Keys Reset", value=str(reset_count), inline=True)
            embed.add_field(name="Note", value="Next time you run the script, your new HWID will be stored.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"reset_hwid_btn error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Get Stats", emoji="📊", style=discord.ButtonStyle.grey, custom_id="stats_btn")
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            users = load_json(USERS_FILE)
            keys = load_json(KEYS_FILE)
            uid = str(interaction.user.id)
            guild_id = str(interaction.guild.id)

            panels = load_json(PANEL_FILE)
            panel = None
            panel_id = None
            if self.message_id:
                for pid, pdata in panels.items():
                    if pdata.get("message_id") == self.message_id:
                        panel = pdata
                        panel_id = pid
                        break
            if not panel:
                panel = panels.get(self.channel_id)
                panel_id = self.channel_id

            if not panel:
                return await interaction.response.send_message("⚠️ Panel not found.", ephemeral=True)

            if ensure_panel_guild(panel, guild_id):
                panels[panel_id] = panel
                save_json(PANEL_FILE, panels)

            user_data = users.get(uid)
            panel_keys = get_user_keys_for_panel(user_data, panel_id, keys)
            if not panel_keys:
                return await interaction.response.send_message("❌ You have no redeemed keys for this panel.", ephemeral=True)

            active_keys_data = []
            for k in panel_keys:
                if k in keys and keys[k]["active"] and keys[k].get("guild_id") == guild_id and keys[k].get("panel_id") == panel_id:
                    active_keys_data.append((k, keys[k]))

            if not active_keys_data:
                return await interaction.response.send_message("❌ All your keys for this panel are invalid or expired.", ephemeral=True)

            panel_title = panel.get("title", "Unknown Panel")
            if len(active_keys_data) == 1:
                key, data = active_keys_data[0]
                view = StatsView(interaction.user, active_keys_data, panel_title)
                embed = view.build_stats_embed(key, data)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                view = StatsView(interaction.user, active_keys_data, panel_title)
                key, data = active_keys_data[0]
                embed = view.build_stats_embed(key, data)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            print(f"stats_btn error: {e}")
            traceback.print_exc()
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.event
async def on_ready():
    print(f"Bot Online: {client.user}")
    panels = load_json(PANEL_FILE)
    for channel_id, panel_data in panels.items():
        message_id = panel_data.get("message_id")
        if message_id:
            view = PanelView(channel_id, message_id)
            client.add_view(view)

@client.tree.command(name="create_panel", description="Create control panel")
@app_commands.describe(script_title="Embed title", role="Role to assign when user clicks 'Get Role'", description="Embed description (optional)")
@app_commands.rename(script_title="script-title")
async def create_panel(interaction: discord.Interaction, script_title: str, role: discord.Role, description: str = None):
    try:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("No permission.", ephemeral=True)

        if not description:
            description = "This control panel is for the project: **{}**\n\nClick the buttons below to redeem your key, get the script, or get your role.".format(script_title)

        embed = discord.Embed(title=script_title, description=description, color=discord.Color.dark_purple())
        embed.set_footer(text=f"{interaction.user.display_name} Control Panel")

        channel_id = str(interaction.channel_id)
        guild_id = str(interaction.guild.id)

        await interaction.response.send_message(embed=embed, view=PanelView(channel_id, None))
        message = await interaction.original_response()
        message_id = str(message.id)

        panels = load_json(PANEL_FILE)
        panels[channel_id] = {
            "title": script_title,
            "description": description,
            "channel_id": channel_id,
            "message_id": message_id,
            "role_id": str(role.id),
            "guild_id": guild_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "creator": interaction.user.display_name,
            "script_id": None
        }
        save_json(PANEL_FILE, panels)

        view = PanelView(channel_id, message_id)
        await message.edit(view=view)

    except Exception as e:
        print(f"create_panel error: {e}")
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.tree.command(name="genkey", description="Generate a new key for a specific panel")
@app_commands.describe(panel="Channel ID or Message ID of the panel", days="Days active")
async def genkey(interaction: discord.Interaction, panel: str, days: int):
    try:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("No permission.", ephemeral=True)

        panels = load_json(PANEL_FILE)
        panel_id, panel_data = find_panel(panels, panel)

        if not panel_data:
            return await interaction.response.send_message(f"❌ Panel not found. Use the channel ID or message ID of the panel.\nHint: Right-click the panel message and copy the ID, or copy the channel ID.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        if ensure_panel_guild(panel_data, guild_id):
            panels[panel_id] = panel_data
            save_json(PANEL_FILE, panels)

        if panel_data.get("guild_id") != guild_id:
            return await interaction.response.send_message("❌ This panel is not in this server.", ephemeral=True)

        user_key = generate_user_key()
        keys = load_json(KEYS_FILE)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=days)
        keys[user_key] = {
            "active": True,
            "expires": expires.isoformat(),
            "owner": str(interaction.user.id),
            "owner_name": interaction.user.name,
            "created_at": now.isoformat(),
            "guild_id": guild_id,
            "panel_id": panel_id,
            # hwid is not set initially
        }
        save_json(KEYS_FILE, keys)
        await interaction.response.send_message(f"✅ Key Generated for panel **{panel_data.get('title', 'Unknown')}** :\n`{user_key}`\nValid: {days} days", ephemeral=True)
    except Exception as e:
        print(f"genkey error: {e}")
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.tree.command(name="view_all_keys", description="View all keys (Admin only) for this server")
async def view_all_keys(interaction: discord.Interaction):
    try:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("No permission.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        keys = load_json(KEYS_FILE)
        panels = load_json(PANEL_FILE)

        active_panel_ids = {pid for pid, pdata in panels.items() if pdata.get("guild_id") == guild_id}

        guild_keys = {}
        for k, v in keys.items():
            if v.get("guild_id") == guild_id and v.get("panel_id") in active_panel_ids:
                guild_keys[k] = v

        if not guild_keys:
            embed = discord.Embed(title="📋 All Keys", description="No keys found for active panels in this server.", color=discord.Color.dark_purple())
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embeds = []
        current_embed = discord.Embed(title="📋 All Keys (Server - Active Panels Only)", color=discord.Color.dark_purple())
        current_embed.set_footer(text=f"Total: {len(guild_keys)} keys")
        field_count = 0

        for k, v in guild_keys.items():
            status = "🟢 Active" if v["active"] else "🔴 Inactive"
            expires = datetime.fromisoformat(v["expires"])
            if datetime.now(timezone.utc) > expires:
                status = "🔴 Expired"
            owner = v.get("owner_name", v.get("owner", "Unknown"))
            panel_id = v.get("panel_id", "Unknown")
            panel_title = panels.get(panel_id, {}).get("title", "Unknown Panel")
            hwid = v.get("hwid", "Not set")
            line = f"`{k}` — {status} — expires: {v['expires']} — owner: {owner} — panel: {panel_title} — HWID: {hwid[:12] if hwid != 'Not set' else 'Not set'}..."

            if len(current_embed.fields) >= 25:
                embeds.append(current_embed)
                current_embed = discord.Embed(title="📋 All Keys (continued)", color=discord.Color.dark_purple())
                current_embed.set_footer(text=f"Total: {len(guild_keys)} keys")
                field_count = 0

            current_embed.add_field(name=f"Key #{field_count+1}", value=line, inline=False)
            field_count += 1

        if current_embed.fields:
            embeds.append(current_embed)

        await interaction.response.send_message(embed=embeds[0], ephemeral=True)
        for embed in embeds[1:]:
            await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        print(f"view_all_keys error: {e}")
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.tree.command(name="delete_keys", description="Delete one or more keys (Admin only)")
@app_commands.describe(key="Specific key to delete", user="Delete all keys for this user")
async def delete_keys(interaction: discord.Interaction, key: str = None, user: discord.User = None):
    try:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("No permission.", ephemeral=True)

        if not key and not user:
            return await interaction.response.send_message("You must specify either a key or a user.", ephemeral=True)

        guild_id = str(interaction.guild.id)
        keys = load_json(KEYS_FILE)
        if not keys:
            return await interaction.response.send_message("No keys exist.", ephemeral=True)

        deleted_count = 0
        if key:
            if key in keys and keys[key].get("guild_id") == guild_id:
                del keys[key]
                deleted_count = 1
            else:
                return await interaction.response.send_message(f"Key `{key}` not found in this server.", ephemeral=True)
        elif user:
            uid = str(user.id)
            to_delete = [k for k, v in keys.items() if v.get("owner") == uid and v.get("guild_id") == guild_id]
            if not to_delete:
                return await interaction.response.send_message(f"No keys found for user {user.mention} in this server.", ephemeral=True)
            for k in to_delete:
                del keys[k]
            deleted_count = len(to_delete)

        save_json(KEYS_FILE, keys)
        await interaction.response.send_message(f"✅ Deleted {deleted_count} key(s).", ephemeral=True)
    except Exception as e:
        print(f"delete_keys error: {e}")
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.tree.command(name="reset_hwid", description="Reset HWID for a specific key (Admin only)")
@app_commands.describe(key="The key to reset HWID for")
async def reset_hwid(interaction: discord.Interaction, key: str):
    try:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("No permission.", ephemeral=True)

        keys = load_json(KEYS_FILE)
        if key not in keys:
            return await interaction.response.send_message(f"❌ Key `{key}` not found.", ephemeral=True)

        if "hwid" in keys[key]:
            del keys[key]["hwid"]
            save_json(KEYS_FILE, keys)
            embed = discord.Embed(title="✅ HWID Reset Successful!", color=discord.Color.green())
            embed.add_field(name="Key", value=f"`{key}`", inline=False)
            embed.add_field(name="Status", value="HWID cleared. Next execution will store new HWID.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"ℹ️ Key `{key}` does not have a HWID stored.", ephemeral=True)
    except Exception as e:
        print(f"reset_hwid command error: {e}")
        traceback.print_exc()
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)

@client.tree.command(name="add_script", description="Add a Lua script file to a specific panel (Admin only)")
@app_commands.describe(message_id="Message ID of the panel embed (REQUIRED – right-click the panel message and Copy ID)", file="Upload .lua or .txt file")
@app_commands.rename(message_id="message-id")
async def add_script(interaction: discord.Interaction, message_id: str, file: discord.Attachment):
    try:
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("No permission.", ephemeral=True)

        panels = load_json(PANEL_FILE)
        panel_key, panel = find_panel(panels, message_id)

        if not panel:
            return await interaction.response.send_message(
                f"❌ No panel found with message ID `{message_id}`. Please right-click the panel message and copy the ID.",
                ephemeral=True
            )

        guild_id = str(interaction.guild.id)
        if ensure_panel_guild(panel, guild_id):
            panels[panel_key] = panel
            save_json(PANEL_FILE, panels)

        if panel.get("guild_id") != guild_id:
            return await interaction.response.send_message("❌ This panel is not in this server.", ephemeral=True)

        if not (file.filename.endswith(".lua") or file.filename.endswith(".txt")):
            return await interaction.response.send_message("❌ Only .lua or .txt files accepted.", ephemeral=True)

        await interaction.response.send_message("🔄 Obfuscating and securing script...", ephemeral=True)

        content = await file.read()
        lua_code = content.decode("utf-8")

        # Use the new obfuscation (with HWID)
        obfuscated_code = obfuscate_script(lua_code, panel_key)

        script_id = panel.get("script_id")
        if not script_id:
            script_id = generate_script_id()
            panel["script_id"] = script_id

        scripts = load_json(SCRIPTS_FILE)
        scripts[script_id] = obfuscated_code
        save_json(SCRIPTS_FILE, scripts)

        panels[panel_key] = panel
        save_json(PANEL_FILE, panels)

        direct_link = f"https://{WEBSITE_DOMAIN}/raw/{script_id}"

        embed = discord.Embed(title="✅ Script Added Successfully!", color=discord.Color.green())
        embed.add_field(name="Panel", value=f"Message ID: {message_id}", inline=False)
        embed.add_field(name="Script ID", value=f"`{script_id}`", inline=False)
        embed.add_field(name="Direct Link", value=f"{direct_link}", inline=False)
        embed.add_field(name="Protection", value="Key + HWID validation", inline=False)
        await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"add_script error: {e}")
        traceback.print_exc()
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

app = Flask(__name__)

@app.route("/raw/<script_id>")
def get_raw_script(script_id):
    scripts = load_json(SCRIPTS_FILE)
    if script_id in scripts:
        return Response(scripts[script_id], mimetype="text/plain")
    return "Script Not Found", 404

@app.route("/checkkey")
def check_key():
    try:
        key = request.args.get("key")
        panel_id = request.args.get("panel")
        if not key or not panel_id:
            return {"valid": False, "reason": "Missing key or panel ID"}

        keys = load_json(KEYS_FILE)
        if key not in keys or not keys[key]["active"]:
            return {"valid": False, "reason": "Invalid key"}

        if keys[key].get("panel_id") != panel_id:
            return {"valid": False, "reason": "Key not valid for this panel"}

        expires = datetime.fromisoformat(keys[key]["expires"])
        if datetime.now(timezone.utc) > expires:
            return {"valid": False, "reason": "Key expired"}

        return {"valid": True, "expires": keys[key]["expires"]}
    except Exception as e:
        print(f"check_key error: {e}")
        return {"valid": False, "reason": "Server error"}

@app.route("/validate")
def validate_hwid():
    try:
        key = request.args.get("key")
        panel_id = request.args.get("panel")
        hwid = request.args.get("hwid")
        if not key or not panel_id or not hwid:
            return {"valid": False, "reason": "Missing parameters"}

        keys = load_json(KEYS_FILE)
        if key not in keys or not keys[key]["active"]:
            return {"valid": False, "reason": "Invalid key"}

        if keys[key].get("panel_id") != panel_id:
            return {"valid": False, "reason": "Key not valid for this panel"}

        expires = datetime.fromisoformat(keys[key]["expires"])
        if datetime.now(timezone.utc) > expires:
            return {"valid": False, "reason": "Key expired"}

        # HWID check
        stored_hwid = keys[key].get("hwid")
        if stored_hwid is None:
            # First time – store HWID
            keys[key]["hwid"] = hwid
            save_json(KEYS_FILE, keys)
            return {"valid": True, "reason": "HWID stored successfully"}
        elif stored_hwid == hwid:
            return {"valid": True, "reason": "HWID matches"}
        else:
            return {"valid": False, "reason": "HWID mismatch – this key is locked to another device"}
    except Exception as e:
        print(f"validate_hwid error: {e}")
        return {"valid": False, "reason": "Server error"}

@app.route("/")
def home():
    return "M1rage Lua Service Online | Protected by key + HWID validation"

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
