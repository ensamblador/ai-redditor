import math
import random
import sqlalchemy
from sqlalchemy import func
from datetime import datetime
import uuid as uuid_generator
from abc import abstractmethod
from enum import IntEnum, unique
from ai_redditor_service.extensions import db
from ai_redditor_service.utils import merge_dicts

@unique
class RecordType(IntEnum):
    '''
    The type of GPT2 finetuned model.

    '''

    TIFU = 0
    WP = 1
    PHC = 2

class RecordMixin(object):
    '''
    The base model class for all records.

    :ivar id:
        The primary-key integer id of the record.
    :ivar uuid:
        The hexadecimal UUID of the record.
    :ivar is_generated:
        Whether the record was generated by the GPT2 model or is
        an original entry from the training/testing dataset
        (i.e. written by a human).
    :ivar is_custom:
        Whether the record was generated with a custom prompt.

    '''

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(32), unique=True, index=True)
    is_generated = db.Column(db.Boolean, index=True)
    is_custom = db.Column(db.Boolean, index=True)
    creation_date = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, uuid=None, is_custom=False, is_generated=True):
        '''
        Base constructor for Record models.

        '''

        if uuid is None:
            uuid = uuid_generator.uuid4().hex
        
        self.uuid = uuid
        self.is_custom = is_custom
        self.is_generated = is_generated

    @abstractmethod
    def to_dict(self):
        '''
        Gets a dictionary object representing the record.

        '''

        return {
            'id': self.id,
            'uuid': self.uuid,
            'is_custom': self.is_custom,
            'is_generated': self.is_generated,
            'creation_date': str(self.creation_date)
        }

    @classmethod
    def select_random_n(cls, count, **filter_kwargs):
        '''
        Selects the specified number of random records from
        a pool filtered using the specified kwargs.

        :param count:
            The number of records to select.
        :returns:
            A list of record objects.

        '''

        if count <= 0:
            raise ValueError('Count must be a positive integer.')

        if 'is_custom' in filter_kwargs and 'is_generated' in \
            filter_kwargs and not filter_kwargs['is_custom']:
            # Use the index table to select a random, non-custom, 
            # record depending on the given value of is_generated.
            if filter_kwargs['is_generated']:
                record_ref_class = cls._generated_record_ref_class
            else:
                record_ref_class = cls._dataset_record_ref_class

            return cls.query.filter(cls.id.in_(
                record_ref_class.query.options(sqlalchemy.orm.load_only('id')).offset(
                    math.floor(random.random() * int(record_ref_class.query.count()))
                ).limit(count)
            )).all()
        else:
            return cls.query.filter_by(**filter_kwargs).order_by(func.random()).limit(count).all()

    @classmethod
    def select_random(cls, **filter_kwargs):
        '''
        Selects a random record from a pool filtered
        using the specified kwargs.

        '''

        return cls.select_random_n(1, **filter_kwargs)[0]

    @sqlalchemy.orm.validates('is_generated')
    def _validate_is_generated(self, key, is_generated):
        if self.is_custom: return is_generated

        # NOTE: this validation function will be called EVERY TIME is_generated changes.
        # Since this function creates a mapping between the index tables for the generated/dataset
        # records, if it is called on anything but an INSERT, a duplicate entry in the index table
        # will be made. However, at this point, we assume that records are constants...
        if is_generated:
            self.generated_record_ref = self._generated_record_ref_class(record_id=record_id)
        
        self.dataset_record_ref = self._dataset_record_ref_class(record_id=record_id)
        return is_generated

class TIFUDatasetRecord(db.Model):
    '''
    TIFU record where ``is_generated`` is false and ``is_custom`` is false. 

    '''

    __tablename__ = 'tifu_dataset_record'
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('tifu_record.id'))
    record = db.relationship('TIFURecord', back_populates='dataset_record_ref')

class TIFUGeneratedRecord(db.Model):
    '''
    TIFU record where ``is_generated`` is true and ``is_custom`` is false.

    '''

    __tablename__ = 'tifu_generated_record'
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('tifu_record.id'))
    record = db.relationship('TIFURecord', back_populates='generated_record_ref')

