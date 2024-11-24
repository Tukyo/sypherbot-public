# Sypherbot - Public Repository for the Telegram Sypherbot
![Banner](assets/readme_banner.jpg)
## 💾 Technologies Used
![License](https://img.shields.io/badge/license-MIT-green) ![Python](https://img.shields.io/badge/python-3.10-blue.svg)

![Telegram Bot](https://img.shields.io/badge/telegram-bot-blue) ![Firebase](https://img.shields.io/badge/firebase-admin-red)  ![APScheduler](https://img.shields.io/badge/scheduler-APScheduler-white)

![Web3](https://img.shields.io/badge/web3-ethereum-teal) ![AlchemyWeb3](https://img.shields.io/badge/endpoints-alchemyWeb3-363ff9)

### TL;DR
This is a crypto-forward group management bot that was developed by **Tukyo** for the Sypher project.  
Sypherbot offers customizable commands and admin controls, along with full charting, price, and buybot functionality.

### **Bot:** [Sypherbot](https://t.me/sypher_robot)

### Key Features:
- Customizable commands for user and admin interactions.
- Charting, price tracking, and buybot functionality. *(Some features only available for premium users)*

### ☎️ **Contact**
🌐 **Web:** [Tukyo](https://tukyowave.com/) • [Tukyo Games](https://tukyogames.com/) • [deSypher](https://desypher.net/)

📰 **Socials:** [X/Twitter](https://x.com/tukyowave/) • [Telegram](https/t.me/tukyogames) *(If you have any issues please reach out on telegram)*

---
### 🔗 Currently Supported Chains
![Ethereum](https://img.shields.io/badge/Ethereum-888888) ![Base](https://img.shields.io/badge/Base-0052FF) ![Arbitrum](https://img.shields.io/badge/Arbitrum-11a5f7) ![Optimism](https://img.shields.io/badge/Optimism-f7041f)

### Coming Soon!
![Avalanche](https://img.shields.io/badge/Avalanche-e13f40)
![BSC](https://img.shields.io/badge/BSC-e8b30b)
![Fantom](https://img.shields.io/badge/Fantom-1866f7)
![Polygon](https://img.shields.io/badge/Polygon-7f45df)

### Currently Supported LP
![Uniswapv3](https://img.shields.io/badge/Uniswap-V3-FF007A) ![Uniswapv2](https://img.shields.io/badge/Uniswap-V2-ff3396)
---
# ❓ Help / Guide
## ⚙️ General Setup
To begin setup for [Sypherbot](https://t.me/sypher_robot) please add the bot to your group by sending it a **/start** command. The group must be **public** for all features to work.

Sypherbot will request you to add it to your group with admin features enabled. If anything is done out of order, or admin features are not granted, the bot should recognize this and request the correct permissions from you. 

After the bot has successfully been added, and it has detected the correct permissions it will grant you access to the setup page if you are the **owner of the group**.

### Admin Setup
Here, you may configure **all admin settings** for your group.

#### User Control
`Mute:` Enable/Disable Mute, Check Mute List

`Warn:` Enable/Disable Warn, Check Warn List, Max Warns

#### Blocklist / Allowlist
`Allowlist:` Add/Remove Links from Allowlist, Check Allowlist or Disable Allowlisting for Links

`Blocklist:` Add/Remove Phrases from Blocklist, Check Blocklist

You may also reset all of your settings on this page.

### Authentication Setup
Here, you may enable or disable authentication. Once enabled, you will need to choose an authentication type.

**Authentication types include:** `Simple` `Math` `Word`

Furthermore, you may also select a timeout for the authentication and check the current settings.

### Crypto Setup
This is the main page where you can setup your project's token details. You will be able to add your `contract` `liquidity` `blockchain` `ABI`. These are **ALL REQUIRED** for the charting, price and other features to work. This bot uses fully onchain solutions to gather this information and data. If you token is unverified, the ABI will not be able to be read and you will be unable to use the crypto features that this bot offers.

You may also check your token details on this page to confirm it is correctly setup, and finally reset all of them if you wish to add a different token or start over.

### Premium Setup
On the premium setup page, if you have purchased premium you will be able to configure your `Welcome Message Header` and your `Buybot Header`.

## 💰 Premium Features
**Contact *[@tukyowave](https://t.me/tukyowave)* on Telegram for Premium**
> Sypherbot offers premium features that are currently being developed, tested and expanded. These features include `group monitoring` and `customization`.

### Customization
- `Buybot Header` - This adds a customizable header to your buybot. **700x250px**
- `Welcome Message Header` - This adds a customizable header to the welcome message when people join your group. **700x250px**
  
### Group Monitoring
- `Buybot` - This feature will allow Sypherbot to monitor transfers from the liquidity pool for your token. Sending buy messages to your group.
  
## 🈹 General Features
Sypherbot offers a plethora of features to manage and control your group. The bot is open-source so you can trust that the processes managing your bot are available to public via this repository.

- `deSypher` - You can play deSypher with this bot!
- `anti-spam` - Control spam within your group by auto-muting spammers.
- `anti-raid` - Stop group raids from happening by blocking new members from joining if a raid is detected.
- `blocklist / allowlist`
  - `allowlist` - Add specific links or domains or crypto addresses to the allowlist. Your `{group_website}` will always be allowed, as well as your LP + Contract addresses.
  - `blocklist` - Block any phrases, words or specific things from being sent via text to your group.
- `mute/warn` - Admins may mute or warn users. You can choose the maximum amount of warns. You must reply to a user's message to mute/warn them with the bot. If you need to unmute a user, check the `/mutelist` and unmute them by username.
- `authentication` • `math` `word` `simple` - There are 3 different authentication types for when a new user joins your group. Simple will make the process the easiest, but will not stop users as effectively as the other options. The authentication challenge is sent to the new user via DM after they join your group.
- `crypto`
  - `token details` - Once your token is fully setup within the bot, you can use a few different commands to view the volume, liquidity and price of the token.
  - `charting` - Charting is also available after setting up your token. There are a few modifiers for this command seen below.
- `caching` - This bot uses an efficient caching system to store and retrieve data when it is already known, making the commands and processes very efficient.

## 🤖 Commands
### Available to All Users
> If a command has a **modifier**, the syntax is /`command` `modifier`

**Example:** `/price USD`

- `/start` - Start the bot
- `/setup` - Set up the bot for your group
- `/commands | /help` - Get a list of commands
- `/play | /endgame` - Start a mini-game of deSypher within Telegram & end any ongoing games
- `/buy | /purchase` - Buy the group token
- `/contract | /ca` - Get the contract address for the SYPHER token
- `/price` - Get the price of the SYPHER token in USD - **Modifiers:** `USD` | `ETH`
- `/chart` - Links to the token chart on various platforms, defaults to `minute` when no argument provided - **Modifiers:** `h` *hour* | `d` *day* | `m` *minute* 
- `/liquidity | /lp` - View the liquidity value of the SYPHER V3 pool
- `/volume` - View the 24-hour trading volume of the SYPHER token
- `/website` - Get links to related websites
- `/report` - Report a message to group admins *(keeps admins anon during reporting process)*
- `/save` - Save a message to your DMs

---

## 🔒 Admin Commands
### Available to Group Admins Only
> All commands are available for the owner of the group. **Setup functionality is only available to the owner**.
- `/admincommands | /adminhelp` - Get a list of admin commands
- `/cleanbot | /clean | /cleanupbot | /cleanup` - Clean all bot messages in the chat
- `/clearcache` - Clears the group's cache
- `/cleargames` - Clear all active games in the chat
- `/kick | /ban` - Reply to a message to kick a user from the chat
- `/mute | /unmute` - Reply to a message to toggle mute for a user
- `/mutelist` - Check the mute list
- `/warn` - Reply to a message to warn a user
- `/warnlist` - Get a list of all warnings
- `/clearwarns` - Clear warnings for a specific user
- `/warnings` - Check warnings for a specific user
- `/block` - Block a user or contract address
- `/removeblock | /unblock` - Remove a user or contract address from the block list
- `/blocklist` - View the block list
- `/allow` - Allow a specific user or contract
- `/allowlist` - View the allow list