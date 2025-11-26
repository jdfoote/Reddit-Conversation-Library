#%%
import pandas as pd
import re
import glob
from pandas.errors import EmptyDataError
import uuid
import numpy as np


modlogs_dir = '../data/modlogs/'
subs = ['aww', 'creepypms', 'futurology', 'india', 'socialskills', 'tifu', 'unitedstatesofindia']
dfs = []
def filter_actions(mod_dir, contacted):
    dfs = []
    for sr in subs:
        expression = re.compile(f"{sr}-")
        flist = [x.lower() for x in glob.glob(f"{mod_dir}/*")]
        flist = [x for x in flist if re.search(expression, x)]
        if len(flist) == 0:
            raise Exception(f"Didn't get any moderation data for {sr}")
        curr_dfs = []
        for f in flist:
            try:
                curr_dfs.append(pd.read_csv(f))
            except EmptyDataError:
                continue
        curr_df = pd.concat(curr_dfs, axis=0, ignore_index=True)
        curr_df = curr_df.drop_duplicates()
        curr_df['subreddit'] = sr
        # Filter out the NAs (TODO: figure out why they are there)
        curr_df = curr_df[curr_df.moderation_details == 'remove']
        # Filter out those already contacted
        curr_df = curr_df[~curr_df.target_author.isin(contacted)]
        dfs.append(curr_df)
    return pd.concat(dfs, axis=0, ignore_index=True)

contacted = pd.read_csv('../data/to_contact.csv').author

df = filter_actions(modlogs_dir, contacted)
#%%

# Get the top 300 potential controls, with tox scores just under our
# threshold and whose comment came after we started the study with all subreddits
df = df.sort_values('tox_score', ascending=False)
df.drop_duplicates('target_author', inplace=True)
potential_controls = df.loc[(df.tox_score < .7) & (df.created_utc > 1700179200)].sort_values('tox_score', ascending=False).head(300)

assert(len(potential_controls.target_author.unique()) == 300)

potential_controls.to_csv('../data/potential_controls.csv', index=False)

# Match columns to the participants.csv file
potential_controls['author'] = potential_controls['target_author']
potential_controls['toxic_comments'] = potential_controls['target_body']
potential_controls['author_id'] = [uuid.uuid4() for _ in range(300)]
potential_controls['condition'] = 'uncontacted_control'
potential_controls['messaging_strategy'] = np.nan
potential_controls['openai_model'] = np.nan
potential_controls['first_consented_msg'] = np.nan
potential_controls['initial_message'] = np.nan

# Reorder columns
potential_controls = potential_controls[['author', 'author_id', 'condition', 'subreddit', 'toxic_comments', 'messaging_strategy', 'openai_model', 'first_consented_msg', 'initial_message']]

participants = pd.read_csv('../data/participants.csv')
participants_combined = pd.concat([participants, potential_controls], axis=0, ignore_index=True)
assert(len(participants_combined) == 300 + len(participants))

participants_combined.to_csv('../data/participants.csv', index=False)

# %%
