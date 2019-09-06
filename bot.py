#!/usr/bin/env python3
"""Reddit Bot that provides downloadable links for v.redd.it videos"""

import time
import re
import os
from urllib.request import Request, urlopen

import praw
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import certifi
import youtube_dl
import requests
from praw.models import Comment
from praw.models import Message


# Constants
BOT_NAME = "u/vredditDownloader"
NO_FOOTER_SUBS = ('furry_irl', 'pcmasterrace', 'bakchodi', 'pakistan')
PM_SUBS = ('funny', 'mademesmile', 'Rainbow6')
DATA_PATH = '/home/pi/bots/vreddit/data/'
COMMENTED_PATH = '/home/pi/bots/vreddit/data/commented.txt'
VIDEO_FORMAT = '.mp4'
BLACKLIST_SUBS = ("The_Donald")
BLACKLIST_USERS = ('null')
ANNOUNCEMENT_MOBILE = "\n\nUse your mobile browser if your app has problems opening my links."
ANNOUNCEMENT_PM = "\n\nI also work with links sent by PM."
HEADER = "^I\'m&#32;a&#32;Bot&#32;*bleep*&#32;*bloop*"
INFO = "[**Info**](https://np.reddit.com/r/VredditDownloader/comments/b61y4i/info)"
CONTACT = "[**Contact&#32;Developer**](https://np.reddit.com/message/compose?to=/u/JohannesPertl)"
DONATE = "[**Contribute**](https://np.reddit.com/r/vredditdownloader/wiki/index)"
FOOTER = "\n\n&nbsp;\n ***  \n ^" + INFO + "&#32;|&#32;" + CONTACT + "&#32;|&#32;" + DONATE
INBOX_LIMIT = 10
RATELIMIT = 2000000
MAX_FILESIZE = 200000000

# Determines if videos without sound get uploaded to external site or linked via direct v.redd.it link
ALWAYS_UPLOAD = True


def main():
    reddit = authenticate()
    while True:
        # Search mentions in inbox
        inbox = list(reddit.inbox.unread(limit=INBOX_LIMIT))
        inbox.reverse()
        for item in inbox:
            author = str(item.author)

            # Check requirements
            match_type = type_of_item(item)
            if not match_type:
                continue
            elif match_type == "comment":
                submission = item.submission
                announcement = ANNOUNCEMENT_PM
            else:  # match_type is message
                submission = get_real_reddit_submission(reddit, match_type)
                announcement = ""

            try:
                if not submission or "v.redd.it" not in str(submission.url) or str(
                        submission.subreddit) in BLACKLIST_SUBS or author in BLACKLIST_USERS:
                    continue
            except Exception as e:
                print(e)
                continue

            # Get media and audio URL
            media_url = create_media_url(submission, reddit)
            if not media_url:
                media_url = submission.url
                reply_no_audio = ""
            else:
                reply_no_audio = '* [**Direct link**](' + media_url + ')'

            audio_url = media_url.rpartition('/')[0] + '/audio'
            has_audio = check_audio(audio_url)
            reply_audio_only = ""
            if has_audio:
                reply_audio_only = '* [**Audio only**](' + audio_url + ')'
                reply_no_audio = '* [**Direct soundless link**](' + media_url + ')'

            reply = reply_no_audio
            if ALWAYS_UPLOAD or has_audio or media_url == submission.url:

                download_path = DATA_PATH + 'downloaded/' + str(submission.id) + VIDEO_FORMAT
                upload_path = DATA_PATH + 'uploaded/' + str(submission.id) + '.txt'

                # Upload
                uploaded_url = upload(submission, download_path, upload_path)
                if uploaded_url:
                    # Create log file with uploaded link, named after the submission ID
                    create_uploaded_log(upload_path, uploaded_url)
                    if "vredd.it" in uploaded_url:
                        direct_link = "* [**Download** via https://vredd.it]("
                    elif "ripsave" in uploaded_url:
                        direct_link = "* [**Download** via https://ripsave.com**]("
                    elif "lew.la" in uploaded_url:
                            direct_link = "* [**Download** via https://lew.la]("
                    else:
                        direct_link = "* [**Download**]("
                    try:
                        reply_audio = direct_link + uploaded_url + ")"
                        reply = reply_audio + '\n\n' + reply_no_audio + '\n\n' + reply_audio_only
                    except Exception as e:
                        print(e)
                elif has_audio:
                    reply = "Sry, I can only provide a soundless video at the moment. Please try again later. \n\n" + reply_no_audio

            reply = reply + announcement
            reply_to_user(item, reply, reddit, author)

            time.sleep(2)

def upload_catbox(file_path):
    """Upload via catbox.moe"""
    try:
        files = {
            'reqtype': (None, 'fileupload'),
            'fileToUpload': (file_path, open(file_path, 'rb')),
        }
        response = requests.post('https://catbox.moe/user/api.php', files=files)
        return response.text
    except Exception as e:
        print(e)
        print("Uploading failed.")
        return ""


