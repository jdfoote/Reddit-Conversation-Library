#%%
import praw
import csv
from perspective import PerspectiveAPI
import auth
import sys
import time
import pandas as pd
import os
import logging
import re

# Open config file
import yaml
# Open and read the YAML file
with open('shared_config.yaml', 'r') as file:
    config = yaml.safe_load(file)

# Set up globals
reddit = praw.Reddit(
        client_id = auth.client_id,
        client_secret = auth.client_secret,
        user_agent = auth.u_agent,
        username = auth.username,
        password = auth.password
)
#%%
p = PerspectiveAPI(auth.perspective_api_key)
CLASSIFIERS = ["TOXICITY", "SEVERE_TOXICITY"]

# Regex to remove quoted text
remove_pattern = re.compile(r'^>.*\n', re.MULTILINE)

subreddits = ['creepypms', 'socialskills', 'india', 'unitedstatesofindia', 'aww', 'tifu','futurology']

script_dir = os.path.dirname(os.path.abspath(__file__))
to_contact_file = os.path.join(script_dir, config['to_contact_file'])
contacted = pd.read_csv(to_contact_file)

# Set up writer
out_file =  os.path.join(script_dir, '../tox_users_to_contact.csv')
f = open(out_file, 'w')
writer = csv.writer(f)
writer.writerow(['author','subreddit', 'toxic_comments', 'timestamp', 'moderator', 'tox_score'])


def get_toxic_comments(subreddit, max_comments = 20, limit = 100):
    comment_count = 0
    try:
        last_contacted = max(contacted.loc[(contacted.subreddit==subreddit) & (pd.notna(contacted.timestamp)), 'timestamp'])
    except ValueError:
        last_contacted = 0
    for log in reddit.subreddit(subreddit).mod.log(limit=limit):
        # Load relevant items
        action = log.action
        moderator = log.mod
        target_body = log.target_body
        target_author = log.target_author
        timestamp = log.created_utc
        details = log.details


        # Ignore all moderation actions except for comment removals
        if action != "removecomment":
            continue


        # If this is earlier than a previous contact then break
        if timestamp <= last_contacted:
            logging.info('Earlier than last existing. Stopping')
            break

        # Get Perspective scores
        score_map = get_toxicity_scores(target_body)
        if not score_map:
            continue
        tox_score = score_map['TOXICITY']
        severe_tox_score = score_map['SEVERE_TOXICITY']
        if moderator == "AutoModerator" or moderator == "reddit":
            if tox_score < .85:
                continue
        if tox_score < .7:
            continue

        writer.writerow([target_author, subreddit, target_body, timestamp, moderator, tox_score])
        comment_count += 1
        if comment_count == max_comments:
            break
        time.sleep(.01)


def get_toxicity_scores(orig_text):
    # Strip out quoted text
    text = remove_pattern.sub('', orig_text)
    if text != orig_text:
        logging.info(f"{orig_text} changed to {text}")    
    try:
        score_map = p.score(text, tests=CLASSIFIERS)
    except Exception as e:
        logging.info(f"Received exception {e}")
        score_map = None
    return score_map

# alternative function using keywords
def get_users_by_keywords(subreddits, keywords, reddit, *kargs):
    """
    Returns a set of usernames who have used any keyword in any of the subreddits.

    Inputs:
        - subreddits (list): List of subreddit names
        - keywords (list): List of keywords (case-insensitive)
        - reddit (praw.Reddit): Authenticated PRAW Reddit instance
        - limit_per_subreddit (int): Number of comments to fetch per subreddit
        - *kargs: Optional keyword arguments.
            - limit_per_subreddit (int, optional): Maximum number of comments 
                                                   to process per subreddit.
    Returns:
        Set of usernames

    Example usage:

    reddit = praw.Reddit(client_id="my_id",
                         client_secret="my_secret",
                         user_agent="my_agent"
                        )
    keywords = ['toxic', 'help', 'question']
    subreddits = ['socialskills', 'india']
    
    users = get_users_by_keywords(subreddits, keywords, reddit)

    """

    if 'limit_per_subreddit' in kargs:
        limit_per_subreddit = kargs['limit_per_subreddit']
    else:
        limit_per_subreddit = None


    matched_users = set()
    keywords_lower = [kw.lower() for kw in keywords]
    for subreddit_name in subreddits:
        comment_count = 0
        subreddit = reddit.subreddit(subreddit_name) 
        submissions = subreddit.new()
        print(f"Searching r/{subreddit_name} for keywords...")
        for submission in submissions:
            comments = submission.comments
            try:
                for comment in comments:
                    comment_text = comment.body.lower()
                    comment_count +=1
                    if any(kw in comment_text for kw in keywords_lower):
                        if comment.author:
                            matched_users.add(comment.author.name)
                    if limit_per_subreddit:
                        if comment_count >= limit_per_subreddit:
                            break
            except Exception as e:
                print(f"Error in r/{subreddit_name}: {e}")
                continue
        if limit_per_subreddit:
            if comment_count >= limit_per_subreddit:
                break
    return matched_users


def main():
    for s in subreddits:
        get_toxic_comments(s, max_comments=80, limit=None)
    f.close()
    new_to_contact = pd.read_csv(out_file)
    combined_file = pd.concat([contacted, new_to_contact], ignore_index=True)
    combined_file.to_csv(to_contact_file, index=False)
    


if __name__ == "__main__":
    main()