class TIFURecord(RecordMixin, db.Model):
    '''
    A TIFU post record.

    :ivar post_title:
        The title of the post.
    :ivar post_title_prompt_end:
        A zero-based index indicating where the post title prompt ends.
        This is equivalent to the length of the prompted post tile
        measured from the start of the string.
    :ivar post_body:
        The body text (self text) of the post.
    :ivar post_body_prompt_end:
        A zero-based index indicating where the post body prompt ends.
        This is equivalent to the length of the prompted post body
        measured from the start of the string.

    '''

    __tablename__ = 'tifu_record'
    post_title = db.Column(db.Text)
    post_title_prompt_end = db.Column(db.Integer, nullable=False, default=0)
    post_body = db.Column(db.Text)
    post_body_prompt_end = db.Column(db.Integer, nullable=False, default=0)

    dataset_record_ref = db.relationship('TIFUDatasetRecord', uselist=False, back_populates='record')
    generated_record_ref = db.relationship('TIFUGeneratedRecord', uselist=False, back_populates='record')
    _generated_record_ref_class = TIFUGeneratedRecord
    _dataset_record_ref_class = TIFUDatasetRecord

    def __init__(self, post_title, post_body, post_title_prompt_end=0,
                 post_body_prompt_end=0, **kwargs):
        '''
        Initializes an instance of :class:`TIFURecord`.

        :param post_title:
            The title of the post.
        :param post_body:
            The body text (self text) of the post.
        :param uuid:
            A 128-bit hexademical string representing the unique integer id of this record.
            Defaults to None, meaning that the UUID will be randomly generated.
        :param is_custom:
            Whether the record was generated with a custom prompt. Defaults to False.
        :param is_generated:
            Whether the record was generated by the GPT2 model or is
            an original entry from the training/testing dataset
            (i.e. written by a human).
        :param post_title_prompt_end:
            A zero-based index indicating where the post title prompt ends.
        :param post_body_prompt_end:
            A zero-based index indicating where the post body prompt ends.
        
        '''

        super().__init__(**kwargs)
        self.post_title = post_title
        self.post_body = post_body
        self.post_title_prompt_end = post_title_prompt_end
        self.post_body_prompt_end = post_body_prompt_end

    def to_dict(self):
        '''
        Gets a dictionary object representing the record.

        '''

        return merge_dicts(super().to_dict(), {
            'post_title': self.post_title,
            'post_body': self.post_body,
            'post_title_prompt_end': self.post_title_prompt_end,
            'post_body_prompt_end': self.post_body_prompt_end
        })

class WPDatasetRecord(db.Model):
    '''
    Writingprompt record where ``is_generated`` is false and ``is_custom`` is false. 

    '''

    __tablename__ = 'wp_dataset_record'
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('wp_record.id'))
    record = db.relationship('WPRecord', back_populates='dataset_record_ref')

class WPGeneratedRecord(db.Model):
    '''
    Writingprompt record where ``is_generated`` is true and ``is_custom`` is false.

    '''

    __tablename__ = 'wp_generated_record'
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('wp_record.id'))
    record = db.relationship('WPRecord', back_populates='generated_record_ref')

class WPRecord(RecordMixin, db.Model):
    '''
    A writingprompt and response pair record.

    :ivar prompt:
        The writingprompt.
    :ivar prompted_prompt_end:
        A zero-based index indicating where the prompted writingprompt
        ends. This is equivalent to the length of the prompt measured
        from the start of the string.
    :ivar prompt_response:
        The response to the writingprompt. 
    :ivar prompted_response_end:
        A zero-based index indicating where the prompted response ends.
        This is equivalent to the length of the response measured from
        the start of the string.

    '''

    __tablename__ = 'wp_record'
    prompt = db.Column(db.Text)
    prompted_prompt_end = db.Column(db.Integer, nullable=False, default=0)
    prompt_response = db.Column(db.Text)
    prompted_response_end = db.Column(db.Integer, nullable=False, default=0)

    dataset_record_ref = db.relationship('WPDatasetRecord', uselist=False, back_populates='record')
    generated_record_ref = db.relationship('WPGeneratedRecord', uselist=False, back_populates='record')
    _generated_record_ref_class = WPGeneratedRecord
    _dataset_record_ref_class = WPDatasetRecord

    def __init__(self, prompt, prompt_response, prompted_prompt_end=0,
                 prompted_response_end=0, **kwargs):
        '''
        Initializes an instance of :class:`WPRecord`.

        :param prompt:
            The writingprompt.
        :param prompt_response:
            The response to the writingprompt.
        :param prompted_prompt_end:
            A zero-based index indicating where the prompted writingprompt ends.
        :param prompted_response_end
            A zero-based index indicating where the prompted response ends.
        
        '''

        super().__init__(**kwargs)
        self.prompt = prompt
        self.prompt_response = prompt_response
        self.prompted_prompt_end = prompted_prompt_end
        self.prompted_response_end = prompted_response_end

    def to_dict(self):
        '''
        Gets a dictionary object representing the record.

        '''

        return merge_dicts(super().to_dict(), {
            'prompt': self.prompt,
            'prompt_response': self.prompt_response,
            'prompted_prompt_end': self.prompted_prompt_end,
            'prompted_response_end': self.prompted_response_end
        })

