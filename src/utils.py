import re
from datetime import timedelta

class FrequencyString(object):
    """Encodes a string containing a number and one of the codes {m|h|D|W|M|Y}
    to describe some number of time periods (minutes, hours, Days, Weeks, Months, Years)
    Note that Months are approximated at 30 days, and Years 365 days.
    As a consequence, for example, 12M != 1Y """

    _valid_regex = re.compile(r"^([\d]+?\.?[\d]*)([mhDWMY])$")

    _tcodes = {  "m" : ("minutes", "minutes", 1), 
                "h" : ("hours", "hours", 1), 
                "D" : ("days", "days", 1), 
                "W" : ("weeks", "weeks", 1), 
                "M" : ("months", "days", 30), 
                "Y" : ("years", "days", 365)}


    def __init__(self, freq_string):
        if self.validate(freq_string):
            self.value = FrequencyString.evaluate(freq_string)

        else:
            raise ValueError(f"{freq_string} doesn't conform to specification: `n{{m|h|D|W|M|Y}}` where n is a number, and the second component describes (m)inutes, (h)ours, (D)ays, (W)eeks, (M)onths or (Y)ears. e.g. 24h = 24 (h)ours, 30D = 30 (D)ays. Case sensitive.")

    @staticmethod
    def validate(freq_string):
        return bool(FrequencyString._valid_regex.match(freq_string))
    
    @staticmethod
    def evaluate(freq_string):
        t,u = FrequencyString._valid_regex.match(freq_string).groups()
        return timedelta(**{FrequencyString._tcodes[u][1]:FrequencyString._strtonum(t)*FrequencyString._tcodes[u][2]})
    
    @staticmethod
    def _strtonum(s):
        try:
            return int(s)
        except ValueError:
            return float(s)