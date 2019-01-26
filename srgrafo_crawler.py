"""
This module scans all the posts and comments of one user and posts them to a subreddit
Attempts to not repost
"""
import urllib.request
import time
import os
import praw

def check_for_new_posted_images(limit):
    """checks new posts in the subreddit and adds their urls and titles to a list"""
    global SUBREDDIT
    new_posts = SUBREDDIT.new(limit=limit)
    for post in new_posts:
        if post.url not in POSTED_IMAGES:
            POSTED_IMAGES.append(post.url)
        if post.title not in POSTED_IMAGES:
            POSTED_IMAGES.append(post.title)

def update_flair():
    """
    updates flair to get link templates
    Note: Need to have mod permission for this to work
    Does not have test to make sure you have permission
    Will crash if you do not have permissions
    """
    flair_names = ['Gaming Series', 'Rimworld Tales', 'EDIT', 'Comic']
    flair_templates = [None for flair in flair_names]
    print('updating flair templates')

    for template in SUBREDDIT.flair.link_templates:
        if template['text'] and template['text'] in flair_names:
            flair_templates[flair_names.index(template['text'])] = template['id']

    return flair_templates


def is_image(url):
    """checks if the url is an image"""
    return ('i.redd.it' in url) or (url[-4:] in ['.jpg', '.png', 'jpeg', '.gif'])

def add_image_to_list(image):
    """record when we post an image"""
    global POSTED_LINKS
    if image not in POSTED_LINKS:
        POSTED_LINKS.append(image)
        with open('posted_links.txt', 'a') as file:
            file.write(image+'\n')

def log_in():
    """
	log in to reddit
	uses a praw.ini file to hold sensitive information
	"""
	
    return praw.Reddit(redirect_uri='http://localhost:8080', \
                       user_agent='SrGrafo Scraper by /u/devTripp')

def post_image(data):
    """post image to the subreddit"""
    submission = None
    if data['path']:
        submission = SUBREDDIT.submit_image(data['title'], \
                                            data['path'], \
                                            flair_id=data['flair'])
    else:
        submission = SUBREDDIT.submit(data['title'], \
                                      url=data['url'], \
                                      flair_id=data['flair'])
    if data['nsfw']:
        submission.mod.nsfw()
    submission.reply(CONTEXT_TEMPLATE.format(data['context']))
    add_image_to_list(data['url'])
    return submission

def decide_flair(data, sub):
    """categorize the post to the appropriate flair"""
    sub = sub.lower()

    flair_type = None

    if sub == 'gaming':
        flair_type = flair_options[0]
    elif sub in ['funny', 'comics']:
        flair_type = flair_options[3]
    elif sub == 'rimworld':
        if '#' in data['title']:
            flair_type = flair_options[1]
        else:
            flair_type = flair_options[3]
    return flair_type

def update_comment_images():
    """
    get all comments, check if they contain the coveted [edit] text to note an image
    and the url hasn't been posted. Checks to see what the parent is (a comment or a
    submission) if it's a comment, we get the post above it's text and trim it. If it's
    a submission, we just use the same title. Also trim the link from the body and use it
    for the subreddit submission
    """
    global IMG_LIST
    global POSTED_IMAGES
    global POSTED_LINKS
    global USER_PROFILE #the user account

    print('updating comment history')

    #this is one api call giving us 1000 posts
    check_for_new_posted_images(1000)
    for comment in USER_PROFILE.comments.new(limit=check_limit): #one call
        if '[EDIT]' in comment.body:
            url = comment.body.split('](')[1]
            url = url[:url.find(')')]
            if (is_image(url)) and \
               (url not in IMG_LIST) and \
               (url not in POSTED_LINKS) and \
               (url not in POSTED_IMAGES):

                #This is our choke point. We are only allowed 60 calls per minute. Each call to
                #parent is an api call. If we haven't eliminated any from our posts and every one is
                #an edit, that's 1000 calls here. This can take a maximum of 1000/60 minutes or
                #about 17 minutes
                parent = comment.parent()
                if type(parent) is praw.models.Comment:
                    IMG_LIST.append({'url':url, \
                                     'title':parent.body.replace('\n', ' ') \
                                     .encode('ascii', 'ignore').decode('ascii')[:300], \
                                     'context':parent.permalink, 'path':None, \
                                     'nsfw':parent.submission.over_18,
                                     'flair':flair_options[2]})
                else:
                    IMG_LIST.append({'url':url, \
                                     'title':parent.title.encode('ascii', 'ignore')\
                                     .decode('ascii')[:300], \
                                     'context':parent.permalink, \
                                     'path':None, \
                                     'nsfw':parent.over_18,\
                                     'flair':flair_options[2]})
                if IMG_LIST[-1]['title'] in POSTED_IMAGES:
                    IMG_LIST.pop()

