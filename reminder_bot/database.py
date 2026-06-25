import aiosqlite
import os
from datetime import datetime
from typing import Optional, List, Dict

DATABASE_PATH = os.getenv('DATABASE_PATH', './data/reminders.db')

async def init_db():
    """Initialize the database and create tables if they don't exist."""
    # Create data directory if it doesn't exist
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER,
                channel_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                reminder_time TEXT NOT NULL,
                timezone TEXT DEFAULT 'UTC',
                recurring_interval TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                timezone TEXT DEFAULT 'UTC'
            )
        ''')

        # Voting tables
        await db.execute('''
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                question TEXT NOT NULL,
                vote_type TEXT NOT NULL,
                end_time TEXT,
                is_anonymous INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS poll_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                option_index INTEGER NOT NULL,
                FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                voted_at TEXT NOT NULL,
                FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE,
                FOREIGN KEY (option_id) REFERENCES poll_options(id) ON DELETE CASCADE
            )
        ''')

        await db.commit()

async def add_reminder(user_id: int, guild_id: Optional[int], channel_id: int,
                       message: str, reminder_time: datetime, timezone: str = 'UTC',
                       recurring_interval: Optional[str] = None) -> int:
    """Add a new reminder to the database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO reminders (user_id, guild_id, channel_id, message, reminder_time,
                                   timezone, recurring_interval, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, guild_id, channel_id, message, reminder_time.isoformat(),
              timezone, recurring_interval, datetime.utcnow().isoformat()))

        await db.commit()
        return cursor.lastrowid

async def get_due_reminders() -> List[Dict]:
    """Get all reminders that are due."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM reminders
            WHERE active = 1 AND datetime(reminder_time) <= datetime('now')
            ORDER BY reminder_time ASC
        ''') as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_user_reminders(user_id: int, active_only: bool = True) -> List[Dict]:
    """Get all reminders for a specific user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = 'SELECT * FROM reminders WHERE user_id = ?'
        if active_only:
            query += ' AND active = 1'
        query += ' ORDER BY reminder_time ASC'

        async with db.execute(query, (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def delete_reminder(reminder_id: int, user_id: int) -> bool:
    """Delete a reminder (only if it belongs to the user)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('''
            DELETE FROM reminders
            WHERE id = ? AND user_id = ?
        ''', (reminder_id, user_id))

        await db.commit()
        return cursor.rowcount > 0

async def deactivate_reminder(reminder_id: int):
    """Mark a reminder as inactive."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            UPDATE reminders
            SET active = 0
            WHERE id = ?
        ''', (reminder_id,))

        await db.commit()

async def update_reminder_time(reminder_id: int, new_time: datetime):
    """Update the reminder time (used for recurring reminders)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            UPDATE reminders
            SET reminder_time = ?
            WHERE id = ?
        ''', (new_time.isoformat(), reminder_id))

        await db.commit()

async def activate_reminder(reminder_id: int):
    """Mark a reminder as active (used for snooze feature)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            UPDATE reminders
            SET active = 1
            WHERE id = ?
        ''', (reminder_id,))

        await db.commit()

async def set_user_timezone(user_id: int, timezone: str):
    """Set or update user's timezone preference."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            INSERT INTO user_settings (user_id, timezone)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET timezone = ?
        ''', (user_id, timezone, timezone))

        await db.commit()

async def get_user_timezone(user_id: int) -> str:
    """Get user's timezone preference."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute('''
            SELECT timezone FROM user_settings WHERE user_id = ?
        ''', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 'UTC'


# Voting/Poll functions

async def create_poll(creator_id: int, guild_id: int, channel_id: int, question: str,
                      options: list, vote_type: str, end_time: Optional[str], is_anonymous: bool) -> int:
    """Create a new poll."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO polls (creator_id, guild_id, channel_id, question, vote_type,
                             end_time, is_anonymous, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (creator_id, guild_id, channel_id, question, vote_type,
              end_time, 1 if is_anonymous else 0, datetime.utcnow().isoformat()))

        poll_id = cursor.lastrowid

        # Add options
        for idx, option in enumerate(options):
            await db.execute('''
                INSERT INTO poll_options (poll_id, option_text, option_index)
                VALUES (?, ?, ?)
            ''', (poll_id, option, idx))

        await db.commit()
        return poll_id


async def update_poll_message_id(poll_id: int, message_id: int):
    """Update the message ID for a poll."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            UPDATE polls SET message_id = ? WHERE id = ?
        ''', (message_id, poll_id))
        await db.commit()


