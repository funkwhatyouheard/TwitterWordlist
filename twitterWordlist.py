#/usr/bin/python
import twitter
import string
import getpass
import requests
import re
import argparse
import sys
import csv
from nltk.corpus import stopwords
from nltk.tokenize import TweetTokenizer
from nltk import download as nltk_download
from collections import Counter
from geopy.geocoders import Nominatim
from datetime import datetime
from os import path


#class TwitterWordlist(twitter.Api):
#    def __init__(self):
#        super(TwitterWordlist, self).__init__()
#

# snagged from https://gist.github.com/sebleier/554280#gistcomment-3126707
# there is a more extensive list than nltk's, import stoplist from custom_stoplist

nltk_download('stopwords')
nltk_download('punkt')
tokenizer = TweetTokenizer()
exclusions = stopwords.words('english')

def remove_punctuation(text):
    return text.translate(str.maketrans('','',string.punctuation))

def trimNonAsciiChars(unicodeStr):
  asciiStr = str()
  for char in unicodeStr:
    if ord(char) <= 126:
      asciiStr += char
  return asciiStr

def clean_tweets(tweets, minwordlen=3):
    cleaned = list()
    if isinstance(tweets,list):
        for tweet in tweets:
            cleaned.extend(clean_tweets(tweet, minwordlen))
    elif isinstance(tweets,str):
        # supports unicode, stripping those characters out
        tweet = remove_punctuation(trimNonAsciiChars(tweets))
        # trim any potential hashtags
        for word in tokenizer.tokenize(tweet.lstrip("#")):
            word = word.lower()
            if word not in exclusions and len(word) > minwordlen:
                cleaned.append(word)
    else:
        TypeError("tweets is expected to be a string or list of strings")
    # could dedupe here, but then wouldn't get the word count
    return cleaned

def expand_location_search(place):
    # format for address is <address number>, <street>, <city>, <county>, <state>, <zip>, <country>
    if place.count(",") >= 1:
        return ",".join(place.split(", ")[2:] if place.count(",") >=6 else place.split(", ")[1:])
    else:
        return None

# ideally... could multithread this to speed up generation
def get_geo_trends(api,place,user_agent="Twitter wordlist builder"):
    if api is not None and place is not None:
        geo_trends = list()
        geolocator = Nominatim(user_agent=user_agent)
        location = geolocator.geocode(place)
        if location.address is None:
            ValueError("Could not find {0}. Please check spelling and try again.".format(place))
        resp = api._RequestUrl(f'{api.base_url}/trends/closest.json',verb='GET',data={'lat':location.latitude,"long":location.longitude})
        try:
            woeid = resp.json()[0]['woeid']
            print("{0} - {1}".format(place, woeid))
            geo_trends = api.GetTrendsWoeid(woeid=woeid)
            geo_trends.extend(geo_trends)
            geo_trends.extend(get_geo_trends(api,expand_location_search(location.address)))
        except:
            KeyError("Was unable to derive the woeid for {0}".format(place))
        return geo_trends
    else:
        return None

def convert_tuple_to_dict(tuplist,fieldnames=['Word','Occurences']):
    converted = list()
    for e in tuplist:
        tmp = dict()
        for index,name in enumerate(fieldnames):
            tmp[name] = e[index]
        converted.append(tmp)
    return converted

