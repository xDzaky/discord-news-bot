import discord
from discord import app_commands
from discord.ext import commands
import os
import sys
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz
from dateutil import parser
import database
from scheduler import ReminderScheduler
import vote_system

# Load environment variables
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables!")

# Bot setup - minimal intents for slash commands only
intents = discord.Intents(guilds=True)  # Only need guilds intent for slash commands

bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize scheduler
scheduler = None


@bot.event
async def on_ready():
    """Called when the bot is ready."""
    global scheduler

    print(f'Logged in as {bot.user} (ID: {bot.user.id})', flush=True)
    print('------', flush=True)

    try:
        # Initialize database
        await database.init_db()
        print('Database initialized', flush=True)

        # Start reminder scheduler
        scheduler = ReminderScheduler(bot)
        scheduler.start()
        print('Reminder scheduler started', flush=True)

        # Sync slash commands
        synced = await bot.tree.sync()
        print(f'Synced {len(synced)} command(s)', flush=True)
    except Exception as e:
        print(f'Error in on_ready: {e}', flush=True)
        import traceback
        traceback.print_exc()
        sys.stdout.flush()


def parse_time_string(time_str: str, user_timezone: str = 'UTC') -> datetime:
    """Parse various time formats into datetime object."""
    import re

    time_str = time_str.strip().lower()
    tz = pytz.timezone(user_timezone)
    now = datetime.now(tz)

    # Handle relative times - try direct format first: "30m", "2h", "1d" (without "in")
    direct_match = re.match(r'^(\d+)\s*([mhd]|min|mins|minute|minutes|hour|hours|day|days)$', time_str)
    if direct_match:
        amount = int(direct_match.group(1))
        unit = direct_match.group(2)

        if unit in ['m', 'min', 'mins', 'minute', 'minutes']:
            delta = timedelta(minutes=amount)
        elif unit in ['h', 'hour', 'hours']:
            delta = timedelta(hours=amount)
        elif unit in ['d', 'day', 'days']:
            delta = timedelta(days=amount)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        result = now + delta
        return result.astimezone(pytz.UTC).replace(tzinfo=None)

    # Handle relative times like "in 30m", "in 2h", "in 1d"
    if time_str.startswith('in '):
        time_str = time_str[3:].strip()

        # Parse amount and unit - more flexible regex
        match = re.match(r'(\d+)\s*([mhd]|min|mins|minute|minutes|hour|hours|day|days)(?:\s|$)', time_str)

        if match:
            amount = int(match.group(1))
            unit = match.group(2)

            if unit in ['m', 'min', 'mins', 'minute', 'minutes']:
                delta = timedelta(minutes=amount)
            elif unit in ['h', 'hour', 'hours']:
                delta = timedelta(hours=amount)
            elif unit in ['d', 'day', 'days']:
                delta = timedelta(days=amount)
            else:
                raise ValueError(f"Unknown time unit: {unit}")

            result = now + delta
            return result.astimezone(pytz.UTC).replace(tzinfo=None)
        else:
            raise ValueError(f"Could not parse relative time: 'in {time_str}'")

    # Handle "tomorrow" or "tomorrow HH:MM"
    if time_str.startswith('tomorrow'):
        tomorrow = now + timedelta(days=1)

        if len(time_str) > 8:  # "tomorrow HH:MM"
            time_part = time_str[8:].strip()
            try:
                parsed_time = parser.parse(time_part)
                result = tomorrow.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)
            except:
                result = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
        else:
            result = tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)  # Default to 9 AM

        return result.astimezone(pytz.UTC).replace(tzinfo=None)

    # Handle "at HH:MM" (today) or just "HH:MM"
    time_pattern = re.match(r'^(at\s+)?(\d{1,2}):(\d{2})\s*(am|pm)?$', time_str)
    if time_pattern or time_str.startswith('at '):
        if time_str.startswith('at '):
            time_str = time_str[3:].strip()

        try:
            parsed_time = parser.parse(time_str)
            result = now.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)

            # If time is in the past, assume tomorrow
            if result < now:
                result += timedelta(days=1)

            return result.astimezone(pytz.UTC).replace(tzinfo=None)
        except:
            raise ValueError(f"Could not parse time: '{time_str}'")

    # Try to parse as full datetime
    try:
        parsed = parser.parse(time_str, fuzzy=True)
        # If no timezone info, assume user's timezone
        if parsed.tzinfo is None:
            parsed = tz.localize(parsed)

        return parsed.astimezone(pytz.UTC).replace(tzinfo=None)
    except:
        raise ValueError(f"Could not parse time string: {time_str}")


