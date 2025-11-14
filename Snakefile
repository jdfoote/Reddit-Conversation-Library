
augmented_dir = "data/augmented_data"
summarized_dir = "data/summarized_data"

rule all:
    input: 
        f"{summarized_dir}/summarized_conversations.csv",
        f"{summarized_dir}/participant_info.csv",
        "data/filtered_convos.csv"

rule make_participant_file:
    conda: "toxic_talk"
    input:
        participants = "data/participants.csv",
        moderated = "data/to_contact.csv",
        convos = f"{summarized_dir}/summarized_conversations.csv",
        script = "code/summarize_data/clean_participant_info.py"
    output:
        f"{summarized_dir}/participant_info.csv"
    shell:
        "python {input.script} --in-file {input.participants} --moderated-file {input.moderated} --convo-file {input.convos} --out-file {output}"

rule summarize_conversations:
    conda: "toxic_talk"
    input:
        convos=f"{augmented_dir}/augmented_conversations.csv",
        done=f"{augmented_dir}/conversations_done.txt"
    output:
        f"{summarized_dir}/summarized_conversations.csv"

    shell:
        "python code/summarize_data/make_conversation_summaries.py --in-file {input.convos} --out-file {output}"

# TODO: Figure out how to simplfy these into one rule
rule augment_comments:
    conda: "toxic_talk"
    input:
        raw = "data/participant_comments.csv",
        augmented = f"{augmented_dir}/augmented_comments.csv",
        feather = f"{augmented_dir}/augmented_comments.feather"
    output:
        f"{augmented_dir}/comments_done.txt"
    shell:
        "python code/augment_data/augment_comments.py --in-file {input.raw} --out-file {input.augmented} --feather-file {input.feather} && touch {output}"

rule augment_conversations:
    conda: "toxic_talk"
    input:
        raw = "data/conversations.csv",
        augmented = f"{augmented_dir}/augmented_conversations.csv"
    output:
        f"{augmented_dir}/conversations_done.txt"
    shell:
        "python code/augment_data/augment_conversations.py --in-file {input.raw} --out-file {input.augmented} && touch {output}"

#rule augment_moderation:
#    conda: "toxic_talk"
#    input:
#        mod_dir="data/modlogs/",
#        participants="data/participants.csv"
#    output:
#        f"{augmented_dir}/augmented_moderation.csv"
#    shell:
#        "python code/augment_data/augment_moderation.py --mod-dir {input.mod_dir} --participant-file {input.participants} --out-file {output}"

rule augment_suspended:
    conda: "toxic_talk"
    input:
        "data/participant_data/suspended_ids.csv"
    output:
        f"{augmented_dir}/augmented_suspended.csv"
    shell:
        "python code/augment_data/augment_suspended.py --in-file {input} --out-file {output}"

rule clean_conversations:
    # TODO: Clean this up, add argparse arguments
    conda: "toxic_talk"
    input:
        "data/conversations.csv"
    output:
        "data/filtered_convos.csv"
    shell:
        "cd code && python get_convos.py"