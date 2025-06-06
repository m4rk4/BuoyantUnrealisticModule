import json
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/home'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'
    if 'news' in paths:
        query = '?news-slug=' + paths[-1]
    elif 'team' in paths:
        query = '?team-id=' + paths[-1]
    elif 'competition' in paths:
        query = '?competition-id=' + paths[-1]
    else:
        query = ''
    next_url = '{}://{}/_next/data/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path, query)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url, site_json=site_json)
        if page_html:
            soup = BeautifulSoup(page_html, 'lxml')
            el = soup.find('script', id='__NEXT_DATA__')
            if el:
                next_data = json.loads(el.string)
                if next_data['buildId'] != site_json['buildId']:
                    logger.debug('updating {} buildId'.format(split_url.netloc))
                    site_json['buildId'] = next_data['buildId']
                    utils.update_sites(url, site_json)
                return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False, gallery_item=None):
    split_url = urlsplit(url)
    page_props = utils.get_url_json('https://api.onefootball.com/web-experience' + split_url.path)
    if not page_props:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        page_props = next_data['pageProps']
    if save_debug:
        utils.write_file(page_props, './debug/debug.json')

    item = {}

    article_json = None
    video_json = None
    content_items = []
    for container in page_props['containers']:
        if 'fullWidth' in container:
            if 'articleHeroBanner' in container['fullWidth']['component']:
                article_json = container['fullWidth']['component']['articleHeroBanner']
            elif 'articleHeader' in container['fullWidth']['component']:
                article_json = container['fullWidth']['component']['articleHeader']
            elif 'videojsPlayer' in container['fullWidth']['component']:
                video_json = container['fullWidth']['component']['videojsPlayer']
        elif 'grid' in container:
            content_items = container['grid']['items']

    if page_props.get('jsonLd'):
        for it in page_props['jsonLd']:
            ld_json = json.loads(it)
            if ld_json.get('@type') == 'VideoObject':
                break
            ld_json = None
        if save_debug:
            utils.write_file(ld_json, './debug/ld_json.json')
    else:
        ld_json = None

    item['id'] = article_json['id']
    item['url'] = utils.clean_url(article_json['nativeShare']['shareUrl'])
    item['title'] = article_json['title']['text']

    if gallery_item and gallery_item.get('publishTimestamp'):
        dt = datetime.fromisoformat(gallery_item['publishTimestamp'])
    elif ld_json and ld_json.get('uploadDate'):
        dt = datetime.fromisoformat(ld_json['uploadDate'])
    else:
        date = next((it for it in page_props['metaTags'] if it.get('name') == 'outbrain:published_time'), None)
        if date:
            dt = datetime.fromisoformat(date['content'] ).replace(tzinfo=timezone.utc)
        else:
            search_json = utils.get_url_json('https://search-api.onefootball.com/v2/en/search?q=' + quote(item['title']))
            if search_json and search_json.get('news'):
                for it in search_json['news']:
                    if str(it['id']) == item['id']:
                        dt = datetime.fromisoformat(it['date'])

    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if article_json['provider'].get('author'):
        item['author'] = {
            "name": article_json['provider']['author'] + ' (' + article_json['provider']['name'] + ')'
        }
    else:
        item['author'] = {
            "name": article_json['provider']['name']
        }

    item['content_html'] = ''
    if article_json.get('image'):
        item['image'] = article_json['image']['path']
        item['content_html'] += utils.add_image(item['image'])
    elif ld_json and ld_json.get('thumbnailUrl'):
        item['image'] = ld_json['thumbnailUrl']

    if ld_json and ld_json.get('keywords'):
        item['tags'] = ld_json['keywords'].split(',')

    if video_json:
        item['content_html'] += utils.add_video(video_json['playlist'][0]['sources'][0]['src'], video_json['playlist'][0]['sources'][0]['type'], video_json['playlist'][0]['poster'], item['title'])

    for it in content_items:
        for component in it['components']:
            if 'articleParagraph' in component:
                item['content_html'] += component['articleParagraph']['content']
            elif 'image' in component:
                item['content_html'] += utils.add_image(component['image']['path'])
            elif 'embeddedVideoPlayer' in component:
                # playlist = json.loads(base64.b64decode(component['embeddedVideoPlayer']['playlistId'].split('-')[-1]).decode())
                # item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/playlists/{}?page_domain=onefootball.com'.format(playlist['pl']))
                if component['embeddedVideoPlayer']['title']['text'] != 'OneFootball Videos':
                    logger.warning('unhandled embeddedVideoPlayer content in ' + item['url'])
            elif 'articleTwitter' in component:
                item['content_html'] += utils.add_embed(component['articleTwitter']['link'])
            elif 'youtube' in component:
                item['content_html'] += utils.add_embed(component['youtube']['videoSrc'])
            elif 'videojsPlayer' in component:
                item['content_html'] += utils.add_video(component['videojsPlayer']['playlist'][0]['sources'][0]['src'], component['videojsPlayer']['playlist'][0]['sources'][0]['type'], component['videojsPlayer']['playlist'][0]['poster'], component['videojsPlayer']['playlist'][0]['comscoreMetadata']['programTitle'])
            elif 'horizontalSeparator' in component:
                item['content_html'] += '<hr>'
            elif 'dividerWithTimestamp' in component:
                dt = datetime.fromisoformat(component['dividerWithTimestamp']['timestamp'])
                item['content_html'] += '<hr style="margin-top:2em;"><div style="font-size:0.9em; font-weight:bold; margin-bottom:2em;">Update: ' + utils.format_display_date(dt) + '</div>'
            elif 'articleList' in component:
                item['content_html'] += '<ul>'
                for li in component['articleList']['items']:
                    item['content_html'] += '<li>' + li + '</li>'
                item['content_html'] += '</ul>'
            elif 'articleBlockquote' in component:
                item['content_html'] += utils.add_pullquote(component['articleBlockquote']['text'], component['articleBlockquote'].get('authorName'))
            elif 'entityChipList' in component:
                item['tags'] = []
                for chip in component['entityChipList']['chips']:
                    if chip.get('title'):
                        item['tags'].append(chip['title']['text'])
            elif 'matchCard' in component:
                item['content_html'] += '<table style="margin:auto; padding:8px; border:1px solid light-dark(#333,#ccc); border-radius:10px;">'
                item['content_html'] += '<tr><td style="height:40px; width:40px;"><img src="{}" style="display:block; width:100%;"></td>'.format(component['matchCard']['homeTeam']['imageObject']['path'])
                item['content_html'] += '<td><b>' + component['matchCard']['homeTeam']['name'] + '</b></td>'
                n = 2
                if component['matchCard']['homeTeam'].get('score'):
                    item['content_html'] += '<td style="padding:4px; vertical-align:middle;"><b>' + component['matchCard']['homeTeam']['score'] + '</b></td>'
                    n += 1
                if component['matchCard'].get('timePeriod'):
                    item['content_html'] += '<td rowspan="2">' + component['matchCard']['timePeriod'] + '</td>'
                    n += 1
                item['content_html'] += '<tr><td style="height:40px; width:40px;"><img src="{}" style="display:block; width:100%;"></td>'.format(component['matchCard']['awayTeam']['imageObject']['path'])
                item['content_html'] += '<td><b>' + component['matchCard']['awayTeam']['name'] + '</b></td>'
                if component['matchCard']['awayTeam'].get('score'):
                    item['content_html'] += '<td style="padding:4px; vertical-align:middle;"><b>' + component['matchCard']['awayTeam']['score'] + '</b></td>'
                dt = datetime.fromisoformat(component['matchCard']['kickoff'])
                item['content_html'] += '</tr><tr><td colspan="{}" style="text-align:center;"><small>Kickoff: {}</td></tr></table>'.format(n, utils.format_display_date(dt))
            elif set(['googleAdsPlaceholder', 'taboolaPlaceholder', 'nativeShare', 'commentsPlaceholder', 'publisherImprintLink', 'relatedNews']) & set(list(component.keys())):
                continue
            else:
                keys = list(component.keys())
                keys.remove('uiKey')
                logger.warning('unhandled component type {} in {}'.format(keys[0], item['url']))

    item['content_html'] = item['content_html'].replace('<hr><hr>', '').replace('<hr>', '<hr style="margin:2em 0;">')
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    page_props = utils.get_url_json('https://api.onefootball.com/web-experience' + split_url.path)
    if not page_props:
        next_data = get_next_data(url, site_json)
        if not next_data:
            return None
        page_props = next_data['pageProps']
    if save_debug:
        utils.write_file(page_props, './debug/feed.json')

    articles = []
    videos = []
    for container in page_props['containers']:
        if 'fullWidth' in container:
            if 'gallery' in container['fullWidth']['component']:
                articles += container['fullWidth']['component']['gallery']['teasers']
        elif 'grid' in container:
            for it in container['grid']['items']:
                for component in it['components']:
                    if 'gallery' in component:
                        articles += component['gallery']['teasers']
                    elif 'videoGallery' in component:
                        videos += component['videoGallery']['items']

    feed_items = []
    for article in articles + videos:
        article_url = 'https://' + split_url.netloc + article['link']
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug, article)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)

    feed = utils.init_jsonfeed(args)
    feed['title'] = page_props['pageTitle']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
