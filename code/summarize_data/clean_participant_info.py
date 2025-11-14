import pandas as pd
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--out-file", dest="out_file", help="Output file")
parser.add_argument("--in-file", dest="input_file", help="Input file")
parser.add_argument("--moderated-file", dest="moderated_file", help="Moderated file (to_contact.csv)")
parser.add_argument("--convo-file", dest="convo_file", help="Conversations file (to get consent status)")
args = parser.parse_args()

df = pd.read_csv(args.input_file)
df = df.rename(columns={"author_id": "user_id"})

mod_df = pd.read_csv(args.moderated_file)
mod_df = mod_df.drop_duplicates(subset="author", keep="first")
mod_df.rename(columns={"timestamp": "moderated_time"}, inplace=True)
mod_df = mod_df.loc[:, ["author", "moderated_time"]]

# Merge the two dataframes, keeping the first row of the moderated dataframe that matches the user_id
df = df.merge(mod_df, on="author", how="left")

convo_df = pd.read_csv(args.convo_file)
convo_df = convo_df.loc[:, ["user_id", "consented"]]

df = df.merge(convo_df, on="user_id", how="left")

del df['author']

convos = pd.read_csv(args.convo_file)
convos = convos.loc[:, ["user_id", "consented"]]
df.merge(convos, on="user_id", how="left")


df.to_csv(args.out_file, index=False)