from marvinbot.utils import localized_date, get_message, trim_accents
from marvinbot.handlers import CommonFilters, CommandHandler, MessageHandler
from marvinbot_simple_replies_plugin.models import SimpleReply, PATTERN_TYPES
from marvinbot.signals import plugin_reload
from marvinbot.plugins import Plugin
from marvinbot.models import User

import logging
import re
import threading
import json

log = logging.getLogger(__name__)


class SimpleRepliesPlugin(Plugin):
    def __init__(self):
        super(SimpleRepliesPlugin, self).__init__('simple_replies')
        self.replies = []
        self.lock = threading.Lock()
        self.bot = None

    def get_default_config(self):
        return {
            'short_name': self.name,
            'enabled': True,
        }

    def configure(self, config):
        log.info("Initializing Simple Replies Plugin")
        self.fetch_replies()

    def setup_handlers(self, adapter):
        self.bot = adapter.bot
        pattern_types = ', '.join([ x[0] for x in PATTERN_TYPES])
        self.add_handler(CommandHandler('reply', self.on_reply_command, command_description='Allows the user to add or remove replies.')
                         .add_argument('--remove', help='Removes a reply.', action='store_true')
                         .add_argument('--new-pattern', help='New words or pattern.')
                         .add_argument('--type', help='Pattern type (e.g. {}).'.format(pattern_types), default='exact')
                         .add_argument('--mode', help='Parse mode (e.g. Markdown, HTML).', default='Markdown')
                         .add_argument('pattern', nargs='*', help='Words or pattern that trigger this reply.'))
        self.add_handler(MessageHandler([CommonFilters.text], self.on_text), priority=90)

    @plugin_reload.connect
    def reload(self, sender, update):
        log.info("Reloading plugin: {}".format(str(sender)))
        self.fetch_replies()
        if update:
            update.message.reply_text('Reloaded')

    def fetch_replies(self):
        with self.lock:
            self.replies = SimpleReply.all()
            if self.replies is None:
                return False
            log.info("Fetched {} replies.".format(len(self.replies)))

            for reply in self.replies:
                reply.pattern = re.compile(reply.pattern, flags=re.IGNORECASE) if reply.pattern_type in ['regexp'] else reply.pattern

    @classmethod
    def fetch_reply(cls, pattern):
        try:
            return SimpleReply.by_pattern(pattern)
        except:
            return None

    @classmethod
    def add_reply(cls, **kwargs):
        try:
            reply = SimpleReply(**kwargs)
            reply.save()
            return True
        except:
            return False

    @classmethod
    def remove_reply(cls, pattern):
        reply = SimpleRepliesPlugin.fetch_reply(pattern)
        if reply and reply.date_deleted is None:
            reply.date_deleted = localized_date()
            reply.save()
            return True
        return False

    @classmethod
    def get_message_type(cls, message):
        result = None
        if message.photo:
            result = 'photo'
        elif message.sticker:
            result = 'sticker'
        elif message.voice:
            result = 'voice'
        elif message.audio:
            result = 'audio'
        elif message.document:
            if message.document.mime_type == 'video/mp4':
                result = 'gif'
            else:
                result = 'file'
        elif message.contact:
            result = 'contact'
        elif message.location:
            result = 'location'
        elif message.text:
            result = 'text'
        return result

    def find_match(self, text, callback):
        with self.lock:
            for reply in self.replies:
                matches = (reply.pattern_type == 'exact' and reply.pattern == text.lower()) \
                    or (reply.pattern_type == 'regexp' and reply.pattern.match(text)) \
                    or (reply.pattern_type == 'begins_with' and text.startswith(reply.pattern)) \
                    or (reply.pattern_type == 'ends_with' and text.endswith(reply.pattern)) \
                    or (reply.pattern_type == 'contains' and reply.pattern in text)
                if matches:
                    callback(text, reply)

    def on_reply_command(self, update, *args, **kwargs):
        log.info('Reply command caught')
        message = get_message(update)

        if not User.is_user_admin(message.from_user):
            self.bot.sendMessage(chat_id=message.chat_id,
                                 text="❌ You are not allowed to do that.")
            return

        remove = kwargs.get('remove')
        new_pattern = kwargs.get('new_pattern')

        pattern = " ".join(kwargs.get('pattern'))
        pattern = trim_accents(pattern).lower()
        pattern_type = kwargs.get('type')

        mime_type = None
        file_name = None
        caption = None
        parse_mode = None

        if remove:
            if SimpleRepliesPlugin.remove_reply(pattern):
                self.bot.sendMessage(chat_id=message.chat_id, text="🚮 1 reply removed.")
                self.fetch_replies()
            else:
                self.bot.sendMessage(
                    chat_id=message.chat_id,
                    text="❌ No such reply.")
            return

        if new_pattern:
            reply = SimpleRepliesPlugin.fetch_reply(pattern)
            if reply is None:
                self.bot.sendMessage(chat_id=message.chat_id, text="❌ No such reply..")
            else:
                new_pattern = trim_accents(str(new_pattern).strip()).lower()
                reply.pattern = new_pattern
                pattern_types = set([ x[0] for x in PATTERN_TYPES ])
                if pattern_type in pattern_types:
                    reply.pattern_type = pattern_type

                reply.save()
                self.fetch_replies()
                self.bot.sendMessage(chat_id=message.chat_id, text="✅ Reply updated.")
            return

        if not message.reply_to_message:
            self.bot.sendMessage(
                chat_id=message.chat_id,
                text="❌ When adding new replies, use this command while replying.")
            return

        response_type = SimpleRepliesPlugin.get_message_type(message.reply_to_message)

        if response_type is None:
            self.bot.sendMessage(
                chat_id=message.chat_id,
                text="❌ Media type is not supported.")
            return

        if response_type == 'sticker':
            response = message.reply_to_message.sticker.file_id
        elif response_type == 'voice':
            response = message.reply_to_message.voice.file_id
        elif response_type == 'audio':
            mime_type = 'audio/mpeg'
            mime_type = 'audio/m3u'
            mime_type = 'audio/ogg'
            mime_type = 'audio/wav'
            mime_type = 'audio/m4a'
            response = message.reply_to_message.audio.file_id
        elif response_type in ('gif', 'file'):
            mime_type = message.reply_to_message.document.mime_type
            response = message.reply_to_message.document.file_id
            file_name = message.reply_to_message.document.file_name
        elif response_type == 'photo':
            mime_type = 'image/jpeg'
            response = message.reply_to_message.photo[-1].file_id
            file_name = "{}.jpg".format(message.reply_to_message.photo[-1].file_id)
            caption = message.reply_to_message.caption
        elif response_type == 'location':
            response = message.reply_to_message.location.to_json()
        elif response_type == 'contact':
            response = message.reply_to_message.contact.to_json()
        else:
            parse_mode = kwargs.get('mode')
            if parse_mode not in ('HTML', 'Markdown'):
                parse_mode = None
            response = get_message(update).reply_to_message.text

        user_id = message.from_user.id
        username = message.from_user.username
        date_added = localized_date()
        date_modified = localized_date()

        if len(pattern) == 0:
            self.bot.sendMessage(
                chat_id=message.chat_id, text="❌ Reply pattern is too short.")
            return

        reply = SimpleRepliesPlugin.fetch_reply(pattern)

        if reply:
            if reply.date_deleted is None:
                self.bot.sendMessage(chat_id=message.chat_id,
                                     text="❌ A reply with this pattern already exists.")
                return
            else:
                result = SimpleRepliesPlugin.add_reply(id=reply.id,
                                                       user_id=user_id,
                                                       username=username,
                                                       pattern=pattern,
                                                       pattern_type=pattern_type,
                                                       response=response,
                                                       response_type=response_type,
                                                       caption=caption,
                                                       parse_mode=parse_mode,
                                                       file_name=file_name,
                                                       mime_type=mime_type,
                                                       date_added=date_added,
                                                       date_modified=date_modified)
        else:
            result = SimpleRepliesPlugin.add_reply(user_id=user_id,
                                                   username=username,
                                                   pattern=pattern,
                                                   pattern_type=pattern_type,
                                                   response=response,
                                                   response_type=response_type,
                                                   caption=caption,
                                                   parse_mode=parse_mode,
                                                   file_name=file_name,
                                                   mime_type=mime_type,
                                                   date_added=date_added,
                                                   date_modified=date_modified)
        if result:
            self.bot.sendMessage(
                chat_id=message.chat_id, text="✅ Reply added.")
            self.fetch_replies()
        else:
            self.bot.sendMessage(chat_id=message.chat_id,
                                 text="❌ Unable to add reply.")

    def on_text(self, update):
        text = trim_accents(get_message(update).text)

        if len(text) == 0:
            log.info('Ignoring text message. Message length is zero')
            return

        def handle_text_response(update, reply):
            self.bot.sendMessage(chat_id=update.message.chat_id,
                                 text=reply.response)

        def handle_photo_response(update, reply):
            self.bot.sendPhoto(chat_id=update.message.chat_id,
                               photo=reply.response,
                               caption=reply.caption)

        def handle_sticker_response(update, reply):
            self.bot.sendSticker(chat_id=update.message.chat_id,
                                 sticker=reply.response)

        def handle_document_response(update, reply):
            self.bot.sendDocument(chat_id=update.message.chat_id,
                                  document=reply.response)

        def handle_audio_response(update, reply):
            self.bot.sendAudio(chat_id=update.message.chat_id,
                               audio=reply.response)

        def handle_video_response(update, reply):
            self.bot.sendVideo(chat_id=update.message.chat_id,
                               video=reply.response)

        def handle_voice_response(update, reply):
            self.bot.sendVoice(chat_id=update.message.chat_id,
                               voice=reply.response)

        def handle_json_response(update, reply):
            data = json.loads(reply.response)
            self.bot.sendContact(chat_id=update.message.chat_id, **data)

        def handle_unknown_response(update, reply):
            self.bot.sendMessage(chat_id=update.message.chat_id,
                                 text="❌ Invalid response type '{response_type}' for '{pattern}'".format(pattern=reply.pattern, response_type=reply.response_type))

        response_handlers = {
            "text": handle_text_response,
            "photo": handle_photo_response,
            "sticker": handle_sticker_response,
            "gif": handle_document_response,
            "audio": handle_audio_response,
            "video": handle_video_response,
            "voice": handle_voice_response,
            "file": handle_document_response,
            "contact": handle_json_response,
            "location": handle_json_response,
        }

        def on_match(text, reply):
            response_handler = response_handlers[reply.response_type] if reply.response_type in response_handlers else handle_unknown_response
            response_handler(update, reply)

        self.find_match(text, on_match)