def generate_word_list(api,since=None,until=None,username=None,location=None,globaltrends=True,number=100,minwordlen=3,outputdir=None):
    date_regex = r"\d{4}(-\d{2}){2}"
    if (since is not None and not re.match(date_regex,since)) or (until is not None and not re.match(date_regex,until)):
        ValueError("Dates must be specified in yyyy-mm-dd format")
    #• Ability to time box the search (between date a and b)
	#• Add the ability to do this overtime
	#	○ Either aggregate, running daily, or find a way to query historical data
    allWords = list()
    # TODO: I think black hills mentioned a better way to get geolocation... look into that
    geolookup_url = "http://ipinfo.io"
    # if specified, get user specific data
    if user is not None:
       	#• search by from/to account
        #• get info on account's hashtag
        #	○ get info on most popular/recent tweets using those (non-account specific)
        user_info = list()
        # get basic information about the user
        user = api.GetUser(screen_name=username)
        user_info.extend([user.location,user.name,user.description,user.status.text])
        # get information for user's location (if available)
        if user.location is not None:
            user_location_trends = get_geo_trends(api,user.location)
            user_info.extend([t.name for t in user_location_trends])
        # get timeline information for the user
        user_timeline = api.GetUserTimeline(user_id=user.id)
        user_info.extend([s.text for s in user_timeline])
        # get favorites
        faves = api.GetFavorites(user_id=user.id)
        user_info.extend([s.text for s in faves])
        # maybe pull out hashtags and mentioned users and get info on them
        allWords.extend(clean_tweets(user_info, minwordlen))
    # if specified, get geo data, if not, attempt to get current location
    if location is None:
        try:
            iplookup = requests.get(geolookup_url).json()
            location = "{0}, {1}, {2}, {3}".format(iplookup['city'],iplookup['region'],iplookup['postal'],iplookup['country'])
        except:
            print("Unable to get geo IP information; skipping location based trend lookup")
            location = None
    # location can be full address, city, county, state, zip, or country
    # this will attempt to expand out from location specified to country in reverse order
    if location is not None:
        location_trends = get_geo_trends(api,location)
        allWords.extend(clean_tweets([t.name for t in location_trends], minwordlen))
    # get worldwide trends
    if globaltrends == True:
        trends = api.GetTrendsCurrent()
        allWords.extend(clean_tweets([t.name for t in trends]), minwordlen)
    # this will effectively handle deduplication and frequency of occurence ordering
    # TODO: see about using pandas (think that's what it's for) to generate a frequency analysis plot of some sort
    if outputdir is None:
        return dict(Counter(allWords).most_common())
    else:
        datestr = datetime.now().isoformat()[:-7]
        filename = "{0}{1}{2}.csv".format(username+"_" if username is not None else "",location+"_" if location is not None else "",datestr)
        # strip out potentially bad chars
        filename = re.sub(r'[^\w\-_\.\s]','_',filename)
        outfile = path.join(outputdir,filename)
        fieldnames = ['Word','Occurences']
        outdict = convert_tuple_to_dict(Counter(allWords).most_common(),fieldnames)
        with open(outfile,mode="w",encoding="UTF-8",newline='') as csvfile:
            writer = csv.DictWriter(csvfile,fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(outdict)


def main(consumer_key=None,consumer_secret=None,access_token_key=None,access_token_secret=None,username=None,
outputdir="./",location=None,globaltrends=False,minwordlen=3):
    if consumer_key is None or access_token_key is None:
        ValueError("Consumer key and access token key are required")
    if consumer_secret is None and consumer_key is not None:
        consumer_secret = getpass.getpass("Please enter your consumer secret:\n")
    if access_token_secret is None and access_token_key is not None:
        access_token_secret = getpass.getpass("Please enter your access token secret:\n")
    api = twitter.Api(consumer_key=consumer_key, consumer_secret=consumer_secret,
        access_token_key=access_token_key,access_token_secret=access_token_secret)
    if api.VerifyCredentials().id is None:
        ValueError("The credentials specified are incorrect, try again")
    generate_word_list(api,username=username,outputdir=outputdir,location=location,globaltrends=globaltrends,minwordlen=minwordlen)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        add_help=False,
        description=
        '''Parse and extract url browsing history and download history from chrome's'''
        '''user history sqlite db handling constant interpretation and tz conversion.''',
        formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=40)
    )

    parser.add_argument('-ck', '--consumerkey', type=str, metavar="STRING", default=None, help="The twitter API consumer key.")
    parser.add_argument('-cs', '--consumersecret', type=str, metavar="STRING", default=None, help="The twitter API consumer secret.")
    parser.add_argument('-ak', '--accesskey', type=str, metavar="STRING", default=None, help="The twitter API accesskey.")
    parser.add_argument('-as', '--accesssecret', type=str, metavar="STRING", default=None, help="The twitter API access secret.")
    parser.add_argument('-u', '--username', type=str, metavar="STRING", default=None, help="The twitter user to pull information from.")
    parser.add_argument('-o', '--outputdir', type=str, metavar="STRING", default="./", help="The directory to write results to. The file name is dynamically generated based on params. (Default=./)")
    parser.add_argument('-l', '--location', type=str, metavar="STRING", default=None, help="The location to get geotrends for. Can be an address, city, county, state, or country.")
    parser.add_argument('-g', '--globaltrends', action='store_true', help="Will return global trends in the result set.")
    parser.add_argument('-m', '--minwordlen', type=str, metavar="INT", default=3, help="The minimum length of words to append to the wordlist. (Default=3)")
    
    if len(sys.argv) >= 2 and sys.argv[1] in ('-h','--help'):
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    main(consumer_key=args.consumer_key,consumer_secret=args.consumer_secret,access_token_key=args.access_token_key,access_token_secret=args.access_token_secret,
    username=args.username,outputdir=args.outputdir,location=args.location,globaltrends=args.globaltrends,minwordlen=args.minwordlen)
    sys.exit(0)