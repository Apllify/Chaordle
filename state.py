from enum import Enum
from report import info, warn, debug
from unidecode import unidecode


import random
import json

class Mode(Enum):
    IDLE = 1
    SEARCH = 2
    PUZZLE = 3

default_params = {
    "min_letters" : 8,
    "max_letters" : 15,
    "force_uncommon" : True,
    "lookup_depth" : 5000, 
    "guess_count" : 8, 
    "win_message" : "ROUND WON!",
    "loss_message" : "GUESSES EXHAUSTED!",
} 

#file wide dictionary lists
english_dict = set()
french_dict = set()

#helper functions 
def wordle_compare(secret, guess) -> list[int]:
    """
    Returns a list of form [-1,0,1,1,2,0] comparing both messages
    """
    if len(secret) != len(guess):
        return [-1] * len(guess)
    
    status = [0] * len(secret)

    #pass 1 : only identify perfect matches
    for i in range(len(secret)):
        if secret[i] == guess[i] : 
            status[i] = 2

    secret_lockout = [secret[i] if status[i] == 0 else "_"    for i in range(len(secret))]

    #pass 2 : identify yellows 
    for i in range(len(secret_lockout)):
        if status[i] == 2:
            continue 

        if guess[i] in secret_lockout:
            status[i] = 1
            match_index = secret_lockout.index(guess[i])
            secret_lockout[match_index] = "_"

    return status

def emojify(status : list[int]) -> str:
    """
    Transforms the output of wordle_compare into the appropriate emoji list
    """
    emojis = []
    for code in status : 
        if code == 0 :
            emojis.append(":white_large_square:")
        elif code == 1 : 
            emojis.append(":yellow_square:")
        elif code == 2 : 
            emojis.append(":green_square:")
        elif code == -1 : 
            emojis.append(":brown_square:")

    return "".join(emojis)

def segment(msg) -> list[str]:
    if len(msg) < 2000:
        return [msg]
    
    #otherwise break up based on line starts
    lines = msg.split("\n")

    segments = [] 
    cur_segment = []

    for line in lines : 
        if sum(map(len, cur_segment)) + len(line) < 1800:
            cur_segment.append(line)
        else : 
            cur_segment = "\n".join(cur_segment)
            segments.append(cur_segment)
            cur_segment = [line]

    cur_segment = "\n".join(cur_segment)
    segments.append(cur_segment)

    return segments

