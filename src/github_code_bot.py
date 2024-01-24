import re
import os
import urllib.parse

import discord
from discord.ext import commands
import aiohttp
import asyncio

from extensions import COMMON_EXTS

#print(f"Discord: {discord.__version__} aiohttp: {aiohttp.__version__}")

# Handle bot token input
BT_FILEPATH = os.path.join(os.getcwd(), "bot_token.txt")
if os.path.exists(BT_FILEPATH):
    with open(BT_FILEPATH, 'r') as btf:
        TOKEN = btf.readline()
else:
    TOKEN = input("Enter bot token here (this happens only once): ")
    with open(BT_FILEPATH, 'w') as btf:
        btf.write(TOKEN)

# Handle command character input
CC_FILEPATH = os.path.join(os.getcwd(), "cmd_char.txt")
if os.path.exists(CC_FILEPATH):
    with open(CC_FILEPATH, 'r') as ccf:
        CMD_CHAR = ccf.readline()
else:
    CMD_CHAR = input("Enter your command character here (this happens only once): ")
    while len(CMD_CHAR) != 1:
        print("The command character is ONE character only. Please retry.")
        CMD_CHAR = input("Enter your command character here (this happens only once): ")
    with open(CC_FILEPATH, 'w') as ccf:
        ccf.write(CMD_CHAR)

# For pyinstaller exe compilation
def resource_path(relative_path):
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
 
def get_ext(urlStr):
    return urlStr[urlStr.rfind('.') + 1:].lower()

PAYLOAD_MAXLEN = 2000 # Discord character limit
HEX_YELLOW = 0xFFDF00
HEX_LBLUE  = 0xADD8E6

# Bot code start here.
ghc_bot = commands.Bot(command_prefix=CMD_CHAR, description="A Discord bot to preview code in Github links.")
ghc_bot.remove_command("help") # We write our own.

aiohttp_session = None
long_code = True
paused = False

async def init_aiohttp_session():
    global aiohttp_session
    print("aiohttp session init.")
    aiohttp_session = aiohttp.ClientSession()

@ghc_bot.event
async def on_ready():
    print(f"{ghc_bot.user} is now online.")
    ghc_bot.user.name = "GithubCodeBot"
    print(f"Username set to {ghc_bot.user.name}.")

    avatarPath = resource_path(os.path.join(r"..\assets", "octo.png"))

    with open(avatarPath, "rb") as pfp:
        try:
            await ghc_bot.user.edit(avatar=pfp.read())
            print(f"Avatar set to {avatarPath}.")
        except discord.errors.HTTPException:
            # In the case that the bot is started many times, Discord may complain that we're setting pfp too much. 
            pass 
    
    await init_aiohttp_session()
    print("Ready.")    

@ghc_bot.event
async def on_message(msg):
    if msg.author == ghc_bot.user:
        return 
    elif not paused:
        # The process looks like this:
        #
        # (1) https://github.com/SeanJxie/3d-engine-from-scratch/blob/main/CppEngine3D/engine.cpp
        #                                            |
        #                                            V
        # (2) ['https:', '', 'github.com', 'SeanJxie', '3d-engine-from-scratch', 'blob', 'main', 'CppEngine3D', 'engine.cpp']
        #                                            |
        #                                            V
        # (3) ['https:/', 'raw.githubusercontent.com', 'SeanJxie', '3d-engine-from-scratch', 'main', 'CppEngine3D', 'engine.cpp']
        #                                            |
        #                                            V
        # (4) https://raw.githubusercontent.com/SeanJxie/3d-engine-from-scratch/main/CppEngine3D/engine.cpp   +1`

        print(f"\nMessage: {msg.content}")
        matches = re.findall("http(s?)://(www\.)?github.com/([^\s]+)", msg.content)

        # We want no reps and valid extensions.
        matches = list(dict.fromkeys(filter(lambda x: get_ext(x[-1]) in COMMON_EXTS.keys(), matches)))

        if len(matches) > 1:
            await msg.channel.send(f"> :eyes: I've detected {len(matches)} valid links here. They will be served in order!")

        if len(matches) != 0:
            for match in matches:

                # (1)
                url = "https://github.com/" + match[-1]
                print(f"\nDetected url: {url}")

                # (2)
                urlSplit = url.split('/')
                    
                # (3)
                urlSplit.remove('')
                if "blob" in urlSplit:
                    urlSplit.remove("blob")
                elif "tree" in urlSplit:
                    urlSplit.remove("tree")

                urlSplit[0] = "https:/"
                urlSplit[1] = "raw.githubusercontent.com"

                # (4)
                rawUrl = '/'.join(urlSplit)
                print(f"Rebuilt url: {rawUrl}")

                # Parse HTML and get all text
                print("Getting response...")
                async with aiohttp_session.get(rawUrl) as response:
                    status = response.status
                    codeString = await response.text()
                print(f"Done.\nStatus: {status}")

                if status == 404:
                    await msg.channel.send("> :scream: Uh oh! It seems I can't find anything in that URL. Perhaps it's a private repo...")
                    print("404 Error send success.")

                else:
                    backtickCount = codeString.count("```")
                    codeString = codeString.replace("```", "`​``") # Zero-width spaces allow triple backticks to be shown in code markdown. THe second string has a zero-width char inbetween the first 2 backticks
                    highlightAlias = COMMON_EXTS[get_ext(urlSplit[-1])]

                    if highlightAlias is not None:
                        payload = f"```{highlightAlias}\n{codeString}```"
                    else:
                        payload = f"```{codeString}```"
                    
                    fileNameUnquoted = urllib.parse.unquote(urlSplit[-1])
                    await msg.channel.send(f"> :desktop: The following code is found in `{fileNameUnquoted}`:")
                    if len(payload) <= PAYLOAD_MAXLEN:
                        
                        print(urlSplit)
                        await msg.channel.send(payload)

                    # Send text and split into multiple messages if it's too long
                    elif long_code:
                        print("Code too long. Splitting.")

                        payloadSegment = ''

                        for line in codeString.split('\n'):
                            payloadSize = len(payloadSegment) + len(line) + len(highlightAlias) + backtickCount + 6 # The +6 accounts for the 6 backticks used for code markup

                            if payloadSize >= PAYLOAD_MAXLEN: 
                                if highlightAlias is not None:
                                    await msg.channel.send(f"```{highlightAlias}\n{payloadSegment}```")
                                else:
                                    await msg.channel.send(f"```{payloadSegment}```")
                                    
                                print(f"Payload segment size: {len(payloadSegment) + 6}")
                                payloadSegment = ''

                            payloadSegment += line + '\n'

                        await msg.channel.send(f"```{highlightAlias}\n{payloadSegment}```")
                        print(f"Payload segment size: {len(payloadSegment) + 6}")

                    else:
                        await msg.channel.send(f"> That's a lot of code! Type `{CMD_CHAR}longcode` to toggle my long code reading ability!")

                    await msg.channel.send(f"> :ok_hand: That's the end of `{fileNameUnquoted}`")
                    print("Send success.")

    await ghc_bot.process_commands(msg)

