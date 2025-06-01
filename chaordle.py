import discord
from state import State
from report import info, warn

#load token 
TOKEN = ""
with open("./token.secret", "r") as token_file :
    TOKEN = token_file.read()


#create client
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


#state dict for each server we're in
states = {}



@client.event
async def on_ready():
    #set default state for all servs
    for server in client.guilds:
        states[server.id] = State(server, client.user)

    info(f'logged in as {client.user}!')



@client.event
async def on_message(message):
    if message.author == client.user:
        return

    #pass on any possibly relevant messages
    if message.content.startswith("!"):
        await states[message.guild.id].process_message(message)


#run bot
client.run(TOKEN)