@bot.tree.command(name="remind", description="Set a reminder")
@app_commands.describe(
    time="When: '1m', '30m', '2h', 'in 1h', '14:30', 'tomorrow 9:00', '2026-04-01 10:00'",
    message="What to remind you about",
    recurring="Optional: Set recurring interval (e.g., 'daily', 'weekly', 'every 2 hours')",
    channel="Optional: Channel to send reminder (default: current channel)"
)
async def remind(
    interaction: discord.Interaction,
    time: str,
    message: str,
    recurring: str = None,
    channel: discord.TextChannel = None
):
    """Create a new reminder."""
    await interaction.response.defer(ephemeral=True)

    try:
        # Get user's timezone
        user_tz = await database.get_user_timezone(interaction.user.id)

        # Parse time
        try:
            reminder_time = parse_time_string(time, user_tz)
        except ValueError as e:
            await interaction.followup.send(
                f"❌ Could not understand the time format!\n\n"
                f"**Error:** {str(e)}\n\n"
                f"**Examples:**\n"
                f"• `1m` or `30m` or `2h` or `1d`\n"
                f"• `in 30m` or `in 2h` or `in 1d`\n"
                f"• `14:30` or `2:30pm` (today at that time)\n"
                f"• `tomorrow 09:00`\n"
                f"• `2026-04-01 10:00`",
                ephemeral=True
            )
            return

        # Get current UTC time
        current_time = datetime.utcnow()

        # Check if time is in the past
        if reminder_time < current_time:
            await interaction.followup.send(
                "❌ The scheduled time is in the past! Please provide a future time.",
                ephemeral=True
            )
            return

        # Use current channel if none specified
        target_channel = channel or interaction.channel

        # Add to database
        reminder_id = await database.add_reminder(
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            channel_id=target_channel.id,
            message=message,
            reminder_time=reminder_time,
            timezone=user_tz,
            recurring_interval=recurring
        )

        # Create response embed - professional style
        timestamp = int(reminder_time.timestamp())

        embed = discord.Embed(
            title="✅ Scheduled Successfully",
            description=f"{message}",
            color=discord.Color.green()
        )

        embed.add_field(
            name="📅 Scheduled Time",
            value=f"<t:{timestamp}:F>\n(<t:{timestamp}:R>)",
            inline=True
        )

        embed.add_field(name="📢 Channel", value=target_channel.mention, inline=True)

        if recurring:
            embed.add_field(name="🔁 Repeat", value=recurring, inline=True)

        embed.set_footer(text=f"Timezone: {user_tz}")

        await interaction.followup.send(embed=embed, ephemeral=True)

    except ValueError as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
        print(f"Error in /remind command: {e}")


@bot.tree.command(name="reminders", description="View all your active reminders")
@app_commands.describe(show_all="Show inactive reminders too")
async def reminders(interaction: discord.Interaction, show_all: bool = False):
    """List all user's reminders."""
    await interaction.response.defer(ephemeral=True)

    try:
        user_reminders = await database.get_user_reminders(
            interaction.user.id,
            active_only=not show_all
        )

        if not user_reminders:
            await interaction.followup.send(
                "You don't have any reminders set!",
                ephemeral=True
            )
            return

        # Create embed
        embed = discord.Embed(
            title=f"📋 Your Reminders ({len(user_reminders)})",
            color=discord.Color.blue()
        )

        for reminder in user_reminders[:25]:  # Discord limit: 25 fields
            reminder_time = datetime.fromisoformat(reminder['reminder_time'])
            timestamp = int(reminder_time.timestamp())

            status = "🟢 Active" if reminder['active'] else "⚫ Inactive"
            recurring_info = f"\n🔁 {reminder['recurring_interval']}" if reminder['recurring_interval'] else ""

            channel = bot.get_channel(reminder['channel_id'])
            channel_mention = channel.mention if channel else f"Channel ID: {reminder['channel_id']}"

            embed.add_field(
                name=f"ID: {reminder['id']} | {status}",
                value=(
                    f"**Message:** {reminder['message'][:100]}\n"
                    f"**When:** <t:{timestamp}:R>\n"
                    f"**Where:** {channel_mention}{recurring_info}"
                ),
                inline=False
            )

        if len(user_reminders) > 25:
            embed.set_footer(text=f"Showing 25 of {len(user_reminders)} reminders")

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
        print(f"Error in /reminders command: {e}")


