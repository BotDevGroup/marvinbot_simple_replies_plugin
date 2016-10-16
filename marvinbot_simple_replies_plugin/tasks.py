from marvinbot.utils import localized_date, get_message, trim_accents
from marvinbot.handlers import CommonFilters, CommandHandler, MessageHandler
from marvinbot_simple_replies_plugin.models import SimpleReply
import logging
import threading
import re
import json

log = logging.getLogger(__name__)
adapter = None
replies = []
lock = threading.Lock()


def get_message_type(message):
    result = None
    if len(message.reply_to_message.photo) > 0:
        result = 'photo'
    elif message.reply_to_message.sticker:
        result = 'sticker'
    elif message.reply_to_message.voice:
        result = 'voice'
    elif message.reply_to_message.document:
        if message.reply_to_message.document.mime_type == 'video/mp4':
            result = 'gif'
        else:
            result = 'file'
    elif message.reply_to_message.contact:
        result = 'contact'
    elif message.reply_to_message.location:
        result = 'location'
    elif message.reply_to_message.text:
        result = 'text'
    return result


def fetch_replies():
    global replies
    with lock:
        replies = SimpleReply.all()
        log.info("Fetched {} replies.".format(len(replies)))

        for reply in replies:
            reply.pattern = re.compile(reply.pattern, flags=re.IGNORECASE) if reply.pattern_type in ['regexp'] else reply.pattern


def add_reply(**kwargs):
    try:
        reply = SimpleReply(**kwargs)
        reply.save()
        return True
    except:
        return False


def remove_reply(pattern):
    reply = SimpleReply.by_pattern(pattern)
    if reply and reply.date_deleted is None:
        # TODO implement soft delete
        # reply.date_deleted = localized_date()
        # reply.save()
        reply.delete()
        return True
    return False


def on_reply_command(update, *args, **kwargs):
    log.info('Reply command caught')

    remove = kwargs.get('remove')

    pattern = " ".join(kwargs.get('pattern'))
    pattern = trim_accents(pattern)
    pattern_type = kwargs.get('type')
    response = None
    mime_type = None
    file_name = None
    caption = None
    parse_mode = None

    if remove:
        if remove_reply(pattern):
            adapter.bot.sendMessage(
                chat_id=update.message.chat_id,
                text="🚮 1 reply removed.")
            fetch_replies()
        else:
            adapter.bot.sendMessage(
                chat_id=update.message.chat_id,
                text="❌ No such reply.")
        return

    if not update.message.reply_to_message:
        adapter.bot.sendMessage(
            chat_id=update.message.chat_id,
            text="❌ When adding new replies, use this command while replying.")
        return

    response_type = get_message_type(update.message)

    if response_type is None:
        adapter.bot.sendMessage(
            chat_id=update.message.chat_id,
            text="❌ Media type is not supported")
        return

    if response_type == 'sticker':
        response = update.message.reply_to_message.sticker.file_id
    elif response_type == 'voice':
        response = update.message.reply_to_message.voice.file_id
    elif response_type in ('gif', 'file'):
        mime_type = update.message.reply_to_message.document.mime_type
        response = update.message.reply_to_message.document.file_id
        file_name = update.message.reply_to_message.document.file_name
    elif response_type == 'photo':
        mime_type = 'image/jpeg'
        response = update.message.reply_to_message.photo[-1].file_id
        file_name = "{}.jpg".format(update.message.reply_to_message.photo[-1].file_id)
        caption = update.message.reply_to_message.caption
    elif response_type == 'location':
        response = update.message.reply_to_message.location.to_json()
    elif response_type == 'contact':
        response = update.message.reply_to_message.contact.to_json()
    else:
        parse_mode = kwargs.get('mode')
        if parse_mode not in ('HTML', 'Markdown'):
            parse_mode = None
        response = update.message.reply_to_message.text

    user_id = update.message.from_user.id
    username = update.message.from_user.username
    date_added = localized_date()
    date_modified = localized_date()

    if len(pattern) == 0:
        adapter.bot.sendMessage(
            chat_id=update.message.chat_id, text="❌ Reply pattern is too short.")
        return

    reply = SimpleReply.by_pattern(pattern)
    if not reply:
        result = add_reply(user_id=user_id, username=username, pattern=pattern,
                           pattern_type=pattern_type, response=response,
                           response_type=response_type, caption=caption,
                           parse_mode=parse_mode, file_name=file_name,
                           mime_type=mime_type, date_added=date_added,
                           date_modified=date_modified)
        if result:
            adapter.bot.sendMessage(
                chat_id=update.message.chat_id, text="✅ Reply added.")
            fetch_replies()
        else:
            adapter.bot.sendMessage(chat_id=update.message.chat_id,
                                    text="❌ Unable to add reply.")
    else:
        adapter.bot.sendMessage(chat_id=update.message.chat_id,
                                text="❌ This pattern already exists.")