def update_post_images():
    """
    get all submissions. Use the same title. Check if the image has been posted before
    before trying to submit it. We also download the image and reupload it to reddit instead
    of just linking to the image.
    Makes sure they are in an appropriate sub as well.
    Formats the title.
    Adds a post to link to the sub and patreon
    """
    global IMG_LIST
    global POSTED_IMAGES
    global POSTED_LINKS
    global USER_PROFILE #the user account

    print('updating post history')

    #this is one api call giving us 1000 posts
    check_for_new_posted_images(1000)

    for post in USER_PROFILE.submissions.new(limit=check_limit):
        if (post.url) and \
           (post.url not in IMG_LIST) and \
           (is_image(post.url)) and \
           (post.subreddit.display_name.lower() in ALLOWED_SUBS) and \
           (post.url not in POSTED_LINKS) and \
           (post.url not in POSTED_IMAGES) and \
           (post.title.encode('ascii', 'ignore').decode('ascii')[:300] not in POSTED_IMAGES):
            path = None
            if 'redd.it' in post.url:
                path = './images'+post.url[post.url.find('.it/')+3:]
                if not is_image(path):
                    path += '.png'
                urllib.request.urlretrieve(post.url, path)
            IMG_LIST.append({'url':post.url, \
                             'title':post.title.encode('ascii', 'ignore').decode('ascii')[:300], \
                             'context':post.permalink, \
                             'path':path, \
                             'nsfw':post.over_18})
            IMG_LIST[-1]['flair'] = decide_flair(IMG_LIST[-1], post.subreddit.display_name)

            if not FIRST_ITER:
                post.reply(REPLY_TEMPLATE)

def post_all_images():
    """goes through our list of images we created and tries to post them"""
    global retry

    for i in iter_list:
        if i['url'] in POSTED_IMAGES:
            print('image has already been posted with url '+i['url'])
            #this line is duplicated in both parts because we want it to happen before the 8
            #minute pause
            add_image_to_list(i['url'])
        else:
            print('submitting image {:40s} image #: {:3d}  complete: {:3.2f}%'.format( \
                i['title'][:40], iter_list.index(i)+1, ((iter_list.index(i)+1)*100/len(iter_list))))
            try:
                submission = post_image(i)
                retry = 2
                time.sleep(60*5)
            except praw.exceptions.APIException as err:
                #there was a problem with the api, wait for 5 minutes
                if retry != 0:
                    print("whoops, api error. Trying again in 5 minutes")
                    print(err)
                    retry -= 1
                else:
                    raise Exception("Failed 3 times. End program")
                time.sleep(60*5) #try again in 5 minutes
            except praw.exceptions.ClientException:
                #socket issue with the upload. It may have gone through
                print('Likely a socket issue. Wait 30 seconds to check')
                time.sleep(30)
                #checking if the post went through to see if we need to post again or
                #if we successfully posted the image
                if i['title'] not in [x.title for x in SUBREDDIT.new(limit=100)]:
                    #try to post it again
                    print('Wasn\'t posted, try uploading again')
                    submission = post_image(i)
                else:
                    print('it was posted.')
                    #we posted the image, so we need to find it so we can post the context
                    for sub_post in SUBREDDIT.new(limit=100):
                        if sub_post.title == i['title']:
                            submission = sub_post
                            break
                #post the context comment
                submission.reply(CONTEXT_TEMPLATE.format(i['context']))
                add_image_to_list(i['url'])
                print('waiting for 3 minutes before we post our next image')
                time.sleep(60*3)
        #remove the image from our list
        if i in IMG_LIST:
            IMG_LIST.remove(i)


IMG_LIST = []
POSTED_LINKS = []

ALLOWED_SUBS = ['gaming', 'rimworld', 'u_srgrafo', 'funny', 'comics']

if os.path.exists('./posted_links.txt') and os.path.isfile('./posted_links.txt'):
    with open('posted_links.txt', 'r') as link_file:
        POSTED_LINKS = link_file.read().split('\n')[:-1] #there is always one too many

REDDIT = log_in()

#setup
USER_PROFILE = REDDIT.redditor('SrGrafo')
SUBREDDIT = REDDIT.subreddit('SrGrafo')
FIRST_ITER = True
retry = 2

flair_options = update_flair()

CONTEXT_TEMPLATE = '[Context for this post!]({:s})\n\nAlso, ' + \
                   'if you like SrGrafo, [support him on patreon!]' + \
                   '(https://www.patreon.com/SrGrafo)'

TIME_TEMPLATE = 'There are {:d} images to try and post. This will take about {:0.3f} ' + \
                'minutes, or {:0.3f} hours, or {:0.3f} days.'


REPLY_TEMPLATE = "To never miss one of SrGrafo's posts (or his edits), " + \
                 "make sure you subscribe to /r/SrGrafo.\n\nAnd if you like SrGrafo's " + \
                 'work, [support him on Patreon](https://www.patreon.com/SrGrafo)'

#download images hosted on reddit since linking seems to not work
#we need to make sure our folder exists
if not os.path.exists('./images'):
    os.mkdir('./images')

#how many items deep we want to check
check_limit = 1000
POSTED_IMAGES = []
print('entering loop')
while True:
    #Checks the flair to make sure all our flair templates are valid
    update_flair()

    update_post_images()
    update_comment_images()

    #post oldest comment first, then newest comment, then oldest post, then newest post
    iter_list = IMG_LIST[::-1]

    #time estimate
    print(TIME_TEMPLATE.format(len(IMG_LIST), len(IMG_LIST)*5, len(IMG_LIST)*5/60, \
                               ((len(IMG_LIST)*5)/60)/24))
    print('start posting')
    post_all_images()

    print('finished posting current batch. Wait 1 minute and try again')
    time.sleep(60)
    FIRST_ITER = False
