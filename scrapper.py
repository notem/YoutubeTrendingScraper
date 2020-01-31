#!/usr/bin/python

import argparse
import re
import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the {{ Google Cloud Console }} at
# {{ https://cloud.google.com/console }}.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = 'client_secret.json'

# This OAuth 2.0 access scope allows for read-only access to the authenticated
# user's account, but not other types of account access.
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
REGION_CODE = 'US'


def get_authenticated_service():
    """
    Authorize the request and store authorization credentials.
    """
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    credentials = flow.run_console()
    return googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials)


def parse_duration(duration):
    """
    Parse an duration string into raw seconds representation.

    Parameters
    ----------
    duration : str
        ISO 8601 duration string

    Returns
    -------
    int
        Parsed duration as seconds
    """
    # match to a ISO 8601 duration string (eg. 'PnYnMnDTnHnMnS')
    m = re.match('^(P(.+)?)'
                 '(T(?P<hours>\\d+H)?(?P<minutes>\\d+M)?(?P<seconds>\\d+S)?)$', duration)
    duration = 0

    # Time duration
    if m:
        d = m.groupdict()
        if d['hours']:
            duration += int(d['hours'][:-1]) * 60 * 60
        if d['minutes']:
            duration += int(d['minutes'][:-1]) * 60
        if d['seconds']:
            duration += int(d['seconds'][:-1])

    # if duration == 0, parsing probably failed?
    assert duration != 0
    return duration


def most_popular(youtube, video_count, **kwargs):
    """
    Parameters
    ----------
    youtube : Youtube API Service object
    video_count : int
    kwargs : Keyword Arguments
        Additional arguments passed to youtube api list() function.

    Returns
    -------
    """
    videos = []
    next_page = None
    while len(videos) < video_count:
        try:
            request = youtube.videos().list(
                part="contentDetails",
                chart="mostPopular",
                regionCode=REGION_CODE,
                pageToken=next_page,
                **kwargs
            )
            response = request.execute()
            videos.extend([(item['id'], parse_duration(item['contentDetails']['duration']))
                           for item in response['items']])
            next_page = response.get('nextPageToken', None)
        except Exception as e:
            print(e)
            break
    return videos


def video_categories(youtube, **kwargs):
    """
    Parameters
    ----------
    youtube : Youtube API Service object
    kwargs : Keyword Arguments
        Additional arguments passed to youtube api list() function.

    Returns
    -------
    dict
        Dictionary mapping video category ID with human understandable name.
    """
    request = youtube.videoCategories().list(
        part="snippet",
        regionCode=REGION_CODE,
        **kwargs
    )
    response = request.execute()
    return {item['id']: item['snippet']['title'] for item in response['items']}


if __name__ == '__main__':

    # parse commandline arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', type=str, required=True,
                        help='File in which to save the scrapped videos.')
    parser.add_argument('--count', type=int, required=True,
                        help='Number of video IDs to scrape.')
    parser.add_argument('--duration', type=int, default=None,
                        help='Select videos which are approximately this number of minutes long.')
    parser.add_argument('--deviation', type=int, default=30,
                        help='Number of seconds a video may deviate from the target duration.')
    parser.add_argument('--category', #choices=categories.values(),
                        help='Filter videos by this category.')
    args = parser.parse_args()

    # get youtube service
    yt = get_authenticated_service()

    # get available categories
    try:
        categories = video_categories(yt)
    except Exception as e:
        print(e)
        categories = []

    # make video requests
    videos = []
    if args.category:
        for identifier, name in categories.items():
            if name == args.category:
                videos = most_popular(yt, args.count, videoCategoryId=identifier)
                break
    else:
        videos = most_popular(yt, args.count)

    # remove videos which do not meet our target duration
    target_duration = args.duration
    if not target_duration:
        times = [video[1]//60 for video in videos]
        target_duration = max(set(times), key=times.count)
    filtered_videos = list(filter(lambda video: abs((target_duration * 60) - video[1]) < args.deviation, videos))

    print('Duration:  {} minutes'.format(target_duration))
    print('Deviation: {} minutes'.format(args.deviation))

    print('Total:     {} videos'.format(len(videos)))
    print('Filtered:  {} videos'.format(len(filtered_videos)))

    # write result to file
    try:
        os.makedirs(os.path.dirname(args.file))
    except:
        pass
    with open(args.file, 'w+') as fp:
        fp.write('# Most popular videos, {}+/-{}\n'.format(target_duration, args.deviation))
        fp.write('\n'.join([video[0] for video in filtered_videos]))
        fp.write('\n# Following video IDs did not meet duration specifications\n')
        fp.write('\n'.join(['# '+video[0] for video in videos if video not in filtered_videos]))