@ghc_bot.command()
async def longcode(ctx):
    global long_code
    if not long_code:
        await ctx.send(f"> :green_circle: Alright! I'll display code over the {PAYLOAD_MAXLEN} character limit!")
        long_code = True
    else:
        await ctx.send(f"> :red_circle: Alright! I'll only display code under the {PAYLOAD_MAXLEN} character limit!")
        long_code = False

@ghc_bot.command()
async def pause(ctx):
    global paused
    if not paused:
        await ctx.send(f"> :pause_button: No problem! I'll stay quiet until you type `{CMD_CHAR}unpause` (I'll still respond to commands, though!).")
        paused = True

@ghc_bot.command()
async def unpause(ctx):
    global paused
    if paused:
        await ctx.send(f"> :arrow_forward: I'm back! Type `{CMD_CHAR}pause` if you want me to stay quiet again.")
        paused = False

@ghc_bot.command()
async def status(ctx):
    embed = discord.Embed(title="GithubCodeBot :robot: Status:", color=HEX_YELLOW)
    embed.add_field(name="Paused", value=f">>> `{paused}`", inline=False)
    embed.add_field(name="Preview long code", value=f">>> `{long_code}`", inline=False)
            
    await ctx.send(embed=embed)

@ghc_bot.command()
async def help(ctx):
    embed = discord.Embed(title="GithubCodeBot :robot: Commands", description="_Here's what you can ask me to do!_", color=HEX_LBLUE)
    embed.add_field(name=f"`{CMD_CHAR}pause`", value=">>> I won't respond to any Github links. I'll still be actively listening for commands, though!", inline=False)
    embed.add_field(name=f"`{CMD_CHAR}unpause`", value=">>> Whatever `pause` does, this un-does.", inline=False)
    embed.add_field(name=f"`{CMD_CHAR}longcode`", value=">>> Toggle my ability to preview long pieces of code (by splitting the code into multiple messages). Be carefull with this! Once I get going, I won't stop!", inline=False)
    embed.add_field(name=f"`{CMD_CHAR}status`", value=">>> View my `pause` and `longcode` states.", inline=False)
    embed.add_field(name=f"`{CMD_CHAR}help`", value=">>> You're looking at it!", inline=False)
           
    await ctx.send(embed=embed)

def main():
    print("Thanks for using GithubCodeBot!\nIf you'd like to reset your bot token or command character, simply delete bot_token.txt or cmd_char.txt and reset the program.\n")
    print("Github repo: https://github.com/SeanJxie/GithubCodeBot")

    try:
        print("\nConnecting...\n")
        ghc_bot.run(TOKEN)
    except discord.errors.LoginFailure:
        os.remove(BT_FILEPATH)
        print("The token you've entered is invalid. Please restart the program.")

if __name__ == "__main__":
    main()
