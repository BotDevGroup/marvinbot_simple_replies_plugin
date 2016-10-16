import mongoengine
from marvinbot.utils import localized_date

PATTERN_TYPES = (('exact', 'Exact match'),
                 ('begins_with', 'Begins with'),
                 ('ends_with', 'Ends with'),
                 ('contains', 'Contains'),
                 ('regexp', 'Regular expression'))

RESPONSE_TYPES = (('text', 'Text'),
                  ('photo', 'Photo'),
                  ('sticker', 'Sticker'),
                  ('gif', 'GIF'),
                  ('audio', 'Audio'),
                  ('video', 'Video'),
                  ('file', 'File'),
                  ('voice', 'Voice note'),
                  ('location', 'Location'),
                  ('contact', 'Contact'))


class SimpleReply(mongoengine.Document):
    id = mongoengine.SequenceField(primary_key=True)
    pattern = mongoengine.StringField(unique=True)
    pattern_type = mongoengine.StringField(
        choices=PATTERN_TYPES, default='exact', required=True)
    response = mongoengine.StringField(required=True)
    response_type = mongoengine.StringField(
        choices=RESPONSE_TYPES, default="text", required=True)
    mime_type = mongoengine.StringField(required=False)
    file_name = mongoengine.StringField(required=False)
    caption = mongoengine.StringField(required=False)
    parse_mode = mongoengine.StringField(required=False)
    user_id = mongoengine.LongField(required=True)
    username = mongoengine.StringField(required=True)

    date_added = mongoengine.DateTimeField(default=localized_date)
    date_modified = mongoengine.DateTimeField(default=localized_date)
    date_deleted = mongoengine.DateTimeField(required=False, null=True)

    @classmethod
    def by_id(cls, id):
        try:
            return cls.objects.get(id=id)
        except cls.DoesNotExist:
            return None

    @classmethod
    def by_pattern(cls, pattern):
        try:
            return cls.objects.get(pattern=pattern)
        except cls.DoesNotExist:
            return None

    @classmethod
    def all(cls):
        try:
            return cls.objects(date_deleted=None)
        except:
            return None

    def __str__(self):
        return "{{ id = {id}, pattern = \"{pattern}\", pattern_type = {pattern_type}, response = \"{response}\", response_type = {response_type} }}".format(id=self.id, pattern=self.pattern, pattern_type=self.pattern_type, response=self.response, response_type=self.response_type)
