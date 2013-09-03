#!/usr/bin/env python
"""
Reddit Comment Processor

Processor for Reddit comments that scans the last comments and runs it through
a chain of commands to allow each command to process the comment.
"""

import abc
import logging
import praw

from abc import ABCMeta
from itertools import product


class Command(object):
    """Abstract comment command processor
       Implementors will need to override process method.
    """
    __metaclass__ = ABCMeta

    def __init__(self, name):
        self.__logger = logging.getLogger('reddit-bot.Command')
        self.name = name

    def execute(self, comment):
        #self.__logger.debug('Processing: %s/_/%s',
        #                    comment.link_id, comment.id)
        self.process(comment)

    @abc.abstractmethod
    def process(self, comment):
        """Process the comment"""
        return


class RedditCommentProcessor(object):
    """Reddit comment processor
       Comment processor that scans the last series of comments and passes it
       to the registered commands.

       Commands will need to be registered by calling register_command.
    """
    def __init__(self,
                 reddit_creds=None,
                 user_agent='Snapshot Bot 0.1 by /u/tazzy531',
                 subreddit_filter=[],
                 comment_limit=50):
        self.logger = logging.getLogger('reddit-bot.RedditCommentProcessor')
        self.reddit = praw.Reddit(user_agent)
        self.subreddit_filter = subreddit_filter
        self.comment_limit = comment_limit
        self.commands = []

        if reddit_creds is not None:
            self.logger.info('Logging into praw with user [/u/%s]',
                             reddit_creds['username'])
            self.reddit.login(username=reddit_creds['username'],
                              password=reddit_creds['password'])

    def register_command(self, command):
        """Register command to execute per comment"""
        self.commands.append(command)

    def run(self):
        """Process the latest comments for a given subreddit"""
        self.logger.info('Executing Run')

        for subreddit in self.subreddit_filter:
            self.logger.info('Processing subreddit: %s', subreddit)
            comments = self.reddit.get_comments(
                subreddit,
                limit=self.comment_limit)

            self._process_comments(comments)

        self.logger.info('Completed run')

    def _process_comments(self, comments):
        for comment, command in product(comments, self.commands):
            try:
                command.execute(comment)
            except Exception, err:
                self.logger.error(
                    'Failed processing on command [%s] with exception: %s',
                    command.name, repr(err), exc_info=True)