@bot.tree.command(name="calendar", description="View your reminders in calendar format")
@app_commands.describe(filter="Filter reminders by timeframe")
@app_commands.choices(filter=[
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="Today", value="today"),
    app_commands.Choice(name="This Week", value="week"),
    app_commands.Choice(name="This Month", value="month")
])
async def calendar(interaction: discord.Interaction, filter: str = "week"):
    """Show reminders in calendar format."""
    await interaction.response.defer(ephemeral=True)

    try:
        user_reminders = await database.get_user_reminders(interaction.user.id, active_only=True)

        if not user_reminders:
            await interaction.followup.send("You don't have any active reminders!", ephemeral=True)
            return

        # Filter reminders based on timeframe
        now = datetime.utcnow()
        filtered_reminders = []

        for reminder in user_reminders:
            reminder_time = datetime.fromisoformat(reminder['reminder_time'])

            if filter == "today":
                if reminder_time.date() == now.date():
                    filtered_reminders.append(reminder)
            elif filter == "week":
                if reminder_time <= now + timedelta(days=7):
                    filtered_reminders.append(reminder)
            elif filter == "month":
                if reminder_time <= now + timedelta(days=30):
                    filtered_reminders.append(reminder)
            else:  # all
                filtered_reminders.append(reminder)

        if not filtered_reminders:
            await interaction.followup.send(
                f"No reminders found for the selected timeframe: {filter}",
                ephemeral=True
            )
            return

        # Create calendar embed
        embed = discord.Embed(
            title=f"📅 Calendar View - {filter.title()}",
            description=f"Showing {len(filtered_reminders)} reminder(s)",
            color=discord.Color.blue()
        )

        # Group by date
        reminders_by_date = {}
        for reminder in filtered_reminders:
            reminder_time = datetime.fromisoformat(reminder['reminder_time'])
            date_key = reminder_time.date()

            if date_key not in reminders_by_date:
                reminders_by_date[date_key] = []

            reminders_by_date[date_key].append(reminder)

        # Add fields for each date
        for date, day_reminders in sorted(reminders_by_date.items())[:10]:
            timestamp = int(datetime.combine(date, datetime.min.time()).timestamp())
            field_value = ""

            for reminder in day_reminders[:5]:  # Max 5 per day to avoid clutter
                reminder_time = datetime.fromisoformat(reminder['reminder_time'])
                time_str = reminder_time.strftime("%H:%M")
                recurring = "🔁" if reminder['recurring_interval'] else ""
                field_value += f"• {time_str} - {reminder['message'][:50]} {recurring}\n"

            embed.add_field(
                name=f"📆 <t:{timestamp}:D>",
                value=field_value or "No reminders",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
        print(f"Error in /calendar command: {e}")


@bot.tree.command(name="settimezone", description="Set your timezone for reminders")
@app_commands.describe(timezone="Your timezone (e.g., 'Asia/Jakarta', 'America/New_York', 'Europe/London')")
async def settimezone(interaction: discord.Interaction, timezone: str):
    """Set user's timezone preference."""
    await interaction.response.defer(ephemeral=True)

    try:
        # Validate timezone
        try:
            pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            await interaction.followup.send(
                f"❌ Unknown timezone: {timezone}\n"
                f"Please use a valid timezone name like 'Asia/Jakarta', 'America/New_York', etc.\n"
                f"See: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
                ephemeral=True
            )
            return

        # Save timezone
        await database.set_user_timezone(interaction.user.id, timezone)

        embed = discord.Embed(
            title="✅ Timezone Set!",
            description=f"Your timezone has been set to **{timezone}**",
            color=discord.Color.green()
        )

        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz)

        embed.add_field(
            name="Current Time",
            value=current_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            inline=False
        )

        embed.set_footer(text="All your future reminders will use this timezone")

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
        print(f"Error in /settimezone command: {e}")


