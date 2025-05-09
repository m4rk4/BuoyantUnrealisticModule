import base64, json, random, re, requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_api_data(api_url, extra_params=None, extra_headers=None):
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9,de;q=0.8',
        'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="98", "Microsoft Edge";v="98"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.50'
    }
    if extra_headers:
        headers.update(extra_headers)

    params = {
        "aid": "1988",
        "app_name": "tiktok_web",
        "channel": "tiktok_web",
        "device_platform": "web_pc",
        "device_id": 7067278850413610501,
        "region": "US",
        "priority_region": "",
        "os": "windows",
        "referer": "",
        "root_referer": "https%3A%2F%2Fwww.tiktok.com%2F",
        "cookie_enabled": "true",
        "screen_width": 1920,
        "screen_height": 1200,
        "browser_language": "en-US",
        "browser_platform": "Win32",
        "browser_name": "Mozilla",
        "browser_version": "5.0%20%28Windows%20NT%2010.0%3B%20Win64%3B%20x64%29%20AppleWebKit%2F537.36%20%28KHTML%2C%20like%20Gecko%29%20Chrome%2F98.0.4758.80%20Safari%2F537.36%20Edg%2F98.0.1108.50",
        "browser_online": "true",
        "app_language": "en",
        "webcast_language": "en",
        "tz_name": "America%2FNew_York",
        "is_page_visible": "true",
        "focus_state": "true",
        "is_fullscreen": "false",
        "history_len": 50,
        "battery_info": 1,
        "cursor": 0,
        "from_page": "fyp",
        "language": "en"
    }
    if extra_params:
        params.update(extra_params)
    param_list = ['{}={}'.format(key, val) for key, val in dict(sorted(params.items())).items()]
    query = '&'.join(param_list)
    return utils.get_url_json(api_url + '?' + query, headers=headers)


def encrypt_params(params):
    # https://medium.com/@sachadehe/encrypt-decrypt-data-between-python-3-and-javascript-true-aes-algorithm-7c4e2fa3a9ff
    param_list = ['{}={}'.format(key, val) for key, val in params.items()]
    param_list.append('is_encryption=1')
    data = '&'.join(param_list)
    pad_data = pad(data.encode(), 16)

    key = 'webapp1.0+20210628'
    n = len(key)
    if n > 16:
        key = key[:16]
    elif n < 16:
        key = ''.join(['0'] * (16 - n)) + key

    iv = key.encode('utf-8')
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv)
    enc_data = cipher.encrypt(pad_data)
    return base64.b64encode(enc_data).decode('utf-8', 'ignore')


def get_fyp_items():
    params = {"count": 30, "versions": "50143350,70405643"}
    return get_api_data('https://m.tiktok.com/api/recommend/item_list/', params)


def get_item_detail(item_id):
    params = {"itemId": item_id}
    return get_api_data('https://m.tiktok.com/api/item/detail/', params)


def get_topic_items(topic):
    params = {"from_page": "topics_{}".format(topic), "topic": topic, "count": 30}
    return get_api_data('https://m.tiktok.com/api/topic/item_list/', params)


def get_challenge_detail(challenge_name):
    params = {"from_page": "hashtag", "challengeName": challenge_name}
    return get_api_data('https://m.tiktok.com/api/challenge/detail/', params)


def get_challenge_items(challenge_name):
    challenge = get_challenge_detail(challenge_name)
    if not challenge:
        return None
    params = {"from_page": "hashtag", "challengeID": challenge['challengeInfo']['challenge']['id'], "count": 30}
    return get_api_data('https://m.tiktok.com/api/challenge/item_list/', params)


def get_music_detail(music_id):
    params = {"from_page": "music", "musicId": music_id}
    return get_api_data('https://m.tiktok.com/api/music/detail/', params)