def handle_text_response(update, reply):
    adapter.bot.sendMessage(chat_id=update.message.chat_id,
                            text=reply.response)


def handle_photo_response(update, reply):
    adapter.bot.sendPhoto(chat_id=update.message.chat_id, photo=reply.response, caption=reply.caption)


def handle_sticker_response(update, reply):
    adapter.bot.sendSticker(chat_id=update.message.chat_id, sticker=reply.response)


def handle_gif_response(update, reply):
    adapter.bot.sendDocument(chat_id=update.message.chat_id, document=reply.response)


def handle_audio_response(update, reply):
    adapter.bot.sendAudio(chat_id=update.message.chat_id, audio=reply.response)


def handle_video_response(update, reply):
    adapter.bot.sendVideo(chat_id=update.message.chat_id, video=reply.response)


def handle_file_response(update, reply):
    adapter.bot.sendDocument(chat_id=update.message.chat_id, document=reply.response)


def handle_voice_response(update, reply):
    adapter.bot.sendVoice(chat_id=update.message.chat_id, voice=reply.response)


def handle_contact_response(update, reply):
    data = json.loads(reply.response)
    adapter.bot.sendContact(chat_id=update.message.chat_id, **data)


def handle_location_response(update, reply):
    data = json.loads(reply.response)
    adapter.bot.sendLocation(chat_id=update.message.chat_id, **data)


def handle_unknown_response(update, reply):
    adapter.bot.sendMessage(chat_id=update.message.chat_id,
                            text="❌ Invalid response type '{response_type}' for '{pattern}'".format(
                                pattern=reply.pattern, response_type=reply.response_type))


response_handlers = {
    "text": handle_text_response,
    "photo": handle_photo_response,
    "sticker": handle_sticker_response,
    "gif": handle_gif_response,
    "audio": handle_audio_response,
    "video": handle_video_response,
    "voice": handle_voice_response,
    "file": handle_file_response,
    "contact": handle_contact_response,
    "location": handle_location_response,
}


def find_match(text, callback):
    global replies
    with lock:
        for reply in replies:
            matches = (reply.pattern_type == 'exact' and reply.pattern == text) \
                or (reply.pattern_type == 'regexp' and reply.pattern.match(text)) \
                or (reply.pattern_type == 'begins_with' and text.startswith(reply.pattern)) \
                or (reply.pattern_type == 'ends_with' and text.endswith(reply.pattern)) \
                or (reply.pattern_type == 'contains' and reply.pattern in text)
            if matches:
                callback(text, reply)


def on_text(update):
    global response_handlers
    text = trim_accents(get_message(update).text)
    log.info('Text message caught')

    if len(text) == 0:
        log.info('Ignoring text message. Message length is zero')
        return

    def on_match(text, reply):
        response_handler = response_handlers[reply.response_type] if reply.response_type in response_handlers else handle_unknown_response
        response_handler(update, reply)

    find_match(text, on_match)


def setup(new_adapter):
    global adapter, replies
    adapter = new_adapter

    fetch_replies()

    adapter.add_handler(CommandHandler('reply', on_reply_command, command_description='Allows the user to add or remove replies.')
                        .add_argument('--remove', help='Remove reply', action='store_true')
                        .add_argument('--type', help='Pattern type', default='exact')
                        .add_argument('--mode', help='Parse mode (e.g. Markdown)', default='Markdown')
                        .add_argument('pattern', nargs='*', help='Words or pattern that trigger this reply'))
    adapter.add_handler(MessageHandler([CommonFilters.text], on_text), priority=90)