@bot.tree.command(name="deletereminder", description="Delete a specific reminder")
@app_commands.describe(reminder_id="The ID of the reminder to delete")
async def deletereminder(interaction: discord.Interaction, reminder_id: int):
    """Delete a specific reminder by ID."""
    await interaction.response.defer(ephemeral=True)

    try:
        success = await database.delete_reminder(reminder_id, interaction.user.id)

        if success:
            embed = discord.Embed(
                title="✅ Reminder Deleted",
                description=f"Reminder ID {reminder_id} has been deleted.",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Reminder Not Found",
                description=f"Could not find reminder ID {reminder_id}, or it doesn't belong to you.",
                color=discord.Color.red()
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
        print(f"Error in /deletereminder command: {e}")


# ==================== VOTING COMMANDS ====================

@bot.tree.command(name="vote", description="Create a poll/vote")
@app_commands.describe(
    question="The question to ask",
    option1="First option",
    option2="Second option",
    option3="Third option (optional)",
    option4="Fourth option (optional)",
    option5="Fifth option (optional)",
    vote_type="Single choice (radio) or Multiple choice (checkbox)",
    anonymous="Hide who voted for what"
)
@app_commands.choices(vote_type=[
    app_commands.Choice(name="Single Choice (Radio)", value="single"),
    app_commands.Choice(name="Multiple Choice (Checkbox)", value="multiple")
])
async def vote(
    interaction: discord.Interaction,
    question: str,
    option1: str,
    option2: str,
    option3: str = None,
    option4: str = None,
    option5: str = None,
    vote_type: str = "single",
    anonymous: bool = False
):
    """Create a new poll."""
    await interaction.response.defer()

    try:
        # Collect options
        options_list = [option1, option2]
        if option3:
            options_list.append(option3)
        if option4:
            options_list.append(option4)
        if option5:
            options_list.append(option5)

        # Create poll in database
        poll_id = await database.create_poll(
            creator_id=interaction.user.id,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            question=question,
            options=options_list,
            vote_type=vote_type,
            end_time=None,
            is_anonymous=anonymous
        )

        # Get poll options from database
        options = await database.get_poll_options(poll_id)

        # Create embed
        embed = await vote_system.create_poll_embed(
            poll_id=poll_id,
            question=question,
            options=options,
            vote_type=vote_type,
            is_anonymous=anonymous
        )

        # Create view with buttons
        view = vote_system.PollView(
            poll_id=poll_id,
            options=options,
            vote_type=vote_type,
            is_anonymous=anonymous
        )

        # Send poll message
        message = await interaction.followup.send(embed=embed, view=view)

        # Save message ID
        await database.update_poll_message_id(poll_id, message.id)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
        print(f"Error in /vote command: {e}")



# Autocomplete for poll_id
async def poll_id_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[int]]:
    """Autocomplete function for poll IDs."""
    try:
        # Get active polls in the guild
        active_polls = await database.get_active_polls_by_guild(interaction.guild_id)

        # Filter by current input if provided
        if current:
            # Try to match by ID or question
            filtered = [
                p for p in active_polls
                if str(p['id']).startswith(current) or current.lower() in p['question'].lower()
            ]
        else:
            filtered = active_polls

        # Return up to 25 choices (Discord limit)
        return [
            app_commands.Choice(
                name=f"#{poll['id']} - {poll['question'][:80]}",
                value=poll['id']
            )
            for poll in filtered[:25]
        ]
    except Exception as e:
        print(f"Error in poll_id autocomplete: {e}")
        return []


