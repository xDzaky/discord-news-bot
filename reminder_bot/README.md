# Remindly - Discord Reminder Bot

A powerful Discord bot that helps you set reminders and never miss important tasks!

## Features

- ⏰ **Flexible Time Formats**: Set reminders using natural language
  - `in 30m`, `at 14:30`, `tomorrow 09:00`, `2026-04-01 10:00`
- 🔁 **Recurring Reminders**: Set daily, weekly, monthly, or custom intervals
- 🌍 **Timezone Support**: Set your timezone for accurate local reminders
- 📅 **Calendar View**: See all your reminders organized by date
- 🎛️ **Interactive Buttons**: Snooze, complete, or delete reminders with one click
- 📝 **List Management**: View and manage all your active reminders

## Commands

- `/remind <time> <message>` - Create a new reminder
- `/reminders` - View all your active reminders
- `/calendar [filter]` - View reminders in calendar format
- `/settimezone <timezone>` - Set your timezone (e.g., `Asia/Jakarta`)
- `/deletereminder <id>` - Delete a specific reminder
- `/help` - Show help information

## Quick Start (Local Development)

1. **Clone and setup**
   ```bash
   cd reminder_bot
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your DISCORD_TOKEN
   ```

3. **Run the bot**
   ```bash
   python main.py
   ```

## Deploy to Fly.io

### Prerequisites

1. Install [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/)
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. Create a Fly.io account and login
   ```bash
   fly auth signup
   # or
   fly auth login
   ```

### Deployment Steps

1. **Initialize Fly app** (this creates the app on Fly.io)
   ```bash
   fly apps create remindly-bot
   # Or use a different name if remindly-bot is taken:
   # fly apps create your-unique-bot-name
   ```

2. **Create a volume for persistent database storage**
   ```bash
   fly volumes create remindly_data --region sin --size 1
   # Note: Use your preferred region (sin = Singapore)
   ```

3. **Set your Discord token as a secret**
   ```bash
   fly secrets set DISCORD_TOKEN=your_actual_discord_token_here
   ```

4. **Update fly.toml** (if you used a different app name)
   - Open `fly.toml`
   - Change `app = "remindly-bot"` to your app name
   - Change `primary_region` if needed

5. **Deploy the bot**
   ```bash
   fly deploy
   ```

6. **Check status**
   ```bash
   fly status
   fly logs
   ```

### Updating the Bot

When you make changes, just redeploy:
```bash
fly deploy
```

### Scaling

The bot runs as a single instance by default. To scale:
```bash
fly scale count 1  # Always keep at 1 for bots
```

### Cost

- Basic resources: **FREE** (within Fly.io's free tier)
- 1GB volume: **FREE**
- Minimal memory: **FREE** (256MB sufficient)

## Discord Bot Setup

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Copy the bot token for deployment
5. Enable required intents:
   - Presence Intent
   - Server Members Intent
   - Message Content Intent
6. Go to OAuth2 → URL Generator:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`
7. Copy the generated URL and invite the bot to your server

## Project Structure

```
reminder_bot/
├── main.py              # Main bot file with commands
├── database.py          # Database operations (SQLite)
├── scheduler.py         # Background reminder scheduler
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container configuration
├── fly.toml            # Fly.io configuration
├── .env.example        # Environment variables template
└── data/               # Database storage (created on first run)
    └── reminders.db    # SQLite database
```

## Environment Variables

- `DISCORD_TOKEN` (required): Your Discord bot token
- `ENVIRONMENT` (optional): Set to `production` or `development`
- `DATABASE_PATH` (optional): Path to SQLite database (default: `./data/reminders.db`)

## Troubleshooting

**Bot not responding to commands?**
- Make sure slash commands are synced (happens automatically on startup)
- Check if the bot has proper permissions in your server
- Verify the bot token is correct

**Reminders not firing?**
- Check bot logs with `fly logs`
- Ensure the bot is running: `fly status`
- Verify database volume is properly mounted

**Database issues?**
- Check volume status: `fly volumes list`
- Access the bot console: `fly ssh console`

## Support

For issues or questions, check the logs:
```bash
fly logs --app remindly-bot
```

## License

MIT License - feel free to modify and use as needed!
