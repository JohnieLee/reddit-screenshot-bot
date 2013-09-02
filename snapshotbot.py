#!/usr/bin/env python
"""
Reddit bot framework

Framework to create Reddit Bots that processes comments.
"""

import praw
import logging
import pyimgur
import pymongo
import re

from datetime import datetime
from urlparse import urlparse
from redditprocessor import Command


class SnapshotCommand(Command):
    """Snapshot Command.
       Command that:
         * is triggered by the keyword '/u/snapshot_bot' in the comment body
         * parses the comment for urls using URL_REGEX expression
         * calls the snapito API to snapshot the URL
         * uploads the snapshot to imgur
    """

    # URL for Snapito API
    SNAPITO_URL_TEMPLATE \
        = 'http://api.snapito.com/web/{API_KEY}/full/{URL}?type=png'

    # URL Regex from http://daringfireball.net
    URL_REGEX = re.compile(
        ur'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)'
        ur'(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+'
        ur'|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?\xab\xbb\u201c\u201d'
        ur'\u2018\u2019]))')

    # String used to trigger the processing of this command.
    TRIGGER_WORD = '/u/snapshot_bot'

    def __init__(self, snapito_key, imgur_key, mongo_url):
        super(SnapshotCommand, self).__init__('SnapshotBot')
        self.logger = logging.getLogger('SnapshotBot')
        self.imgur = pyimgur.Imgur(imgur_key)
        self.snapito_key = snapito_key
        self.db = self._open_db(mongo_url)

    def process(self, comment):
        '''Process the latest comments for a given subreddit'''
        if (comment.author != None
            and comment.author.name != u'snapshot_bot'
            and SnapshotCommand.TRIGGER_WORD in comment.body):
            self.logger.debug('comment: %s - %s - %s',
                comment.id, comment.author, comment.body[:50])
            self._process_comment(comment)

    def _process_comment(self, comment):
        '''Process a comment that contains the trigger'''
        self.logger.debug(
            'Processing comment: %s - %s - %s - %s',
            comment.link_id, comment.id, comment.author.name, comment.body[:50])

        if (self._is_already_processed(comment)):
            return

        self.logger.info('not processed')
        self._log_to_db(comment)

        urls = self._extract_urls(comment.body)
        self._log_to_db(comment, urls)

        if len(urls) == 0:
            self.logger.info('No URLs to process, skipping.')
            self._log_to_db(comment, urls, reply_completed=True)
            return

        imgur_album = self._create_imgur_album(comment)
        self._log_to_db(comment, urls, imgur_album)

        imgur_urls = self._screenshot_urls(urls, comment, imgur_album)
        self._log_to_db(comment, urls, imgur_album, imgur_urls)

        if (len(imgur_urls) > 0):
            self._log_to_db(comment, urls, imgur_album, imgur_urls)

            reply_text = self._create_reply(urls, imgur_urls, imgur_album)
            self._log_to_db(comment, urls, imgur_album, imgur_urls,
                            reply_text, False)

            self._send_reply(comment,reply_text)
            self._log_to_db(comment, urls, imgur_album, imgur_urls,
                            reply_text, True)

    def _extract_urls(self, body) :
        matches = re.findall(SnapshotCommand.URL_REGEX, body)
        urls = [x[0] for x in matches]
        return urls

    def _create_reply(self, urls, imgur_urls, album):
        REPLY_HEADER = 'The following URLs have been snapshotted:\n\n'
        REPLY_LINK = '* {url} - [[snapshot]({snapshot})]\n\n'
        REPLY_ALBUM_LINK = '* [Snapshot Album]({album_link})\n\n'
        REPLY_FOOTER = ("\n\n____\n\n"
            "`To snapshot URLs, add '/u/snapshot_bot' to your comment.`\n\n"
            "`For more information go to:` [r/snapshot_bot]("
            "http://reddit.com/r/snapshot_bot).\n\n"
            "`Built with love by tazzy531.`")

        self.logger.debug("FOO: %s\n %s", urls, imgur_urls)
        links_txt =''.join([REPLY_LINK.format(url=url, snapshot=imgur_url)
            for url, imgur_url in zip(urls, imgur_urls)])

        album_txt = REPLY_ALBUM_LINK.format(album_link=album.link)

        reply = ''.join([REPLY_HEADER, links_txt, album_txt, REPLY_FOOTER])

        self.logger.debug('Reply text: %s', reply)
        return reply

    def _send_reply(self, comment, text):
        try:
            comment.reply(text)
        except praw.errors.RateLimitExceeded as e:
            self.logger.warning('Rate limit exceeded', e)

    def _open_db(self, mongo_url):
        # Get a connection
        conn = pymongo.Connection(mongo_url)
        # Get the db
        return conn[urlparse(mongo_url).path[1:]]

    def _get_db_key(self, comment):
        return {
                    'submission_id': comment.link_id,
                    'comment_id': comment.id
                }

    def _is_already_processed(self, comment):
        key = self._get_db_key(comment)
        curr = self.db.snapshot_log.find_one(key)
        return (curr != None and curr['reply_completed'] == True)

    def _log_to_db(self, comment, snapshot_urls=None, imgur_album=None,
            imgur_urls=None, reply_text=None, reply_completed=None):
        key = self._get_db_key(comment)
        imgur_album_id = imgur_album.id if imgur_album != None else None
        self.db.snapshot_log.update(
            key,
            {
                'submission_id': comment.link_id,
                'comment_id': comment.id,
                'author': comment.author.name,
                'created_datetime': datetime.fromtimestamp(comment.created_utc),
                'snapshot_urls': snapshot_urls,
                'imgur_album': imgur_album_id,
                'imgur_urls': imgur_urls,
                'reply_text': reply_text,
                'reply_completed': reply_completed
            },
            upsert=True)

        self.logger.debug('Wrote log: %s', key)

    def _create_imgur_album(self, comment):
        ALBUM_DESCRIPTION_TEMPLATE = ('Snapshot for {author} at {permalink}.\n'
            'Snapshot by: /u/snapshot_bot')
        album_title = "{0}'s snapshot".format(comment.author.name)
        album_description = ALBUM_DESCRIPTION_TEMPLATE.format(
                author=comment.author.name, permalink=comment.permalink)

        album = self.imgur.create_album(title=album_title,
                                description=album_description)
        self.logger.debug('created album %s', album)
        return album

    def _screenshot_urls(self, urls, comment, album):
        IMAGE_DESCRIPTION_TEMPLATE = ('Snapshot for {author} at {permalink}.\n'
            'URL: {url}\n\n'
            'Snapshot by: /u/snapshot_bot')

        self.logger.info('capturing url: %s', urls)
        imgur_urls = []
        for url in urls:
            snapito_url = self.SNAPITO_URL_TEMPLATE.format(
                API_KEY=self.snapito_key, URL=url)
            self.logger.info('snapito: %s', snapito_url)

            title_url = (url[:30] + '..') if len(url) > 30 else url
            title = 'Snapshot {0} [{1}]'.format(title_url, datetime.now())
            description = IMAGE_DESCRIPTION_TEMPLATE.format(
                author=comment.author.name, permalink=comment.permalink,
                url=url)

            image = self.imgur.upload_image(url=snapito_url,
                                            title=title,
                                            description=description,
                                            album=album.deletehash)

            self.logger.info('successfully captured %s to %s',
                             image.id, image.link)
            imgur_urls.append(image.link)

        return imgur_urls
