#%%
import csv
from perspective import PerspectiveAPI
import auth
import pandas as pd
import time

######
# This code takes the comments made by users, adds the subreddit that we contacted them from, and
# adds a toxicity score, if these don't yet exist. It then saves these files.
######

augmented_file = '../data/participant_data/augmented_comments.csv'
participant_comments_file = '../data/participant_comments.csv'
participants_file = '../data/participants.csv'
conversations_file = '../data/conversations.csv'
p = PerspectiveAPI(auth.perspective_api_key)
#%%

def get_toxicity(s, tests = ['TOXICITY', 'SEVERE_TOXICITY']):
    attempts = 0
    while True:
        try:
            toxicity  = p.score(s, tests=tests)
            return (toxicity['TOXICITY'], toxicity['SEVERE_TOXICITY'])
        except TypeError as e:
            print(f"TypeError for {s}")
            return (None, None)
        except Exception as e:
            if e.code == 400:
                return (None, None)
            else:
                print('Pausing for a bit')
                time.sleep(10)
                if attempts < 10:
                    attempts += 1
                    continue
                else:
                    print(f"Giving up on {s}")
                    return (None, None)

def get_convo_toxicity(g):
    text = g.loc[g.message_type == 'user', 'text'].str.cat(sep = ' ')
    lowered_text = text.strip().lower()
    if len(text) == 0 or lowered_text == 'yes' or lowered_text == 'no':
        return (None, None)
    return get_toxicity(text)

def get_group_stats(g):
    toxicity, severe_toxicity = get_convo_toxicity(g)
    return pd.Series({
    'consented': 'handoff' in g.message_type.unique(),
    'messages_sent': sum(g.message_type == 'user'),
    'ai_convo_toxicity' : toxicity,
    'ai_convo_severe_toxicity': severe_toxicity,
    'handoff_time':  g.loc[g.message_type=='user', 'created_utc'].min(),
    'last_message_time': g.created_utc.max()
    }) 


#%%
# Get conversation data about participants - whether consented, and how many messages they sent
convos = pd.read_csv(conversations_file)
convo_data = convos.groupby('user_id').apply(get_group_stats).reset_index()

print(convo_data.head())
#%%

# TODO:
# Filter to only a subset of those who never consented; get all data for the rest
# Save a file with a list of ids of the subset.


subreddits_dict = {}
with open(participants_file, 'r') as f:
    participant_file = csv.DictReader(f)
    for line in participant_file:
        subreddits_dict[line['author_id']] = line['subreddit']

try:
    augmented_df = pd.read_csv(augmented_file)
except FileNotFoundError:
    augmented_df = None

comments_df = pd.read_csv(participant_comments_file)

if augmented_df is not None:
    # Get the comments which aren't already in the augmented dataset
    print(f"Started with {len(comments_df)} comments")
    comments = comments_df[~(comments_df.text + comments_df.created_utc.astype(str) + comments_df.author_id).isin((augmented_df.text + augmented_df.created_utc.astype(str) + augmented_df.author_id))]
    # TODO: Remove this filter when we want to get scores for everyone
    consented_users = convo_data.loc[convo_data.consented == True, 'user_id']
    comments = comments[comments.author_id.isin(consented_users)]
    print(f"Now we have {len(comments)} comments to augment")
else:
    comments = comments_df

header = ['created_utc', 'text', 'subreddit', 'author_id', 'toxicity_score', 'severe_toxicity_score', 'messaged_subreddit']
if augmented_df is None:
    with open(augmented_file, 'w') as f:
        out_file = csv.writer(f)
        out_file.writerow(header)

with open(augmented_file, 'a') as f:
    out_file = csv.DictWriter(f, fieldnames = header)
    for _, comment in comments.iterrows():

        # Turning this into a loop so that we try again when we hit a 429 error
        attempts = 1
        tox_scores = get_toxicity(comment['text'])
        if not tox_scores:
            continue
        else:
            comment['toxicity_score'] = tox_scores[0]
            comment['severe_toxicity_score'] = tox_scores[1]
            comment['messaged_subreddit'] = subreddits_dict[comment['author_id']]
            out_file.writerow(comment.to_dict())

## I forgot to add the conditions, so I'm just doing that at the end.

## TODO: Add conversation length
#%%
aug_comments_df = pd.read_csv(augmented_file)
participants_df = pd.read_csv(participants_file)

aug_comments = aug_comments_df.merge(participants_df.loc[:,['author_id', 'condition']], on='author_id', how='left')
aug_comments = aug_comments.merge(convo_data,left_on='author_id', right_on='user_id', how='left')

print(aug_comments)
aug_comments.drop(columns=['user_id']).to_csv('../data/participant_data/augmented_final.csv', index=False)
aug_comments.drop(columns=['user_id']).to_feather('../data/participant_data/augmented_final.feather')