def get_music_items(music_id):
    params = {
        "aid": "1988",
        "app_name": "tiktok_web",
        "channel": "tiktok_web",
        "device_platform": "web_pc",
        "device_id": 7067278850413610501,
        "region": "US",
        "priority_region": "",
        "os": "windows",
        "referer": "",
        "root_referer": "https://www.tiktok.com/",
        "cookie_enabled": "true",
        "screen_width": 1920,
        "screen_height": 1200,
        "browser_language": "en-US",
        "browser_platform": "Win32",
        "browser_name": "Mozilla",
        "browser_version": "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.50",
        "browser_online": "true",
        "verifyFp": "undefined",
        "app_language": "en",
        "webcast_language": "en",
        "tz_name": "America/New_York",
        "is_page_visible": "true",
        "focus_state": "true",
        "is_fullscreen": "false",
        "history_len": random.randint(0, 99),
        "battery_info": 1,
        "from_page": "music",
        "musicID": music_id,
        "count": 30,
        "cursor": 0,
        "language": "en",
        "userId": "undefined",
    }
    x_tt_params = encrypt_params(params)
    return get_api_data('https://m.tiktok.com/api/music/item_list/', extra_headers={"x-tt-params": x_tt_params})


def get_user_detail(username):
    params = {"uniqueId": username, "secUid": ""}
    return get_api_data('https://www.tiktok.com/api/user/detail/', params)


def get_user_items(username):
    user_detail = get_user_detail(username)
    if not user_detail:
        return None

    # Not sure if order matters
    params = {
        "aid": "1988",
        "app_name": "tiktok_web",
        "channel": "tiktok_web",
        "device_platform": "web_pc",
        "device_id": 7067278850413610501,
        "region": "US",
        "priority_region": "",
        "os": "windows",
        "referer": "",
        "root_referer": "https://www.tiktok.com/",
        "cookie_enabled": "true",
        "screen_width": 1920,
        "screen_height": 1200,
        "browser_language": "en-US",
        "browser_platform": "Win32",
        "browser_name": "Mozilla",
        "browser_version": "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.50",
        "browser_online": "true",
        "verifyFp": "undefined",
        "app_language": "en",
        "webcast_language": "en",
        "tz_name": "America/New_York",
        "is_page_visible": "true",
        "focus_state": "true",
        "is_fullscreen": "false",
        "history_len": random.randint(0, 99),
        "battery_info": 1,
        "from_page": "user",
        "secUid": user_detail['userInfo']['user']['secUid'],
        "count": 30,
        "cursor": 0,
        "language": "en",
        "userId": "undefined",
    }
    x_tt_params = encrypt_params(params)
    return get_api_data('https://m.tiktok.com/api/post/item_list/', extra_headers={"x-tt-params": x_tt_params})


def replace_entity(matchobj):
    if matchobj.group(1) == '@':
        return '<a href="https://www.tiktok.com/@{0}">@{0}</a>'.format(matchobj.group(2))
    elif matchobj.group(1) == '#':
        return '<a href="https://www.tiktok.com/tag/{0}">#{0}</a>'.format(matchobj.group(2))
    return matchobj.group(0)


