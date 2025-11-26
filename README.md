# Reddit Conversation Library

Authors: Dr. Jeremy Foote ([jdfoote@purdue.edu](mailto:jdfoote@purdue.edu)), Dr. Deepak Kumar ([kumarde@ucsd.edu](mailto:kumarde@ucsd.edu)), Hitesh Goel ([hitesh.goel@research.iiit.ac.in](mailto:hitesh.goel@research.iiit.ac.in)), Loizos Bitsikokos ([lbitsiko@purdue.edu](mailto:lbitsiko@purdue.edu))

Software toolkit and pipeline for conducting field experiments with AI agents on Reddit. This repository is a Python-based software that identifies participants, messages and consents them, and conducts conversational experiments with researcher-designed AI chatbots. In addition to storing all conversations, the software can also record participant behavior before and after conversations. 

The toolkit also contains scripts to fetch Reddit comments, prepare conversation-level data, augment comments with moderation and suspension signals, and generate summarized outputs for downstream analysis.

## Quick overview
- Chatbot and conversation software: [code/chatbot.py](code/chatbot.py) contains code to set-up and run the chatbot.
- Fetching / collection: [code/fetch_comms/](code/fetch_comms/) and [code/get_convos.py](code/get_convos.py).
- Augmentation: [code/augment_data/](code/augment_data/) contains scripts that add moderation, suspension, and other columns.
- Summarization: [code/summarize_data/](code/summarize_data/) contains scripts to summarize conversation data and clean participant information
- Utilities: other scripts for preparing datasets and moderation extraction live in the top-level [code/](code/) folder.

## Repository structure

Top-level:

- [environment.yml](environment.yml) - Conda environment specifications
- [Snakefile](Snakefile) - Snakemake pipeline that puts together augmentation and cleaning rules
- [code/](code/) - Python scripts
- [data/](data/) - Expected output and input data folders

## Prerequisites

- Conda / Miniforge / Anaconda installed. The repo includes [environment.yml](environment.yml) to create the environment used by the [Snakefile](Snakefile) rules.
- Snakemake installed.

## Setup (create environment)

Create the conda environment from the provided specs:

```bash
conda env create -f environment.yml
conda activate toxic_talk
```

## Running the pipeline (Snakemake)

From the repository root you can run a dry-run to see the planned actions:

```bash
# show what Snakemake would run (no commands executed)
snakemake -n
```

To actually run the default pipeline (the `rule all` targets in the `Snakefile`):

```bash
# run the pipeline using up to 4 cores (adjust -j as needed)
snakemake -j 4
```

## Configuration

The repository uses a small set of YAML configuration files (located in `code/`) to control messaging text, file paths, and model settings. The two primary files are:

- [code/shared_config.yaml](code/shared_config.yaml) - active configuration read by several scripts (`chatbot.py`, `get_convos.py`, `get_toxic_moderated_comments.py`). Key entries:
    - `openai_models` - list of OpenAI model names the chatbot can use.
    - `max_interactions` and `max_tokens` - limits used when building prompts and calling OpenAI.
    - `conversations_file`, `to_contact_file`, `participants_file`, `subreddits_file`, `bad_accounts_file` - relative paths to project CSVs.
    - `initial_message`, `clarifying_message`, `handoff_message`, `first_consented_message`, `prompt_dict` - message templates and system prompts used by the chatbot. These are multiline strings and may include formatting placeholders like `{subreddit}` and `{comment}`.
    - `goodbye_message` - final message shown when the bot stops replying.

- [code/example_config.yaml](code/example_config.yaml) - a trimmed example of the same keys with shortened messages. Use this as a starting point for custom configs.


## Code files (brief descriptions)

Top-level scripts in `code/`:

- [code/chatbot.py](code/chatbot.py) - Main chatbot controller: reads conversations, inbox/modmail, decides whether to reply, and sends messages via PRAW/OpenAI; contains conversation and run logic.
- [code/get_convos.py](code/get_convos.py) - Aggregate and clean conversation records into [data/filtered_convos.csv](data/filtered_convos.csv) (groups messages by user, filters by AI replies and test subreddits).
- [code/get_toxic_moderated_comments.py](code/get_toxic_moderated_comments.py) - Scans subreddit mod logs for removed comments, scores them with Perspective API, records toxic removed comments or comments containing certain keywords for contacting.
- [code/fetch_comms/retrieve_latest_user_comments.py](code/fetch_comms/retrieve_latest_user_comments.py) - Fetches recent comments for users (uses PRAW), writes [data/participant_comments.csv](data/participant_comments.csv) and suspended status.
- [code/invite_mods.py](code/invite_mods.py) - Script to contact subreddit moderators (used to recruit subreddits for the study).
- [code/get_noncontacted_control.py](code/get_noncontacted_control.py) - Builds an uncontacted control sample from moderation logs and appends matched controls to [data/participants.csv](data/participants.csv).

Augmentation scripts in `code/augment_data/`:

- [code/augment_data/augment_comments.py](code/augment_data/augment_comments.py) - Add toxicity scores to participant comments and write augmented CSV / feather outputs.
- [code/augment_data/augment_conversations.py](code/augment_data/augment_conversations.py) - Add toxicity scores to conversation-level texts and append to augmented conversations file.
- [code/augment_data/augment_moderation.py](code/augment_data/augment_moderation.py) - Parse moderation log CSVs, filter removal actions for our participants, and produce augmented moderation data.
- [code/augment_data/augment_suspended.py](code/augment_data/augment_suspended.py) - Normalize suspension files and convert date strings to `created_utc` timestamps.
- [code/augment_data/prep_data.py](code/augment_data/prep_data.py) - one-off preprocessing that computes conversation stats and writes aggregated augmented outputs.
- [code/augment_data/get_toxicity.py](code/augment_data/get_toxicity.py) - Wrapper around the Perspective API client used by augmentation scripts to get toxicity and severe toxicity scores.

Summarization scripts in `code/summarize_data/`:

- [code/summarize_data/clean_participant_info.py](code/summarize_data/clean_participant_info.py) - Cleans and produces a `participant_info.csv` file from raw participants and moderation outputs.
- [code/summarize_data/make_conversation_summaries.py](code/summarize_data/make_conversation_summaries.py) - Generates conversation-level summary CSVs from augmented conversations.
