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

# there is a more extensive list than nltk's, import stoplist from custom_stoplist
# snagged from https://gist.github.com/sebleier/554280#gistcomment-3126707

global tokenizer
global exclusions

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

def get_location(place,user_agent="Twitter wordlist builder"):
    geolocator = Nominatim(user_agent=user_agent)
    location = geolocator.geocode(place)
    return location

# ideally... could multithread this to speed up generation
def get_geo_trends(api,place,user_agent="Twitter wordlist builder"):
    if api is not None and place is not None:
        geo_trends = list()
        location = get_location(place)
        if location.address is None:
            ValueError("Could not find {0}. Please check spelling and try again.".format(place))
        resp = api._RequestUrl(f'{api.base_url}/trends/closest.json',verb='GET',data={'lat':location.latitude,"long":location.longitude})
        try:
            woeid = resp.json()[0]['woeid']
            print("Pulling trends for place: {0} - woeid: {1}".format(place, woeid))
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

def generate_word_list(api,since=None,until=None,username=None,lists=False,subscriptions=False,mentions=False,tweets_to=False,tweets_from=False,
count=20,location=None,currentlocation=False,loc_popular=False,loc_recent=False,radius=5,globaltrends=False,number=100,minwordlen=3,
outputdir=None,all=False):
    global tokenizer
    global exclusions
    nltk_download('stopwords')
    nltk_download('punkt')
    tokenizer = TweetTokenizer()
    exclusions = stopwords.words('english')
    date_regex = r"\d{4}(-\d{2}){2}"
    if count > 200:
        print("Count lowest common denominator max is 200 but specified {0}. Setting to 200.".format(count))
        count = 200
    if all:
        lists = subscriptions = mentions = tweets_to = tweets_from = currentlocation = globaltrends = loc_popular = loc_recent = True
    # TODO: evaluate if date/time boxing is practical to implement
    if (since is not None and not re.match(date_regex,since)) or (until is not None and not re.match(date_regex,until)):
        ValueError("Dates must be specified in yyyy-mm-dd format")
    #• Ability to time box the search (between date a and b)
	#• Add the ability to do this overtime
	#	○ Either aggregate, running daily, or find a way to query historical data
    allWords = list()
    # TODO: I think black hills mentioned a more precise way to get geolocation... look into that
    # TODO: also, seems like twitter has a built in API to handle lookup by IP and lat/long to woeid
    geolookup_url = "http://ipinfo.io"
    # if specified, get user specific data
    if username is not None:
        #• get info on account's hashtag
        #	○ get info on most popular/recent tweets using those (non-account specific)
        user_info = list()
        # **** PROFILE INFO ****
        # get basic information about the user
        print("Pulling profile info for {0}".format(username))
        user = api.GetUser(screen_name=username)
        user_info.extend([user.location,user.name,user.description,user.status.text])
        # get information for user's location (if available)
        if user.location is not None:
            print("Found associated location for {0}.".format(username))
            user_location_trends = get_geo_trends(api,user.location)
            user_info.extend([t.name for t in user_location_trends])
        # get timeline information for the user
        print("Pulling timeline info for {0}".format(username))
        user_timeline = api.GetUserTimeline(user_id=user.id,count=count)
        user_info.extend([s.text for s in user_timeline])
        # get favorites
        print("Pulling favorites info for {0}".format(username))
        faves = api.GetFavorites(user_id=user.id,count=count)
        user_info.extend([s.text for s in faves])
        # **** SEARCHES ****
        # these searches will all be a mix of popular and current, seems good enough for me
        if mentions:
            print("Pulling mentions for {0}".format(username))
            mentions_query = "@{0}".format(username)
            mentions_search = api.GetSearch(term=mentions_query,count=count)
            user_info.extend([s.text for s in mentions_search])
        if tweets_to:
            print("Pulling tweets to {0}".format(username))
            to_query = "to:{0}".format(username)
            to_search = api.GetSearch(term=to_query,count=count)
            user_info.extend([s.text for s in to_search])
        if tweets_from:
            print("Pulling tweets from {0}".format(username))
            from_query = "from:{0}".format(username)
            from_search = api.GetSearch(term=from_query,count=count)
            user_info.extend([s.text for s in from_search])
        # **** LISTS ****
        if lists:
            print("Pulling list timelines for {0}".format(username))
            lists = api.GetLists(user_id=user.id,count=count)
            listTimelines = list()
            for entry in lists:
                listTimelines.extend(api.GetListTimeline(list_id=entry.id,count=count))
            user_info.extend([l.text for l in listTimelines])
        if subscriptions:
            print("Pulling subscribed list timelines for {0}".format(username))
            subs = api.GetSubscriptions(user_id=user.id,count=count)
            subTimelines = list()
            for entry in subs:
                subTimelines.extend(api.GetListTimeline(list_id=entry.id,count=count))
            user_info.extend([l.text for l in subTimelines])
        allWords.extend(clean_tweets(user_info, minwordlen))
    # if specified, get geo data, if not, attempt to get current location
    if location is None and currentlocation:
        try:
            iplookup = requests.get(geolookup_url).json()
            location = "{0}, {1}, {2}, {3}".format(iplookup['city'],iplookup['region'],iplookup['postal'],iplookup['country'])
            print("No location specified, pulling from IP: {0}".format(location))
        except:
            print("Unable to get geo IP information; skipping location based trend lookup")
            location = None
    # location can be full address, city, county, state, zip, or country
    # this will attempt to expand out from location specified to country in reverse order
    if location is not None:
        if loc_recent or loc_popular:
            loc = get_location(location)
            search_geocode = [loc.latitude,loc.longitude,"{0}mi".format(radius)]
        location_trends = get_geo_trends(api,location)
        allWords.extend(clean_tweets([t.name for t in location_trends], minwordlen))
        if loc_popular:
            print("Pulling popular tweets for {0}".format(location))
            popular_tweets = api.GetSearch(geocode=search_geocode,result_type="popular",count=count)
            allWords.extend(clean_tweets([t.text for t in popular_tweets], minwordlen))
        if loc_recent:
            print("Pulling recent tweets for {0}".format(location))
            recent_tweets = api.GetSearch(geocode=search_geocode,result_type="recent",count=count)
            allWords.extend(clean_tweets([t.text for t in recent_tweets], minwordlen))
    # get worldwide trends
    if globaltrends == True:
        print("Pulling glocal trends")
        trends = api.GetTrendsCurrent()
        allWords.extend(clean_tweets([t.name for t in trends], minwordlen))
    # this will effectively handle deduplication and frequency of occurence ordering
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
lists=False,subscriptions=False,count=20,outputdir="./",location=None,current_location=False,loc_popular=False,loc_recent=False,
radius=5,globaltrends=False,minwordlen=3,all=False):
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
    generate_word_list(api,username=username,lists=lists,subscriptions=subscriptions,count=count,outputdir=outputdir,location=location,
    currentlocation=current_location,loc_popular=loc_popular,loc_recent=loc_recent,radius=radius,globaltrends=globaltrends,minwordlen=minwordlen,all=all)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        add_help=False,
        description=
        '''Parse and extract english words from trending tweets and perform frequency analysis.'''
        '''If desirable, can specify a specific user to target as well.''',
        formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=40)
    )

    parser.add_argument('-ck', '--consumer_key', type=str, metavar="STRING", default=None, help="The twitter API consumer key.")
    parser.add_argument('-cs', '--consumer_secret', type=str, metavar="STRING", default=None, help="The twitter API consumer secret.")
    parser.add_argument('-ak', '--access_token_key', type=str, metavar="STRING", default=None, help="The twitter API accesskey.")
    parser.add_argument('-as', '--access_token_secret', type=str, metavar="STRING", default=None, help="The twitter API access secret.")
    parser.add_argument('-u', '--username', type=str, metavar="STRING", default=None, help="The twitter user to pull information from.")
    parser.add_argument('--lists', action='store_true', help="Pull lists created by the specified user and their timeline info.")
    parser.add_argument('-s', '--subscriptions', action='store_true', help="Pull lists subscribed to by the specified user and their timeline info.")
    parser.add_argument('-c', '--count', type=int, metavar="INT", default=20, help="The number of results to pull from each query. Max is 200 as a lowest common denominator. (default=20)")
    parser.add_argument('-o', '--outputdir', type=str, metavar="STRING", default="./", help="The directory to write results to. The file name is dynamically generated based on params. (Default=./)")
    parser.add_argument('-l', '--location', type=str, metavar="STRING", default=None, help="The location to get geotrends for. Can be an address, city, county, state, or country.")
    parser.add_argument('-c', '--current_location', action='store_true', help="Attempt to retrieve current location based on IP. Explicit locations take precedence of this parameter.")
    parser.add_argument('--loc_popular', action='store_true', help="Retrieve popular tweets in the location specified or retrieved from IP.")
    parser.add_argument('--loc_recent', action='store_true', help="Retrieve recent tweets in the location specified or retrieved from IP.")
    parser.add_argument('-r', '--radius', type=int, metavar="INT", default=5, help="The radius to return results for in miles if loc_popular or loc_recent are specified. (default=5)")
    parser.add_argument('-g', '--globaltrends', action='store_true', help="Includes global trends in the result set.")
    parser.add_argument('-m', '--minwordlen', type=str, metavar="INT", default=3, help="The minimum length of words to append to the wordlist. (Default=3)")
    parser.add_argument('-a','--all', action='store_true', help="Set all options to 'True'.")
    
    if len(sys.argv) >= 2 and sys.argv[1] in ('-h','--help'):
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    main(consumer_key=args.consumer_key,consumer_secret=args.consumer_secret,access_token_key=args.access_token_key,access_token_secret=args.access_token_secret,
    username=args.username,lists=args.lists,subscriptions=args.subscriptions,count=args.count,outputdir=args.outputdir,location=args.location,
    current_location=args.current_location,loc_popular=args.loc_popular,loc_recent=args.loc_recent,radius=args.radius,globaltrends=args.globaltrends,minwordlen=args.minwordlen,
    all=args.all)
    sys.exit(0)