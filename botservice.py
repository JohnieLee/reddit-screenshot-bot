#!/usr/bin/env python
"""
Reddit bot framework

Framework to create Reddit Bots that processes comments.
"""

import logging
import os
import time

from redditprocessor import RedditCommentProcessor, Command
from snapshotbot import SnapshotCommand


class NameMatchCommand(Command):

    def __init__(self):
        super(NameMatchCommand, self).__init__('NameMatchCommand')
        self.logger = logging.getLogger('reddit-bot.NameMatchCommand')

    def process(self, comment):
        if self.should_run(comment):
            self.logger.info('NameMatch Processing: %s', comment)

    def should_run(self, comment):
        return self.name in comment.body


def main():
    MONGO_URL = os.environ.get('MONGOLAB_URI')

    SNAPITO_API_KEY = os.environ.get('SNAPITO_API_KEY')
    IMGUR_API_KEY = os.environ.get('IMGUR_API_KEY')

    SUBREDDIT_LIST = os.environ.get('SUBREDDIT_LIST', '')
    COMMENT_LIMIT = os.environ.get('COMMENT_LIMIT', 100)

    SNAP_API_URL = os.environ.get(
        'SNAP_API_URL',
        'http://api.snapito.com/web/{API_KEY}/full/{URL}?type=png')

    reddit_creds = {
        'username': os.environ.get('REDDIT_BOT_USER'),
        'password': os.environ.get('REDDIT_BOT_PASSWORD')
    }

    # How long to run
    LOOP_TIMEOUT_SECS = float(os.environ.get('LOOP_TIMEOUT', 480))
    # How long to sleep between runs
    LOOP_SLEEP_SECS = float(os.environ.get('LOOP_SLEEP', 30))

    processor = RedditCommentProcessor(
        reddit_creds=reddit_creds, subreddit_filter=SUBREDDIT_LIST.split(','),
        comment_limit=COMMENT_LIMIT)

    #name_match_command = NameMatchCommand('snapshot_bot')

    snapshot_command = SnapshotCommand(
        snapito_key=SNAPITO_API_KEY, imgur_key=IMGUR_API_KEY,
        mongo_url=MONGO_URL, snap_url_template=SNAP_API_URL)

    #processor.register_command(name_match_command)
    processor.register_command(snapshot_command)


    timeout = time.time() + LOOP_TIMEOUT_SECS
    while True:
        processor.run()
        if time.time() > timeout:
            break
        time.sleep(LOOP_SLEEP_SECS)

    logging.getLogger('main').info('Done looping')


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    main()
