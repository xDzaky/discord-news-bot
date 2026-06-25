import asyncio
import discord
from datetime import datetime, timedelta
from typing import Optional
import database
import pytz
from dateutil.relativedelta import relativedelta

class ReminderScheduler:
    def __init__(self, bot):
        self.bot = bot
        self.task = None
        self.cleanup_task = None

    def start(self):
        """Start the scheduler background task."""
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._check_reminders_loop())

        # Start cleanup task for old polls
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self._cleanup_polls_loop())

    def stop(self):
        """Stop the scheduler background task."""
        if self.task and not self.task.done():
            self.task.cancel()

        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()

    async def _check_reminders_loop(self):
        """Background task that checks for due reminders every 30 seconds."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                await self._process_due_reminders()
            except Exception as e:
                print(f"Error in reminder scheduler: {e}")

            # Wait 30 seconds before checking again
            await asyncio.sleep(30)

    async def _cleanup_polls_loop(self):
        """Background task that cleans up old ended polls daily."""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                # Clean up polls older than 30 days
                deleted_count = await database.cleanup_old_ended_polls(days=30)
                if deleted_count > 0:
                    print(f"Cleaned up {deleted_count} old ended poll(s)", flush=True)
            except Exception as e:
                print(f"Error in poll cleanup: {e}", flush=True)

            # Wait 24 hours before cleaning again
            await asyncio.sleep(86400)  # 24 hours = 86400 seconds

    async def _process_due_reminders(self):
        """Process all due reminders."""
        reminders = await database.get_due_reminders()

        for reminder in reminders:
            try:
                await self._send_reminder(reminder)

                # Handle recurring reminders
                if reminder['recurring_interval']:
                    next_time = self._calculate_next_time(
                        datetime.fromisoformat(reminder['reminder_time']),
                        reminder['recurring_interval']
                    )
                    await database.update_reminder_time(reminder['id'], next_time)
                else:
                    # Deactivate one-time reminders
                    await database.deactivate_reminder(reminder['id'])

            except Exception as e:
                print(f"Error processing reminder {reminder['id']}: {e}")
                # Deactivate failed reminders to prevent spam
                await database.deactivate_reminder(reminder['id'])

    async def _send_reminder(self, reminder: dict):
        """Send a reminder message."""
        channel = self.bot.get_channel(reminder['channel_id'])

        if not channel:
            print(f"Channel {reminder['channel_id']} not found for reminder {reminder['id']}")
            return

        user = self.bot.get_user(reminder['user_id'])
        user_mention = user.mention if user else f"<@{reminder['user_id']}>"

        # Professional announcement style embed
        embed = discord.Embed(
            description=reminder['message'],
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        # Clean footer without reminder ID
        embed.set_footer(text="📢 Announcement")

        # Send without buttons for clean professional look
        await channel.send(
            content=user_mention,
            embed=embed
        )

    def _calculate_next_time(self, current_time: datetime, interval: str) -> datetime:
        """Calculate the next time for a recurring reminder."""
        now = datetime.utcnow()

        # Parse interval (e.g., "daily", "weekly", "monthly", "every 2 hours")
        interval = interval.lower()

        if interval == "daily":
            next_time = current_time + timedelta(days=1)
        elif interval == "weekly":
            next_time = current_time + timedelta(weeks=1)
        elif interval == "monthly":
            next_time = current_time + relativedelta(months=1)
        elif interval.startswith("every "):
            parts = interval.split()
            if len(parts) >= 3:
                amount = int(parts[1])
                unit = parts[2].rstrip('s')  # Remove plural 's'

                if unit in ["hour", "minute"]:
                    delta = timedelta(hours=amount) if unit == "hour" else timedelta(minutes=amount)
                    next_time = current_time + delta
                elif unit == "day":
                    next_time = current_time + timedelta(days=amount)
                elif unit == "week":
                    next_time = current_time + timedelta(weeks=amount)
                elif unit == "month":
                    next_time = current_time + relativedelta(months=amount)
                else:
                    next_time = current_time + timedelta(days=1)
            else:
                next_time = current_time + timedelta(days=1)
        else:
            # Default to daily if unknown
            next_time = current_time + timedelta(days=1)

        # Ensure next_time is in the future
        while next_time <= now:
            if "hour" in interval or "minute" in interval:
                next_time += timedelta(hours=1)
            else:
                next_time += timedelta(days=1)

        return next_time


class ReminderView(discord.ui.View):
    """Interactive buttons for reminders."""

    def __init__(self, reminder_id: int, user_id: int, is_recurring: Optional[str]):
        super().__init__(timeout=None)
        self.reminder_id = reminder_id
        self.user_id = user_id
        self.is_recurring = is_recurring

    @discord.ui.button(label="Done ✓", style=discord.ButtonStyle.success)
    async def done_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Mark reminder as done."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This reminder is not for you!", ephemeral=True)
            return

        await interaction.response.send_message("Reminder marked as done! ✓", ephemeral=True)

        # Disable all buttons
        for item in self.children:
            item.disabled = True

        await interaction.message.edit(view=self)

    @discord.ui.button(label="Snooze 10m", style=discord.ButtonStyle.primary)
    async def snooze_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Snooze reminder for 10 minutes."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This reminder is not for you!", ephemeral=True)
            return

        new_time = datetime.utcnow() + timedelta(minutes=10)
        await database.update_reminder_time(self.reminder_id, new_time)
        await database.activate_reminder(self.reminder_id)

        await interaction.response.send_message(
            f"Reminder snoozed for 10 minutes! I'll remind you at <t:{int(new_time.timestamp())}:t>",
            ephemeral=True
        )

        # Disable buttons
        for item in self.children:
            item.disabled = True

        await interaction.message.edit(view=self)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Delete the reminder permanently."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This reminder is not for you!", ephemeral=True)
            return

        success = await database.delete_reminder(self.reminder_id, self.user_id)

        if success:
            await interaction.response.send_message("Reminder deleted!", ephemeral=True)
        else:
            await interaction.response.send_message("Failed to delete reminder.", ephemeral=True)

        # Disable buttons
        for item in self.children:
            item.disabled = True

        await interaction.message.edit(view=self)