def download(download_url, download_path):
    try:
        ydl_opts = {
            'outtmpl': download_path,
            # 'format': 'bestvideo',        #uncomment for video without audio only, see youtube-dl documentation
            'max_filesize': MAX_FILESIZE,
            'ratelimit': RATELIMIT,
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([download_url])
        return download_path

    except Exception as e:
        print('ERROR: Downloading failed.')
        print(e)
        return ""


def authenticate():
    """Authenticate via praw.ini file, look at praw documentation for more info"""
    print('Authenticating...\n')
    reddit = praw.Reddit('vreddit', user_agent='vreddit')
    print('Authenticated as {}\n'.format(reddit.user.me()))
    return reddit


def upload_via_lewla(url):
    """Upload Video via lew.la"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    webpage_url = 'https://lew.la/reddit/'
    driver.get(webpage_url)

    url_box = driver.find_element_by_id('url-input')

    url_box.send_keys(url)

    download_button = driver.find_element_by_class_name('download-button')
    download_button.click()

    for i in range(100):
        try:
            uploaded_url = driver.find_element_by_partial_link_text(".mp4").get_attribute('href')
            driver.quit()
            return uploaded_url
        except:
            continue

    driver.quit()
    return ""


def upload_via_vreddit(url):
    """Upload Video via https://vredd.it"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(chrome_options=options)
    webpage_url = 'https://vredd.it'
    driver.get(webpage_url)

    url_box = driver.find_element_by_id('r_url')

    url_box.send_keys(url)

    login_button = driver.find_element_by_id('submit_url')
    login_button.click()

    for i in range(100):
        try:
            driver.find_element_by_xpath("//*[text()='Play Video']")
            break
        except:
            continue
    uploaded_url = driver.find_element_by_class_name('btn').get_attribute('href')
    driver.quit()
    return uploaded_url


def upload_via_ripsave(url):
    """Upload Video via https://ripsave"""
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(chrome_options=options)
    webpage_url = 'https://ripsave.com/reddit-video-downloader'
    driver.get(webpage_url)

    url_box = driver.find_element_by_name('video')
    url_box.send_keys(url)

    login_button = driver.find_element_by_id('btnGetvideo')
    login_button.click()

    found_url = False
    for i in range(100):
        try:
            driver.find_element_by_xpath("//*[text()='Your video is ready to download']")
            found_url = True
            break
        except:
            continue
    if found_url:
        uploaded_url = driver.current_url
    else:
        uploaded_url = ""
    driver.quit()
    return uploaded_url


def check_audio(url):
    """Check if v.redd.it link has audio"""
    try:
        req = Request(url)
        resp = urlopen(req)
        resp.read()
        return True
    except:
        return False

    
def create_uploaded_log(upload_path, uploaded_url):
    """Create .txt file that contains uploaded url"""
    try:
        print('Creating txt file.')
        with open(upload_path, "w+") as f:
            f.write(uploaded_url)
    except Exception as e:
        print(e)
        print("ERROR: Can't create txt file.")

     
def reply_per_pm(item, reply, reddit, user):
    pm = reply + FOOTER
    subject = "I couldn't reply to your comment so you get a PM instead :)"
    print("Can't comment. Replying per PM.")
    reddit.redditor(user).message(subject, pm)
    item.mark_read()
    
    
def reply_to_user(item, reply, reddit, user):
    """Reply per comment"""
    if str(item.subreddit) in NO_FOOTER_SUBS:
        footer = ""
    else:
        footer = FOOTER
    print('Replying... \n')
    if str(item.subreddit) in PM_SUBS:
        reply_per_pm(item, reply, reddit, user)
    else:
        try:
            item.reply(reply + footer)
            item.mark_read()

        # Send PM if replying to the comment went wrong
        except Exception as e:
            print(e)
            try:
                reply_per_pm(item, reply, reddit, user)
            except Exception as f:
                print(f)


def is_url_valid(url):
    try:
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        urlopen(req, cafile=certifi.where())
    except Exception as e:
        return False
    else:
        return True

def create_media_url(submission, reddit):
    """Read video url from reddit submission"""
    media_url = "False"
    try:
        media_url = submission.media['reddit_video']['fallback_url']
        media_url = str(media_url)
    except Exception as e:
        print(e)
        try:
            crosspost_id = submission.crosspost_parent.split('_')[1]
            s = reddit.submission(crosspost_id)
            media_url = s.media['reddit_video']['fallback_url']
        except Exception as f:
            print(f)
            print("Can't read media_url, skipping")

    return media_url


def get_real_reddit_submission(reddit, url):
    try:
        link = re.sub('DASH.*', '', url)
        return reddit.submission(url=requests.get(link).url)
    except Exception as e:
        return ""
        print(e)

def type_of_item(item):
    """Check if item to reply to is comment or private message"""
    body = str(item.body)
    match_text = re.search(r"(?i)" + BOT_NAME, body)
    match_link = re.search(
        r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)", body)

    if isinstance(item, Comment) and match_text:
        return "comment"

    elif isinstance(item, Message) and match_link:
        return match_link[0]

    return ""


def uploaded_log_exists(upload_path):
    """Check if video has been uploaded before"""
    if not os.path.exists(upload_path):
        return ""

    try:
        with open(upload_path, 'r') as content_file:
            uploaded_url = content_file.read()
            if not is_url_valid(uploaded_url):
                print("Old URL not valid anymore, deleting..")
                os.remove(upload_path)
                return ""
            return uploaded_url
    except Exception as e:
        print(e)
        print("Couldn't get URL, continuing..")
        return ""


def upload(submission, download_path, upload_path):
    """Check if already uploaded before"""
    print("Check uploaded log")
    uploaded_url = uploaded_log_exists(upload_path)
    if uploaded_url:
        return uploaded_url


    permalink = "https://www.reddit.com" + submission.permalink
    
    try:
        print("Uploading via lew.la")
        uploaded_url = upload_via_lewla(permalink)
        if is_url_valid(uploaded_url):
            return uploaded_url
    except Exception as e:
        print(e)

    try:
        print("Uploading via Ripsave")
        uploaded_url = upload_via_ripsave(permalink)
        if is_url_valid(uploaded_url):
            return uploaded_url
    except Exception as e:
        print(e)

    print("Downloading..")
    download_path = download(submission.url, download_path)
    
    print("Uploading to catbox.moe")
    uploaded_url = upload_catbox(download_path)
    if uploaded_url:
        os.remove(download_path)
    return uploaded_url


if __name__ == '__main__':
    main()
