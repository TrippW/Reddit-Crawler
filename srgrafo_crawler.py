"""
This module scans all the posts and comments of one user and posts them to a subreddit
Attempts to not repost
"""
import urllib.request
import time
import os
import praw
import prawcore
import re

def check_for_new_posted_images(limit):
    """checks new posts in the subreddit and adds their urls and titles to a list"""
    global SUBREDDIT
    new_posts = SUBREDDIT.new(limit=limit)
    for post in new_posts:
        if post.url not in POSTED_IMAGES:
            POSTED_IMAGES.append(post.url)
            add_image_to_list(post.url)

def is_image(url):
    """checks if the url is an image"""
    return ('i.redd.it' in url) or (url.split('.')[-1] in ['jpg', 'png', 'jpeg', 'gif'])

def add_image_to_list(image):
    """record when we post an image"""
    global POSTED_LINKS
    url = image.encode('ascii', 'backslashreplace').decode('ascii')
    if url not in POSTED_LINKS:
        POSTED_LINKS.append(url)
        with open('posted_links.txt', 'a') as file:
           file.write(url+'\n')

def log_in():
    """
    log in to reddit
    uses a praw.ini file to hold sensitive information
    """
	
    return praw.Reddit(redirect_uri='http://localhost:8080', \
                       user_agent='SrGrafo Scraper by /u/devTripp')

def post_image(data):
    """post image to the subreddit"""
    #The post we created
    submission = None
    #Create the post
    submission = SUBREDDIT.submit(data['title'], \
                                  url=data['url'])
    #If the original post was nsfw, mark this nsfw
    if data['nsfw']:
        submission.mod.nsfw()
    #reply to the post we just made
    t_name = data['data'].replace('\n', '. ') \
             .replace('. . ', '. ') \
             .replace('..', '.') \
             .replace('?.', '?') \
             .replace('!.', '!')
    if t_name[-1] in ('\\', '/'):
        t_name = t_name[:-1]
    submission.reply(CONTEXT_TEMPLATE.format(t_name, \
                                             data['context']))
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
    else:
        flair_type = flair_options[3]
    return flair_type