def get_item(item_info, args, site_json, save_debug):
    item = {}
    item['id'] = item_info['id']
    item['url'] = 'https://www.tiktok.com/@{}/video/{}'.format(item_info['author']['uniqueId'], item_info['id'])

    if item_info.get('desc'):
        desc = item_info['desc'].replace('#', ' #').replace('  ', ' ').strip()
        if len(desc) > 50:
            item['title'] = desc[:50] + '...'
        else:
            item['title'] = desc
        item['summary'] = re.sub(r'(@|#)(\w+)', replace_entity, desc, flags=re.I)
    else:
        item['title'] = 'A video from ' + item_info['author']['uniqueId']

    dt = datetime.fromtimestamp(int(item_info['createTime']))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    item['author']['name'] = '{} (@{})'.format(item_info['author']['nickname'], item_info['author']['uniqueId'])

    avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(item_info['author']['avatarMedium']))
    author_info = '<a href="https://www.tiktok.com/@{0}"><b>{0}</b></a>&nbsp;<small>'.format(item_info['author']['uniqueId'])
    if item_info['author']['verified']:
        author_info += '&#9989;&nbsp;'
    author_info += '{}</small>'.format(item_info['author']['nickname'])

    if item_info.get('challenges'):
        item['tags'] = []
        for tag in item_info['challenges']:
            if not tag['title'] in item['tags']:
                item['tags'].append(tag['title'])

    item['_image'] = item_info['video']['cover']
    item['_video'] = item_info['video']['playAddr']

    if item_info.get('music'):
        item['_audio'] = item_info['music']['playUrl']
        music_info = '<a href="https://www.tiktok.com/music/{}-{}?lang=en">{} &ndash; {}</a>'.format(
            item_info['music']['title'].replace(' ', '-'), item_info['music']['id'], item_info['music']['title'],
            item_info['music']['authorName'])

    #item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{}"/><div style="overflow:hidden;">{}<br/><small>{}</small></div><div style="clear:left;"></div></div>'.format(avatar, author_info, dt.strftime('%Y-%m-%d'))

    #item['content_html'] = '<table style="width:90%; max-width:496px; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><tr><td style="width:48px;"><img src="{}"/></td><td style="text-align:left; vertical-align:middle;">{}<br/><small>{}</small></td></tr><tr><td colspan="2">'.format(avatar, author_info, dt.strftime('%Y-%m-%d'))
    item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid light-dark(#ccc, #333); border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><tr><td style="width:48px;"><img src="{}"/></td><td style="text-align:left; vertical-align:middle;">{}<br/><small>{}</small></td></tr><tr><td colspan="2">'.format(avatar, author_info, dt.strftime('%Y-%m-%d'))

    if item.get('summary'):
        item['content_html'] += '<p>{}</p>'.format(item['summary'])

    if music_info:
        item['content_html'] += '<p>&#127925;&nbsp;{}</p>'.format(music_info)

    item['content_html'] += utils.add_video(item['_video'], 'video/mp4', item['_image'], width=540, img_style='border-radius:10px; width:100%;')
    item['content_html'] += '<br/><a href="{}" target="_blank"><small>Open in TikTok</small></a></td></tr></table>'.format(item['url'])
    return item


def get_content(url, args, site_json, save_debug=False):
    video_id = ''
    if not url.startswith('http'):
        if isinstance(url, int):
            video_id = str(url)
        elif url.isnumeric():
            video_id = url
        else:
            logger.warning('unhandled video id in url ' + url)
            return None

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'video' in paths:
        video_id = paths[paths.index('video') + 1]
    elif 'embed' in paths:
        if 'v2' in paths:
            video_id = paths[paths.index('v2') + 1]
        else:
            video_id = paths[paths.index('embed') + 1]
    if not video_id:
        logger.warning('unable to determine video id in ' + url)
        return None

    if paths[0].startswith('@'):
        user_id = paths[0][1:]
    else:
        embed_path = '/embed/v2/' + video_id
        embed_url = 'https://www.tiktok.com' + embed_path
        embed_html = utils.get_url_html(embed_url)
        if not embed_html:
            return None
        soup = BeautifulSoup(embed_html, 'lxml')
        el = soup.find('script', id='__FRONTITY_CONNECT_STATE__')
        if not el:
            logger.warning('unable to find __FRONTITY_CONNECT_STATE__ in ' + embed_url)
            return None
        connect_state = json.loads(el.string)
        if save_debug:
            utils.write_file(connect_state, './debug/tiktok.json')
        user_id = connect_state['source']['data'][embed_path]['videoData']['authorInfos']['uniqueId']

    if not user_id:
        logger.warning('unknown user id for video ' + url)
        return None

    video_url = 'https://www.tiktok.com/@{}/video/{}'.format(user_id, video_id)
    r = requests.get(video_url)
    if r.status_code != 200:
        return None
    # Need the tt_chain_token cookie to play videos: https://github.com/yt-dlp/yt-dlp/issues/9997#issuecomment-2175010516
    cookies = r.cookies.get_dict()
    if 'tt_chain_token' in cookies:
        tt_chain_token = cookies['tt_chain_token']
    else:
        tt_chain_token = ''
    video_soup = BeautifulSoup(r.text, 'lxml')
    el = video_soup.find(id='__UNIVERSAL_DATA_FOR_REHYDRATION__')
    if not el:
        logger.warning('unable to find __UNIVERSAL_DATA_FOR_REHYDRATION__ in ' + video_url)
        return None
    data_json = json.loads(el.string)
    if save_debug:
        utils.write_file(data_json, './debug/tiktok.json')
    item_info = data_json['__DEFAULT_SCOPE__']['webapp.video-detail']['itemInfo']['itemStruct']

    item = {}
    item['id'] = item_info['id']
    item['url'] = 'https://www.tiktok.com/@{}/video/{}'.format(item_info['author']['uniqueId'], item_info['id'])
    item['title'] = '{} posted'.format(item_info['author']['uniqueId'])

    content_html = ''
    if item_info.get('contents'):
        for content in item_info['contents']:
            item['summary'] = content['desc']
            if len(item['summary']) > 50:
                item['title'] += ': ' + item['summary'][:50] + '...'
            else:
                item['title'] += ': ' + item['summary']
            n = 0
            for it in content['textExtra']:
                x = (len(content['desc'][:it['start']].encode('utf-16-le')) // 2) - len(content['desc'][:it['start']])
                i = it['start'] - x
                j = it['end'] - x
                txt = content['desc'][i:j]
                if it.get('hashtagName'):
                    new_txt = '<a href="https://www.tiktok.com/tag/{}">{}</a>'.format(it['hashtagName'], txt)
                elif it.get('userUniqueId'):
                    if it.get('AwemeId'):
                        new_txt = '▶ <a href="https://www.tiktok.com/@{}/video/{}">{}</a>'.format(it['UserUniqueId'], it['AwemeId'], txt)
                    else:
                        new_txt = '<a href="https://www.tiktok.com/@{}">{}</a>'.format(it['userUniqueId'], txt)
                else:
                    logger.warning('unhandled textExtra in ' + item['url'])
                    new_txt = txt
                i = i + n
                j = j + n
                item['summary'] = item['summary'][:i] + new_txt + item['summary'][j:]
                n = n + len(new_txt) - len(txt)
    else:
        item['title'] = ' a TikTok'

    item['author'] = {}
    item['author']['name'] = '{} (@{})'.format(item_info['author']['nickname'], item_info['author']['uniqueId'])
    avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(item_info['author']['avatarMedium']))

    if len(item_info['challenges']) > 0:
        item['tags'] = []
        for challenge in item_info['challenges']:
            if not challenge['title'] in item['tags']:
                item['tags'].append(challenge['title'])

    # TODO: item_info['channelTags']

    item['_image'] = item_info['video']['cover']

    # Use the proxy to pass the tt_chain_token cookie
    item['_video'] = config.server + '/proxy/' + item_info['video']['playAddr'].replace('tt_chain_token', 'tt_chain_token_' + tt_chain_token)

    #item['content_html'] = '<div style="width:488px; padding:8px 0 8px 8px; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><div><img style="float:left; margin-right:8px;" src="{}"/><div style="overflow:hidden;">{}<br/><small>{}</small></div><div style="clear:left;"></div></div>'.format(avatar, author_info, dt.strftime('%Y-%m-%d'))

    #item['content_html'] = '<table style="width:90%; max-width:496px; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><tr><td style="width:48px;"><img src="{}"/></td><td style="text-align:left; vertical-align:middle;">{}<br/><small>{}</small></td></tr><tr><td colspan="2">'.format(avatar, author_info, dt.strftime('%Y-%m-%d'))
    #item['content_html'] = '<table style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid black; border-radius:10px; font-family:Roboto,Helvetica,Arial,sans-serif;"><tr><td style="width:48px;"><img src="{}"/></td><td style="text-align:left; vertical-align:middle;">{}<br/><small>{}</small></td></tr><tr><td colspan="2">'.format(avatar, author_info, dt.strftime('%Y-%m-%d'))
    item['content_html'] = '<table style="min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border-collapse:collapse; border-style:hidden; border-radius:10px; box-shadow:0 0 0 1px light-dark(#ccc, #333); font-family:Roboto,Helvetica,Arial,sans-serif;"><tr><td colspan="3" style="margin:0; padding:0 0 8px 0;">'

    # item['content_html'] += utils.add_video(item['_video'], 'video/mp4', item['_image'], width=540, img_style='width:100%;')
    poster = config.server + '/image?url=' + quote_plus(item['_image']) + '&width=540&overlay=video'
    # video_src = '{}/videojs?src={}&poster={}'.format(config.server, quote_plus(item['_video']), quote_plus(item['_image']))
    video_src = config.server + '/video?url=' + quote_plus(item['url'])
    item['content_html'] += '<a href="{}" target="_blank"><img src="{}" style="width:100%; border-radius:10px 10px 0 0;"></a>'.format(video_src, poster)

    item['content_html'] += '</td></tr><tr><td style="width:48px; padding:0 8px 0 8px; vertical-align:middle;"><img src="{0}"/></td><td style="text-align:left; vertical-align:middle;"><a href="https://www.tiktok.com/@{1}"><b>{1}</b></a>'.format(avatar, item_info['author']['uniqueId'])
    if item_info['author']['verified']:
        item['content_html'] += '&nbsp;<small>&#9989</small>'
    item['content_html'] += '<br/><small>{}</small>'.format(item_info['author']['nickname'])

    dt = None
    if item_info['createTime'] != '0':
        dt = datetime.fromtimestamp(int(item_info['createTime']))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        item['content_html'] += '&nbsp;&bull;&nbsp;<small>{}</small>'.format(utils.format_display_date(dt, False))

    item['content_html'] += '</td><td style="width:32px; padding:0 8px 0 8px; text-align:right; vertical-align:middle;"><a href="{}"><img src="https://lf16-tiktok-common.ttwstatic.com/obj/tiktok-web-common-sg/mtact/static/images/logo_144c91a.png?v=2" style="width:100%;"/></a></td></tr>'.format(item['url'])

    item['content_html'] += '<tr><td colspan="3" style="padding:8px;">'

    if item.get('summary'):
        item['content_html'] += '<p style="max-width:540px; word-wrap:break-word;">{}</p>'.format(item['summary'])

    if item_info.get('music'):
        item['_audio'] = item_info['music']['playUrl']
        item['content_html'] += '<p>&#127925;&nbsp;<a href="https://www.tiktok.com/music/{}-{}?lang=en">{} &ndash; {}</a></p>'.format(item_info['music']['title'].replace(' ', '-'), item_info['music']['id'], item_info['music']['title'], item_info['music']['authorName'])

    item['content_html'] += '<div><a href="{}"><small>Open in TikTok</small></a></div></td></tr></table>'.format(item['url'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    items_data = None
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) == 0:
        return None
    elif paths[0].startswith('@'):
        items_data = get_user_items(paths[0][1:])
    elif paths[0] == 'topics':
        items_data = get_topic_items(paths[1])
    elif paths[0] == 'tag':
        items_data = get_challenge_items(paths[1])
    elif paths[0] == 'music':
        m = re.search(r'-(\d+)$', paths[1])
        if not m:
            logger.warning('unable to determine music id in ' + args['url'])
            return None
        items_data = get_music_items(m.group(1))
    else:
        logger.warning('unhandled feed url ' + args['url'])

    if not items_data:
        return None

    if save_debug:
        utils.write_file(items_data, './debug/feed.json')

    n = 0
    items = []
    for item_info in items_data['itemList']:
        item = get_item(item_info, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed
