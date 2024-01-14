import feedparser, json, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown
from urllib.parse import urlsplit, quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)

rss_feed = None


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
    path += '.json'
    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    # print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_podcast_episode(item):
    global rss_feed
    if not rss_feed:
        rss_html = utils.get_url_html('https://rss.art19.com/olympic-channel')
        if rss_html:
            rss_feed = feedparser.parse(rss_html)
    if rss_feed:
        title = re.sub(r'^Podcast: ', '', item['title'], flags=re.I)
        episode = next((it for it in rss_feed['entries'] if it['title'] == title), None)
        if episode:
            attachment = episode.enclosures[0].copy()
            item['attachments'] = []
            item['attachments'].append(attachment)
            item['_audio'] = attachment['href']

            if episode.get('image'):
                poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(episode['image']['href']))
            else:
                poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(item['_image']))

            duration = re.sub(r'^[0:]*', '', episode['itunes_duration'])

            dt = dateutil.parser.parse(episode['published'])
            display_date = utils.format_display_date(dt, False)

            content_html = '<div>&nbsp;</div><table><tr><td style="width:128px;"><a href="{}"><img src="{}"></a></td>'.format(item['_audio'], poster)
            content_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold; padding-bottom:8px;"><a href="{}">{}</a></div>'.format(item['url'], item['title'])
            content_html += '<div style="padding-bottom:8px;">By <a href="https://olympics.com/en/podcast/">Olympics.com Podcast</a></div>'
            content_html += '<div style="font-size:0.9em;">{} &bull; {}</div></td></tr></table>'.format(display_date, duration)
            return content_html
    return '<p>Listen on <a href="https://open.spotify.com/show/78cyGdRl1eplfnatrvf5fw">Spotify</a> or <a href="https://podcasts.apple.com/us/podcast/olympic-channel-podcast/id1347405249">Apple Podcasts</a></p>'


def get_video_content(url, args, site_json, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_url = 'https://olympics.com/en/api/v1/d3vp/vod/detail/slug/' + paths[-1]
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    video_json = next((it for it in api_json if it['slug'] == paths[-1]), None)
    if not video_json:
        logger.warning('unable to get vod info for ' + url)
        return None

    item = {}
    item['id'] = video_json['entityId']
    item['url'] = url
    item['title'] = video_json['title']

    dt = datetime.fromisoformat(video_json['metaData']['contentDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": "Olympics.com"}

    if video_json['metaData'].get('tags'):
        item['tags'] = []
        for it in video_json['metaData']['tags']:
            item['tags'].append(it['title'])

    item['summary'] = video_json['description']

    item['_image'] = video_json['imageTemplate'].replace('{formatInstructions}', 't_16-9_1280/f_auto')

    # TODO: videos don't play
    # TODO: for podcast, embed Spotify or Apple player
    item['content_html'] = ''
    if video_json.get('src'):
        item['content_html'] += utils.add_video(video_json['src'], 'application/x-mpegURL', item['_image'], item['title'])
    else:
        poster = '{}/image?width=1280&height=720'.format(config.server)
        item['content_html'] += utils.add_image(poster, 'Video is unavailable')

    if '/podcast/' in item['url']:
        item['content_html'] += get_podcast_episode(item)

    item['content_html'] += '<p>' + video_json['description'] + '</p>'
    return item


def get_content(url, args, site_json, save_debug=False):
    if '/video/' in url or '/podcast/' in url:
        return get_video_content(url, args, site_json, save_debug)

    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')

    page_props = next_data['pageProps']

    item = {}
    item['id'] = page_props['entityID']

    link = next((it for it in page_props['metaPage']['hreflangSlug'] if it['hreflang'] == page_props['locale']), None)
    if link:
        item['url'] = link['slug']
    else:
        item['url'] = url

    item['title'] = page_props['title']

    dt = datetime.fromisoformat(page_props['contentDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": page_props['author']}

    if page_props.get('tags'):
        item['tags'] = []
        for it in page_props['tags']:
            item['tags'].append(it['title'])

    item['content_html'] = ''
    if page_props.get('description'):
        item['summary'] = page_props['description']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if page_props.get('thumbnail'):
        item['_image'] = page_props['thumbnail']['urlTemplate'].replace('{formatInstructions}', 't_s_w960/t_s_16_9_g_auto/f_auto')
        captions = []
        if page_props['thumbnail'].get('title'):
            captions.append(page_props['thumbnail']['title'])
        elif page_props['thumbnail'].get('description'):
            captions.append(page_props['thumbnail']['description'])
        if page_props['thumbnail'].get('credits'):
            captions.append(page_props['thumbnail']['credits'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    for part in page_props['parts']:
        if part['__typename'] == 'TextBlock':
            item['content_html'] += markdown(part['content'])
        elif part['__typename'] == 'Image':
            img_src = part['urlTemplate'].replace('{formatInstructions}', 't_s_w960/t_s_16_9_g_auto/f_auto')
            captions = []
            if part.get('title'):
                captions.append(part['title'])
            elif part.get('description'):
                captions.append(part['description'])
            if part.get('credits'):
                captions.append(part['credits'])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))
        elif part['__typename'] == 'OEmb':
            if part['provider'] == 'Instagram':
                m = re.search(r'data-instgrm-permalink="([^"]+)"', part['html'])
                item['content_html'] += utils.add_embed(m.group(1))
            elif part['provider'] == 'Twitter':
                m = re.findall(r'href="([^"]+)"', part['html'])
                item['content_html'] += utils.add_embed(m[-1])
            elif part['provider'] == 'YouTube':
                m = re.search(r'src="([^"]+)"', part['html'])
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled OEmb content in ' + item['url'])
        elif part['__typename'] == 'Vod':
            poster = part['thumbnail']['urlTemplate'].replace('{formatInstructions}', 't_16-9_1280/f_auto')
            item['content_html'] += utils.add_video(part['streamURL'], 'application/x-mpegURL', poster, part.get('title'))
        elif part['__typename'] == 'Html':
            for content in part['htmlContent']:
                if 'fcc-btn' in content and 'join now' in content:
                    continue
                else:
                    logger.warning('unhandled Html content in ' + item['url'])
        else:
            logger.warning('unhandled {} content in {}'.format(part['__typename'], item['url']))
    return item


def get_feed(url, args, site_json, save_debug=False):
    links = []
    if '/news' in url:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        for it in next_data['pageProps']['page']['items']:
            if it['name'] == 'contentListAdvanced' and it.get('data'):
                for content in it['data']['contentList']:
                    links.append(content['meta']['url'])
    elif '/topics' in url:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        if save_debug:
            utils.write_file(next_data, './debug/feed.json')
        for key, val in next_data['pageProps']['topic'].items():
            if isinstance(val, list):
                for it in val:
                    if it.get('__typename') and it['__typename'] == 'ContentList' and it.get('contentList'):
                        for content in it['contentList']:
                            links.append(content['meta']['url'])
    elif '/podcast' in url:
        page_html = utils.get_url_html(url)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            for el in soup.find_all('article', class_='card--podcast-list'):
                if el.a:
                    links.append('https://olympics.com' + el.a['href'])
    else:
        logger.warning('unhandled feed url ' + url)
        return None

    n = 0
    feed_items = []
    for link in links:
        if save_debug:
            logger.debug('getting content for ' + link)
        item = get_content(link, args, site_json, save_debug)
        if item:
          if utils.filter_item(item, args) == True:
            feed_items.append(item)
            n += 1
            if 'max' in args:
                if n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
