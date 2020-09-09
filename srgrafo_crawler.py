"""A PEP8, improved Grafo Scraping bot
Watches a specific reddit user ('/u/SrGrafo') for new comments
If those comments contain image links (and the keyword 'edit')
the bot x-posts them to a specific subreddit ('/r/edit') unless
the comments are from some specified subreddits. Once the post is
live, it adds a 'context'/bot-reply comment to the x-post linking
users to the post the reddit user ('/u/SrGrafo') posted the 'edit' on.
"""
import re
from datetime import datetime, timedelta
from os.path import exists, getmtime
from time import sleep
import traceback
import praw

NL = '\n\n'
NSFW_WARNING = 'The following thread may be NSFW!'
CONTEXT_TEMPLATE = '[Context for the post: {:s}]({:s})' \
    + NL + 'If you have any suggestions or need to ' \
    + 'get a hold of me, just reply to this post or shoot ' \
    + 'me a message. This is my main account as ' \
    + 'well, so I see all your messages.' \
    + NL + 'Source Code found [here](https://github.com/TrippW/Reddit-Crawler)'
USER_MENTION_TEMPLATE = 'User Mention: /u/{:s}'

SRGRAFO_LAST_POST_TIME_FILE = 'grafo_post_time'
LOG_FILE = 'srgrafo_edit_bot.log'
SRGRAFO_IGNORED_SUBREDDIT_FILE = 'subreddits.ignored'
SRGRAFO_APPROVED_TEXT_FILE = 'link_text.approved'

FILES = [SRGRAFO_LAST_POST_TIME_FILE,
         LOG_FILE,
         SRGRAFO_IGNORED_SUBREDDIT_FILE,
         SRGRAFO_APPROVED_TEXT_FILE]

UPDATE_FILES_EACH_TRY = True


def get_links(body):
    """helper to find all reddit markup links and split them into
    a list of (text, link)
    """
    return re.findall(r'\[([^\n\r\]]+)\]\(([^\n\r\)]+)\)', body)


def log(text):
    """helper to log to file and print at the same time"""
    with open(LOG_FILE, 'a', encoding='utf-8') as logger:
        log_text = text.replace('\n', '\n\t')
        logger.write(f'\n{str(datetime.utcnow())}: {log_text}')
    print(text)


def get_text_from_file(file_name):
    with open(file_name, 'r') as f:
        return [line.strip() for line in f.readlines()]


def remove_nested_links(body):
    """Removes the link portion of text and replaces it with the
    hyperlink text
    """
    return ''.join(re.split(r'\[([^\n\r]]+)\]\([^\n\r)]+\)', body))


def is_image_link(link):
    return ('i.redd.it' in link) \
           or (link.split('.')[-1] in ['jpg', 'png', 'jpeg', 'gif'])


def clean_body(body):
    body = remove_nested_links(body)
    body = body.replace('\n', '. ').replace('..', '.')\
        .replace('?.', '?').replace('!.', '!')
    if body[-1] in ('\\', '/'):
        body = body[:-1]
    return body


