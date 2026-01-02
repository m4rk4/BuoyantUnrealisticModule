import base64, math, re
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def calculate_duration(sec):
    duration = []
    t = math.floor(float(sec) / 3600)
    if t >= 1:
        duration.append('{} hr'.format(t))
    t = math.ceil((float(sec) - 3600 * t) / 60)
    if t > 0:
        duration.append('{} min.'.format(t))
    return ', '.join(duration)


def decode_stream_url(encoded):
    X = 'DONOTDOWNLOADFROMMIXCLOUD'
    STREAM_INFO_XOR_KEY = 'IFYOUWANTTHEARTISTSTOGETPAID' + X
    STREAM_INFO_XOR_KEY_LEN = len(STREAM_INFO_XOR_KEY)
    data = base64.b64decode(encoded).decode('utf-8')
    datalen = len(data)
    output = ''
    for i in range(datalen):
        output += chr(ord(data[i]) ^ ord(STREAM_INFO_XOR_KEY[i % STREAM_INFO_XOR_KEY_LEN]))
    return output


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if '/widget/iframe' in url:
        url_query = parse_qs(split_url.query)
        if 'feed' not in url_query:
            logger.warning('unhandled url ' + url)
            return None
        feed = url_query['feed'][0]
    else:
        feed = split_url.path

    gql_url = 'https://www.mixcloud.com/graphql'
    gql_query = {"query":"query PlayerWidgetContainerQuery(\n  $feed: String!\n  $first: Int\n) {\n  viewer {\n    ...PlayerWidgetRenderer_viewer_hBTIE\n    id\n  }\n}\n\nfragment CloudcastImage_cloudcast on Cloudcast {\n  slug\n  owner {\n    username\n    id\n  }\n  picture {\n    ...UGCImage_picture\n  }\n}\n\nfragment CoverImage_cloudcast on Cloudcast {\n  name\n  slug\n  owner {\n    username\n    displayName\n    id\n  }\n  picture {\n    urlRoot\n  }\n  ...ExclusiveBadge_cloudcast\n  ...WidgetPlayButton_cloudcast\n}\n\nfragment ExclusiveBadge_cloudcast on Cloudcast {\n  isExclusive\n  owner {\n    username\n    id\n  }\n}\n\nfragment ExclusiveMessage_user on User {\n  displayName\n  username\n}\n\nfragment FollowToggleButton_user on User {\n  id\n  isFollowing\n  username\n  isViewer\n  followers {\n    totalCount\n  }\n}\n\nfragment FollowToggleButton_viewer on Viewer {\n  me {\n    id\n  }\n}\n\nfragment MiniControls_cloudcast on Cloudcast {\n  isUnlisted\n  ...WidgetFavoriteButton_cloudcast\n  ...WidgetRepostButton_cloudcast\n}\n\nfragment MiniControls_viewer on Viewer {\n  ...WidgetFavoriteButton_viewer\n  ...WidgetRepostButton_viewer\n}\n\nfragment PlayerSlider_cloudcast on Cloudcast {\n  isExclusive\n  owner {\n    username\n    isSubscribedTo\n    isViewer\n    id\n  }\n  ...WidgetSeekWarning_cloudcast\n}\n\nfragment PlayerWidgetRenderer_viewer_hBTIE on Viewer {\n  playerWidgetFeed(feed: $feed, first: $first) {\n    edges {\n      node {\n        id\n        owner {\n          isViewer\n          isSubscribedTo\n          ...ExclusiveMessage_user\n          ...SelectUpsell_user\n          id\n        }\n        isPlayable\n        isExclusive\n        streamInfo {\n          hlsUrl\n          dashUrl\n          url\n          uuid\n        }\n        currentPosition\n        audioLength\n        seekRestriction\n        ...UpNext_currentCloudcast\n        ...TrackList_cloudcast\n        ...CoverImage_cloudcast\n        ...WidgetControls_cloudcast\n        ...CloudcastImage_cloudcast\n        ...ShareModal_cloudcast\n      }\n    }\n    ...UpNext_cloudcasts\n  }\n  ...WidgetControls_viewer\n}\n\nfragment SelectUpsell_user on User {\n  displayName\n  username\n}\n\nfragment ShareModal_cloudcast on Cloudcast {\n  slug\n  name\n  owner {\n    username\n    id\n  }\n}\n\nfragment Stats_cloudcast on Cloudcast {\n  plays\n  hiddenStats\n  favorites {\n    totalCount\n  }\n  reposts {\n    totalCount\n  }\n}\n\nfragment Title_cloudcast on Cloudcast {\n  name\n  slug\n  isExclusive\n  owner {\n    username\n    displayName\n    isFollowing\n    isSubscribedTo\n    isSelect\n    ...FollowToggleButton_user\n    id\n  }\n  ...ExclusiveBadge_cloudcast\n}\n\nfragment Title_viewer on Viewer {\n  ...FollowToggleButton_viewer\n}\n\nfragment TrackList_cloudcast on Cloudcast {\n  featuringArtistList\n  moreFeaturingArtists\n  isExclusive\n  owner {\n    isSelect\n    isSubscribedTo\n    isViewer\n    displayName\n    username\n    id\n  }\n  sections {\n    __typename\n    ... on TrackSection {\n      songName\n      artistName\n    }\n    ... on ChapterSection {\n      chapter\n    }\n    ... on Node {\n      __isNode: __typename\n      id\n    }\n  }\n}\n\nfragment UGCImage_picture on Picture {\n  urlRoot\n  primaryColor\n}\n\nfragment UpNextItem_cloudcast on Cloudcast {\n  name\n  owner {\n    displayName\n    id\n  }\n  picture {\n    ...UGCImage_picture\n  }\n}\n\nfragment UpNext_cloudcasts on CloudcastConnection {\n  edges {\n    node {\n      id\n      ...UpNextItem_cloudcast\n    }\n  }\n}\n\nfragment UpNext_currentCloudcast on Cloudcast {\n  id\n}\n\nfragment WidgetControls_cloudcast on Cloudcast {\n  ...WidgetLogo_cloudcast\n  ...PlayerSlider_cloudcast\n  ...MiniControls_cloudcast\n  ...WidgetErrorMessage_cloudcast\n  ...Title_cloudcast\n  ...Stats_cloudcast\n  ...WidgetRepostButton_cloudcast\n  ...WidgetFavoriteButton_cloudcast\n  ...WidgetPlayButton_cloudcast\n}\n\nfragment WidgetControls_viewer on Viewer {\n  ...WidgetFavoriteButton_viewer\n  ...WidgetRepostButton_viewer\n  ...MiniControls_viewer\n  ...Title_viewer\n}\n\nfragment WidgetErrorMessage_cloudcast on Cloudcast {\n  restrictedReason\n  isAwaitingAudio\n  isExclusive\n  owner {\n    isSubscribedTo\n    isViewer\n    id\n  }\n}\n\nfragment WidgetFavoriteButton_cloudcast on Cloudcast {\n  id\n  isFavorited\n  slug\n  owner {\n    username\n    id\n  }\n  favorites {\n    totalCount\n  }\n}\n\nfragment WidgetFavoriteButton_viewer on Viewer {\n  me {\n    id\n  }\n}\n\nfragment WidgetLogo_cloudcast on Cloudcast {\n  slug\n  owner {\n    username\n    id\n  }\n}\n\nfragment WidgetPlayButton_cloudcast on Cloudcast {\n  isExclusive\n  owner {\n    isSubscribedTo\n    isViewer\n    isSelect\n    id\n  }\n}\n\nfragment WidgetRepostButton_cloudcast on Cloudcast {\n  id\n  slug\n  isReposted\n  isExclusive\n  reposts {\n    totalCount\n  }\n  owner {\n    isViewer\n    username\n    isSubscribedTo\n    id\n  }\n}\n\nfragment WidgetRepostButton_viewer on Viewer {\n  me {\n    id\n  }\n}\n\nfragment WidgetSeekWarning_cloudcast on Cloudcast {\n  owner {\n    displayName\n    isSelect\n    username\n    selectUpsell {\n      __typename\n    }\n    id\n  }\n}\n","variables":{"feed":feed,"first":20}}
    gql_data = utils.post_url(gql_url, json_data=gql_query)
    if not gql_data:
        return None
    if save_debug:
        utils.write_file(gql_data, './debug/audio.json')

    episode = gql_data['data']['viewer']['playerWidgetFeed']['edges'][0]['node']

    item = {}
    item['id'] = episode['id']
    item['url'] = 'https://www.mixcloud.com/{}/{}'.format(episode['owner']['username'], episode['slug'])
    item['title'] = episode['name']

    # Dummy date
    dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt, True)

    item['author'] = {"name": episode['owner']['displayName']}
    item['tags'] = episode['featuringArtistList'].copy()
    item['_image'] = 'https://thumbnailer.mixcloud.com/unsafe/128x128/' + episode['picture']['urlRoot']
    item['_audio'] = decode_stream_url(episode['streamInfo']['hlsUrl'])
    play_url = config.server + '/videojs?src=' + quote_plus(item['_audio'])

    item['_duration'] = calculate_duration(episode['audioLength'])

    poster = '{}/image?url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))
    desc = '<h4 style="margin-top:0; margin-bottom:0.5em;"><a href="{}">{}</a></h4><small>by {}<br/>{}</small>'.format(item['url'], item['title'], item['author']['name'], item['_duration'])
    item['content_html'] = '<table style="width:100%"><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;">{}</td></tr></table>'.format(play_url, poster, desc)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return None