@bot.tree.command(name="endvote", description="End a poll and show final results")
@app_commands.describe(poll_id="The ID of the poll to end")
@app_commands.autocomplete(poll_id=poll_id_autocomplete)
async def endvote(interaction: discord.Interaction, poll_id: int):
    """End a poll and show results."""
    await interaction.response.defer(ephemeral=True)

    try:
        # Check if poll exists and user is creator
        poll = await database.get_poll(poll_id)

        if not poll:
            await interaction.followup.send("❌ Poll not found!", ephemeral=True)
            return

        if poll['creator_id'] != interaction.user.id:
            await interaction.followup.send("❌ Only the poll creator can end it!", ephemeral=True)
            return

        if not poll['is_active']:
            await interaction.followup.send("❌ This poll has already ended!", ephemeral=True)
            return

        # End the poll
        await database.end_poll(poll_id)

        # Create results embed
        results_embed = await vote_system.create_results_embed(poll_id)

        # Try to update original message
        try:
            channel = bot.get_channel(poll['channel_id'])
            if channel and poll['message_id']:
                message = await channel.fetch_message(poll['message_id'])
                # Remove buttons and show results
                await message.edit(embed=results_embed, view=None)
        except:
            pass

        # Send confirmation
        await interaction.followup.send(
            f"✅ Poll #{poll_id} has been ended!\n\nResults have been updated in the original message.",
            ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
        print(f"Error in /endvote command: {e}")



@bot.tree.command(name="pollresults", description="View current results of a poll")
@app_commands.describe(poll_id="The ID of the poll")
@app_commands.autocomplete(poll_id=poll_id_autocomplete)
async def pollresults(interaction: discord.Interaction, poll_id: int):
    """View poll results."""
    await interaction.response.defer(ephemeral=True)

    try:
        poll = await database.get_poll(poll_id)

        if not poll:
            await interaction.followup.send("❌ Poll not found!", ephemeral=True)
            return

        options = await database.get_poll_options(poll_id)
        results = await database.get_poll_results(poll_id)
        total_votes = sum(results.values())

        # Build results
        results_text = ""
        for option in options:
            vote_count = results.get(option['id'], 0)
            percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0

            bar_length = 12
            filled = int(bar_length * percentage / 100)
            bar = "█" * filled + "░" * (bar_length - filled)

            results_text += f"**{option['option_text']}**\n"
            results_text += f"{bar} {vote_count} ({percentage:.1f}%)\n\n"

            # Show voters if not anonymous
            if not poll['is_anonymous']:
                voters = await database.get_poll_voters(poll_id, option['id'])
                if voters:
                    voter_mentions = [f"<@{uid}>" for uid in voters[:5]]
                    if len(voters) > 5:
                        voter_mentions.append(f"and {len(voters) - 5} more...")
                    results_text += f"*Voters: {', '.join(voter_mentions)}*\n\n"

        status = "🟢 Active" if poll['is_active'] else "🔴 Ended"

        embed = discord.Embed(
            title=f"📊 {poll['question']}",
            description=results_text if results_text else "No votes yet",
            color=discord.Color.blue() if poll['is_active'] else discord.Color.gold()
        )

        embed.set_footer(text=f"Poll ID: {poll_id} • {status} • Total: {total_votes} votes")

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
        print(f"Error in /pollresults command: {e}")


@bot.tree.command(name="polls", description="View all active polls in this server")
async def polls_command(interaction: discord.Interaction):
    """List all active polls in the server."""
    await interaction.response.defer(ephemeral=True)

    try:
        # Get active polls in the guild
        active_polls = await database.get_active_polls_by_guild(interaction.guild_id)

        if not active_polls:
            await interaction.followup.send(
                "📊 **No Active Polls**\n\nThere are currently no active polls in this server.\n\nCreate one with `/vote`!",
                ephemeral=True
            )
            return

        # Build embed
        embed = discord.Embed(
            title="📊 Active Polls",
            description=f"Found {len(active_polls)} active poll(s) in this server",
            color=discord.Color.blue()
        )

        for poll in active_polls[:10]:  # Show max 10 polls
            # Get vote count
            results = await database.get_poll_results(poll['id'])
            total_votes = sum(results.values())

            # Get creator
            creator = interaction.guild.get_member(poll['creator_id'])
            creator_name = creator.mention if creator else "Unknown"

            # Format created time
            from datetime import datetime
            created_at = datetime.fromisoformat(poll['created_at'])
            created_str = discord.utils.format_dt(created_at, style='R')

            embed.add_field(
                name=f"#{poll['id']} - {poll['question'][:100]}",
                value=f"👤 Creator: {creator_name}\n"
                      f"🗳️ {total_votes} vote(s)\n"
                      f"📝 Type: {poll['vote_type'].capitalize()}\n"
                      f"⏰ Created {created_str}\n"
                      f"💬 Use `/endvote {poll['id']}` to end or `/pollresults {poll['id']}` to view",
                inline=False
            )

        embed.set_footer(text=f"Use /vote to create a new poll • {len(active_polls)} total")

        await interaction.followup.send(embed=embed, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
        print(f"Error in /polls command: {e}")


@bot.tree.command(name="help", description="Get help with using Remindly")
async def help_command(interaction: discord.Interaction):
    """Show help information."""
    embed = discord.Embed(
        title="📢 Remindly - Scheduled Announcements",
        description="Schedule professional announcements and messages for your server",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="/remind",
        value="Schedule a new announcement\n"
              "**Time formats:**\n"
              "• `1m`, `30m`, `2h`, `1d`\n"
              "• `14:30` or `2:30pm`\n"
              "• `tomorrow 09:00`\n"
              "• `2026-04-01 10:00`",
        inline=False
    )

    embed.add_field(
        name="/reminders",
        value="View all scheduled messages",
        inline=True
    )

    embed.add_field(
        name="/calendar",
        value="Calendar view of schedules",
        inline=True
    )

    embed.add_field(
        name="/settimezone",
        value="Set your timezone",
        inline=True
    )

    embed.add_field(
        name="/deletereminder",
        value="Delete a scheduled message",
        inline=True
    )

    embed.add_field(
        name="🔁 Recurring",
        value="Add `recurring: daily`, `weekly`, or `monthly` for repeating announcements",
        inline=False
    )

    # Voting section
    embed.add_field(
        name="📊 Voting System",
        value="**`/vote`** - Create a poll (single/multiple choice)\n"
              "**`/polls`** - View all active polls in the server\n"
              "**`/endvote`** - End a poll and show results\n"
              "**`/pollresults`** - View current poll results",
        inline=False
    )

    embed.set_footer(text="Remindly • Professional Scheduled Announcements")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# Run the bot
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