class RedditBot:
    def __init__(self,
                 last_known_post_time_utc,
                 approved_text_file,
                 ignored_subreddit_file):
        self.last_update = datetime.utcnow()
        self.REDDIT = self.login()
        self.USER_PROFILE = self.REDDIT.redditor('SrGrafo')
        self.SUBREDDIT = self.REDDIT.subreddit('edit')
        self.last_known_post_time_utc = last_known_post_time_utc
        self.approved_text_file = approved_text_file
        self.approved_text = self.get_approved_text()
        self.ignored_subreddit_file = ignored_subreddit_file
        self.ignored_subreddits = self.get_ignored_subreddits()
        # cached to minimize api calls
        self.parent_cache = None

    def login(self):
        """log in to reddit
        uses a praw.ini file to hold sensitive information
        """
        return praw.Reddit(redirect_uri='http://localhost:8080',
                           user_agent='STS Scraper by /u/devTripp')

    def get_approved_text(self):
        return get_text_from_file(self.approved_text_file)

    def get_ignored_subreddits(self):
        return get_text_from_file(self.ignored_subreddit_file)

    def start(self):
        """starts the bot, runs forever"""
        while True:
            log('Starting up...')
            try:
                for post in self.USER_PROFILE.stream.comments():
                    if self.can_skip(post):
                        continue
                    self.try_update()
                    self.process(post)

            except Exception as e:
                print(traceback.format_exc())
                log(str(e))
                sleep(60)

    def can_skip(self, post):
        created_utc = datetime.utcfromtimestamp(post.created_utc)
        return (created_utc <= self.last_known_post_time_utc) \
            or ('template' in post.body.lower())

    def try_update(self):
        last_update = self.last_update

        if datetime.utcnow() - last_update >= timedelta(days=1) \
                or UPDATE_FILES_EACH_TRY:
            last_update_timestamp = last_update.timestamp()
            if getmtime(self.approved_text_file) > last_update_timestamp:
                self.approved_text = self.get_approved_text()
            if getmtime(self.ignored_subreddit_file) > last_update_timestamp:
                self.ignored_subreddits = self.get_ignored_subreddits()
            self.last_update = datetime.utcnow()

    def process(self, post):
        body = post.body
        if post.subreddit.display_name.lower() in self.ignored_subreddits:
            return None

        for text, link in get_links(body):
            if is_image_link(link) and self.is_approved_text(text):
                submission = self.post(post, link)
                self.update_last_known_post_time(post.created_utc)
                self.post_context(post, submission)
            self.parent_cache = None

    def is_approved_text(self, text):
        return text.lower().strip(' \n!@#$%^&*()_-+=,<.>/?;:[]{}\\|`~"'+"'") \
               in self.approved_text

    def post(self, post, link):
        title = self.generate_post_title(post)
        log(f'posting {link} to {self.SUBREDDIT.display_name} : {title[:100]}')
        return self.SUBREDDIT.submit(title, url=link)

    def generate_post_title(self, post):
        parent = self.parent_cache = post.parent()
        if post.is_root:
            return parent.title.encode('ascii', 'ignore').decode('ascii')[:300]
        else:
            person = parent.author.name if (parent.author) else 'mystery user'
            return f'EDIT to {person}'

    def update_last_known_post_time(self, t):
        if type(t) is float:
            t = datetime.utcfromtimestamp(t)
        with open(SRGRAFO_LAST_POST_TIME_FILE, 'w') as file:
            file.write(t.isoformat())
        self.last_known_post_time_utc = t

    def post_context(self, post, submission):
        while True:
            try:
                reply = CONTEXT_TEMPLATE.format(
                        self.get_parent_body(),
                        self.parent_cache.permalink)
                if post.submission.over_18:
                    reply = NSFW_WARNING + NL + reply
                author = self.parent_cache.author
                if author and author.name.lower() != 'srgrafo':
                    reply += NL + USER_MENTION_TEMPLATE.format(author.name)
                submission.reply(reply)
                return None
            except Exception as e:
                print(traceback.format_exc())
                log(str(e))
                log('Failed to post context, try again in 5 seconds...')
                sleep(5)

    def get_parent_body(self):
        text = self.parent_cache.title if type(self.parent_cache) is praw.models.Submission else self.parent_cache.body
        return clean_body(text)


if __name__ == '__main__':
    def create_file_if_missing(filename):
        if not exists(filename):
            with open(filename, 'w') as f:
                f.write('')

    for file in FILES:
        create_file_if_missing(file)

    last_post_time = get_text_from_file(SRGRAFO_LAST_POST_TIME_FILE)[0]
    if last_post_time is None or not last_post_time:
        last_post_time = datetime.utcnow()
    else:
        last_post_time = datetime.fromisoformat(last_post_time)

    bot = RedditBot(last_post_time,
                    SRGRAFO_APPROVED_TEXT_FILE,
                    SRGRAFO_IGNORED_SUBREDDIT_FILE)
    bot.start()
