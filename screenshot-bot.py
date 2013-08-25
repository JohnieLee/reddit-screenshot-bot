#!/usr/bin/env python
"""
Reddit bot that takes a screenshot using http://snapito.com/
"""

import os
import praw
import logging
import pyimgur
import pymongo
import re
import requests
import sys

from datetime import datetime
from urlparse import urlparse


MONGO_URL = os.environ.get('MONGOLAB_URI')

SNAPITO_API_KEY = os.environ.get('SNAPITO_API_KEY')
IMGUR_API_KEY = os.environ.get('IMGUR_API_KEY')

SUBREDDIT_LIST = os.environ.get('SUBREDDIT_LIST')

REDDIT_CREDS = {
    'username' : os.environ.get('REDDIT_BOT_USER'),
    'password' : os.environ.get('REDDIT_BOT_PASSWORD')
}

class SnapshotBot(object) :

    SNAPITO_URL_TEMPLATE \
        = 'http://api.snapito.com/web/{API_KEY}/full/{URL}?type=png'

    URL_REGEX \
        = 'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

    def __init__(self, snapito_key, imgur_key, reddit_creds, mongo_url) :
        self._init_logger()
        self.imgur = pyimgur.Imgur(imgur_key)
        self.snapito_key = snapito_key
        self.praw = praw.Reddit("Snapshot Bot 0.1 by /u/tazzy531")
        self.praw.login(username = reddit_creds['username'], 
            password = reddit_creds['password'])
        self.db = self._open_db(mongo_url)

    def _init_logger(self) :
        '''Initialize the logger configuration for this bot'''
        self.logger = logging.getLogger('SnapshotBot')
        self.logger.setLevel(logging.DEBUG)

    def _open_db(self, mongo_url) :
        # Get a connection
        conn = pymongo.Connection(mongo_url)
        # Get the db
        db = conn[urlparse(MONGO_URL).path[1:]]
        return db

    def process(self, subreddits) :
        '''Executes a full run'''
        comments = self.praw.get_comments('test', limit = 50)
        for comment in comments :
            self.logger.debug('comment: %s - %s - %s', 
                comment.id, comment.author, comment.body[:50])
            if (comment.author.name == '/u/snapshot_bot') :
                self._process_comment(comment)
    
    def _process_comment(self, comment) :
        '''Process a comment that contains the trigger'''
        self.logger.debug('Processing comment: %s - %s - %s', 
            comment.id, comment.author.name, comment.body[:50])

        if (not self._is_already_processed(comment)) :
            self.logger.info('not processed')
            self._log_to_db(comment)
            urls = re.findall(SnapshotBot.URL_REGEX, comment.body)
            imgur_urls = self.screenshot_urls(urls)
            self._log_to_db(comment, urls, imgur_urls)
            if (len(imgur_urls) > 0) :
                self._add_comment(comment, \
                    'URLs Snapshotted: {0}'.format(', '.join(imgur_urls)))

    def _add_comment(self, comment, text) :
        try :
            comment.reply(text)
        except praw.errors.RateLimitExceeded as e:
            self.logger.warning('Rate limit exceeded, adding to queue %s', e)
            self.db.snapshot_queue.update(
                self._get_db_key(comment),
                {
                    'comment_id' : comment.id,
                    'text' : text,
                    'queue_ts' : datetime.now()
                },
                upsert = True)

    def _get_db_key(self, comment) :
        key = {'comment_id' : comment.id}
        return key

    def _is_already_processed(self, comment) :
        key = self._get_db_key(comment)
        cursor = self.db.snapshot_log.find(key)
        return (cursor.count() > 0)

    def _log_to_db(self, comment, snapshot_urls = None, imgur_urls = None) :
        key = self._get_db_key(comment) 
        result = self.db.snapshot_log.update(
           key,
           {
               'comment_id' : comment.id,
               'author' : comment.author.name,
               'created_datetime' : datetime.fromtimestamp(comment.created_utc),
               'snapshot_urls' : snapshot_urls,
               'imgur_urls' : imgur_urls
           },
           upsert = True)

        self.logger.debug('Wrote log: %s', key)
    
    def _extract_urls(self, body_text) : 
        return re.findall(URL_REGEX, body_text)

    def screenshot_urls(self, urls) :
        self.logger.info('capturing url: %s', urls)

        imgur_urls = [] 

        for url in urls :
            snapito_url = self.SNAPITO_URL_TEMPLATE.format(API_KEY=self.snapito_key, URL=url)
            self.logger.info('snapito: %s', snapito_url)

            title_url = (url[:30] + '..') if len(url) > 30 else url
            title = 'Snapshot {0} [{1}]'.format(title_url, datetime.now()) 
            description = 'Snapshot by /u/snapshot_bot'
            image = self.imgur.upload_image(url=snapito_url, title=title,
                                            description = description)
            self.logger.info('successfully captured %s to %s', image.id, image.link)
            imgur_urls.append(image.link)
        return imgur_urls


def main() :
    bot = SnapshotBot(SNAPITO_API_KEY, IMGUR_API_KEY, REDDIT_CREDS, MONGO_URL)
    bot.process('test')
    #bot.capture_url('www.cnn.com')


if __name__ == "__main__":

    root = logging.getLogger()

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    root.addHandler(ch)

    main()
    pass
