import argparse
import pandas as pd


#%%


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--in-file', 
                        dest='in_f',
                        help="Input file (with original dates)")
    parser.add_argument('--out-file', dest='out_f', help="Output file")
    args = parser.parse_args()

    suspended_df = pd.read_csv(args.in_f)
    suspended_df = suspended_df.drop_duplicates()
    suspended_df['created_utc'] = pd.to_datetime(suspended_df.date).astype(int)/10**9
    suspended_df.to_csv(args.out_f)

if __name__ == '__main__':
    main()