def remove_nested_links(text):
    '''Removes the link portion of text and replaces it with the hyperlink text'''
    return ''.join(re.split('\[([^\n\r]+)\]\([^\n\r]+\)', text))

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
    check_for_new_posted_images(check_limit)
    for comment in USER_PROFILE.comments.new(limit=check_limit): #one call
        body_text = comment.body
        #Check if post is a comic (denoted by the famous edit)
        if 'EDIT' in body_text and '](' in body_text:
            #get the URL from the edit
            url = body_text.split('](')[1]
            url = url[:url.find(')')]
            #Check that it is an image and not already posted
            if (is_image(url)) and \
               (url not in IMG_LIST) and \
               (url not in POSTED_LINKS) and \
               (url not in POSTED_IMAGES):
                print('this looks new')
                data = 'Link to the original post!'
                parent = comment.parent()
                nsfw = None
                #gather the correct data from the parent comment or submission
                #and parse out the title
                if comment.is_root:
                    print('parent is a post')
                    title = parent.title.encode('ascii', 'ignore').decode('ascii')[:300]
                    nsfw = parent.over_18
                else:
                    print('parent is a comment')
                    person = parent.author.name if (parent.author) else 'Mystery user'
                    title = 'EDIT to {:s}'.format(person)
                    data = remove_nested_links(parent.body)
                    nsfw = parent.submission.over_18

                #add to the list of posts to make
                IMG_LIST.append({'url':url, \
                                 'title':title, \
                                 'context':parent.permalink,\
                                 'nsfw':nsfw,\
                                 'data':data})
                if IMG_LIST:
                    print(IMG_LIST[-1])
                    
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

    #this is one api call giving us 100 posts
    check_for_new_posted_images(check_limit)

    for post in USER_PROFILE.submissions.new(limit=check_limit):
        #check if the submission is a link to an image, has not been posted before, is not from a blacklisted subreddit
        if (post.url) and \
           (post.url not in IMG_LIST) and \
           (is_image(post.url)) and \
           (post.subreddit.display_name.lower() not in BLACKLIST_SUBS) and \
           (post.url not in POSTED_LINKS) and \
           (post.url not in POSTED_IMAGES) and \
           (post.title.encode('ascii', 'ignore').decode('ascii')[:300] not in POSTED_IMAGES):
            title = post.title.encode('ascii', 'ignore').decode('ascii')[:300]
            IMG_LIST.append({'url':post.url, \
                             'title':title, \
                             'context':post.permalink, \
                             'nsfw':post.over_18,
                             'data':'Link to the original post!'})
            #if we're playing catchup, we do not want to post redirect links to the subreddit.
            if not FIRST_ITER:
                if(post.subreddit.display_name.lower() == 'u_srgrafo'):
                    post.reply(PROFILE_REPLY_TEMPLATE)
                else:
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
            if i in IMG_LIST:
                    IMG_LIST.remove(i)
        else:
            print('submitting image {:40s} image #: {:3d}  complete: {:3.2f}%'.format( \
                i['title'][:40], iter_list.index(i)+1, ((iter_list.index(i)+1)*100/len(iter_list))))
            try:
                submission = post_image(i)
                #remove the image from our list
                if i in IMG_LIST:
                    IMG_LIST.remove(i)
            except praw.exceptions.APIException as err:
            #there was a problem with the api, wait for 5 minutes
                print("whoops, api error. Trying again in 30 seconds")
                print(err)
                time.sleep(30) #try again in 5 minutes
            except praw.exceptions.ClientException as err:
                #socket issue with the upload. It may have gone through
                print('Likely a socket issue. Wait 30 seconds to check')
                print(err)
                time.sleep(30)
                #checking if the post went through to see if we need to post again or
                #if we successfully posted the image
                if i['title'] not in [x.title for x in SUBREDDIT.new(limit=check_limit)]:
                    #try to post it again
                    print('Wasn\'t posted, try uploading again')
                    submission = post_image(i)
                else:
                    print('it was posted.')
                    #we posted the image, so we need to find it so we can post the context
                    for sub_post in SUBREDDIT.new(limit=check_limit):
                        if sub_post.title == i['title']:
                            submission = sub_post
                            break
                #post the context comment
                submission.reply(CONTEXT_TEMPLATE.format(i['context']))
                add_image_to_list(i['url'])
                #remove the image from our list
                if i in IMG_LIST:
                    IMG_LIST.remove(i)
            except prawcore.exceptions.ServerError as err:
                if '503' in err:
                    print('503 error! Wait 10 minutes and try again')
                    sleep(10*60)
                else:
                    print('Some other server error happened. Wait 2 minutes and try again')
                    sleep(2*60)
                
            except Exception as err:
                print("There was a problem.")
                print(err)


IMG_LIST = []
POSTED_LINKS = []

BLACKLIST_SUBS = ['rpvoid', 'pixelart', 'srgrafo', 'animesketch', 'animegifs']

if os.path.exists('./posted_links.txt') and os.path.isfile('./posted_links.txt'):
    with open('posted_links.txt', 'r') as link_file:
        POSTED_LINKS = link_file.read().split('\n')[:-1] #there is always one too many

REDDIT = log_in()

#setup
USER_PROFILE = REDDIT.redditor('SrGrafo')
SUBREDDIT = REDDIT.subreddit('edit')
FIRST_ITER = True

CONTEXT_TEMPLATE = '[Context for the post: {:s}]({:s})\n\nAlso, ' + \
                   'if you like SrGrafo and want more information, check out his profile ' + \
                   'here /u/SrGrafo\n\nIf you have any suggestions or need to get a hold of me, ' + \
                   'just reply to this post or shoot me a message. This is my main account as ' + \
                   'well, so I see all your messages.'

PROFILE_REPLY_TEMPLATE = "To never miss one of SrGrafo's posts (or his edits), " + \
                         'make sure you subscribe to /r/SrGrafo.'

REPLY_TEMPLATE = PROFILE_REPLY_TEMPLATE + "\n\nAnd if you like SrGrafo's " + \
                 'work, find more of it on his profile at /u/SrGrafo'



#download images hosted on reddit since linking seems to not work
#we need to make sure our folder exists
if not os.path.exists('./images'):
    os.mkdir('./images')

#how many items deep we want to check
check_limit = 300
POSTED_IMAGES = []
print('entering loop')
while True:
    #update_post_images()
    update_comment_images()

    #post oldest comment first, then newest comment, then oldest post, then newest post
    iter_list = IMG_LIST[::-1]

    print('start posting')
    post_all_images()

    print('finished posting current batch. Wait 1 minute and try again')
    time.sleep(60)
    FIRST_ITER = False
