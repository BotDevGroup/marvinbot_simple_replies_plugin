from marvinbot.utils import get_message
from marvinbot.handlers import Filters, CommandHandler, MessageHandler
from celery.utils.log import get_task_logger
from marvinbot_simple_replies_plugin.models import SimpleReply
from celery import task
from datetime import datetime
import re

log = get_task_logger(__name__)
adapter = None
replies = []


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
    elif message.reply_to_message.text:
        result = 'text'
    return result


def remove_reply(pattern):
    reply = SimpleReply.by_pattern(pattern)
    if reply and reply.date_deleted is None:
        reply.date_deleted = datetime.now()
        reply.save()
        return True
    return False


@task
def on_reply_command(update, *args, **kwargs):
    log.info('Reply command caught')

    remove = kwargs.get('remove')

    pattern = " ".join(kwargs.get('pattern'))
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

    if response_type in ('sticker', 'voice', 'gif', 'file'):
        mime_type = update.message.reply_to_message.document.mime_type
        response = update.message.reply_to_message.document.file_id
        file_name = update.message.reply_to_message.document.file_name
    elif response_type == 'photo':
        mime_type = 'image/jpeg'
        response = update.message.reply_to_message.photo[-1].file_id
        file_name = "{}.jpg".format(update.message.reply_to_message.photo[-1].file_id)
        caption = update.message.caption
    else:
        parse_mode = kwargs.get('mode')
        if parse_mode not in ('HTML', 'Markdown'):
            parse_mode = None
        response = update.message.reply_to_message.text

    user_id = update.message.from_user.id
    username = update.message.from_user.username
    date_added = datetime.now()
    date_modified = datetime.now()

    if not len(pattern) > 0:
        adapter.bot.sendMessage(
            chat_id=update.message.chat_id, text="❌ Reply pattern is too short.")
        return

    reply = SimpleReply.by_pattern(pattern)
    if not reply:
        reply = SimpleReply(user_id=user_id, username=username,
                            pattern=pattern, pattern_type=pattern_type,
                            response=response, response_type=response_type,
                            caption=caption, parse_mode=parse_mode,
                            file_name=file_name, mime_type=mime_type,
                            date_added=date_added, date_modified=date_modified)
        reply.save()
        log.info(reply)
        adapter.bot.sendMessage(
            chat_id=update.message.chat_id, text="✅ Reply added.")
    else:
        adapter.bot.sendMessage(chat_id=update.message.chat_id,
                                text="❌ This pattern already exists.")


def setup(new_adapter):
    global adapter, replies
    adapter = new_adapter

    replies = SimpleReply.all()
    log.info("Fetched {} replies.".format(len(replies)))

    for reply in replies:
        reply.pattern = re.compile(reply.pattern, flags=re.IGNORECASE) if reply.pattern_type in ['regexp'] else reply.pattern

    adapter.add_handler(CommandHandler('reply', on_reply_command, command_description='Allows the user to add or remove replies.')
                        .add_argument('--remove', help='Remove reply', action='store_true')
                        .add_argument('--type', help='Pattern type', default='exact')
                        .add_argument('--mode', help='Parse mode (e.g. Markdown)', default='Markdown')
                        .add_argument('pattern', nargs='*', help='Words or pattern that trigger this reply'))
