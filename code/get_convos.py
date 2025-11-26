import pandas as pd
import datetime

OUT_FILE = '../data/filtered_convos.csv'

# Open config file
import yaml
# Open and read the YAML file
with open('shared_config.yaml', 'r') as file:
    config = yaml.safe_load(file)

df = pd.read_csv(config['conversations_file'])

df = df.sort_values('created_utc')

df['combined_text'] = '\n' + df.message_type + ':\n' + df.text

agg_df = df.groupby('user_id').agg(
    conversation = ('combined_text', lambda x: '\n'.join(x)),
    first_message = ('created_utc', lambda x: datetime.datetime.fromtimestamp(x.min())),
    subreddit = ('subreddit', 'first')
)

agg_df = agg_df[agg_df.conversation.str.contains('AI_reply:')]
agg_df = agg_df[agg_df.subreddit != 'survey_invite_testing']

agg_df = agg_df.sort_values('first_message').reset_index()

participants_df = pd.read_csv('../data/participants.csv')

combined_df = agg_df.merge(participants_df, how='left', left_on = ['user_id', 'subreddit'], right_on=['author_id', 'subreddit'])
del(combined_df['toxic_comments'])
del combined_df['author']

combined_df.to_csv(OUT_FILE, index=False)
