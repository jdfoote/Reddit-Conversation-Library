import argparse
import csv
import pandas as pd
from get_toxicity import get_toxicity
import os.path
import logging


#%%

def get_convo_toxicity(text):
    lowered_text = text.strip().lower()
    if len(text) == 0 or lowered_text == 'yes' or lowered_text == 'no':
        return (None, None)
    return get_toxicity(text)

def filter_conversations(convos_df, augmented_df):
    if augmented_df is not None:
        convos_df = convos_df[~(convos_df.created_utc.astype(str) + convos_df.user_id).isin((augmented_df.created_utc.astype(str) + augmented_df.user_id))]
    #convos = convos_df[convos_df.message_type != "initial"]
    return convos_df

def add_toxicity(convos, augmented_file):
    header = list(convos.columns) + ['toxicity_score', 'severe_toxicity_score']
    if not os.path.exists(augmented_file):
        logging.warning(f"Creating a header")
        with open(augmented_file, 'w') as f:
            out = csv.writer(f)
            out.writerow(header)
    with open(augmented_file, 'a') as f:
        out_file = csv.DictWriter(f, fieldnames = header)
        for _, row in convos.iterrows():
            tox_scores = get_convo_toxicity(row['text'])
            if not tox_scores:
                continue
            else:
                row['toxicity_score'] = tox_scores[0]
                row['severe_toxicity_score'] = tox_scores[1]
                out_file.writerow(row.to_dict())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--in-file', 
                        dest='in_f',
                        help="Input file (without toxicity scores)")
    parser.add_argument('--out-file', dest='out_f', help="Output file (conversations and toxicity scores)")
    parser.add_argument( '-log',
                     '--loglevel',
                     default='warning',
                     help='Provide logging level. Example --loglevel debug, default=warning' )
    args = parser.parse_args()
    logging.basicConfig( level=args.loglevel.upper() )
    logging.info( 'Logging now setup.' )

    raw_conversation = pd.read_csv(args.in_f)
    augmented_file = args.out_f
    try:
        augmented_df = pd.read_csv(augmented_file)
    except FileNotFoundError:
        logging.warning(f"Didn't find {augmented_file}")
        augmented_df = None
    filtered_convos = filter_conversations(raw_conversation, augmented_df)
    logging.info(f"Getting toxicity for {len(filtered_convos)} texts")
    add_toxicity(filtered_convos, augmented_file)

if __name__ == '__main__':
    main()