async def get_poll(poll_id: int) -> Optional[Dict]:
    """Get poll by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM polls WHERE id = ?
        ''', (poll_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_poll_options(poll_id: int) -> List[Dict]:
    """Get all options for a poll."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM poll_options WHERE poll_id = ? ORDER BY option_index
        ''', (poll_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def add_vote(poll_id: int, user_id: int, option_id: int):
    """Add a vote to a poll."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            INSERT INTO poll_votes (poll_id, user_id, option_id, voted_at)
            VALUES (?, ?, ?, ?)
        ''', (poll_id, user_id, option_id, datetime.utcnow().isoformat()))
        await db.commit()


async def remove_user_votes(poll_id: int, user_id: int):
    """Remove all votes from a user for a specific poll."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            DELETE FROM poll_votes WHERE poll_id = ? AND user_id = ?
        ''', (poll_id, user_id))
        await db.commit()


async def get_user_votes(poll_id: int, user_id: int) -> List[int]:
    """Get option IDs that a user has voted for."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute('''
            SELECT option_id FROM poll_votes WHERE poll_id = ? AND user_id = ?
        ''', (poll_id, user_id)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_poll_results(poll_id: int) -> Dict:
    """Get vote counts for each option."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute('''
            SELECT option_id, COUNT(*) as count
            FROM poll_votes
            WHERE poll_id = ?
            GROUP BY option_id
        ''', (poll_id,)) as cursor:
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}


async def get_poll_voters(poll_id: int, option_id: int) -> List[int]:
    """Get list of user IDs who voted for a specific option."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute('''
            SELECT user_id FROM poll_votes WHERE poll_id = ? AND option_id = ?
        ''', (poll_id, option_id)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def end_poll(poll_id: int):
    """Mark a poll as inactive."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            UPDATE polls SET is_active = 0 WHERE id = ?
        ''', (poll_id,))
        await db.commit()


async def get_active_polls_by_user(user_id: int) -> List[Dict]:
    """Get all active polls created by a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM polls WHERE creator_id = ? AND is_active = 1
        ''', (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_active_polls_by_guild(guild_id: int) -> List[Dict]:
    """Get all active polls in a guild."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT * FROM polls WHERE guild_id = ? AND is_active = 1
            ORDER BY created_at DESC
            LIMIT 25
        ''', (guild_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def cleanup_old_ended_polls(days: int = 30):
    """Delete ended polls older than specified days."""
    from datetime import datetime, timedelta
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Delete old poll votes first (foreign key)
        await db.execute('''
            DELETE FROM poll_votes WHERE poll_id IN (
                SELECT id FROM polls
                WHERE is_active = 0 AND created_at < ?
            )
        ''', (cutoff_date,))

        # Delete old poll options
        await db.execute('''
            DELETE FROM poll_options WHERE poll_id IN (
                SELECT id FROM polls
                WHERE is_active = 0 AND created_at < ?
            )
        ''', (cutoff_date,))

        # Delete old polls
        cursor = await db.execute('''
            DELETE FROM polls
            WHERE is_active = 0 AND created_at < ?
        ''', (cutoff_date,))

        deleted_count = cursor.rowcount
        await db.commit()
        return deleted_count


async def get_poll_count_by_guild(guild_id: int, active_only: bool = True) -> int:
    """Get total count of polls in a guild."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        query = '''
            SELECT COUNT(*) FROM polls WHERE guild_id = ?
        '''
        if active_only:
            query += ' AND is_active = 1'

        async with db.execute(query, (guild_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


