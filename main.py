from keep_alive import keep_alive

#keep_alive()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Updater, CommandHandler, MessageHandler,
                          CallbackContext, CallbackQueryHandler, Filters,
                          PicklePersistence)
import random
import time
import requests
from collections import defaultdict
import os
import logging

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)


# Dictionary API function
def get_random_word(difficulty="medium"):
    """Fetches random dictionary words"""
    # Word length ranges by difficulty
    length_ranges = {"easy": (4, 6), "medium": (6, 9), "hard": (8, 12)}
    min_len, max_len = length_ranges[difficulty]
    target_length = random.randint(min_len, max_len)

    # Try multiple API endpoints
    api_endpoints = [
        f"https://random-word-api.herokuapp.com/word?length={target_length}",
        f"https://random-word-api.vercel.app/api?length={target_length}",
    ]

    for endpoint in api_endpoints:
        try:
            response = requests.get(endpoint, timeout=3)
            if response.status_code == 200:
                words = response.json()
                if isinstance(words, list) and words:
                    word = random.choice(words)
                    if word.isalpha() and min_len <= len(word) <= max_len:
                        return word.lower()
        except Exception as e:
            logger.warning(f"Failed to fetch word from {endpoint}: {e}")
            continue

    # Fallback word generation
    vowels = 'aeiou'
    consonants = 'bcdfghjklmnpqrstvwxyz'
    word = ''.join(
        random.choice(consonants if i % 2 == 0 else vowels)
        for i in range(target_length))
    return word


def get_word_meaning(word):
    """Fetches word meaning from Free Dictionary API"""
    try:
        response = requests.get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
            timeout=3)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                meanings = data[0].get("meanings", [])
                if meanings:
                    definitions = meanings[0].get("definitions", [])
                    if definitions:
                        return definitions[0].get("definition",
                                                  "No definition found")
    except Exception as e:
        logger.warning(f"Failed to fetch meaning for {word}: {e}")
    return "No definition available"


# Initialize persistence for saving data
persistence = PicklePersistence(filename='anagram_bot_data')
active_games = {}
hint_progress = defaultdict(dict)  # {chat_id: {user_id: hint_level}}


def start(update: Update, context: CallbackContext):
    """Send welcome message."""
    try:
        user = update.effective_user
        welcome_message = (
            f"🌟 Welcome {user.first_name} to Anagram Challenge! 🌟\n\n"
            "🧠 Test your word skills by unscrambling letters!\n\n"
            "📌 Available Commands:\n"
            "/help - How to play\n"
            "/newgame - Start a new game in groups\n"
            "/newplay - Play solo in private chat\n"
            "/leaderboard - Top players of all time\n"
            "/stats - Your personal statistics\n\n"
            "🏆 Compete with friends and climb the leaderboard!")
        update.message.reply_text(welcome_message)
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        update.message.reply_text("An error occurred. Please try again.")


def help_command(update: Update, context: CallbackContext):
    """Show help instructions."""
    try:
        help_text = (
            "📖 How to Play Anagram Challenge:\n\n"
            "1. Start a game with /newgame (in groups) or /newplay (in private)\n"
            "2. You'll see scrambled letters of a word\n"
            "3. Type the correct word to earn points\n"
            "4. Faster answers earn more points!\n\n"
            "💡 Tips:\n"
            "- Use /hint to get help with the current word\n"
            "- Check /leaderboard to see top players\n"
            "- Your points accumulate across all games!")
        update.message.reply_text(help_text)
    except Exception as e:
        logger.error(f"Error in help command: {e}")
        update.message.reply_text("An error occurred. Please try again.")


def stats(update: Update, context: CallbackContext):
    """Show user's personal statistics."""
    try:
        user_id = update.effective_user.id

        # Get global stats from bot_data
        total_points = context.bot_data.get('global_stats',
                                            {}).get(user_id,
                                                    {}).get('points', 0)
        games_played = context.bot_data.get('global_stats',
                                            {}).get(user_id,
                                                    {}).get('games_played', 0)

        # Get current game stats if available
        current_game_points = 0
        for chat_id, game in active_games.items():
            if user_id in game.get('players', {}):
                current_game_points += game['players'][user_id]

        stats_text = (f"📊 Your Statistics 📊\n\n"
                      f"🏆 Total Points: {total_points + current_game_points}\n"
                      f"🎮 Games Played: {games_played}\n"
                      f"🔥 Current Game Points: {current_game_points}\n\n"
                      "Keep playing to climb the leaderboard! 🚀")

        update.message.reply_text(stats_text)
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        update.message.reply_text(
            "An error occurred while fetching your stats.")


