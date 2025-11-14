import praw
import csv
import auth
import datetime
from tqdm import tqdm
import pandas as pd
import os
import json
from prawcore.exceptions import NotFound, TooManyRequests, Forbidden
import time
import logging
import argparse

parser = argparse.ArgumentParser()
parser.add_argument( '-log',
                     '--loglevel',
                     default='warning',
                     help='Provide logging level. Example --loglevel debug, default=warning' )

args = parser.parse_args()

logging.basicConfig(level=args.loglevel.upper() )
logging.info( 'Logging now setup.' )

## TODO: Figure out where all of the comments are coming from. If it's too many users, drop a bunch
# of unconsented, and change the proportion

def get_unames(conversations_fn, 
               participants_fn,
               unconsented_sample_fn, 
               unconsented_prop = .2):

    # Get the consented users (we'll get comments for all of them)
    df = pd.read_csv(conversations_fn)
    df = df.loc[(pd.notna(df.subreddit)) & (df.subreddit != 'survey_invite_testing'), :]
    consented_ids = df.loc[df.message_type == 'handoff', 'user_id']

    # Now, get the unconsented users. We keep a temp file of the ids we've already sampled.
    # We filter to those that are newer than these, and then sample from those
    unconsented = df.loc[~df.user_id.isin(consented_ids), :]
    # Just keep the first message sent
    unconsented = unconsented.groupby('user_id')['created_utc'].min().reset_index()
    try:
        with open(unconsented_sample_fn, 'r') as f:
            already_sampled = json.load(f)
        last_run = max(unconsented[unconsented.user_id.isin(already_sampled)]['created_utc'])
        already_sampled = [x for x in already_sampled if x not in list(consented_ids)]
    except Exception as e:
        print(e)
        last_run = None
        already_sampled = []
    if last_run:
        # If we've run before, then only sample from new participants
        unconsented = unconsented[unconsented.created_utc > last_run]
    unconsented_ids = unconsented.user_id.sample(frac=unconsented_prop)

    with open(unconsented_sample_fn, 'w') as f:
        json.dump(already_sampled + list(unconsented_ids), f)


    combined_ids = list(consented_ids) + list(unconsented_ids) + already_sampled

    

    assert len(combined_ids) == len(set(combined_ids))

    # Add the uncontacted sample
    participants_df = pd.read_csv(participants_fn)
    uncontacted_ids = participants_df.loc[participants_df.condition == 'uncontacted_control', 'author_id']
    assert(uncontacted_ids.isin(combined_ids).sum() == 0)
    combined_ids += list(uncontacted_ids)
    # Get the usernames for the combined ids
    usernames = participants_df.loc[participants_df.author_id.isin(combined_ids), ['author', 'author_id']]
    # Add a row for whether they consented
    usernames['participant'] = usernames.author_id.isin(consented_ids)
    print(sum(usernames.author_id.isin(uncontacted_ids)))
    return usernames


def fetch_all_comments(usernames, reddit, out_f, suspended_f):
    try:
        df = pd.read_csv(out_f)
        #df = df.groupby('author_id')['created_utc']
    except FileNotFoundError:
        df = pd.DataFrame({'author_id': []})
    day_of_week = datetime.datetime.now(datetime.UTC).weekday()
    # Go through the usernames (randomly shuffled) and get data for each one
    for _, row in usernames.sample(frac=1).iterrows():
        username = row.author 
        user_id = row.author_id
        is_participant = row.participant
        ## This is hacky. Make it better. For now, just getting the full set once
        # per week
        if is_participant == False and day_of_week != 4:
            continue
        curr_comments = []
        try:
            user = reddit.redditor(username)
            # check if username already present in the comments file
        except praw.exceptions.RedditAPIException as e:
            print(f"An error occurred for {username}: {str(e)}")
            continue
        try:
            user.is_suspended
            add_status(user_id, 'suspended', suspended_f)
            continue
        except AttributeError:
            pass
        except NotFound:
            add_status(user_id, 'removed', suspended_f)
            continue
        except Forbidden:
            print(f"{user.name} messages are forbidden")
            continue
        except TooManyRequests:
            time.sleep(60)
        add_status(user_id, 'exists', suspended_f)
        if user_id in df.author_id.unique():
            last_retrieved_time = df.loc[df.author_id == user_id, 'created_utc'].max()
        else:
            logging.info(f"Didn't find {user_id} in the dataset")
            last_retrieved_time = None
        logging.info(f"Last retrieved time for {user_id} is {last_retrieved_time}")

        curr_oldest_comment = None
        for comment in user.comments.new(limit=None):
            if curr_oldest_comment == None:
                curr_oldest_comment = comment.created_utc
            # If this comment is newer than the oldest comment before it, then something went wrong
            if comment.created_utc > curr_oldest_comment:
                logging.warning(f"Comment from {user} appears to be out of order")
            else:
                curr_oldest_comment = comment.created_utc
            if last_retrieved_time and comment.created_utc <= last_retrieved_time:
                break
            try:
                body = clean_text(comment.body)
                curr_comments.append({
                    'created_utc': comment.created_utc,
                    'text' : body,
                    'subreddit' : comment.subreddit.display_name,
                    'author_id': user_id
                })
            except TooManyRequests:
                time.sleep(60)
        logging.info(f"Adding {len(curr_comments)} comments for {username}")
        write_comments(out_f, curr_comments)
        if len(curr_comments) > 50:
            time.sleep(3)
        else:
            time.sleep(2)

def clean_text(s):
    s = s.strip()
    s = s.replace('\r\n', '\n')
    return s


def write_comments(fn, comments):
    header = ['created_utc', 'text', 'subreddit', 'author_id']
    if not os.path.exists(fn):
        with open(fn, 'w', newline='') as f:
            out = csv.writer(f)
            out.writerow(header)
    
    with open(fn,'a', newline='') as f:
        out = csv.DictWriter(f, fieldnames = header)
        out.writerows(comments)


def add_status(user, status, suspended_file):
    if not os.path.exists(suspended_file):
        with open(suspended_file, 'w') as f:
            out = csv.writer(f)
            out.writerow(['user_id', 'date', 'status'])
    with open(suspended_file, 'a') as f:
        out = csv.writer(f)
        out.writerow([user,
                      datetime.datetime.now().date(),
                      status
                      ])

if __name__ == "__main__":
    reddit = praw.Reddit(
        client_id=auth.client_id,
        client_secret=auth.client_secret,
        username = auth.username,
        password = auth.password,
        user_agent=auth.u_agent
    )
    
    conversations_file = './data/conversations.csv'
    username_file = './data/participants.csv'
    output_file = './data/participant_comments.csv'
    unconsented_sample = './data/unconsented_sample_ids.csv'
    suspended_file = './data/participant_data/suspended_ids.csv'


    
    
    usernames = get_unames(conversations_fn=conversations_file,
                            participants_fn=username_file,
                            unconsented_sample_fn=unconsented_sample)
    fetch_all_comments(usernames, reddit, out_f = output_file, suspended_f=suspended_file)