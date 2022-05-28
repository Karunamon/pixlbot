# Pixlbot

Pixl is a Discord utility bot and bot 'framework' based on [Pycord](https://pycord.dev/). By itself, it does nothing interesting. It acts as a host for various cogs (plug-ins) that do useful things.

Please note, this bot is a hobby project and is somewhat idiosyncratic as a result. It has been built up over a couple of years, and so has some annoying inconsistencies I have yet to address.

## Installation

You require:

* Python 3.9 or later
* `pip` for installing libraries

The basic installation looks like this:

```bash
git clone https://github.com/Karunamon/pixlbot.git 
python3 -m ensurepip
pip install pipenv
cd pixlbot
pipenv install
```

### Discord Setup

You will need to register a bot account on the [Discord developer portal](https://discord.com/developers/applications). 

1. Select 'new application' and enter what you want your bot to be named.
2. Select Bot on the left bar and add a bot account. Upload an avatar if you want.
3. Hit 'reset token' and copy this text aside
4. On this page, enable all privileged gateway intents
5. Save changes
6. Select OAuth2 on the left bar, then URL Generator
7. Check `bot` and `applications.commands`. A new panel will appear, check `Administrator`
8. Press copy on the URL that appears, paste into a web browser, and follow the instructions to add the bot to your server

It would also be helpful to enable developer mode in your Discord client (under advanced in your settings), this will allow you to copy numeric IDs you will need for the configuration file.

### Configuration

Copy `config.yml.example` to `config.yml` and open it in a good text editor (i.e. not Notepad). Insert your bot's token from the developer portal in the appropriate place.

You will notice a couple of plug-ins commented out. These require further configuration before they can be used. Read on to see how to set these up.

### Running

`python3 main.py`

## Plugin Reference

### Bonk
A thing to redirect messages posted in inappropriate places to more appropriate places. To use it, right click on any message and a select "bonk this message". The bot will then delete the message, re-post it in the desired channel, and send the author a private message castigating them for their for poor posting habits.

This also results in the author getting mentioned like three or four times which is actually kind of annoying, and so this serves as an effective deterrent.

##### Setup

Grab the ID of the channel bonked messages should go to. You should also upload a sticker which will be used as a reply to the bonked message, and grab its ID as well. Fill these numeric IDs in `config.yml` and uncomment `- cogs.bonk`