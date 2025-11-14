import pandas as pd
import argparse


#%%
def get_group_stats(g):
    handoff_time =  g.loc[g.message_type=='user', 'created_utc'].min()
    post_handoff = g[g.created_utc > handoff_time]
    return pd.Series({
    'consented': 'handoff' in g.message_type.unique(),
    'num_messages_sent': sum(post_handoff.message_type == 'user'),
    'num_messages_received': sum(post_handoff.message_type == 'AI_reply'),
    'median_sent_length': post_handoff.loc[post_handoff.message_type == 'user', 'text'].str.len().median(),
    'median_received_length': post_handoff.loc[post_handoff.message_type == 'AI_reply', 'text'].str.len().median(),
    'mean_convo_toxicity': post_handoff.toxicity_score.mean(),
    'mean_convo_severe_toxicity': post_handoff.severe_toxicity_score.mean(),
    'max_convo_toxicity': post_handoff.toxicity_score.max(),
    'max_convo_severe_toxicity': post_handoff.severe_toxicity_score.max(), 
    # Choosing to define handoff as when the user first responds
    'handoff_time':  g.loc[g.message_type=='user', 'created_utc'].min(),
    'invitation_time': g.loc[g.message_type == "initial", 'created_utc'].min(),
    'last_message_time': g.created_utc.max()
    }) 


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--in-file", dest="in_file", help="Input file (conversations with the AI)")
    parser.add_argument("--out-file", dest="out_file", help="Output file")
    args = parser.parse_args()

    convos = pd.read_csv(args.in_file)
    convo_data = convos.groupby('user_id').apply(get_group_stats).reset_index()
    convo_data.to_csv(args.out_file, index=False)

if __name__ == '__main__':
    main()
