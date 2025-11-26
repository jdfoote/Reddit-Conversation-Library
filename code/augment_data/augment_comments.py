import csv
import auth
import pandas as pd
import get_toxicity
import argparse
import logging
import os.path

######
# This code takes the comments made by users, adds the subreddit that we contacted them from, and
# adds a toxicity score, if these don't yet exist. It then saves these files.
######

#%%

def filter_comments(comments_df, augmented_df, only_consented = False):
    logging.info(f"Started with {len(comments_df)} comments")
    if augmented_df is not None:
        # Get the comments which aren't already in the augmented dataset
        # Don't get toxicity for comments if the created_utc + author is already in the augmented file
        comments_df = comments_df[~(comments_df.created_utc.astype(str) + comments_df.author_id).isin((augmented_df.created_utc.astype(str) + augmented_df.author_id))]
    if only_consented:
        logging.warning("Not yet implemented")
        #consented_users = convo_data.loc[convo_data.consented == True, 'user_id']
        #comments = comments[comments.author_id.isin(consented_users)]
    logging.info(f"Now we have {len(comments_df)} comments to augment")
    # Remove NaNs
    comments_df = comments_df[pd.notna(comments_df.text)]
    return comments_df

def add_toxicity(comments, augmented_file):
    header = ['created_utc', 'text', 'subreddit', 'author_id', 'toxicity_score', 'severe_toxicity_score']
    if not os.path.exists(augmented_file):
        logging.warn(f"Didn't find augmented comments file. Creating new file at {augmented_file}")
        with open(augmented_file, 'w') as f:
            out_file = csv.writer(f)
            out_file.writerow(header)

    with open(augmented_file, 'a', newline='') as f:
        out_file = csv.DictWriter(f, fieldnames = header)
        for _, comment in comments.iterrows():
            comment = comment.to_dict()
            # Not sure how these weird carriage returns are getting through, but try removing them here
            comment['text'] = comment['text'].replace('\r\r', '\n')
            try:
                float(comment['created_utc'])
            except ValueError:
                logging.error(f"Malformed input for {comment}")
                continue
            tox_scores = get_toxicity.get_toxicity(comment['text'])
            if not tox_scores:
                continue
            else:
                comment['toxicity_score'] = tox_scores[0]
                comment['severe_toxicity_score'] = tox_scores[1]
                out_file.writerow(comment)

#%%
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--in-file', 
                        dest='in_f',
                        help="Input file (without toxicity scores)")
    parser.add_argument('--feather-file', dest='feather_file', help="Feather output (for reading in and sharing out). If exists, will replace the out-file")
    parser.add_argument('--out-file', dest='out_f', help="Output file (comments and toxicity scores)")
    parser.add_argument( '-log',
                     '--loglevel',
                     default='warning',
                     help='Provide logging level. Example --loglevel debug, default=warning' )
    args = parser.parse_args()
    logging.basicConfig( level=args.loglevel.upper() )
    logging.info( 'Logging now setup.' )
    raw_comments = args.in_f
    augmented_file = args.out_f

    try:
        augmented_df = pd.read_feather(args.feather_file)
        augmented_df.to_csv(augmented_file, index=False)
    except FileNotFoundError or TypeError:
        try:
            augmented_df = pd.read_csv(augmented_file, dtype={'created_utc':float})
        except FileNotFoundError or TypeError:
            augmented_df = None


    comments_df = pd.read_csv(raw_comments)

    comments_to_augment = filter_comments(comments_df, augmented_df)

    add_toxicity(comments_to_augment, augmented_file)

    if args.feather_file is not None:
        pd.read_csv(augmented_file).to_feather(args.feather_file)


if __name__ == '__main__':

    main()
