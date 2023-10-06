import re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import unquote_plus, urlsplit

import utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    api_url = '{}{}?clienttype=container.json'.format(site_json['api_endpoint'], split_url.path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    item = {}
    item['id'] = api_json['id']
    item['url'] = api_json['link']
    item['title'] = api_json['headline']

    dt = datetime.fromisoformat(api_json['publishedDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(api_json['updatedDate'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    if api_json.get('bylines'):
        authors = []
        for it in api_json['bylines']:
            author = []
            if it.get('firstname'):
                author.append(it['firstname'])
            if it.get('lastname'):
                author.append(it['lastname'])
            authors.append(' '.join(author))
        if authors:
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif api_json.get('abstract') and api_json['abstract'].startswith('By'):
        item['author'] = {"name": re.sub(r'^By ', '', api_json['abstract'], flags=re.I)}
    elif api_json.get('seo') and api_json['seo'].get('description') and api_json['seo']['description'].startswith('By'):
        item['author'] = {"name": re.sub(r'^By ', '', api_json['seo']['description'], flags=re.I)}

    item['tags'] = []
    if api_json['seo'].get('keywords'):
        item['tags'] = [tag.strip() for tag in api_json['seo']['keywords'].split(',')]
    if api_json.get('topics'):
        for it in api_json['topics']:
            if it['value'] not in item['tags']:
                item['tags'].append(it['value'])
    if not item.get('tags'):
        del item['tags']

    if api_json['abridged'].get('abstractimage'):
        item['_image'] = api_json['abridged']['abstractimage']['filename']

    item['content_html'] = ''
    if api_json.get('abstract') and not api_json['abstract'].startswith('By'):
        item['summary'] = api_json['abstract']
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    if api_json['type'] == 'clip':
        video = None
        if api_json.get('group'):
            video = utils.closest_dict(api_json['group'], 'bitrate', 500)
        if api_json.get('headline'):
            caption = 'Watch: ' + api_json['headline']
        else:
            caption = ''
        if video:
            item['content_html'] += utils.add_video(unquote_plus(video['url']), video['type'], api_json['thumbnailimage']['filename'], caption)
        else:
            item['content_html'] += utils.add_video(api_json['uri'], 'application/x-mpegURL', api_json['thumbnailimage']['filename'], caption)
        return item

    lede = False
    for feature in api_json['features']:
        if feature['type'] == 'weatheralerts' or feature['type'] == 'category' or feature['type'] == 'menu' or feature['type'] == 'story' or feature['type'] == 'xmlblock':
            continue
        elif feature['type'] == 'clip' and not lede:
            video = None
            if feature.get('group'):
                video = utils.closest_dict(feature['group'], 'bitrate', 500)
            if feature.get('headline'):
                caption = 'Watch: ' + feature['headline']
            else:
                caption = ''
            if video:
                item['content_html'] += utils.add_video(unquote_plus(video['url']), video['type'], feature['thumbnailimage']['filename'], caption)
            else:
                item['content_html'] += utils.add_video(feature['uri'], 'application/x-mpegURL', feature['thumbnailimage']['filename'], caption)
            lede = True
        else:
            logger.warning('unhandled feature type {} in {}'.format(feature['type'], item['url']))

    if not lede:
        if api_json.get('storyimages'):
            item['content_html'] += utils.add_image(api_json['storyimages'][0]['filename'], api_json['storyimages'][0].get('caption'))
        elif api_json['abridged'].get('abstractimage'):
            item['content_html'] += utils.add_image(api_json['abridged']['abstractimage']['filename'], api_json['abridged']['abstractimage'].get('caption'))

    if not api_json.get('body'):
        return item

    soup = BeautifulSoup(api_json['body'], 'html.parser')
    if soup.find(class_=re.compile(r'^wp-')):
        item['content_html'] += wp_posts.format_content(api_json['body'], item, site_json=None)
        return item

    for el in soup.find_all(class_='mml-element'):
        new_html = ''
        if el['data-mml-type'] == 'image':
            src = ''
            if el.get('data-mml-uri'):
                src = el['data-mml-uri']
            else:
                it = el.find('img')
                if it:
                    src = it['src']
            if src:
                if src.startswith('/'):
                    src = 'https:' + src
                captions = []
                if el.get('data-mml-caption'):
                    captions.append(el['data-mml-caption'])
                if el.get('data-mml-credits'):
                    captions.append(el['data-mml-credits'])
                new_html = utils.add_image(src, ' | '.join(captions))
        elif el['data-mml-type'] == 'youtube' or el['data-mml-type'] == 'gmaps':
            src = ''
            if el.get('data-mml-uri'):
                src = el['data-mml-uri']
            else:
                it = el.find('iframe')
                if it:
                    src = it['src']
            if src:
                if src.startswith('/'):
                    src = 'https:' + src
                new_html = utils.add_embed(src)
        elif el['data-mml-type'] == 'twitter':
            src = ''
            if el.get('data-mml-uri'):
                src = el['data-mml-uri']
            else:
                links = el.find_all('a')
                if links:
                    src = links[-1]['href']
            if src:
                if src.startswith('/'):
                    src = 'https:' + src
                new_html = utils.add_embed(src)
        elif el['data-mml-type'] == 'facebook':
            src = ''
            if el.get('data-mml-uri'):
                src = el['data-mml-uri']
            else:
                it = el.find('blockquote')
                if it:
                    src = it['cite']
            if src:
                if src.startswith('/'):
                    src = 'https:' + src
                new_html = utils.add_embed(src)
        elif el['data-mml-type'] == 'clip':
            feature = next((it for it in api_json['features'] if it['id'] == int(el['data-embed-id'])), None)
            if feature:
                video = None
                if feature.get('group'):
                    video = utils.closest_dict(feature['group'], 'bitrate', 500)
                if feature.get('headline'):
                    caption = 'Watch: ' + feature['headline']
                else:
                    caption = ''
                if video:
                    new_html = utils.add_video(unquote_plus(video['url']), video['type'], feature['thumbnailimage']['filename'], caption)
                else:
                    new_html = utils.add_video(feature['uri'], 'application/x-mpegURL', feature['thumbnailimage']['filename'], caption)
        elif el['data-mml-type'] == 'relatedstorylink':
            new_html = '<b>Related:</b> '
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert(0, new_el)
            el.unwrap()
            continue
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unknown mml-element in ' + item['url'])

    for el in soup.find_all('script'):
        el.decompose()

    # For debugging
    if False:
        for el in soup.find_all(class_=True):
            if 'production-element' in el['class'] or 'nanospell-typo' in el['class'] or 'Apple-converted-space' in el['class'] or 'apple-converted-space' in el['class']:
                el.unwrap()
            elif el.name == 'div' and ('Article-paragraph' in el['class'] or 'page' in el['class'] or 'column' in el['class'] or 'layoutArea' in el['class']):
                el.unwrap()
            elif el.name == 'span' and ('LinkEnhancement' in el['class'] or 'currentHitHighlight' in el['class']):
                el.unwrap()
            elif 'ContentPasted0' in el['class'] or 'x_ContentPasted0' in el['class']:
                if el.name == 'span':
                    el.unwrap()
                else:
                    del el['class']
            elif el.name == 'a' and ('Link' in el['class'] or 'mml-element-story-link' in el['class']):
                del el['class']
            elif 'article-text' in el['class'] or 'Standard' in el['class'] or 'x_BasicParagraph' in el['class'] or 'x_MsoNormal' in el['class'] or 'x_MsoBodyText' in el['class'] or 'paywall-content' in el['class'] or 'p1' in el['class'] or 'p2' in el['class'] or 'p3' in el['class'] or 's1' in el['class'] or 's2' in el['class']:
                del el['class']
            else:
                logger.warning('unhandled element class {} in {}'.format(el['class'], item['url']))

    item['content_html'] += str(soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    api_url = '{}{}?clienttype=container.json'.format(site_json['api_endpoint'], split_url.path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for feature in api_json['features']:
        if feature['type'] == 'story' or feature['type'] == 'clip':
            if save_debug:
                logger.debug('getting content for ' + feature['link'])
            item = get_content(feature['link'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    feed_items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    feed = utils.init_jsonfeed(args)
    if api_json.get('headline'):
        feed['title'] = '{} | {}'.format(api_json['headline'], api_json['owner']['name'])
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
