import praw
from prawcore.exceptions import NotFound
from praw.exceptions import RedditAPIException
import os
import csv
import pandas as pd
import time
import random
from openai import OpenAI
from openai import BadRequestError
import uuid
import logging
from dataclasses import dataclass
import argparse
import json
import auth

# Open config file
import yaml
# Open and read the YAML file
with open('shared_config.yaml', 'r') as file:
    config = yaml.safe_load(file)

###########
#
# The chatbot works like this: It keeps a record of all the conversations it has had. It also checks the reddit inbox for new conversations.
# If someone has sent a new message, then we use OpenAI to respond.
#
# Here are the files:
# to_contact - list of redittors to contact. When first contacted, each person is placed into a condition randomly
# participants - table of participants, conditions, and uuids to keep anonymous
# conversations - table of conversations - both sent by us and replies from user
#
# When it comes to responding to people, there are three different flows:
#
# 'default': We send an initial message via modmail. If they consent, then we send a handoff message and start a chat via DMs.
#
# 'dm': We send an initial message via DMs. If they consent, then we start a chat via DMs.
#
# 'modmail': We send an initial message via modmail. If they consent, then we start a chat via modmail.
#
###################


## Bugs:

# The default condition allows users to continue chatting via modmail. We should probably have some default message we send one time,
# and then stop responding to them.

# Initialize logging
parser = argparse.ArgumentParser()
parser.add_argument( '-log',
                     '--loglevel',
                     default='warning',
                     help='Provide logging level. Example --loglevel debug, default=warning' )
args = parser.parse_args()
logging.basicConfig( level=args.loglevel.upper() )
logging.info( 'Logging now setup.' )

# Initialize OpenAI client
OpenAIClient=OpenAI(api_key = auth.openai_key)

script_dir = os.path.dirname(os.path.abspath(__file__))


def main():
    curr_run = Run()
    curr_run.get_messages()
    curr_run.continue_convos()
    curr_run.contact_new()


@dataclass
class Message:
    user_id: str
    message_type: str # ['initial', 'clarifying', 'AI_reply', 'user']
    text: str
    created_utc: float
    subreddit: str
    conversation_or_message_id: str
    is_modmail: bool
    condition: str
    
@dataclass
class User:
    user_name: str
    user_id: str
    condition: str
    messaging_strategy: str
    subreddit: str
    toxic_comments: str
    openai_model: str
    first_consented_msg: str
    initial_message: str

