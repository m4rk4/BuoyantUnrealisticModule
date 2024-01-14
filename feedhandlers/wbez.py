import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    story_url = 'https://www.wbez.org/api/stories/{}?format=story'.format(paths[-1])
    story_json = utils.get_url_json(story_url)
    if not story_json:
        return None
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')

    item = {}
    item['id'] = story_json['id']
    item['url'] = story_json['dataLayer']['dl_CanonicalUrl']
    item['title'] = story_json['title']

    dt = datetime.fromisoformat(story_json['published'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if story_json['schema'].get('dateModified'):
        dt = datetime.fromisoformat(story_json['schema']['dateModified'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if story_json.get('byline'):
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(story_json['byline']))
    elif story_json.get('show'):
        if story_json['dataLayer'].get('showTitle'):
            item['author']['name'] = story_json['showTitle']
        elif story_json['dataLayer'].get('dl_ShowName'):
            item['author']['name'] = story_json['dataLayer']['dl_ShowName']
        elif story_json['taxonomy']:
            show = next((it for it in story_json['taxonomy'] if it['taxonomyId'] == story_json['show']), None)
            if show:
                item['author']['name'] = show['title']
            else:
                show = utils.get_url_json('https://www.wbez.org/api/shows/' + story_json['show'])
                if show:
                    item['author']['name'] = show['title']

    if story_json.get('taxonomy'):
        item['tags'] = []
        for it in story_json['taxonomy']:
            item['tags'].append(it['title'])

    item['content_html'] = ''
    if story_json.get('description'):
        item['summary'] = story_json['description']
        item['content_html'] += '<p><em>{}</em></p>'.format(story_json['description'])

    if story_json.get('image'):
        item['_image'] = 'https://api.wbez.org/v2/images/{}.jpg?width=1200&height=0&mode=ASPECT_WIDTH'.format(story_json['image']['id'])
        captions = []
        if story_json['image'].get('caption'):
            captions.append(story_json['image']['caption'])
        if story_json['image'].get('byline'):
            caption = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(story_json['image']['byline']))
            if story_json['image'].get('source'):
                caption += ' / ' + story_json['image']['source']
            captions.append(caption)
        elif story_json['image'].get('source'):
            captions.append(story_json['image']['source'])
        item['content_html'] += utils.add_image(item['_image'], ' | '.join(captions))

    if story_json.get('audio'):
        item['_audio'] = story_json['audio'][0]['path']
        attachment = {}
        attachment['url'] = story_json['audio'][0]['path']
        attachment['mime_type'] = story_json['audio'][0]['type']
        item['attachments'] = []
        item['attachments'].append(attachment)
        item['content_html'] += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span>&nbsp;<a href="{0}">Listen ({2})</a></span></div><div>&nbsp;</div>'.format(story_json['audio'][0]['path'], config.server, utils.calc_duration(story_json['audio'][0]['duration']))

    soup = BeautifulSoup(story_json['content'], 'html.parser')
    for el in soup.find_all(['story-google-ad-slot', 'story-promo']):
        el.decompose()

    for el in soup.find_all('div', class_='l-align-center-children'):
        el.unwrap()

    for el in soup.find_all('div', class_='storyMajorUpdateDate'):
        el.name = 'h2'
        el.attrs = {}

    for el in soup.find_all('p', class_='wbz-has-dropcap'):
        el.attrs = {}
        new_html = re.sub(r'>("?\w)', r'><span style="float:left; font-size:4em; line-height:0.8em;">\1</span>', str(el), 1)
        new_html = re.sub(r'</p>$', '<span style="clear:left;"></span></p>', new_html)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('figure', class_='wbz-image'):
        it = el.find('cdn-img')
        if it:
            img_src = 'https://api.wbez.org/v2/images/{}.jpg?width=1200&height=0&mode=ASPECT_WIDTH'.format(it['id'])
            captions = []
            it = el.find(class_='c-caption__credit')
            if it:
                captions.append(it.decode_contents())
                it.decompose()
            it = el.find(class_='c-caption')
            if it:
                captions.insert(0, it.decode_contents())
            new_html = utils.add_image(img_src, ' | '.join(captions))
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wbz-image in ' + item['url'])

    for el in soup.find_all('blockquote', class_='instagram-media'):
        new_html = utils.add_embed(el['data-instgrm-permalink'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('aside', class_='wbz-card'):
        new_html = utils.add_blockquote(el.decode_contents())
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('podcast-subscribe-widget'):
        show = utils.get_url_json('https://www.wbez.org/api/shows/' + el['show-id'])
        if show:
            img_src = 'https://api.wbez.org/v2/images/{}.jpg?width=128&height=0&mode=ASPECT_WIDTH'.format(show['image']['id'])
            new_html = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}" style="width:100%;"/></td><td>'.format(show['dataLayer']['dl_CanonicalUrl'], img_src)
            new_html += '<td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div><div>{}</div></td></tr></table>'.format(show['dataLayer']['dl_CanonicalUrl'], show['title'], show['description'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='flourish-embed'):
        new_html = utils.add_embed('https://flo.uri.sh/{}/embed?auto=1'.format(el['data-src']))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('iframe'):
        new_html = ''
        if el.get('data-src'):
            new_html = utils.add_embed(el['data-src'])
        elif el.get('src'):
            new_html = utils.add_embed(el['src'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled iframe in ' + item['url'])

    item['content_html'] += str(soup)

    if story_json.get('images') and len(story_json['images']) > 1:
        item['content_html'] += '<h2>Gallery</h2>'
        for image in story_json['images']:
            img_src = 'https://api.wbez.org/v2/images/{}.jpg?width=1200&height=0&mode=ASPECT_WIDTH'.format(image['id'])
            captions = []
            if image.get('caption'):
                captions.append(image['caption'])
            if image.get('byline'):
                caption = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(image['byline']))
                if image.get('source'):
                    caption += ' / ' + image['source']
                captions.append(caption)
            elif image.get('source'):
                captions.append(image['source'])
            item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_json = None
    if len(paths) == 0 or paths[-1] == 'latest-news':
        api_json = utils.get_url_json('https://www.wbez.org/api/homepage')
    elif 'topics' in paths:
        api_json = utils.get_url_json('https://www.wbez.org/api/stories?order=-published&limit=10&offset=0&topic=' + paths[-1])
    elif 'shows' in paths:
        if len(paths) > 1:
            api_json = utils.get_url_json('https://www.wbez.org/api/stories?order=-published&limit=10&offset=0&show=' + paths[-1])
        else:
            shows = utils.get_url_json('https://www.wbez.org/api/shows/directory')
            if shows:
                feed_items = []
                for show in shows:
                    show_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, show['canonical'])
                    show_feed = get_feed(show_url, args, site_json, save_debug)
                    if show_feed:
                        feed_items += show_feed['items'].copy()
                feed = utils.init_jsonfeed(args)
                feed['title'] = 'Shows | WBEZ Chicago'
                feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
                return feed
    elif 'staff' in paths:
        api_json = utils.get_url_json('https://www.wbez.org/api/staff/' + paths[1])
        if api_json:
            api_json = utils.get_url_json('https://www.wbez.org/api/stories?order=-published&limit=10&offset=0&q=byline:%22{}%22'.format(quote_plus(api_json['title'])))
    else:
        logger.warning('unsupported feed url ' + url)
        return None

    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    if isinstance(api_json, list):
        articles = api_json
    elif api_json.get('items'):
        articles = api_json['items']
    else:
        logger.warning('unknown items in ' + url)
        return None

    n = 0
    feed_items = []
    for article in articles:
        article_url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article['canonical'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    # feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
