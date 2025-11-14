import praw
import invite_config
import random
import logging
from prawcore.exceptions import Forbidden
from prawcore.exceptions import NotFound
from praw.exceptions import RedditAPIException


max_size = 8000000000
min_size = 1000
n_sr_to_contact = 3

#logging.basicConfig(level=logging.DEBUG)

def contact_sr(sr, conn):
    subject = 'Toxic comment intervention study'
    msg = f'''Hello r/{sr} moderators,

My name is Jeremy Foote—I am a Communication professor at Purdue University in the USA. I am part of a research team that is working to design interventions to help with toxic content on Reddit. Based on communication theories, we are developing a set of chatbots intended to help those who post toxic content to change their behavior.

The bot is currently active on a few subreddits, and the initial results have been promising.

We are wondering if your moderation team would be willing to consider participating in our study? We are hopeful that our interventions will help communities to be safer and will help users learn to engage more prosocially.

If you choose to participate, what would that mean?

Subreddits who choose to participate would make our bot a mod on your subreddit, with the modmail permission. The bot would look through the modlogs to identify extremely toxic comments which have been removed. The bot would then use modmail to send a message to a random set of users who posted these toxic comments, inviting them to begin a conversation via DM. The bot would identify itself as a bot, and would offer to talk with the user about their behavior. There are a few different conditions, such as a bot that focuses on using stories to try to persuade users. All of the bots are instructed to be patient and non-confrontational.

We will use both modlogs and public comments to look at whether the users who are contacted by our bot reduce toxic behavior more than the users that are not contacted. We will also analyze the content of the conversations that users have with our bots.

A webpage describing the project (and which is shared in our initial message with users) is at https://wiki.communitydata.science/Chatbot_study_consent.

Would you be willing to consider participating in our research? If you're open to discussing it, please either respond to me on Reddit or via email at jdfoote@purdue.edu.

Thanks so much for your time.

Jeremy'''
    try:
        conn.subreddit(sr).message(subject=subject, message=msg)
    except (NotFound, RedditAPIException) as e:
        print(e)
        return e


def main():
    reddit = praw.Reddit(
        client_id=invite_config.client_id,
        client_secret=invite_config.client_secret,
        user_agent=invite_config.u_agent,
        username=invite_config.username,
        password=invite_config.password
    )

    candidates = []
    with open(invite_config.sr_to_contact_file, 'r') as f:
        for line in f.readlines():
            candidates.append(line.strip())
    n_candidates = len(set(candidates))

    contacted = []
    with open(invite_config.contacted_file, 'r') as f:
        for line in f.readlines():
            contacted.append(line.strip())

    candidates = set(candidates) - set(contacted)

    assert len(candidates) < n_candidates
    assert len(candidates) > 0
    candidates = list(candidates)
    print(candidates)

    to_contact = []
    while len(to_contact) < n_sr_to_contact and len(candidates) > 0:
        curr_sr = random.choice(candidates)
        print(curr_sr)
        if curr_sr in to_contact:
            continue
        try:
            curr_sr_subscribers = reddit.subreddit(curr_sr).subscribers
            print(curr_sr_subscribers)
        except Forbidden:
            logging.error(f"We can't get subscribers for {curr_sr}")
            candidates.remove(curr_sr)
            continue
        except NotFound:
            logging.error(f"The subreddit {curr_sr} doesn't seem to exist")
            candidates.remove(curr_sr)
            continue

        if curr_sr_subscribers > max_size or curr_sr_subscribers < min_size:
            candidates.remove(curr_sr)
            continue
        to_contact.append(curr_sr)
        candidates.remove(curr_sr)


    for sr in to_contact:
        logging.debug(f'Contacting subreddit {sr}')
        contact_sr(sr, conn=reddit)
        with open(invite_config.contacted_file, 'a') as f:
            f.write(f"{sr}\n")


if __name__ == '__main__':
    main()
