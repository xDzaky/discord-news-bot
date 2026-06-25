import discord
from discord import ui
from datetime import datetime
from typing import Optional
import database


class PollView(ui.View):
    """Interactive voting buttons for polls."""

    def __init__(self, poll_id: int, options: list, vote_type: str, is_anonymous: bool):
        super().__init__(timeout=None)
        self.poll_id = poll_id
        self.vote_type = vote_type  # "single" or "multiple"
        self.is_anonymous = is_anonymous

        # Add buttons for each option
        for idx, option in enumerate(options):
            button = VoteButton(
                poll_id=poll_id,
                option_id=option['id'],
                option_text=option['option_text'],
                option_index=idx,
                vote_type=vote_type
            )
            self.add_item(button)


class VoteButton(ui.Button):
    """Individual vote button."""

    def __init__(self, poll_id: int, option_id: int, option_text: str, option_index: int, vote_type: str):
        # Use different styles for visual variety
        styles = [
            discord.ButtonStyle.primary,
            discord.ButtonStyle.success,
            discord.ButtonStyle.secondary,
            discord.ButtonStyle.primary,
            discord.ButtonStyle.success
        ]

        super().__init__(
            label=option_text[:80],  # Discord limit
            style=styles[option_index % len(styles)],
            custom_id=f"vote_{poll_id}_{option_id}"
        )
        self.poll_id = poll_id
        self.option_id = option_id
        self.vote_type = vote_type

    async def callback(self, interaction: discord.Interaction):
        """Handle vote button click."""
        # Check if poll is still active
        poll = await database.get_poll(self.poll_id)
        if not poll or not poll['is_active']:
            await interaction.response.send_message(
                "This poll has ended!",
                ephemeral=True
            )
            return

        # Get user's current votes
        user_votes = await database.get_user_votes(self.poll_id, interaction.user.id)

        if self.vote_type == "single":
            # Single choice - replace previous vote
            if self.option_id in user_votes:
                # Already voted for this option - remove vote
                await database.remove_user_votes(self.poll_id, interaction.user.id)
                await interaction.response.send_message(
                    "Your vote has been removed!",
                    ephemeral=True
                )
            else:
                # Remove old vote and add new one
                await database.remove_user_votes(self.poll_id, interaction.user.id)
                await database.add_vote(self.poll_id, interaction.user.id, self.option_id)
                await interaction.response.send_message(
                    f"You voted for: **{self.label}**",
                    ephemeral=True
                )
        else:
            # Multiple choice - toggle this option
            if self.option_id in user_votes:
                # Remove vote for this option only
                async with database.aiosqlite.connect(database.DATABASE_PATH) as db:
                    await db.execute('''
                        DELETE FROM poll_votes
                        WHERE poll_id = ? AND user_id = ? AND option_id = ?
                    ''', (self.poll_id, interaction.user.id, self.option_id))
                    await db.commit()
                await interaction.response.send_message(
                    f"Removed vote for: **{self.label}**",
                    ephemeral=True
                )
            else:
                # Add vote for this option
                await database.add_vote(self.poll_id, interaction.user.id, self.option_id)
                await interaction.response.send_message(
                    f"Added vote for: **{self.label}**",
                    ephemeral=True
                )

        # Update the poll embed with new results
        await update_poll_message(interaction, self.poll_id)


async def update_poll_message(interaction: discord.Interaction, poll_id: int):
    """Update the poll message with current results."""
    try:
        poll = await database.get_poll(poll_id)
        options = await database.get_poll_options(poll_id)
        results = await database.get_poll_results(poll_id)

        # Calculate total votes
        total_votes = sum(results.values())

        # Build results display
        results_text = ""
        for option in options:
            vote_count = results.get(option['id'], 0)
            percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0

            # Create progress bar
            bar_length = 10
            filled = int(bar_length * percentage / 100)
            bar = "█" * filled + "░" * (bar_length - filled)

            results_text += f"**{option['option_text']}**\n"
            results_text += f"{bar} {vote_count} votes ({percentage:.1f}%)\n\n"

        # Create updated embed
        embed = discord.Embed(
            title=f"📊 {poll['question']}",
            description=results_text if results_text else "No votes yet",
            color=discord.Color.blue()
        )

        vote_type_text = "Single choice" if poll['vote_type'] == "single" else "Multiple choice"
        anonymous_text = " • Anonymous" if poll['is_anonymous'] else ""

        embed.set_footer(text=f"Poll ID: {poll_id} • {vote_type_text}{anonymous_text} • Total: {total_votes} votes")

        # Update the message
        await interaction.message.edit(embed=embed)

    except Exception as e:
        print(f"Error updating poll message: {e}")


async def create_poll_embed(poll_id: int, question: str, options: list, vote_type: str, is_anonymous: bool) -> discord.Embed:
    """Create the initial poll embed."""
    options_text = ""
    for idx, option in enumerate(options):
        emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][idx] if idx < 10 else "•"
        options_text += f"{emoji} {option['option_text']}\n"

    embed = discord.Embed(
        title=f"📊 {question}",
        description=f"{options_text}\n*Click a button below to vote!*",
        color=discord.Color.blue()
    )

    vote_type_text = "Single choice" if vote_type == "single" else "Multiple choice"
    anonymous_text = " • Anonymous" if is_anonymous else ""

    embed.set_footer(text=f"Poll ID: {poll_id} • {vote_type_text}{anonymous_text} • 0 votes")

    return embed


async def create_results_embed(poll_id: int) -> discord.Embed:
    """Create a results embed for ended polls."""
    poll = await database.get_poll(poll_id)
    options = await database.get_poll_options(poll_id)
    results = await database.get_poll_results(poll_id)

    total_votes = sum(results.values())

    # Find winner(s)
    max_votes = max(results.values()) if results else 0
    winners = [opt for opt in options if results.get(opt['id'], 0) == max_votes]

    results_text = ""
    for option in options:
        vote_count = results.get(option['id'], 0)
        percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0

        # Create progress bar
        bar_length = 15
        filled = int(bar_length * percentage / 100)
        bar = "█" * filled + "░" * (bar_length - filled)

        # Mark winner
        winner_mark = " 👑" if option in winners and max_votes > 0 else ""

        results_text += f"**{option['option_text']}**{winner_mark}\n"
        results_text += f"{bar} {vote_count} ({percentage:.1f}%)\n\n"

    embed = discord.Embed(
        title=f"📊 Poll Results: {poll['question']}",
        description=results_text if results_text else "No votes were cast",
        color=discord.Color.gold()
    )

    embed.set_footer(text=f"Poll ID: {poll_id} • Poll ended • Total: {total_votes} votes")

    return embed