class Conversation:
    
    def __init__(self, convo_df, clean_modmail = True):
        """
        Given a dataframe of messages, creates a conversation object. 
        If clean_modmail is True, then we remove any modmail messages
        """
        self.messages = []
        for _, row in convo_df.iterrows():
            self.messages.append(Message(
                user_id = row['user_id'],
                message_type = row['message_type'],
                text = row['text'],
                created_utc = row['created_utc'],
                subreddit = row['subreddit'],
                conversation_or_message_id = row['conversation_or_message_id'],
                is_modmail=row['is_modmail'],
                condition = row['condition']
            ))
        if clean_modmail:
            self.clean_messages()
        self.user_id = self.messages[0].user_id
        self.subreddit = self.messages[0].subreddit
        self.consent_status = None

    def clean_messages(self):
        '''
        When users are consented and then send messages to modmail, 
        we want to just ignore those messages
        '''
        has_handoff = False
        new_messages = []
        for message in self.messages:
            if message.message_type == 'handoff':
                has_handoff = True
            elif has_handoff == True:
                # Don't keep the modmail messages that happened after the handoff
                if message.is_modmail == True:
                    continue
            else:
                pass
            new_messages.append(message)
        self.messages = new_messages



    def should_we_reply(self):
        """
        Given a conversation, determines if we should reply. 
        We only reply if the last message was from the user
        """
        # Figure out if we need to reply; we only reply if the last message was from the user
        if self.messages[-1].message_type != 'user':
            return False

    def needs_handoff(self, user):
        ''' 
        Figure out if we need to send a handoff message. Checks the user object to see if the
        strategy is 'default'. Assumes that the get_conversation_status() method has already been called
        and determined that the user has consented, or 'skip'.

        For the default condition, we will end up sending two handoff messages. One via modmail, and one via DMs.
        For the other conditions, we will only send one handoff message.
        '''
        if user.messaging_strategy == 'default':
            return True
        else:
            return False

    def get_conversation_status(self, user):
        '''
        Given a string, returns 'consented', 'declined', 'needs_clarification', 'needs_handoff', or 'skip'.

        Here's the flow:
        We send an initial message. If they respond, we check to see if they consented.
        If they don't respond "yes" or "no" as the first word, then we send a clarifying message. If they respond "no", then we ignore them.

        If they respond "yes" to either an initial or clarifying message, then we send a handoff message.
        Therefore, to determine the status, we only have to look the message type of our last message. If it isn't an initial or clarifying message,
        then the consent process must have already happened and they said yes.

        TODO: There may be some edge cases here; e.g., when someone responds "no", and then sends a second message.
        '''

        # I think there may be a bug. This is a very hacky way of handling it.

        if self.messages[0].message_type != 'initial':
            logging.error(f'First message sent to {self.user_id} appears to be missing')
            self.messages = [Message(user_id = self.messages[0].user_id,
                                     text = config['initial_message'][user.initial_message],
                                     subreddit = self.messages[0].subreddit,
                                     conversation_or_message_id = None,
                                     is_modmail = True,
                                     message_type = 'initial',
                                     condition = self.messages[0].condition,
                                     created_utc = None)] + self.messages

        # We look at our last message. If it was a new message or clarifying message, then we need to check consent
        if self.consent_status is not None:
            return self.consent_status
        if self.messages[-1].message_type != 'user':
            self.consent_status = 'skip'
        elif self.messages[-2].message_type in ['initial', 'clarifying']:
            text = self.messages[-1].text
            # We just look at the first word of the message
            text = text.lower().strip('" \n\'').split()[0]
            logging.info(f'Response appears to be: {text}')
            if text in ['yes', 'sure', 'y', 'ok']:
                self.consent_status = 'needs_handoff'
            elif text in ['no', 'n', 'nope']:
                self.consent_status = 'declined'
            else:
                # If we can't determine, then we return None (triggers a clarifying message)
                self.consent_status = 'needs_clarification'
        # Otherwise, we assume we're in the midst of a conversation, and we don't need to check consent
        else:
            self.consent_status = 'consented'
        logging.debug(f'Consent status for {self.user_id} is {self.consent_status}')
        return self.consent_status
    

        

    
