# Fingrid Electricity Status Maubot

This Maubot plugin fetches electricity status from Fingrid's API and displays it in Matrix rooms upon command.

## Features

- Fetches electricity status data from Fingrid's API endpoint
- Displays consumption, production, CO2 emissions, and electricity price
- Shows production types with different colors
- Colors electricity price based on a gradient from green to red

## Installation

1. Set up a [Maubot instance](https://github.com/maubot/maubot).
2. Build the plugin:

```bash
maubot build
```

3. Upload the plugin to your Maubot instance using the Maubot web interface.
4. Create a new bot in your Maubot instance and associate it with the uploaded plugin.
5. Invite the bot to your Matrix room.

## Usage

Type the following command in the Matrix room to fetch and display the electricity status:

```
!sähkö
```

The bot will fetch the electricity status data from Fingrid's API and display it in the room.
