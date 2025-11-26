from perspective import PerspectiveAPI
import auth
import time
import logging
import re

p = PerspectiveAPI(auth.perspective_api_key)
remove_pattern = re.compile(r'^>.*\n', re.MULTILINE)

def get_toxicity(s, tests = ['TOXICITY', 'SEVERE_TOXICITY'], remove_quoted = True):
    if remove_quoted:
        try:
            new = remove_pattern.sub('', s)
        except TypeError:
            raise TypeError(f"{s} threw a TypeError")
        if new != s:
            logging.info(f"Removed quotation from \n{s}. \n Now equal to \n{new}.")
        s = new
    attempts = 0
    while True:
        try:
            toxicity  = p.score(s, tests=tests)
            return (toxicity['TOXICITY'], toxicity['SEVERE_TOXICITY'])
        except TypeError as e:
            print(f"TypeError for {s}")
            return (None, None)
        except Exception as e:
            if e.code == 400:
                return (None, None)
            else:
                print(f'Pausing for a bit (attempt {attempts})')
                print(f'Error: {e}')
                time.sleep(10 * attempts)
                if attempts < 10:
                    attempts += 1
                    continue
                else:
                    print(f"Giving up on {s}")
                    return (None, None)