def update_global_stats(user_id: int, points: int, context: CallbackContext):
    """Update the global statistics for a user."""
    try:
        if 'global_stats' not in context.bot_data:
            context.bot_data['global_stats'] = {}

        user_stats = context.bot_data['global_stats'].setdefault(
            user_id, {
                'points': 0,
                'games_played': 0,
                'name': context.bot.get_chat(user_id).first_name
            })

        user_stats['points'] += points
        user_stats['games_played'] += 1

        # Explicitly save the persistence
        if hasattr(context.bot, 'persistence'):
            context.bot.persistence.flush()

    except Exception as e:
        logger.error(f"Error updating global stats: {e}")


def leaderboard(update: Update, context: CallbackContext):
    """Show all-time leaderboard."""
    try:
        if 'global_stats' not in context.bot_data or not context.bot_data[
                'global_stats']:
            update.message.reply_text(
                "No leaderboard data yet. Be the first to play!")
            return

        # Get top 10 players
        all_players = context.bot_data['global_stats'].items()
        sorted_players = sorted(all_players,
                                key=lambda x: x[1]['points'],
                                reverse=True)[:10]

        leaderboard_text = "🏆 All-Time Leaderboard 🏆\n\n"
        for i, (user_id, stats) in enumerate(sorted_players, 1):
            leaderboard_text += f"{i}. {stats['name']}: {stats['points']} points\n"

        # Add current user's position if not in top 10
        current_user_id = update.effective_user.id
        if current_user_id in context.bot_data['global_stats']:
            user_points = context.bot_data['global_stats'][current_user_id][
                'points']
            user_position = next((i + 1
                                  for i, (uid, _) in enumerate(sorted_players)
                                  if uid == current_user_id),
                                 len(sorted_players) + 1)
            if user_position > 10:
                leaderboard_text += f"\nYour position: {user_position} with {user_points} points"

        update.message.reply_text(leaderboard_text)
    except Exception as e:
        logger.error(f"Error in leaderboard command: {e}")
        update.message.reply_text(
            "An error occurred while fetching the leaderboard.")