class PHCDatasetRecord(db.Model):
    '''
    PHC record where ``is_generated`` is false and ``is_custom`` is false. 

    '''

    __tablename__ = 'phc_dataset_record'
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('phc_record.id'))
    record = db.relationship('PHCRecord', back_populates='dataset_record_ref')

class PHCGeneratedRecord(db.Model):
    '''
    PHC record where ``is_generated`` is true and ``is_custom`` is false.

    '''

    __tablename__ = 'phc_generated_record'
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('phc_record.id'))
    record = db.relationship('PHCRecord', back_populates='generated_record_ref')

class PHCRecord(RecordMixin, db.Model):
    '''
    A pornhub comment record.

    :ivar author_username:
        The username of the author.
    :ivar prompted_author_username_end:
        A zero-based index indicating where the prompted author username
        ends. This is equivalent to the length of the prompted username
        measured from the start of the string.
    :ivar likes:
        The number of likes the comment has.
    :ivar is_likes_prompted:
        Whether the likes value was prompted. 
    :ivar comment:
        The comment text.
    :ivar prompted_comment_end:
        A zero-based index indicating whether the prompted comment ends.
        This is equivalent to the length of the prompted comment measured
        from the start of the string.

    '''

    __tablename__ = 'phc_record'
    author_username = db.Column(db.Text)
    prompted_author_username_end = db.Column(db.Integer, nullable=False, default=0)
    likes = db.Column(db.BigInteger)
    is_likes_prompted = db.Column(db.Boolean, nullable=False, default=False)
    comment = db.Column(db.Text)
    prompted_comment_end = db.Column(db.Integer, nullable=False, default=0)

    dataset_record_ref = db.relationship('PHCDatasetRecord', uselist=False, back_populates='record')
    generated_record_ref = db.relationship('PHCGeneratedRecord', uselist=False, back_populates='record')
    _generated_record_ref_class = PHCGeneratedRecord
    _dataset_record_ref_class = PHCDatasetRecord

    def __init__(self, author_username, likes, comment, prompted_author_username_end=0,
                 is_likes_prompted=False, prompted_comment_end=0, **kwargs):
        '''
        Initializes an instance of :class:`WPRecord`.

        :param author_username:
            The username of the author.
        :param likes:
            The number of likes the comment has.
        :param comment:
            The comment text.
        :param prompted_author_username_end:
            A zero-based index indicating where the prompted author username ends.
        :param is_likes_prompted:
            Whether the likes value was prompted.
        :param prompted_comment_end:
            A zero-based index indicating whether the prompted comment ends.
        
        '''

        super().__init__(**kwargs)
        self.author_username = author_username
        self.likes = likes
        self.comment = comment
        self.prompted_author_username_end = prompted_author_username_end
        self.is_likes_prompted = is_likes_prompted
        self.prompted_comment_end = prompted_comment_end

    def to_dict(self):
        '''
        Gets a dictionary object representing the record.

        '''

        return merge_dicts(super().to_dict(), {
            'author_username': self.author_username,
            'likes': self.likes,
            'comment': self.comment,
            'prompted_author_username_end': self.prompted_author_username_end,
            'is_likes_prompted': self.is_likes_prompted,
            'prompted_comment_end': self.prompted_comment_end
        })

RECORD_MODEL_CLASSES = {
    RecordType.TIFU: TIFURecord,
    RecordType.WP: WPRecord,
    RecordType.PHC: PHCRecord
}