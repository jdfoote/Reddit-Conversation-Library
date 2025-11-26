import argparse
import csv
import pandas as pd
from get_toxicity import get_toxicity
import os.path
import logging
import re
from pandas.errors import EmptyDataError
import glob

#%%
def filter_actions(mod_dir, participant_data):
    dfs = []
    for sr in participant_data.subreddit.unique():
        if sr == 'survey_invite_testing':
            continue
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
        dfs.append(curr_df)
    full_df = pd.concat(dfs, axis=0, ignore_index=True)
    logging.info(f"Starting with {len(full_df)} moderation actions")
    full_df = full_df[full_df.moderation_details == 'remove']
    logging.info(f"{len(full_df)} moderation actions that are removals")
    filtered_df = full_df[full_df.target_author.isin(participant_data.author)]
    logging.info(f"{len(filtered_df)} moderation actions that include our participants")
    filtered_df['user_id'] = filtered_df.target_author.map(participant_data.set_index('author')['author_id'])
    del(filtered_df['target_author'])
    return filtered_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mod-dir', 
                        dest='moderation_dir',
                        help="Input file (without toxicity scores)")
    parser.add_argument('--out-file', dest='out_f', help="Output file (conversations and toxicity scores)")
    parser.add_argument('--participant-file', dest='participant_file', help="Participant file to filter moderation actions")
    parser.add_argument( '-log',
                     '--loglevel',
                     default='warning',
                     help='Provide logging level. Example --loglevel debug, default=warning' )
    args = parser.parse_args()
    logging.basicConfig( level=args.loglevel.upper() )
    logging.info( 'Logging now setup.' )

    augmented_file = args.out_f
    participant_df = pd.read_csv(args.participant_file)
    filtered_df = filter_actions(args.moderation_dir, participant_df)
    filtered_df.to_csv(augmented_file, index = False)

if __name__ == '__main__':
    main()

