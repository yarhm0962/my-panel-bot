import discord
from discord import app_commands
import json
import random
import os
from datetime import datetime, timedelta
from flask import Flask, Response
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
        json.dump(data, f)

def generate_user_key():
    parts = []
    for _ in range(4):
        part = ''.join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(4))
        parts.append(part)
    return "-".join(parts)

def generate_script_id():
    return ''.join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") for _ in range(8))

def obfuscate_with_xfu5k470r(lua_code):
    # Key check – only requires SCRIPT_KEY to be set (not empty)
    key_check = '''
getgenv().SCRIPT_KEY = getgenv().SCRIPT_KEY or nil
if not getgenv().SCRIPT_KEY or getgenv().SCRIPT_KEY == "" then
    game:GetService("Players").LocalPlayer:Kick('Pls Put Your getgenv().SCRIPT_KEY = "<KEY HERE>" to execute this script or contact the owner')
    return
end
'''
    full_code = key_check + "\n" + lua_code
    
    # Obfuscator as a RAW string (r"""...""") to preserve backslashes
    obfuscator = r'''
function obfuscate(code, level, mxLevel)
    local function print(...) end
    local concat = function(...) return table.concat({...}, "") end
    math.randomseed(os and os.time() or tick())
    level = level or 1
    mxLevel = mxLevel or 3
    
    local a = ""
    code = code:gsub("(%-%-%[(=*)%[.-%]%2%])", "")
    code = code:gsub("(%-%-[^\r\n]*)", "")
    
    local function dumpString(x) return concat("\\"", x:gsub(".", function(d) return "\\" .. string.byte(d) end), "\\"") end end
    local function dumpString2(x) 
        local x2 = "\\""
        local x3 = ""
        for _,__ in x:gmatch("%[(=*)%[(.-)%]%1%]") do
            x3 = __:gsub(".", function(d) return "\\" .. string.byte(d) end)
        end
        return concat(x2, x3, x2)
    end end
    local function GenerateSomeFluff()
        local randomTable = { "N00BING N00B TABLE", "game.Workspace:ClearAllChildren()", "?????????", "game", "Workspace", "wait", "loadstring", "Lighting", "TeleportService", "error", "crash__", "_", "____", "\\\\FOOLED YA?!?!\\", "\\\\MWAHAHA H4X0RZ\\", "string", "table", "\\\\KR3D17 70 XFU5K470R\\", "string", "os", "tick", "\system\"" }
        local x = math.random(1, #randomTable)
        if x > (#randomTable / 2) then
            local randomName = randomTable[x]
            return concat("local ", string.rep("_", math.random(5, 10)), " = ", "____[#____ - 9](", dumpString("loadstring(\\"return " .. randomName .. "\\")()"), ")\\n")
        elseif x > 3 then
            return concat("local ", string.rep("_", math.random(5, 10)), " = ____[", math.random(1, 31), "]\\n")
        else
            return concat("local ", ("_"):rep(100), " = ", dumpString("XFU5K470R R00LZ"), "\\n")
        end
    end
    local function GenerateFluff() return GenerateSomeFluff() end

    a = a .. "local CONSTANT_POOL = { "
    local CONSTANT_POOL = { }
    local i = 0
    local last = ""
    local instr = false
    local foundOne = true
    while foundOne do
        foundOne = false
        for i2 = 1, code:len() do
            local c = code:sub(i2, i2)
            if c == "\\"" then
                if code:sub(i2 - 1, i2 - 1) == "\\\\" then
                    if instr then last = last .. "\\"" end
                else
                    instr = not instr
                    if not instr then
                        if not CONSTANT_POOL[last] then
                            CONSTANT_POOL[last] = i
                            a = a .. "[" .. i .. "]" .. " = " .. dumpString(last) .. ", "
                            code = code:gsub("\\"" .. last .. "\\""", "(CONSTANT_POOL[" .. CONSTANT_POOL[last] .. "])")
                            i = i + 1
                        else
                            code = code:gsub("\\"" .. last .. "\\""", "(CONSTANT_POOL[" .. CONSTANT_POOL[last] .. "])")
                        end
                        last = ""
                        foundOne = true
                        break
                    end
                end
            else
                if instr then last = last .. c end
            end
        end
    end
    local last = ""
    local instr = false
    local foundOne = true
    while foundOne do
        foundOne = false
        for i2 = 1, code:len() do
            local c = code:sub(i2, i2)
            if c == "\\'" then
                if code:sub(i2 - 1, i2 - 1) == "\\\\" then
                    if instr then last = last .. "\\'" end
                else
                    instr = not instr
                    if not instr then
                        if not CONSTANT_POOL[last] then
                            CONSTANT_POOL[last] = i
                            a = a .. "[" .. i .. "]" .. " = " .. dumpString(last) .. ", "
                            code = code:gsub("\\'" .. last .. "\\'", "(CONSTANT_POOL[" .. CONSTANT_POOL[last] .. "])")
                            i = i + 1
                        else
                            code = code:gsub("\\'" .. last .. "\\'", "(CONSTANT_POOL[" .. CONSTANT_POOL[last] .. "])")
                        end
                        last = ""
                        foundOne = true
                        break
                    end
                end
            else
                if instr then last = last .. c end
            end
        end
    end
    for var in code:gmatch("(%[(=*)%[.*%]%2%])") do
        if not CONSTANT_POOL[var] then
            a = a .. "[" .. i .. "]" .. " = " .. dumpString2(var) .. ", "
            CONSTANT_POOL[var] = i
            i = i + 1
        end
    end
    a = a .. concat("[", i, "] = \\"\\88\\70\\85\\53\\75\\52\\55\\48\\82\\32\\49\\53\\32\\52\\87\\51\\53\\48\\77\\51\\46\\32\\75\\82\\51\\68\\49\\57\\32\\55\\48\\32\\88\\70\\85\\53\\75\\52\\55\\48\\82\\33\\"")
    a = a .. " }\\n"

    if level == 1 then
        local chars = "QWERTYUIOPASDFGHJKLZXCVBNMqwertyuioplkjhgfdsazxcvbnm_"
        local chars2 = "QWERTYUIOPASDFGHJKLZXCVBNMqwertyuioplkjhgfdsazxcvbnm_1234567890"
        local taken = { }
        taken[""] = true
        local function GetReplacement()
            local s = ""
            while taken[s] do
                local n = math.random(1, #chars)
                s = s .. chars:sub(n, n)
                for i = 1, math.random(6,20) do
                    local n = math.random(1, #chars2)
                    s = s .. chars2:sub(n, n)
                end
            end
            taken[s] = true
            return s
        end
        local library = {}
        for fType in code:gmatch("local%s*function%s*([%w_]+)%(") do
            local replacement = GetReplacement()
            if #fType > 5 then
                library[fType] = replacement
                code = code:gsub("function " .. fType, "function " .. replacement)
            end
        end
        for fCall in code:gmatch("([%w_]+)%s*%(") do
            if library[fCall] then code = code:gsub(fCall .. "%(", library[fCall] .. "%(") end
        end
        local function isKeyword(s)
            local s2 = "and break do else elseif end false for function if in local nil not or repeat return then true until"
            for w in s2:gmatch("(%w+)") do if w == s then return true end end
            return false
        end
        for each in code:gmatch("local%s*([%w_]*)%s*=") do
            if #each > 3 and not isKeyword(each) then
                local varName = GetReplacement()
                code = code:gsub("local%s+" .. each .. "%s*=", "local " .. varName .. " = ")
            end
        end
    end
    code = code:gsub("(%s+)", " ")
    a = a .. code
    math.randomseed(os and os.time() or tick())
    local __X = math.random()
    local a2 = [[ math.randomseed(]] .. __X .. [[)
local ____
____ = { function(...) local t = { ...} return ____[8](t) end, print, game, math.frexp, math.random(1, 1100), string.dump, string.sub, table.concat, wait, tick, loadstring, "t", function(x) local x2 = loadstring(x) if x2 then return ____[tonumber("5048")](function() x2() end) else return nil end end, "InsertService", 1234567890, getfenv, "", "wai", 7.2, pcall, math.pi, ""}
]] .. GenerateFluff() .. [[local ___ = ____[5]
]] .. GenerateFluff() .. [[local _ = function(x) return string.char(x / ___) end
]] .. GenerateFluff() .. [[local __ = {]]
    math.randomseed(__X)
    local ___X = math.random(1, 1100)
    local a3 = { }
    for i = 1, a:len() do
        table.insert(a3, concat("_(", (string.byte(a:sub(i, i)) * ___X), "), "))
    end
    a2 = a2 .. table.concat(a3, "")
    a2 = a2 .. " } \\n"
    a2 = a2 .. GenerateFluff()
    a2 = a2 .. "return ____[11]((____[8](__)), ____[#____])()\\n"
    if level < mxLevel then
        return obfuscate(a2, level + 1, mxLevel)
    else
        a2 = a2:gsub("[\\n\\r\\t ]+", " ")
        return a2
    end
end
xfuscate = function(code) return obfuscate(code, 1, 2) end
return xfuscate
'''
    
    import lupa
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    obfuscator_func = lua.execute(obfuscator)
    obfuscated_result = obfuscator_func(full_code)
    return obfuscated_result

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
    
    await interaction.response.send_message("🔄 Script is being obfuscated with XFU5K470R...", ephemeral=True)
    
    try:
        content = await file.read()
        lua_code = content.decode("utf-8")
        
        # --- Obfuscate the script ---
        obfuscated_code = obfuscate_with_xfu5k470r(lua_code)
        
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
        embed.add_field(name="Obfuscator", value="XFU5K470R Advanced ✅", inline=False)
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Obfuscation failed: {str(e)}", ephemeral=True)

app = Flask(__name__)

@app.route("/<script_id>")
def get_script(script_id):
    scripts = load_json(SCRIPTS_FILE)
    if script_id in scripts:
        return Response(scripts[script_id], mimetype="text/plain")
    return "Script Not Found", 404

@app.route("/")
def home():
    return "M1rage Lua Service Online | XFU5K470R Obfuscator"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask, daemon=True).start()

client.run(TOKEN)