#state encapsulation class
class State():
    def __init__(self, server, bot):
        self.mode = Mode.IDLE
        self.params = default_params

        self.server = server
        self.bot = bot

        self.puzzle_channel = None
        self.secret_word = "ZZZZZZ"
        self.secret_word_link = "[UNAVAILABLE]"

        self.guess_history = []

    async def process_message(self, message):
        """
        Handles all command responding
        """
        content = message.content

        if not content.startswith("!"):
            return

        #case 1 : puzzle start command 
        if self.mode == Mode.IDLE and content.startswith("!chaordle"):
            #check for integer channel argument
            try : 
                channel_id = int(content.split()[1])
            except: 
                await message.channel.send("Invalid syntax : command must be of form ```!chaordle [channel_id]```")
                return
            
            #check that channel exists
            try : 
                channel = await message.guild.fetch_channel(channel_id)
            except:
                await message.channel.send("Invalid channel id provided. Reminder : command must be of form ```!chaordle [channel_id]```")
                return 
            
            #begin the puzzle
            success = await self.start_puzzle(channel)
            if not success : 
                warn("puzzle starting failed", True)
                return

            #send the initial puzzle update
            await self.send_update(message.channel)
            return
        
        #processing depends on state 
        command = content.split()[0][1:]

        #case 1 : we process this as a guess
        if self.mode == Mode.PUZZLE : 
            await self.process_guess(message.channel, command)
        
        #case 2 : we process this as a command 
        elif self.mode == Mode.IDLE : 

            #dump our params dict to user
            if command == "params" : 
                params_string = json.dumps(self.params, indent=2)
                await message.channel.send(params_string)
                return
            
            elif command == "param" : 
                #try parse user input 
                try : 
                    name, value = content.split()[1:3]
                except : 
                    await message.channel.send("Command syntax error. Reminder : command must be of form ```!param [param_name] [param_value]```")
                    return 

                success = self.set_param(name, value)

                #report on success status
                if not success :
                    await message.channel.send("Param assignment failed. Reminder : command must be of form ```!param [param_name] [param_value]```")
                else : 
                    await message.channel.send("Param assignment succeeded.")
                return                 

        
        

    async def start_puzzle(self, channel) -> bool:
        """
        Begins the puzzle
        """
        #reject requests if not idle
        if self.mode != Mode.IDLE : 
            return False
        
        self.mode = Mode.SEARCH
        self.puzzle_channel = channel

        self.guess_history = [] 

        #decide on secret word
        await self.fetch_word(channel)
        self.mode = Mode.PUZZLE

        return True


    async def fetch_word(self, channel):
        """
        Scour channel for random valid word
        """
        #load the full message history by non-self senders
        messages = [message async for message in channel.history(limit=self.params["lookup_depth"])]
        messages = [message for message in messages if message.author != self.bot]

        #transform into pairs for each word
        text_pairs = [(message.content, message) for message in messages]
        word_pairs = []
        for (text, msg) in text_pairs : 
            words = text.split()
            for word in words : 
                #remove accents+capitalization
                clean_word = unidecode(word.lower())
                
                #add the pair if word valid
                if self.is_word_valid(clean_word):
                    word_pairs.append((clean_word, msg))


        if len(word_pairs) == 0:
            warn("no valid words found in seek", True)
            return "123459"

        #pick out random candidate
        self.secret_word, secret_msg = random.choice(word_pairs)
        self.secret_word_link = secret_msg.jump_url
    

    async def send_update(self, channel):
        """
        Sends an update in the channel with the current guessing state
        """
        lines = []

        lines.append("Guess history:")


        #actual guesses
        for guess in self.guess_history:
            comparison = wordle_compare(self.secret_word, guess)
            emojis = emojify(comparison)

            line_text = emojis + f" : `{guess.upper()}`"
            lines.append(line_text)

        #padding for unused guesses
        for i in range(self.params["guess_count"] - len(self.guess_history)):
            lines.append(":black_large_square:" * len(self.secret_word))

        #specify word length
        lines.append(f"Word length = {len(self.secret_word)}.")

        message_content = "\n".join(lines)


        #segment message for character limit reasons 
        message_segments = segment(message_content)
        for seg in message_segments : 
            await channel.send(seg)




    async def process_guess(self, channel, guess : str) :
        """
        Takes a guess and updates state accordingly + sends status update 
        """
        if self.mode != Mode.PUZZLE:
            return

        guess = guess.lower()

        self.guess_history.append(guess)
        await self.send_update(channel)

        #check for win or loss
        game_done = False
        if guess == self.secret_word : 
            await channel.send(self.params["win_message"])
            game_done = True
        elif len(self.guess_history) >= self.params["guess_count"]:
            await channel.send(self.params["loss_message"])
            await channel.send(f"The real answer was : `{self.secret_word.upper()}`.")
            game_done = True

        #if game done, reveal link and reset mode 
        if game_done :
            await channel.send(f"Original message link : {self.secret_word_link}")
            self.mode = Mode.IDLE



    def is_word_valid(self, word) -> bool:
        #length check
        if len(word) < self.params["min_letters"] or len(word) > self.params["max_letters"]:
            return False
        
        #alphabetical check
        if not word.isalpha():
            return False
        
        #common-ness check
        if self.params["force_uncommon"]:
            if word in english_dict or word in french_dict :
                return False
        
        return True
    
    def set_param(self, name, new_value) -> bool :
        #check that param exists
        if not name in self.params : 
            return False
        
        #try to cast to param type 
        try : 
            if type(self.params[name]) == int : 
                typed_value = int(new_value)
            elif type(self.params[name]) == bool :
                typed_value = (new_value.lower() == "true")
            else :
                typed_value = new_value
        except : 
            return False
        
        #actually make the assignment
        self.params[name] = typed_value
        return True
        


        







#load both language dictionaries 
with open("words/english.txt", "r") as english:
    english_dict = set()
    for word in english.readlines():
        english_dict.add(word.strip())

with open("words/french.txt", "r", encoding="utf-8") as french:
    #remove accents from all words before adding 
    french_dict = set()
    for word in french.readlines():
        french_dict.add(unidecode(word.strip()))