def newgame(update: Update, context: CallbackContext):
    """Start a new game setup (choose difficulty & rounds) in groups."""
    try:
        if update.effective_chat.type == 'private':
            update.message.reply_text(
                "Use /newplay for solo games in private chat!")
            return

        keyboard = [
            [InlineKeyboardButton("Easy", callback_data="easy")],
            [InlineKeyboardButton("Medium", callback_data="medium")],
            [InlineKeyboardButton("Hard", callback_data="hard")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Choose difficulty:",
                                  reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in newgame command: {e}")
        update.message.reply_text("An error occurred. Please try again.")


def newplay(update: Update, context: CallbackContext):
    """Start a new solo game in private chat."""
    try:
        if update.effective_chat.type != 'private':
            update.message.reply_text(
                "This is for private chat only! Use /newgame in groups.")
            return

        keyboard = [
            [InlineKeyboardButton("Easy", callback_data="easy_solo")],
            [InlineKeyboardButton("Medium", callback_data="medium_solo")],
            [InlineKeyboardButton("Hard", callback_data="hard_solo")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Choose difficulty for your solo game:",
                                  reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in newplay command: {e}")
        update.message.reply_text("An error occurred. Please try again.")


def choose_rounds(update: Update, context: CallbackContext):
    """After selecting difficulty, choose number of rounds."""
    try:
        query = update.callback_query
        query.answer()

        difficulty = query.data.replace('_solo', '')
        context.user_data["difficulty"] = difficulty
        context.user_data["is_solo"] = '_solo' in query.data

        keyboard = [
            [InlineKeyboardButton("10 Rounds", callback_data="10")],
            [InlineKeyboardButton("30 Rounds", callback_data="30")],
            [InlineKeyboardButton("50 Rounds", callback_data="50")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(
            f"Difficulty: {difficulty.capitalize()}\n\n"
            "Now select the number of rounds:",
            reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in choose_rounds: {e}")
        if update.callback_query:
            update.callback_query.message.reply_text(
                "An error occurred. Please try again.")


def start_game(update: Update, context: CallbackContext):
    """Initialize the game with selected settings."""
    try:
        query = update.callback_query
        query.answer()

        chat_id = query.message.chat_id
        user_id = query.from_user.id

        if "difficulty" not in context.user_data:
            query.edit_message_text(
                "Please start a new game and select difficulty first! Use /newgame or /newplay"
            )
            return

        rounds = int(query.data)
        difficulty = context.user_data["difficulty"]
        is_solo = context.user_data.get("is_solo", False)

        # Initialize game
        active_games[chat_id] = {
            "players": {},
            "round": 1,
            "max_rounds": rounds,
            "difficulty": difficulty,
            "is_solo": is_solo,
            "solo_player": user_id if is_solo else None,
            "solved_by": {},  # Track who solved each round
            "words_used": []  # Track all words used
        }

        # Reset hint progress for this chat
        if chat_id in hint_progress:
            del hint_progress[chat_id]

        # Start first round
        next_round(chat_id, context.bot)
    except Exception as e:
        logger.error(f"Error in start_game: {e}")
        if update.callback_query:
            update.callback_query.message.reply_text(
                "An error occurred. Please try again.")


def next_round(chat_id, bot):
    """Load a new word for the next round."""
    try:
        game = active_games[chat_id]

        # Get fresh random word from API
        word = get_random_word(game["difficulty"])
        scrambled = ''.join(random.sample(word, len(word)))

        game["current_word"] = word
        game["scrambled"] = scrambled
        game["start_time"] = time.time()
        game["words_used"].append(word)  # Track the word used

        # Reset hints for new round
        if chat_id in hint_progress:
            hint_progress[chat_id] = {}

        round_text = (f"🔤 Round {game['round']}/{game['max_rounds']}\n"
                      f"Unscramble this word: {scrambled}\n\n")

        if game.get('is_solo'):
            round_text += "⏳ Faster answers earn more points!\n💡 Use /hint to get help"
        else:
            round_text += "⏳ Fastest correct answer wins points!\n💡 Use /hint to get help"

        bot.send_message(chat_id, round_text)
    except Exception as e:
        logger.error(f"Error in next_round: {e}")
        bot.send_message(chat_id,
                         "An error occurred. Please start a new game.")


def hint(update: Update, context: CallbackContext):
    """Provide progressive hints about the current word."""
    try:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if chat_id not in active_games:
            update.message.reply_text(
                "No active game! Start a new game with /newgame or /newplay")
            return

        word = active_games[chat_id]["current_word"]

        # Initialize or update hint progress
        if chat_id not in hint_progress:
            hint_progress[chat_id] = {}
        if user_id not in hint_progress[chat_id]:
            hint_progress[chat_id][user_id] = 0

        hint_level = hint_progress[chat_id][user_id]

        # Calculate how many letters to reveal (progressive)
        reveal_count = min(hint_level + 1, len(word))
        revealed = word[:reveal_count]
        hidden = "_" * (len(word) - reveal_count)

        hint_progress[chat_id][user_id] += 1

        update.message.reply_text(
            f"💡 Hint ({hint_level+1}/{len(word)}):\n"
            f"The word starts with: {revealed}{hidden}\n\n"
            f"Original scrambled: {active_games[chat_id]['scrambled']}")
    except Exception as e:
        logger.error(f"Error in hint command: {e}")
        update.message.reply_text("An error occurred. Please try again.")


def check_answer(update: Update, context: CallbackContext):
    """Check if the player's guess is correct."""
    try:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user_guess = update.message.text.lower()

        if chat_id not in active_games:
            return  # No active game

        game = active_games[chat_id]
        correct_word = game["current_word"]

        if user_guess == correct_word:
            time_taken = time.time() - game["start_time"]
            score = max(10 - int(time_taken), 1)  # Faster = More points

            # Update player score
            if user_id not in game["players"]:
                game["players"][user_id] = 0
            game["players"][user_id] += score

            # Track who solved this round
            game["solved_by"][game["round"]] = user_id

            # Get word meaning
            meaning = get_word_meaning(correct_word)

            # Announce winner
            user_name = update.effective_user.first_name

            if game.get('is_solo'):
                message = (
                    f"✅ Correct! ✅\n"
                    f"🎯 Word: {correct_word}\n"
                    f"⏱️ Time: {time_taken:.1f}s (+{score} points)\n"
                    f"💰 Total this game: {game['players'][user_id]} points\n\n"
                    "Next word coming up...")
            else:
                message = (f"🏆 {user_name} got it!\n"
                           f"✅ Word: {correct_word}\n"
                           f"⏱️ Time: {time_taken:.1f}s (+{score} points)\n\n"
                           "Next round starting soon...")

            update.message.reply_text(message)

            # Send definition separately after a short delay
            def send_meaning():
                try:
                    time.sleep(0.5)
                    context.bot.send_message(
                        chat_id, f"📖 Definition of {correct_word}: {meaning}")
                except Exception as e:
                    logger.error(f"Error sending meaning: {e}")

            import threading
            threading.Thread(target=send_meaning).start()

            # Move to next round or end game
            game["round"] += 1
            if game["round"] > game["max_rounds"]:
                end_game(chat_id, context.bot)
            else:
                next_round(chat_id, context.bot)
    except Exception as e:
        logger.error(f"Error in check_answer: {e}")
        update.message.reply_text("An error occurred. Please try again.")


def end_game(chat_id, bot):
    """End the game and show final scores."""
    try:
        game = active_games[chat_id]
        players = game["players"]

        if not players:
            bot.send_message(chat_id, "Game ended with no winners.")
            del active_games[chat_id]
            return

        # Sort players by score
        sorted_players = sorted(players.items(),
                                key=lambda x: x[1],
                                reverse=True)

        if game.get('is_solo'):
            # Solo game ending
            user_id = game['solo_player']
            score = players.get(user_id, 0)
            user_name = bot.get_chat(user_id).first_name

            # Update global stats
            if hasattr(bot, 'bot_data'):
                update_global_stats(user_id, score, bot)

            message = (f"🎉 Game Over! 🎉\n\n"
                       f"👤 Player: {user_name}\n"
                       f"🏆 Total Score: {score} points\n\n"
                       f"Check /stats to see your updated total points!")
            bot.send_message(chat_id, message)
        else:
            # Multiplayer game ending - enhanced display
            leaderboard_text = "🏆 *Final Scores* 🏆\n\n"

            # Player rankings
            for i, (user_id, score) in enumerate(sorted_players, 1):
                user_name = bot.get_chat(user_id).first_name
                leaderboard_text += f"{i}. {user_name}: {score} points\n"

                # Update global stats
                if hasattr(bot, 'bot_data'):
                    update_global_stats(user_id, score, bot)

            # Additional stats
            leaderboard_text += "\n🔹 *Game Statistics:*\n"

            # Count of words solved by each player
            solved_counts = defaultdict(int)
            for round_num, solver_id in game['solved_by'].items():
                solved_counts[solver_id] += 1

            for solver_id, count in sorted(solved_counts.items(),
                                           key=lambda x: x[1],
                                           reverse=True):
                if count > 0:
                    leaderboard_text += f"🔸 {bot.get_chat(solver_id).first_name} solved {count} words\n"

            # Longest word
            if game['words_used']:
                longest_word = max(game['words_used'], key=len)
                leaderboard_text += f"\n📏 Longest word: {longest_word} ({len(longest_word)} letters)"

            bot.send_message(chat_id, leaderboard_text, parse_mode='Markdown')

        del active_games[chat_id]
    except Exception as e:
        logger.error(f"Error in end_game: {e}")
        bot.send_message(chat_id, "An error occurred ending the game.")


def error_handler(update: Update, context: CallbackContext):
    """Handle errors gracefully."""
    try:
        raise context.error
    except Exception as e:
        logger.error(f"Error: {e}")
        if update and update.effective_message:
            update.effective_message.reply_text(
                "An error occurred. Please try again later.")


def main():
    """Run the bot."""
    try:
        # Get token from environment variable or use default
        TOKEN = os.getenv('TELEGRAM_TOKEN',
                          '8119846665:AAEntRdHrgcAdgo-89GbgcOD8ZlG8mNLl-E')

        # Set up persistence to save data between restarts
        persistence = PicklePersistence(filename='anagram_bot_data')
        updater = Updater(TOKEN, use_context=True, persistence=persistence)
        dispatcher = updater.dispatcher

        # Add error handler
        dispatcher.add_error_handler(error_handler)

        # Command handlers
        dispatcher.add_handler(CommandHandler("start", start))
        dispatcher.add_handler(CommandHandler("help", help_command))
        dispatcher.add_handler(CommandHandler("newgame", newgame))
        dispatcher.add_handler(CommandHandler("newplay", newplay))
        dispatcher.add_handler(CommandHandler("leaderboard", leaderboard))
        dispatcher.add_handler(CommandHandler("stats", stats))
        dispatcher.add_handler(CommandHandler("hint", hint))

        # Callback handlers
        dispatcher.add_handler(
            CallbackQueryHandler(
                choose_rounds,
                pattern="^(easy|medium|hard|easy_solo|medium_solo|hard_solo)$")
        )
        dispatcher.add_handler(
            CallbackQueryHandler(start_game, pattern="^(10|30|50)$"))

        # Message handler
        dispatcher.add_handler(
            MessageHandler(Filters.text & ~Filters.command, check_answer))

        # Start the bot
        logger.info("Bot is running...")
        keep_alive()
        updater.start_polling()
        updater.idle()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")


if __name__ == "__main__":
    main()
