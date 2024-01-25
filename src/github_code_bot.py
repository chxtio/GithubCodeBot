import re
import os
import urllib.parse

import discord
from discord.ext import commands
import aiohttp
import asyncio

from extensions import COMMON_EXTS

#print(f"Discord: {discord.__version__} aiohttp: {aiohttp.__version__}")

from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv("TOKEN")
CMD_CHAR = os.getenv("CMD_CHR")
GH_TOKEN = os.getenv("GH_TOKEN")

intents = discord.Intents.all()
intents.members = True

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
ghc_bot = commands.Bot(command_prefix=CMD_CHAR, description="A Discord bot to preview code in Github links.", intents=intents)
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
        code_links = find_github_links(msg.content)

        # # Check if the message is in a thread
        # if isinstance(msg.channel, discord.Thread):
        #     # Respond to the message in the thread
        #     await msg.channel.send(f'Hello, {msg.author.mention}! I received your message in the thread.')
        
        if len(code_links) > 1:
            await msg.channel.send(f"> :eyes: I've detected {len(code_links)} valid links here. They will be served in order!")

        if code_links:
            print(f'code_links: {code_links}')
            for link in code_links:
                print(f'link: {link}')
                await process_github_link(msg, link)

    await ghc_bot.process_commands(msg)

def find_github_links(content):
    # matches = re.findall("http(s?)://(www\.)?github.com/([^\s]+)", content)
    # matches = list(dict.fromkeys(filter(lambda x: get_ext(x[-1]) in COMMON_EXTS.keys(), matches)))
    # return matches

    # Updated regular expression to capture optional line range (#L1-L10)
    matches = re.findall(r"http(s?)://(www\.)?github.com/([^\s#]+)(?:#L(\d+)-L(\d+))?", content)
    print(f'matches: {matches}')

    # Filtering and de-duplicating as before
    matches = list(dict.fromkeys(filter(lambda x: get_ext(x[2]) in COMMON_EXTS.keys(), matches)))
    print(f'matches (after ext): {matches}')
    return matches

async def process_github_link(msg, link):
    # url = "https://github.com/" + link[-1]
    url = "https://github.com/" + link[-3]
    start, end = link[-2], link[-1]
    print(f'url: {url}')

    url_split = url.split('/')

    url_split.remove('')
    if "blob" in url_split:
        url_split.remove("blob")
    elif "tree" in url_split:
        url_split.remove("tree")

    url_split[0] = "https:/"
    url_split[1] = f"{GH_TOKEN}@raw.githubusercontent.com"

    raw_url = '/'.join(url_split)
    print(f'raw_url: {raw_url}')

    async with aiohttp_session.get(raw_url) as response:
        status = response.status
        code_string = await response.text()

    if status == 404:
        await msg.channel.send("> :scream: Uh oh! It seems I can't find anything in that URL...")
    else:
        await send_code_payload(msg, code_string, url_split, start, end)

async def send_code_payload(msg, code_string, url_split, start, end):
    backtick_count = code_string.count("```")
    code_string = code_string.replace("```", "`​``")  # Zero-width spaces allow triple backticks to be shown in code markdown.
    highlight_alias = COMMON_EXTS[get_ext(url_split[-1])]

    if start and end:  # Check if start and end lines were specified
        start, end = int(start), int(end)
        # start_line, end_line = map(int, url_split[-1].split('#L')[1].split('-'))
        code_lines = code_string.split('\n')[start - 1:end]
        code_string = '\n'.join(code_lines)

    if highlight_alias is not None:
        payload = f"```{highlight_alias}\n{code_string}```"
    else:
        payload = f"```{code_string}```"

    file_name_unquoted = urllib.parse.unquote(url_split[-1])

    if start and end:
        await msg.channel.send(f"> :desktop: The following code is found in `{file_name_unquoted}` lines {start} to {end}:")
    else:
        await msg.channel.send(f"> :desktop: The following code is found in `{file_name_unquoted}`:")
    
    if len(payload) <= PAYLOAD_MAXLEN:
        await msg.channel.send(payload)
    elif long_code:
        await split_and_send_code_payload(msg, code_string, highlight_alias, backtick_count)
    else:
        await msg.channel.send(f"> That's a lot of code! Type `{CMD_CHAR}longcode` to toggle my long code reading ability!")

    await msg.channel.send(f"> :ok_hand: That's the end of `{file_name_unquoted}`")

async def split_and_send_code_payload(msg, code_string, highlight_alias, backtick_count):
    print("Code too long. Splitting.")
    payload_segment = ''

    for line in code_string.split('\n'):
        payload_size = len(payload_segment) + len(line) + len(highlight_alias) + backtick_count + 6

        if payload_size >= PAYLOAD_MAXLEN:
            if highlight_alias is not None:
                await msg.channel.send(f"```{highlight_alias}\n{payload_segment}```")
            else:
                await msg.channel.send(f"```{payload_segment}```")

            print(f"Payload segment size: {len(payload_segment) + 6}")
            payload_segment = ''

        payload_segment += line + '\n'

    await msg.channel.send(f"```{highlight_alias}\n{payload_segment}```")
    print(f"Payload segment size: {len(payload_segment) + 6}")

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
    try:
        print("\nConnecting...\n")
        ghc_bot.run(TOKEN)
    except discord.errors.LoginFailure:
        os.remove(BT_FILEPATH)
        print("The token you've entered is invalid. Please restart the program.")

if __name__ == "__main__":
    main()
