import binascii, hashlib, hmac, json, pytz, re, time
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_cffi_requests
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'lxml')
    el = soup.find('script', id='__NEXT_DATA__')
    if not el:
        logger.warning('unable to find __NEXT_DATA__ in ' + url)
        return None
    return  json.loads(el.string)


def get_api_url(api_path):
    def sub_lower(matchobj):
        return matchobj.group(0).lower()
    escape_path = re.sub(r'%[A-F0-9]{2}', sub_lower, quote_plus(api_path))
    exp = int(time.time()) + 60
    msg = 'exp={}~url={}'.format(exp, escape_path)
    key = '9ced54a89687e1173e91c1f225fc02abf275a119fda8a41d731d2b04dac95ff5'
    digest = hmac.new(binascii.a2b_hex(key), msg.encode(), hashlib.sha256)
    headers = {
        "x-hsci-auth-token": "exp={}~hmac={}".format(exp, digest.hexdigest())
    }
    api_url = 'https://hs-consumer-api.espncricinfo.com' + api_path
    r = curl_cffi_requests.get(api_url, impersonate="chrome", headers=headers, proxies=config.proxies)
    if r.status_code != 200:
        logger.warning('requests error {} getting {}'.format(r.status_code, api_url))
        return None
    return r.json()


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'story' in paths:
        content_type = 'story'
        if split_url.path.endswith('.html'):
            m = re.search(r'/(\d+)\.html$', split_url.path)
        else:
            m = re.search(r'-(\d+)$', paths[-1])
        api_path = '/v1/pages/story/home?storyId=' + m.group(1)
        api_json = get_api_url(api_path)
        if api_json:
            story = api_json['story']
            content = api_json['content']
    elif 'cricket-videos' in paths:
        content_type = 'cricket-videos'
        m = re.search(r'-(\d+)$', paths[-1])
        api_path = '/v1/pages/video/home?country=us&videoId=' + m.group(1)
        api_json = get_api_url(api_path)
        if api_json:
            story = api_json['video']
            content = api_json['content']
    else:
        logger.warning('unhandled url ' + url)
        return None

    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = story['id']
    item['url'] = 'https://www.espncricinfo.com/{}/{}-{}'.format(content_type, story['slug'], story['objectId'])
    item['title'] = story['title']

    if content_type == 'cricket-videos':
        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = datetime.fromisoformat(story['publishedAt'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['_display_date'] = utils.format_display_date(dt, date_only=True)
    else:
        dt = datetime.fromisoformat(story['publishedAt'])
        item['_display_date'] = utils.format_display_date(dt)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    dt = datetime.fromisoformat(story['modifiedAt'])
    item['date_modified'] = dt.isoformat()

    if story.get('byline'):
        item['author'] = {
            "name": story['byline']
        }
    else:
        item['author'] = {
            "name": 'ESPNcricinfo.com'
        }
    item['authors'] = []
    item['authors'].append(item['author'])

    item['tags'] = []
    if story.get('genreName'):
        item['tags'].append(story['genreName'])
    if content.get('related'):
        if content['related'].get('players'):
            item['tags'] += [x['longName'] for x in content['related']['players']]
        if content['related'].get('teams'):
            item['tags'] += [x['longName'] for x in content['related']['teams']]
        if content['related'].get('serieses'):
            item['tags'] += [x['longName'] for x in content['related']['serieses']]
    elif story.get('keywords'):
        item['tags'] += [x for x in story['keywords'] if x != '']

    if story.get('summary'):
        item['summary'] = story['summary']

    if content_type == 'cricket-videos':
        item['image'] = 'https://img1.hscicdn.com/image/upload/f_auto,w_1200,q_70/esci' + story['imageUrl']
        video = next((it for it in story['playbacks'] if it['type'] == 'HLS'), None)
        if video:
            item['_video'] = video['url']
            item['_video_type'] = 'application/x-mpegURL'
            item['content_html'] = utils.add_video(item['_video'], item['_video_type'], item['image'], item['title'])
        if 'embed' not in args and story.get('summary'):
            item['content_html'] += '<p>' + story['summary'] + '</p>'
        return item

    if story.get('image'):
        item['image'] = 'https://img1.hscicdn.com/image/upload/f_auto,w_1200,q_70' + story['image']['url']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    if story.get('summary'):
        item['content_html'] += '<p><em>' + story['summary'] + '</em></p>'

    for block in content['content']['items']:
        if block['type'] == 'HTML':
            if re.search(r'^<h\d>', block['html']):
                item['content_html'] += re.sub(r'<//(h\d)>', r'</\1>', block['html'])
            else:
                item['content_html'] += '<p>' + block['html'] + '</p>'
        elif block['type'] == 'IMAGE':
            img_src = 'https://img1.hscicdn.com/image/upload/f_auto' + block['image']['url']
            captions = []
            if block['image'].get('caption'):
                captions.append(block['image']['caption'])
            if block['image'].get('credit'):
                captions.append(block['image']['credit'])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
        elif block['type'] == 'VIDEO':
            video = next((it for it in block['video']['playbacks'] if it['type'] == 'HLS'), None)
            if video:
                img_src = 'https://img1.hscicdn.com/image/upload/f_auto,w_1200,q_70/esci' + block['video']['imageUrl']
                item['content_html'] += utils.add_video(video['url'], 'application/x-mpegURL', img_src, block['video']['title'])
        elif block['type'] == 'IFRAME':
            if 'twitter-tweet' in block['html']:
                m = re.findall(r'href="([^"]+)', block['html'])
                src = m[-1]
            else:
                m = re.search(r'src="([^"]+)', block['html'])
                src = m.group(1)
            item['content_html'] += utils.add_embed(src)
        elif block['type'] == 'PULL_QUOTE':
            item['content_html'] += utils.add_pullquote(block['quote'], block.get('caption'))
        elif block['type'] == 'EDITORS_PICK':
            pass
        else:
            logger.warning('unhandled content block type {} in {}'.format(block['type'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    stories = []
    videos = []
    if 'rss' in paths:
        # https://www.espncricinfo.com/ci/content/rss/feeds_rss_cricket.html
        return rss.get_feed(url, args, site_json, save_debug, get_content)
    elif 'cricket-news' in paths:
        if len(paths) > 1:
            m = re.search(r'-(\d+)$', paths[1])
            api_path = '/v1/pages/subject/home?lang=en&subjectId=' + m.group(1)
            api_json = get_api_url(api_path)
            if api_json:
                stories = api_json['content']['contentItems']['results']
                feed_title = api_json['subject']['title'] + ' | ESPNcricinfo.com'
        else:
            api_path = '/v1/pages/story/news?lang=en'
            api_json = get_api_url(api_path)
            if api_json:
                stories = api_json['content']['stories']['results']
                feed_title = 'Cricket News | ESPNcricinfo.com'
    elif 'cricket-features' in paths:
        api_path = '/v1/pages/story/features?lang=en'
        api_json = get_api_url(api_path)
        if api_json:
            stories = api_json['content']['stories']
            feed_title = 'Cricket Features | ESPNcricinfo.com'
    elif 'cricket-videos' in paths:
        if len(paths) > 1 and 'genre' in paths:
            m = re.search(r'-(\d+)$', paths[-1])
            api_path = '/v1/pages/video/genre-home?country=us&videoGenreId=' +  m.group(1)
            api_json = get_api_url(api_path)
            if api_json:
                videos = api_json['content']['videos']['results']
                feed_title = api_json['videoGenre']['title'] + ' Videos | ESPNcricinfo.com'
        else:
            api_path = '/v1/pages/video?country=us'
            api_json = get_api_url(api_path)
            if api_json:
                videos = api_json['content']['featuredVideos']
                feed_title = 'Cricket Videos | ESPNcricinfo.com'
    elif 'author' in paths:
        m = re.search(r'-(\d+)$', paths[-1])
        api_path = '/v1/pages/author/home?lang=en&authorId=' + m.group(1)
        api_json = get_api_url(api_path)
        if api_json:
            stories = api_json['content']['stories']['results']
            feed_title = api_json['author']['name'] + ' | Cricket Author | ESPNcricinfo.com'
    elif 'team' in paths:
        m = re.search(r'-(\d+)$', paths[-1])
        api_path = '/v1/pages/team/home?lang=en&teamId=' + m.group(1)
        api_json = get_api_url(api_path)
        if api_json:
            stories = api_json['content']['feed']['results']
            feed_title = api_json['team']['longName'] + ' Team News | ESPNcricinfo.com'
    elif 'cricketers' in paths:
        m = re.search(r'-(\d+)$', paths[-1])
        api_path = '/v1/pages/player/home?playerId=' + m.group(1)
        api_json = get_api_url(api_path)
        if api_json:
            stories = api_json['content']['stories']
            videos = api_json['content']['videos']
            feed_title = api_json['player']['longName'] + ' News | ESPNcricinfo.com'
    elif 'series' in paths:
        # TODO: feed for series match?
        # https://www.espncricinfo.com/series/england-lions-in-australia-2024-25-1468871/cricket-australia-xi-vs-england-lions-tour-match-1468874/match-report-2
        m = re.search(r'-(\d+)$', paths[1])
        api_path = '/v1/pages/series/home?lang=en&seriesId=' + m.group(1)
        api_json = get_api_url(api_path)
        if api_json:
            stories = api_json['content']['feed']['results']
            feed_title = str(api_json['series']['year']) + ' '  + api_json['series']['longName'] + ' | ESPNcricinfo.com'

    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for story in stories + videos:
        if story.get('cardType') and story.get('containers'):
            it = story['containers'][0]['item']
            if story['id'].split(':')[0] == 'video':
                story_url = 'https://www.espncricinfo.com/cricket-videos/{}-{}'.format(it['video']['slug'], it['video']['objectId'])
            else:
                story_url = 'https://www.espncricinfo.com/story/{}-{}'.format(it['story']['slug'], it['story']['objectId'])
        elif story.get('playbacks'):
            story_url = 'https://www.espncricinfo.com/cricket-videos/{}-{}'.format(story['slug'], story['objectId'])
        else:
            story_url = 'https://www.espncricinfo.com/story/{}-{}'.format(story['slug'], story['objectId'])
        if save_debug:
            logger.debug('getting content for ' + story_url)
        item = get_content(story_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    if feed_title:
        feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