class Run:
    
    def __init__(self):
        self.reddit = praw.Reddit(
            client_id = auth.client_id,
            client_secret = auth.client_secret,
            user_agent = auth.u_agent,
            username = auth.username,
            password = auth.password,
            )
        self.conversations_file, self.to_contact_file, self.participants_file, self.subreddits_file = (os.path.join(script_dir, x) for x in [config['conversations_file'], config['to_contact_file'], config['participants_file'], config['subreddits_file']])
        self.bad_accounts_file = os.path.join(script_dir, config['bad_accounts_file'])
        self.load_participants()
        self.load_bad_accounts()
        self.load_conversations()
        self.load_subreddits()
        self.conditions = ['default', 'narrative', 'norms', 'control', 'casual']
        self.conditions = ['casual-general', 'control']
        self.clarifying_message = config['clarifying_message']

    def load_bad_accounts(self):
        try:
            with open(self.bad_accounts_file, 'r') as f:
                self.bad_accounts = json.load(f)
        except FileNotFoundError:
            self.bad_accounts = []

    def get_subject(self, condition):
        return "Chat with our chatbot about how people behave online"
        return "Some recent toxic messages"       

    def get_condition_message(self, user):
        # TODO: Determine if we need different messages for different conditions or subreddits
        return config['initial_message'][user.initial_message].format(username=user.user_name, subreddit=user.subreddit)
    
    def get_subred_rules(self, subred):
        rules = list()
        for rule in self.reddit.subreddit(subred).rules:
            rules.append(rule)
        rules = ', '.join(map(str, rules))
        logging.info(f"Rules for {subred} are: {rules}")
        new_sub = pd.DataFrame({'subreddit': [subred], 'rules': [rules]})
        self.subreddits = pd.concat([self.subreddits, new_sub], ignore_index=True)
        self.subreddits.to_csv(self.subreddits_file, index=False)
        
        return rules
              
    def get_condition_prompt(self, user):
        subreddit_rules = self.subreddits.loc[self.subreddits.subreddit == user.subreddit, 'rules']
        if len(subreddit_rules) == 0:
            try:
                subreddit_rules = self.get_subred_rules(user.subreddit)
            except Exception as e:
                logging.error(e)
                logging.error("Error getting sub rules")
                subreddit_rules = ''

        prompt_dict = config['prompt_dict'] 
        try:
            prompt = prompt_dict[user.condition]
            prompt = prompt.format(user=user, subreddit_rules = subreddit_rules)
            return prompt
        except KeyError:
            raise KeyError("Condition must be one of [default, narrative, norms]")
            
            
    def load_conversations(self):
        try:
            self.conversations = pd.read_csv(self.conversations_file)
        except FileNotFoundError:
            self.conversations = pd.DataFrame()

    def get_condition(self, user_id):
        '''Gets the condition that the user_id is in, from the participants dictionary'''
        try:
            return self.participants[user_id].condition
        except KeyError:
            raise KeyError("User not found in participants dictionary")



    def get_subreddit(self, user_id):
        '''Gets the condition that the user_id is in, from the participants dictionary'''
        try:
            return self.participants[user_id].subreddit
        except KeyError:
            raise KeyError("User not found in participants dictionary")


    def load_participants(self):
        '''
        Loads the table of participants; a CSV file stored in `config['participants_file']`. Should have the following columns:
        author(str), author_id(str), subreddit (str), toxic_comments (str), condition (str), messaging_strategy (str). Converts it to
        a dictionary of User objects, indexed by author_id'''
     
        try:
            df = pd.read_csv(self.participants_file, index_col = 'author_id')
        except FileNotFoundError:
            df = pd.DataFrame()

        self.participants = dict()
        self.username_to_id_map = dict()
        for author_id, row in df.iterrows():
            author_id = str(author_id)
            self.participants[author_id] = User(user_name=row['author'],
                                                user_id=author_id, 
                                                subreddit=row['subreddit'], 
                                                toxic_comments=row['toxic_comments'], 
                                                condition=row['condition'], 
                                                messaging_strategy=row['messaging_strategy'],
                                                openai_model=row['openai_model'],
                                                first_consented_msg=row['first_consented_msg'],
                                                initial_message=row['initial_message']
                                                )
            self.username_to_id_map[row['author']] = author_id
        

    def load_subreddits(self):
        '''Loads the table of subreddit info (subreddit rules). Should have the following columns:
        subreddit (str), rules (str)'''

        try:
            self.subreddits = pd.read_csv(self.subreddits_file)
        except FileNotFoundError:
            self.subreddits = pd.DataFrame()

    def get_messages(self):
        '''Gets the unread messages in our inbox, filters out those that aren't part of conversations with participants,
        and writes the conversations to the conversations file.
        '''
        
        self.get_modmail_messages()
        self.get_inbox_messages()

        
    def get_modmail_messages(self, max_age_seconds = 24*60*60*4, archive=True):
        ## TODO: Change temporal filter so that it only gets those newer than our last run?
        conversations = self.reddit.subreddit("all").modmail.conversations(state='all', sort='recent')
        
        to_add = []
        for conversation in conversations:
            logging.info(f"Checking conversation {conversation} with {[x.author.name for x in conversation.messages]}")
            messages = conversation.messages
            last_message = messages[-1]
            
            # Check if it's older than one day
            created_utc = to_timestamp(last_message.date)
            if created_utc < (time.time() - max_age_seconds):
                logging.info(f"Stopping because {conversation} is older than {max_age_seconds} seconds")
                break
           
            # Archive our messages if they didn't get archived.
            if messages[-1].author.name == auth.username and conversation.state != 2:
                print(f'Trying to archive {conversation}')
                conversation.archive()

            # Get only conversations where we initiated the conversation, and where we
            # were not the final author
            if messages[0].author.name != auth.username or messages[-1].author.name == auth.username:
                logging.info(f"First message was from {messages[0].author.name} and last message was from {messages[-1].author.name}. Skipping {conversation}")
                continue 
          
            try:
                # If the author isn't in the participant list, then don't reply
                uid = self.username_to_id_map[last_message.author.name]
            except KeyError:
                logging.info(f"Skipping {conversation} due to KeyError. {last_message.author.name} not in list of participants")
                continue
         
            text = last_message.body_markdown
            conversation_id = conversation.id
            subreddit = conversation.owner.display_name
            to_add.append(Message(user_id = uid,
                                  message_type = 'user',
                                  text = text,
                                  created_utc = created_utc,
                                  subreddit = subreddit,
                                  conversation_or_message_id = conversation_id,
                                  is_modmail=True,
                                  condition = self.get_condition(uid)
                                 ))
            if archive:
                conversation.archive()
        self.write_conversations(to_add)
        # Just grab and archive things that Reddit filtered (for some reason not included in "all")
        filtered_convos = self.reddit.subreddit("all").modmail.conversations(state='filtered', sort='recent')
        for convo in filtered_convos:
            if auth.username in convo.authors:
                logging.info(f"Archiving message {convo.id}, which was filtered.")
                convo.archive()
        
    def get_inbox_messages(self):
        ## TODO: Add a temporal filter so that we only get messages later than our last run
        inbox = self.reddit.inbox.unread()
        to_add = []
        for message in inbox:
            if not isinstance(message, praw.models.Message):
                continue

            ## Look for the easter egg which adds people to the to_contact file
            if message.subject == 'toxictalk':
                add_to_contact(message.author.name, message.body)
                message.mark_read()
            # Just get the replies?
            if not message.parent_id:
                try:
                    logging.info(f'Message from {message.author.name} not a reply: \n {message.subject} \n {message.body}')
                except AttributeError:
                    logging.info(f"There is an unread message from {message.subreddit}")
                continue
            else:
                try:
                    author_id = self.username_to_id_map[message.author.name]
                except KeyError:
                    logging.info(f"Skipping {message} due to KeyError. {message.author.name} not in list of participants")
                    continue
                except AttributeError:
                    logging.info(f"There is an unread message from {message.subreddit}")
                    continue
                to_add.append(Message(user_id = author_id,
                                    message_type = 'user',
                                    text = message.body,
                                    created_utc = message.created_utc,
                                    subreddit = self.get_subreddit(author_id),
                                    conversation_or_message_id = message.id,
                                    is_modmail=False,
                                    condition = self.get_condition(author_id)
                                 ))
                message.mark_read()
        self.write_conversations(to_add)

    def add_bad_account(self, user, exception):
        if exception == 'consent_declined' or user_is_missing(exception) or user_blocked_us(exception):
            logging.error(f"Adding {user} as bad account")
            self.bad_accounts.append(user.user_name)
            self.bad_accounts.append(user.user_id)
        else:
            logging.error(exception)
            return
        with open (self.bad_accounts_file, 'w') as f:
            json.dump(self.bad_accounts, f)


    def send_dm(self, user, subject, body, message_type):
        '''Sends a DM to a user. Returns True if successfull'''
        try:
            self.reddit.redditor(user.user_name).message(subject=subject, message=body)
            message = self.make_message(user, text=body, message_type=message_type, is_modmail=False)
            self.write_conversations([message])
            return True
        except (NotFound, RedditAPIException) as e:
            logging.error(f"Error sending message to {user.user_name}: {e}")
            self.add_bad_account(user, e)
            return False

    def send_modmail(self, user, subject, body, message_type, archive=True):
        '''Sends a modmail to a user. Returns the message object'''
        try:
            modmail_convo = self.reddit.subreddit(user.subreddit).modmail.create(subject=subject, 
                                                                        body=body,
                                                                        recipient=user.user_name
                                                                        )
            message = self.make_message(user, text=body, message_type=message_type, is_modmail=True)
            self.write_conversations([message])
            sent = True
        except RedditAPIException as e:
            self.add_bad_account(user, e)
            sent = False
        except Exception as e:
            logging.error(e)
            logging.error(type(e).__name__)
            logging.error(f"Couldn't send a message to {user.user_name}")
            sent = False

        if sent and archive:
            try:
                modmail_convo.archive()
            except Exception as e:
                logging.error(f"Couldn't archive message from {user.user_name}")
                logging.error(e)
        return sent

    def send_dm_reply(self, message, text_to_send):
        logging.info('Attempting to send message via inbox')
        try:
            self.reddit.inbox.message(message.conversation_or_message_id).reply(text_to_send)
            return True
        except RedditAPIException as e:
            user_id = message.user_id
            user = self.participants[user_id]
            self.add_bad_account(user, e)
            return False
        except Exception as e:
            logging.error(e)
            logging.error(f"Couldn't send a message to {self.participants[message.user_id].user_name}")
            user = self.participants[user_id]
            self.add_bad_account(user, e)
            return False
        
    def send_modmail_reply(self, message, text_to_send, archive=True): 
        try:
            conversation = self.reddit.subreddit(message.subreddit).modmail(message.conversation_or_message_id)
            conversation.reply(body=text_to_send)
            sent = True
            logging.info("Modmail message sent")
        except RedditAPIException as e:
            user_id = message.user_id
            user = self.participants[user_id]
            self.add_bad_account(user, e)
            sent = False
            logging.info("Modmail reply got reddit api exception")
        except Exception as e:
            logging.error(e)
            logging.error(f"Couldn't send a modmail reply to {self.participants[user_id].user_name}")
            sent = False 
            logging.info("Modmail reply got other exception")
        if sent and archive:
            logging.info("Trying to archive")
            try:
                conversation.archive()
            except Exception as e:
                logging.error(e)
        return sent

    def send_reply(self, user, message, conversation, message_type):
        '''Sends a reply to a user. This must be a response to an ongoing conversation'''
        logging.info(f"Attempting to send message {message} to {user.user_name}")
        is_modmail = conversation.messages[-1].is_modmail
        if is_modmail:
            sent = self.send_modmail_reply(conversation.messages[-1], message)
        else:
            sent = self.send_dm_reply(conversation.messages[-1], message)

        if sent:
            message = self.make_message(user=user, text=message, message_type=message_type, is_modmail=is_modmail)
            self.write_conversations([message])

    def make_message(self, user, text, message_type, is_modmail):
        return Message(user_id = user.user_id,
                message_type = message_type,
                text = text,
                created_utc = get_curr_timestamp(),
                subreddit = user.subreddit,
                conversation_or_message_id = None,
                is_modmail=is_modmail,
                condition = user.condition)


    def write_conversations(self, messages):
        """Takes in a list of message objects. Concatenates them with the existing conversations, and writes them out"""
        if len(messages) == 0:
            return
        new_messages = pd.DataFrame(messages)
        # Add these to the current conversations only if they aren't already in the 
        # existing conversations
        # TODO: An easier way would be to replace the current conversations file
        # But I like that this doesn't open it for writing, just appending
        result = new_messages.merge(self.conversations, on=list(new_messages.columns), how='left', indicator=True)
        result = result[result['_merge'] == 'left_only']
        new_messages = result.drop(columns=['_merge'])
        self.conversations = pd.concat([self.conversations, new_messages])
                         
        # And append them to the conversations file
        if not os.path.isfile(self.conversations_file):
            new_messages.to_csv(self.conversations_file, index=False)
        else:
            new_messages.to_csv(self.conversations_file, mode = 'a', header=False, index=False)



    def contact_new(self, messaging_strategy = 'default', max_contacts = 2):
        '''Randomly assigns users who have sent toxic comments to one of the conditions, and contacts them with the initial message.
        messaging_strategy can be one of [default, modmail, dm]. Default starts with a modmail message, and then
        switches to DMs if the user replies. Modmail keeps using modmail, and 'dm' starts with a DM.
        '''
        df = pd.read_csv(self.to_contact_file)
        df = df.drop_duplicates('author')
        df = df[df.author != '[deleted]']
        df = df[~df.author.isin(self.username_to_id_map.keys())]
        df = df[~df.author.isin(self.bad_accounts)]
        df = df.iloc[:max_contacts]
        for i, row in df.iterrows():
            user = User(
                user_name=row['author'],
                user_id=uuid.uuid4(),
                condition=random.choice(self.conditions),
                messaging_strategy=messaging_strategy,
                toxic_comments=row['toxic_comments'],
                subreddit=row['subreddit'],
                openai_model=random.choice(config['openai_models']),
                # TODO put this logic somewhere else
                first_consented_msg=random.choice(['conversational', 'not-proud']),
                initial_message=random.choice(list(config['initial_message'].keys()))
            )
            logging.info(f"Sending initial message to {user.user_name}")
            # For now, sending messages to control
            #if user.condition != 'control':
            message_sent = self.send_new_message(user)
            #else:
            #    message_sent = True
            if message_sent:
                self.add_participant(user)
    
    def add_participant(self, author):
        '''Writes to the file and also updates self.participants and self.username_to_id_map'''
        
        if not os.path.isfile(self.participants_file):
            # Open the CSV file in write mode and write the header row
            with open(self.participants_file, 'w') as f:
                writer = csv.writer(f)
                writer.writerow(['author', 'author_id', 'condition', 'subreddit', 
                                 'toxic_comments', 'messaging_strategy', 'openai_model', 'first_consented_msg','initial_message'])
        
        with open(self.participants_file, 'a') as f:
            out = csv.writer(f)
            out.writerow([author.user_name,
                            author.user_id,
                            author.condition,                                                                                     
                            author.subreddit,
                            author.toxic_comments,
                            author.messaging_strategy,
                            author.openai_model,
                            author.first_consented_msg,
                            author.initial_message
                            ])
        self.participants[author.user_id] = author
        self.username_to_id_map[author.user_name] = author.user_id
                
        
    def write_new_conversation(self, user, message):
        '''Takes in a user object and the message. Stores
        everything in the conversations file.
        '''
        if user.messaging_strategy in ['default', 'modmail']:
            is_modmail = True
        else:
            is_modmail = False
        message = Message(user_id = user.user_id,
                          message_type='initial',
                          text = message,
                        created_utc = get_curr_timestamp(),
                                  subreddit = user.subreddit,
                                  conversation_or_message_id = None,
                                  is_modmail = is_modmail,
                                  condition = user.condition) 
        self.write_conversations([message])


    def send_new_message(self, user):
        '''Sends the initial message to users who have sent toxic comments. Returns True if the message was sent successfully, or returns an error'''
        subject = self.get_subject(user.condition)
        message = self.get_condition_message(user)

        ## I'm going to assume that we'll always be getting permission from a subreddit, and so I'm changing the logic to just look
        # at messaging strategiy instead.
        if user.messaging_strategy == 'dm':
            # Send message through normal DMs
            return self.send_dm(user=user, 
                          subject=subject,
                          body = message, message_type='initial')
        else:
            # Send message through modmail
            try:
                self.send_modmail(user, subject, message, message_type='initial')
                return True
            except Exception as e:
                logging.error(f"Couldn't send new message to {user.user_id}. Error {e}, {[x.error_type for x in e.items]}")
                return False

            

    def continue_convos(self):
        '''
        Gets the conversations that we need to reply to, and sends a reply. This is where the logic exists that routes conversations based on
        the messaging strategy.
        '''
        if not os.path.isfile(self.conversations_file):
            return
        convo_df = pd.read_csv(self.conversations_file)
        # Filters to those where the last reply was written by users
        convo_df = convo_df[~convo_df.user_id.isin(self.bad_accounts)]
        convo_df = convo_df.groupby('user_id').filter(lambda x: x.iloc[-1].message_type == 'user')
        # Determines whether the user consented; if this is their first message to us, or if our last message was asking for consent,
        # Then we check if they consented. If they didn't, we don't reply. If it's unclear, then we send a clarifying message.
        conversations = [Conversation(convo_df[convo_df.user_id == x]) for x in convo_df.user_id.unique()]
        for conversation in conversations:
            logging.info("Loading next convo")
            logging.info(f"Conversation with {conversation.user_id}. Messages are {conversation.messages}")
            user = self.participants[conversation.messages[0].user_id]
            consent_status = conversation.get_conversation_status(user=user)
            if consent_status == 'declined': 
                logging.info("Consent declined")
                self.archive_modmail(conversation=conversation)
                self.add_bad_account(user, exception = 'consent_declined')
                continue
            elif consent_status == 'skip':
                logging.info("Skipping conversation (should be because it happened in modmail)")
                continue
            elif consent_status == 'needs_clarification':
                # Send a clarifying message if we didn't understand the response to the consent
                return self.send_clarifying_message(user=user,
                                             conversation=conversation)
            elif consent_status == 'needs_handoff':
                logging.info(f"Sending handoff message to {user.user_name}")
                return self.send_handoff_message(user=user, conversation=conversation)
            elif user.condition == 'control':
                continue
            else:
                return self.send_ai_reply(user=user, conversation=conversation)
            

    def send_clarifying_message(self, user, conversation):
        '''Sends a clarifying message if we didn't understand the user's response to the consent question'''
        return self.send_reply(user=user, message=self.clarifying_message, conversation=conversation, message_type='clarifying')

    def send_handoff_message(self, user, conversation):
        '''Sends a handoff message if the user has consented to the study'''
        if user.messaging_strategy == 'default':
            self.send_reply(user=user, message=config['handoff_message'], conversation=conversation, message_type='handoff')
        if user.condition != 'control':
            self.send_first_consented_message(user, conversation)

    def send_first_consented_message(self, user, conversation):
        '''Sends a message to the user if they have consented to the study'''
        # If the user is in the default flow, then we send a DM. Otherwise, we send a reply to the user.
        first_consented_message = config['first_consented_message'][user.first_consented_msg]
        message = first_consented_message.format(subreddit=user.subreddit, comment = user.toxic_comments)
        if user.messaging_strategy == 'default':
            return self.send_dm(user=user, subject=self.get_subject(user.condition), body=message, message_type='first_consented_message')
        else:
            self.send_reply(user=user, message=message, conversation=conversation, message_type='first_consented_message')

    def send_ai_reply(self, user, conversation):
        '''Sends a reply to the user, based on the current conversation. The curr_convo is the Conversation object.
        Checks whether we need to send a handoff message, and if so, sends it. Otherwise, sends a message from the AI.
        '''

        bot_instructions = self.get_condition_prompt(user)
        message = self.get_ai_reply(conversation=conversation, bot_instructions=bot_instructions,
                                    openai_model=user.openai_model)
        if message == 'Error occurred.':
            logging.error(f"OpenAI returned: {message}. Not sending.")
            return None
        logging.info(f"Preparing to send message: {message}")
        return self.send_reply(user, message, conversation, message_type = 'AI_reply')
            
    def get_messaging_strategy(self, user_id):
        try:
            return self.participants.loc[self.participants.author_id == user_id, 'messaging_strategy'].values[0]
        except KeyError:
            raise("Tried to find {user_id} in the participants file, but it wasn't there")


    def get_toxic_comments(self, user_id):
        try:
            return self.participants.loc[self.participants.author_id == user_id, 'toxic_comments'].values[0]
        except KeyError:
            raise("Tried to find {user_id} in the participants file, but it wasn't there")

    def get_ai_reply(self, conversation, bot_instructions, openai_model='gpt-3.5-turbo'):
        ## TODO: If we include more models, don't hard code this, but put it in config
        try:
            max_tokens = config['max_tokens'][openai_model]
        except KeyError: 
            raise(f"openai_model must be one of {config['openai_models']}")
        except Exception as e:  # Unknown Exception
            raise(e)
        if len(conversation.messages) > config['max_interactions']:
            return config['goodbye_message']
        message_len = len(bot_instructions.split())
        messages=[{"role": "system", "content": bot_instructions}]
        for message in conversation.messages:
            if message.message_type == 'user':
                role = 'user'
            else:
                role = 'assistant'
            messages.append({"role": role, "content": message.text})
            message_len += len(message.text.split())
        if message_len > max_tokens:
            if len(conversation.messages) == 1:
                return "I'm sorry, but your response is too long. Can you try something shorter?"
            
            conversation.messages = conversation.messages[1:]
            bot_instructions += " You are in the middle of a conversation with the user."
            return self.get_ai_reply(conversation, bot_instructions)
        
        try:
            gpt_response = OpenAIClient.chat.completions.create(
                model=openai_model,
                messages = messages)

            reply = gpt_response.choices[0].message.content
        
        except BadRequestError as e:
            logging.warning(f"Got a BadRequestError for {messages}. Error is {e}")
            #if e['error']['message'].startswith("Sorry! We've encountered an issue with repetitive patterns"):
            return "I can't figure out how to respond to your message. Could you try again?"
        #except:
            ## If it's too long, then try removing the earliest message
            #reply = 'Error occurred.'
            #logging.warning('Some unknown error occured while trying to genrate gpt_response. Possibly, it is receiving too many API calls at once.')
                
        return reply

    def archive_modmail(self, conversation):
        if not conversation.messages[-1].is_modmail:
            logging.warn(f"Can't archive conversation with {conversation.messages[0].user_id}. Not in modmail")
            return
        sr = conversation.messages[-1].subreddit
        id = conversation.messages[-1].conversation_or_message_id
        self.reddit.subreddit(sr).modmail(id).archive()


def add_to_contact(username, toxic_comment):
    with open(os.path.join(script_dir, config['to_contact_file']), 'a') as f:
        out = csv.writer(f)
        out.writerow([username, 'survey_invite_testing', toxic_comment])

def user_is_missing(exception):
    for item in exception.items:
        if item.error_type == 'USER_DOESNT_EXIST':
            return True
    return False        

def user_blocked_us(exception):
    for item in exception.items:
        if item.message == "Can't send a message to that user.":
            return True
    return False        

def to_timestamp(datestring):
    return pd.Timestamp(datestring).timestamp()
                
def get_curr_timestamp():
    return pd.Timestamp.now().timestamp()
                
if __name__ == '__main__':
    main()
