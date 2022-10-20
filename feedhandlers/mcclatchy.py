import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import brightcove, rss

import logging

logger = logging.getLogger(__name__)


# Compatible sites
# https://www.mcclatchy.com/our-impact/markets#map

def get_initial_state(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', string=re.compile('__INITIAL_STATE__'))
    if not el:
        logger.warning('unable to find INITIAL_STATE in ' + url)
        return None
    return json.loads(el.string[25:])


def add_gallery(url, save_debug=False):
    initial_state = get_initial_state(url)
    if not initial_state:
        return ''
    if save_debug:
        utils.write_file(initial_state, './debug/gallery.json')
    gallery_html = ''
    for photo in initial_state['galleryPhotos']:
        if photo['asset_type'] != 'picture':
            logger.warning('skipping gallery photo type {} in {}'.format(photo['asset_type'], url))
        if photo.get('thumbnail'):
            img_src = photo['thumbnail']
        else:
            img_src = photo['url'] + '/alternates/FREE_1140/' + photo['title']
        captions = []
        if photo.get('caption') and photo['caption'] != '-':
            captions.append(photo['caption'])
        if photo.get('photographer') and photo['photographer'] != '-':
            captions.append(photo['photographer'])
        if photo.get('credit') and photo['credit'] != '-':
            captions.append(photo['credit'])
        gallery_html += utils.add_image(img_src, ' | '.join(captions))
    return gallery_html


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    m = re.search(r'(\d+)\.html$', split_url.path)
    if not m:
        logger.warning('unable to determine article id from ' + url)
        return None
    article_id = m.group(1)

    content_json = utils.get_url_json('https://publicapi.misitemgr.com/webapi-public/v2/content/' + article_id)
    if not content_json:
        return None

    article_json = None
    for section_id in content_json['additional_sections']:
        section_json = utils.get_url_json('https://publicapi.misitemgr.com/webapi-public/v2/sections/{}/content?limit=75'.format(section_id))
        if not section_json:
            continue
        article_json = next((it for it in section_json['items'] if it['id'] == article_id), None)
        if article_json:
            break

    if not article_json:
        logger.warning('unable to find full content for ' + url)
        return None
    return get_item(article_json, args, save_debug)


def get_item(article_json, args, save_debug):
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['url']
    item['title'] = article_json['title']

    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(article_json['published_date'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = datetime.fromtimestamp(article_json['modified_date'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    if article_json.get('authors'):
        authors = []
        for it in article_json['authors']:
            authors.append(it['name'])
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif article_json.get('byline'):
        item['author'] = {}
        el = BeautifulSoup(article_json['byline'], 'html.parser')
        it = el.find('ng_byline_name')
        if it:
            item['author']['name'] = it.get_text().strip()
        it = el.find('ng_byline_credit')
        if it:
            item['author']['name'] += ', {}'.format(it.get_text().strip())

    if article_json.get('keywords'):
        item['tags'] = article_json['keywords'].split(', ')

    item['content_html'] = ''
    if article_json.get('story_teaser'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['story_teaser'])

    soup = None
    if article_json.get('lead_media'):
        if article_json['lead_media']['asset_type'] == 'picture':
            item['_image'] = article_json['lead_media']['thumbnail']
            captions = []
            if article_json['lead_media'].get('caption') and article_json['lead_media']['caption'] != '-':
                captions.append(article_json['lead_media']['caption'])
            if article_json['lead_media'].get('photographer') and article_json['lead_media']['photographer'] != '-':
                captions.append(article_json['lead_media']['photographer'])
            if article_json['lead_media'].get('credit') and article_json['lead_media']['credit'] != '-':
                captions.append(article_json['lead_media']['credit'])
            item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))
        elif article_json['lead_media']['asset_type'] == 'videoIngest':
            item['_image'] = article_json['lead_media']['thumbnail']
            if not soup:
                page_html = utils.get_url_html(item['url'])
                if page_html:
                    soup = BeautifulSoup(page_html, 'html.parser')
            if soup:
                video = soup.find('video', id=re.compile(r'player-{}'.format(article_json['lead_media']['id'])))
                if video:
                    video_args = {
                        "embed": True,
                        "data-account": video['data-account'],
                        "data-key": video['data-key'],
                        "data-video-id": video['data-video-id']
                    }
                    video_item = brightcove.get_content(item['url'], video_args)
                    if video_item:
                        item['content_html'] += video_item['content_html']

    if article_json['asset_type'] == 'gallery':
        item['content_html'] = ''
        if article_json.get('leadtext'):
            for it in article_json['leadtext']:
                item['content_html'] += '<p>{}</p>'.format(it['text'])
        item['content_html'] += add_gallery(item['url'], save_debug)
        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', item['content_html'])
        return item

    item['content_html'] += article_json['content']

    n = 0
    for asset in re.findall(r'(<!--[^>]*%asset:(\d+);?%?[^>]*-->)', item['content_html']):
        embeds = None
        asset_html = ''
        asset_url = 'https://publicapi.misitemgr.com/webapi-public/v2/content/{}'.format(asset[1])
        asset_json = utils.get_url_json(asset_url)
        if not asset_json:
            logger.warning('skipping asset {} in {}'.format(asset[1], item['url']))
            continue
        if asset_json['asset_type'] == 'picture':
            if asset_json.get('thumbnail'):
                img_src = asset_json['thumbnail']
            else:
                img_src = asset_json['url'] + '/alternates/FREE_1140/' + asset_json['title']
            captions = []
            if asset_json.get('caption') and asset_json['caption'] != '-':
                captions.append(asset_json['caption'])
            if asset_json.get('photographer') and asset_json['photographer'] != '-':
                captions.append(asset_json['photographer'])
            if asset_json.get('credit') and asset_json['credit'] != '-':
                captions.append(asset_json['credit'])
            asset_html = utils.add_image(img_src, ' | '.join(captions))

        elif asset_json['asset_type'] == 'videoIngest':
            if not soup:
                page_html = utils.get_url_html(item['url'])
                if page_html:
                    soup = BeautifulSoup(page_html, 'html.parser')
            if soup:
                video = soup.find('video', id=re.compile(r'player-{}'.format(asset_json['id'])))
                if video:
                    video_args = {
                        "embed": True,
                        "data-account": video['data-account'],
                        "data-key": video['data-key'],
                        "data-video-id": video['data-video-id']
                    }
                    video_item = brightcove.get_content(item['url'], video_args)
                    if video_item:
                        asset_html = video_item['content_html']

        elif asset_json['asset_type'] == 'embedInfographic':
            if not embeds:
                if not soup:
                    page_html = utils.get_url_html(item['url'])
                    if page_html:
                        soup = BeautifulSoup(page_html, 'html.parser')
                if soup:
                    embeds = soup.find_all(class_='embed-infographic')
            if embeds:
                if embeds[n].iframe:
                    asset_html = utils.add_embed(embeds[n].iframe['src'])
                elif embeds[n].blockquote and 'tiktok-embed' in embeds[n].blockquote['class']:
                    asset_html = utils.add_embed(embeds[n].blockquote['cite'])
            n = n + 1
            if 'NL sign-up' in asset_json['title']:
                continue

        elif asset_json['asset_type'] == 'story':
            # These are usually just related stories
            continue

        if asset_html:
            item['content_html'] = item['content_html'].replace(asset[0], asset_html)
        else:
            logger.warning('unhandled asset type {} in {}'.format(asset_json['asset_type'], asset_url))

    return item


def get_feed(args, save_debug):
    if 'feeds.mcclatchy.com' in args['url']:
        return rss.get_feed(args, save_debug, get_content)

    feed = None
    feed_items = []
    initial_state = get_initial_state(args['url'])
    if initial_state:
        if save_debug:
            utils.write_file(initial_state, './debug/feed.json')
        n = 0
        for article in initial_state['content']['contentitems']:
            if save_debug:
                logger.debug('getting content for ' + article['url'])
            item = get_content(article['url'], args, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break
    else:
        page_html = utils.get_url_html(args['url'])
        if not page_html:
            return None
        m = re.search(r'"sectionId":"(\d+)"', page_html)
        if m:
            split_url = urlsplit(args['url'])
            section_json = utils.get_url_json('https://publicapi.misitemgr.com/webapi-public/v2/sections/{}/content?limit=20'.format(m.group(1)))
            if section_json:
                if save_debug:
                    utils.write_file(section_json, './debug/feed.json')
                n = 0
                for article in section_json['items']:
                    if 'www.mcclatchy-wires.com' in article['url']:
                        paths = list(filter(None, urlsplit(article['url']).path.split('/')))
                        article['url'] = args['url'] + paths[-1]
                    else:
                        article['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, urlsplit(article['url']).path)
                    if save_debug:
                        logger.debug('getting content for ' + article['url'])
                    item = get_item(article, args, save_debug)
                    if item:
                        if utils.filter_item(item, args) == True:
                            feed_items.append(item)
                            n += 1
                            if 'max' in args:
                                if n == int(args['max']):
                                    break
    if feed_items:
        feed = utils.init_jsonfeed(args)
        #feed['title'] = page_json['title']
        feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
